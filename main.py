import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, func, select

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEMOSC_URL = 'https://www.hemosc.org.br/'
REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    )
}
REQUEST_TIMEOUT = 15  # segundos
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


class TipoSanguineo(SQLModel, table=True):
    __tablename__ = 'tipo_sanguineo'

    id: int | None = Field(default=None, primary_key=True)
    tipo_sanguineo: str = Field(index=True)

    registros_estoque: List['RegistroEstoqueHemosc'] = Relationship(back_populates='tipo_sanguineo')


class RegistroEstoqueHemosc(SQLModel, table=True):
    __tablename__ = 'registro_estoque_hemosc'

    id: int | None = Field(default=None, primary_key=True)
    data_do_registro: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    estado_do_estoque: int = Field(default=None, index=True)
    tipo_sanguineo_id: int | None = Field(default=None, foreign_key='tipo_sanguineo.id')

    tipo_sanguineo: Optional[TipoSanguineo] = Relationship(back_populates='registros_estoque')


engine = create_engine('sqlite:///hemosc.db')


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def populate_database():
    with Session(engine) as session:
        total_tipos = session.exec(select(func.count(TipoSanguineo.id))).one()

        if total_tipos == 0:
            tipos_sanguineos = ['A-', 'A+', 'B-', 'B+', 'AB+', 'AB-', 'O+', 'O-']

            for tipo in tipos_sanguineos:
                novo_tipo = TipoSanguineo(tipo_sanguineo=tipo)
                session.add(novo_tipo)

            session.commit()


def buscar_pagina_hemosc() -> requests.Response:
    """Faz a requisição para o HEMOSC com timeout, User-Agent de navegador e
    algumas tentativas com backoff antes de desistir."""
    ultimo_erro = None

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            logger.info('Tentativa %d/%d de acessar %s', tentativa, MAX_RETRIES, HEMOSC_URL)
            response = requests.get(HEMOSC_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as erro:
            ultimo_erro = erro
            logger.warning('Falha na tentativa %d: %s', tentativa, erro)
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * tentativa)

    raise RuntimeError(
        f'Não foi possível acessar {HEMOSC_URL} após {MAX_RETRIES} tentativas. '
        'Se o site abre normalmente no navegador, é provável que o IP do runner '
        '(GitHub Actions roda em datacenters da Azure) esteja sendo bloqueado pelo '
        'firewall/WAF do site. Considere um self-hosted runner ou um proxy com IP '
        'brasileiro para contornar isso.'
    ) from ultimo_erro


def crawler():
    """Abre a página do HEMOSC e grava os estoques de sangue atuais para cada
    tipo sanguíneo"""

    # Abre a página do HEMOSC
    response = buscar_pagina_hemosc()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Retorna a div com o estado dos estoques de sangue
    estoque_sangues_soup = soup.find_all('div', class_='dirt_home_estq')

    if not estoque_sangues_soup:
        raise RuntimeError(
            'Não encontrei a div "dirt_home_estq" na página. '
            'O HTML do site pode ter mudado de estrutura.'
        )

    # Retorna uma lista das divs de cada tipo sanguineo e seu estado de estoque
    estoque_atual_por_tipo = estoque_sangues_soup[0].find_all('div')

    # Relação de estado de estoque da página com o estado do banco
    estados_de_estoque = {
        'Adequado': 5,
        'Estável': 4,
        'Reduzido': 3,
        'Alerta': 2,
        'Crítico': 1,
    }

    with Session(engine) as session:
        for tipo in estoque_atual_por_tipo:
            img = tipo.find('img')
            if img is None:
                continue

            # Busca o tipo sanguineo do site
            tipo_sanguineo = img.get('alt', '').split('tipo ')[-1]

            # Busca o estado do estoque do tipo sanguineo do site
            estoque_do_dia = img.get('title', '').split(' - ')[0]

            estado_do_estoque_hoje = estados_de_estoque.get(estoque_do_dia)
            if estado_do_estoque_hoje is None:
                logger.warning('Estado de estoque desconhecido: %r (tipo %r)', estoque_do_dia, tipo_sanguineo)
                continue

            # Busca o id do tipo sanguineo no banco (agora a query é executada!)
            id_tipo_sanguineo = session.exec(
                select(TipoSanguineo.id).where(TipoSanguineo.tipo_sanguineo == tipo_sanguineo)
            ).one_or_none()

            if id_tipo_sanguineo is None:
                logger.warning('Tipo sanguíneo não cadastrado no banco: %r', tipo_sanguineo)
                continue

            # Registra o novo estado no banco
            novo_registro = RegistroEstoqueHemosc(
                estado_do_estoque=estado_do_estoque_hoje,
                tipo_sanguineo_id=id_tipo_sanguineo,
            )
            session.add(novo_registro)

        session.commit()

    logger.info('Crawler finalizado com sucesso.')


def main():
    create_db_and_tables()
    populate_database()
    crawler()


if __name__ == "__main__":
    main()

"""
- O estoque está ideal. Continue nos acompanhando, e agende sua doação quando necessário.
- Continue doando para manter os estoques adequados
- Venha doar sangue, precisamos de você.
- Venha doar e nos ajude a divulgar essa necessidade.
- Precisamos de você!
"""
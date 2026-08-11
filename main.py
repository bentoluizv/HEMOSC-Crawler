import time
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from typing import List, Optional
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, func, select

class TipoSanguineo(SQLModel, table=True):
    __tablename__ = 'tipo_sanguineo'

    id: int | None = Field(default=None, primary_key=True)
    tipo_sanguineo: str = Field(index=True)

    registros_estoque: List['RegistroEstoqueHemosc'] = Relationship(back_populates='tipo_sanguineo')

class RegistroEstoqueHemosc(SQLModel, table=True):
    __tablename__ = 'registro_estoque_hemosc'

    id: int | None = Field(default=None, primary_key=True)
    data_do_registro: datetime = Field(default_factory = lambda: datetime.now(timezone.utc))
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

def crawler():
    """Abre a página do HEMOSC e grava os estoques de sangue atuais para cada
    tipo sanguíneo"""

    with sync_playwright() as p:
        # Headless false para rodar localmente, true para rodar no actions
        browser = p.firefox.launch(headless=True)

        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                ' (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1280, 'height': 720},
        )

        page = context.new_page()

        page.goto('https://www.hemosc.org.br/', wait_until='domcontentloaded')

        html_hemosc = page.content()


    soup = BeautifulSoup(html_hemosc, 'html.parser')

    # Retorna a div com o estado dos estoques de sangue
    div_estoque_de_sangue = soup.find_all('div', class_='dirt_home_estq')

    # Retorna a lista das divs de cada tipo sanguineo e seu estado de estoque
    estoque_diario_de_sangue_por_tipo = div_estoque_de_sangue[0].find_all('div')

    # Relação de estado de estoque da página com o estado do banco
    dict_estados_de_estoque_banco = {
                            'Adequado':5,
                            'Estável':4,
                            'Reduzido':3,
                            'Alerta':2, 'Crítico':1
                          }

    with Session(engine) as session:
        for estoque_por_tipo in estoque_diario_de_sangue_por_tipo:

            # Extrai o tipo sanguineo da tag img
            tipo_sanguineo = estoque_por_tipo.find('img').get('alt').split('tipo ')[-1]

            # Extrai o estoque atual do tipo sanguineo da tag img
            estoque_do_dia = estoque_por_tipo.find('img').get('title').split(' - ')[0]
            
            # Busca o tipo sanguineo no banco
            statement = select(TipoSanguineo.id).where(TipoSanguineo.tipo_sanguineo == tipo_sanguineo)
            grupo_tipo_sanguineo = session.exec(statement).first()

            # Busca identificador do estado do estoque no banco
            estado_do_estoque_hoje = dict_estados_de_estoque_banco[estoque_do_dia]

            # Registra o novo estado no banco
            novo_registro = RegistroEstoqueHemosc(estado_do_estoque=estado_do_estoque_hoje,
                                                  tipo_sanguineo_id=grupo_tipo_sanguineo)

            session.add(novo_registro)

        session.commit()


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

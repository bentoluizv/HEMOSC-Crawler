import time
import requests
from datetime import date, datetime, timezone
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

    # Abre a página do HEMOSC
    response = requests.get('https://www.hemosc.org.br/')
    soup = BeautifulSoup(response.text, 'html.parser')

    # Retorna a div com o estado dos estoques de sangue
    estoque_sangues_soup = soup.find_all('div', class_='dirt_home_estq')

    # Retorna uma lista das divs de cada tipo sanguineo e seu estado de estoque
    estoque_atual_por_tipo = estoque_sangues_soup[0].find_all('div')

    # Relação de estado de estoque da página com o estado do banco
    estados_de_estoque = {
                            'Adequado':5,
                            'Estável':4,
                            'Reduzido':3,
                            'Alerta':2, 'Crítico':1
                          }

    with Session(engine) as session:
        for tipo in estoque_atual_por_tipo:

            # Busca o tipo sanguineo do site
            tipo_sanguineo = tipo.find('img').get('alt').split('tipo ')[-1]

            # Busca o estado do estoque do tipo sanguineo do site
            estoque_do_dia = tipo.find('img').get('title').split(' - ')[0]

            # Busca o tipo sanguineo no banco
            grupo_tipo_sanguineo = select(TipoSanguineo.id).where(TipoSanguineo.tipo_sanguineo == tipo_sanguineo)

            # Busca identificador do estado do estoque no banco
            estado_do_estoque_hoje = estados_de_estoque[estoque_do_dia]

            # Registra o novo estado no banco
            novo_registro = RegistroEstoqueHemosc(estado_do_estoque=estado_do_estoque_hoje,
                                                  tipo_sanguineo_id=grupo_tipo_sanguineo)

            session.add(novo_registro)

        session.commit()

def observador_de_dia(ultimo_dia_verificado):
    """Verifica se o dia mudou, caso tenha mudado, extrai os dados
    e atualiza oa variável ultimo_dia_verificado"""

    hoje = date.today()

    if hoje != ultimo_dia_verificado:
        try:
            crawler()
            print('Estoque extraído com sucesso!')

        except Exception as e:
            print(f'Houve um erro. \n Erro: {e}')

        ultimo_dia_verificado = hoje

def main():
    create_db_and_tables()
    populate_database()

    crawler()

    print(f"| Observador iniciou. | \n | Dia de início: {ultimo_dia_verificado} |")
    while True:
        observador_de_dia(ultimo_dia_verificado)

        # Sleep para evitar alto uso de CPU (aqui, verifica a cada 1 hora)
        time.sleep(3600)

ultimo_dia_verificado = date.today()

if __name__ == "__main__":
    main()


"""
 - O estoque está ideal. Continue nos acompanhando, e agende sua doação quando necessário.
 - Continue doando para manter os estoques adequados
 - Venha doar sangue, precisamos de você.
 - Venha doar e nos ajude a divulgar essa necessidade.
 - Precisamos de você!
"""
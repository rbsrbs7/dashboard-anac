import streamlit as st
import pandas as pd
import numpy as np
import datetime

# Configuração da página
st.set_page_config(
    page_title="Dashboard Aviação Civil - ANAC",
    page_icon="✈️",
    layout="wide"
)

# Título Principal
st.title("✈️ Painel de Monitoramento de Voos e Passageiros (ANAC)")
st.markdown("Consulta interativa de decolagens, fluxo de passageiros, cancelamentos e faixas de atraso por terminal.")

# Carregamento de dados (Cache para alta performance)
@st.cache_data
def load_sample_data():
    """Gera dados com a mesma estrutura de colunas dos microdados VRA/ANAC."""
    np.random.seed(42)
    datas = pd.date_range(start="2025-01-01", end="2025-12-31", freq="H")
    aeroportos = ['SBGR (Guarulhos)', 'SBSP (Congonhas)', 'SBRJ (Santos Dumont)', 'SBGL (Galeão)', 'SBFZ (Fortaleza)']
    
    n_rows = 5000
    dates_sample = np.random.choice(datas, size=n_rows)
    
    df = pd.DataFrame({
        'Data_Partida': dates_sample,
        'Aeroporto_Origem': np.random.choice(aeroportos, size=n_rows),
        'Passageiros': np.random.randint(50, 220, size=n_rows),
        'Situacao_Voo': np.random.choice(['REALIZADO', 'CANCELADO'], size=n_rows, p=[0.93, 0.07]),
        'Atraso_Minutos': np.random.exponential(scale=20, size=n_rows).astype(int)
    })
    
    # Ajusta atrasos de voos cancelados para NaN
    df.loc[df['Situacao_Voo'] == 'CANCELADO', 'Atraso_Minutos'] = 0
    df.loc[df['Situacao_Voo'] == 'CANCELADO', 'Passageiros'] = 0
    
    df['Ano_Mes'] = df['Data_Partida'].dt.to_period('M')
    return df

# Sidebar - Filtros
st.sidebar.header("⚙️ Filtros de Consulta")

# Opção de Upload de Arquivo Real ou Dados Simulados
uploaded_file = st.sidebar.file_uploader("Carregar CSV da ANAC (Opcional)", type=["csv"])

if uploaded_file is not None:
    df_raw = pd.read_csv(uploaded_file)
    st.sidebar.success("Base enviada com sucesso!")
else:
    df_raw = load_sample_data()

# Filtro 1: Período
min_date = df_raw['Data_Partida'].min().date()
max_date = df_raw['Data_Partida'].max().date()

start_date, end_date = st.sidebar.date_input(
    "Selecione o Intervalo de Tempo:",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Filtro 2: Terminal / Aeroporto
terminais = sorted(df_raw['Aeroporto_Origem'].unique())
selected_terminal = st.sidebar.selectbox("Selecione o Terminal/Aeroporto:", ["Todos"] + terminais)

# Aplicando Filtros
mask = (df_raw['Data_Partida'].dt.date >= start_date) & (df_raw['Data_Partida'].dt.date <= end_date)
if selected_terminal != "Todos":
    mask = mask & (df_raw['Aeroporto_Origem'] == selected_terminal)

df_filtered = df_raw[mask].copy()

# ---- ÁREA PRINCIPAL: KPIs ----
col1, col2, col3, col4 = st.columns(4)

total_decolagens = len(df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO'])
total_passageiros = df_filtered['Passageiros'].sum()
total_cancelados = len(df_filtered[df_filtered['Situacao_Voo'] == 'CANCELADO'])
taxa_cancelamento = (total_cancelados / len(df_filtered) * 100) if len(df_filtered) > 0 else 0

col1.metric("Decolagens Realizadas", f"{total_decolagens:,}")
col2.metric("Passageiros Embarcados", f"{total_passageiros:,}")
col3.metric("Voos Cancelados", f"{total_cancelados:,}")
col4.metric("Taxa de Cancelamento", f"{taxa_cancelamento:.2f}%")

st.markdown("---")

# ---- ANÁLISE DE ATRASOS POR FAIXAS ----
st.subheader("⏱️ Classificação de Atrasos no Período")

voos_decolados = df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO']

atraso_10 = len(voos_decolados[(voos_decolados['Atraso_Minutos'] > 0) & (voos_decolados['Atraso_Minutos'] <= 10)])
atraso_30 = len(voos_decolados[(voos_decolados['Atraso_Minutos'] > 10) & (voos_decolados['Atraso_Minutos'] <= 30)])
atraso_1h = len(voos_decolados[(voos_decolados['Atraso_Minutos'] > 30) & (voos_decolados['Atraso_Minutos'] <= 60)])
atraso_3h = len(voos_decolados[voos_decolados['Atraso_Minutos'] > 60])

col_a, col_b, col_c, col_d = st.columns(4)
col_a.warning(f"**Até 10 min:** {atraso_10} voos")
col_b.warning(f"**11 a 30 min:** {atraso_30} voos")
col_c.error(f"**31 min a 1 hora:** {atraso_1h} voos")
col_d.error(f"**Acima de 1 hora:** {atraso_3h} voos")

st.markdown("---")

# ---- GRÁFICOS E TABELAS ----
tab1, tab2 = st.tabs(["📊 Visão Mensal", "📋 Detalhes dos Dados"])

with tab1:
    st.write("### Movimentação Mensal por Terminal")
    df_mensal = df_filtered.groupby(['Ano_Mes', 'Situacao_Voo']).agg(
        Decolagens=('Passageiros', 'count'),
        Passageiros=('Passageiros', 'sum')
    ).reset_index()
    df_mensal['Ano_Mes'] = df_mensal['Ano_Mes'].astype(str)
    
    st.line_chart(df_mensal, x='Ano_Mes', y='Decolagens', color='Situacao_Voo')

with tab2:
    st.write("### Base Filtrada")
    st.dataframe(df_filtered, use_container_width=True)
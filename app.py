import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import datetime
import plotly.express as px

# Configuração da página
st.set_page_config(
    page_title="Dashboard Aviação Civil - ANAC",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ Painel de Monitoramento de Voos da ANAC")
st.markdown("Consulta interativa com gráficos Plotly Express e integração ao Portal de Dados Abertos.")

# --- GERADOR DE DADOS MOCK ---
def generate_fallback_data(ano: int, mes: int) -> pd.DataFrame:
    """Gera uma estrutura válida de dados simulados caso o arquivo da ANAC retorne 404."""
    np.random.seed(ano + mes)
    datas = pd.date_range(start=f"{ano}-{mes:02d}-01", periods=1000, freq="h")
    aeroportos = ['SBGR (Guarulhos)', 'SBSP (Congonhas)', 'SBRJ (Santos Dumont)', 'SBGL (Galeão)', 'SBFZ (Fortaleza)']
    
    df = pd.DataFrame({
        'Aeroporto_Origem': np.random.choice(aeroportos, size=1000),
        'Aeroporto_Destino': np.random.choice(aeroportos, size=1000),
        'Situacao_Voo': np.random.choice(['REALIZADO', 'CANCELADO'], size=1000, p=[0.92, 0.08]),
        'Partida_Prevista': datas,
        'Partida_Real': datas + pd.to_timedelta(np.random.exponential(scale=20, size=1000), unit='m'),
        'Passageiros': np.random.randint(50, 200, size=1000)
    })
    
    df.loc[df['Situacao_Voo'] == 'CANCELADO', 'Passageiros'] = 0
    df['Atraso_Minutos'] = (df['Partida_Real'] - df['Partida_Prevista']).dt.total_seconds() / 60
    df.loc[df['Situacao_Voo'] == 'CANCELADO', 'Atraso_Minutos'] = 0
    
    return df

# --- FUNÇÃO DE DOWNLOAD E TRATAMENTO DOS DADOS ---
@st.cache_data(ttl=86400)
def fetch_anac_data(ano: int, mes: int, allow_fallback: bool = True) -> tuple[pd.DataFrame, str]:
    url = f"https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20operacoes%20aereas/Voo%20Regular%20Ativo%20(VRA)/{ano}/VRA_{ano}{mes:02d}.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.content.decode('utf-8-sig', errors='ignore')), sep=';', on_bad_lines='skip')
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            col_map = {
                'ICAO AERÓDROMO ORIGEM': 'Aeroporto_Origem', 'ICAO AERODROMO ORIGEM': 'Aeroporto_Origem',
                'ICAO AERÓDROMO DESTINO': 'Aeroporto_Destino', 'ICAO AERODROMO DESTINO': 'Aeroporto_Destino',
                'SITUAÇÃO VOO': 'Situacao_Voo', 'SITUACAO VOO': 'Situacao_Voo',
                'PARTIDA PREVISTA': 'Partida_Prevista', 'PARTIDA REAL': 'Partida_Real',
                'NÚMERO PASSAGEIROS': 'Passageiros', 'NUMERO PASSAGEIROS': 'Passageiros'
            }
            df = df.rename(columns=col_map)
            
            if 'Partida_Prevista' in df.columns and 'Partida_Real' in df.columns:
                df['Partida_Prevista'] = pd.to_datetime(df['Partida_Prevista'], errors='coerce')
                df['Partida_Real'] = pd.to_datetime(df['Partida_Real'], errors='coerce')
                df['Atraso_Minutos'] = (df['Partida_Real'] - df['Partida_Prevista']).dt.total_seconds() / 60
                df['Atraso_Minutos'] = df['Atraso_Minutos'].apply(lambda x: max(x, 0) if pd.notnull(x) else 0)

            if 'Passageiros' in df.columns:
                df['Passageiros'] = pd.to_numeric(df['Passageiros'], errors='coerce').fillna(0)

            return df, "oficial"
        elif response.status_code == 404 and allow_fallback:
            return generate_fallback_data(ano, mes), "simulado"
        else:
            return pd.DataFrame(), "erro"
    except Exception:
        if allow_fallback:
            return generate_fallback_data(ano, mes), "simulado"
        return pd.DataFrame(), "erro"

# --- BARRA LATERAL (FILTROS) ---
st.sidebar.header("⚙️ Parâmetros de Busca")
hoje = datetime.date.today()

ano_selecionado = st.sidebar.number_input("Ano da Consulta", min_value=2020, max_value=hoje.year, value=2025)
mes_selecionado = st.sidebar.slider("Mês da Consulta", min_value=1, max_value=12, value=1)
usar_simulacao = st.sidebar.checkbox("Carregar dados simulados se o arquivo não existir na ANAC", value=True)

with st.spinner("Buscando dados na base da ANAC..."):
    df_raw, origem = fetch_anac_data(ano_selecionado, mes_selecionado, allow_fallback=usar_simulacao)

if origem == "simulado":
    st.info(f"ℹ️ Exibindo **dados simulados** para {mes_selecionado:02d}/{ano_selecionado} (base da ANAC indisponível ou não publicada para este mês).")

if not df_raw.empty:
    if 'Aeroporto_Origem' in df_raw.columns:
        terminais = sorted(df_raw['Aeroporto_Origem'].dropna().unique())
        selected_terminal = st.sidebar.selectbox("Selecione o Aeroporto de Origem:", ["Todos"] + terminais)

        if selected_terminal != "Todos":
            df_filtered = df_raw[df_raw['Aeroporto_Origem'] == selected_terminal].copy()
        else:
            df_filtered = df_raw.copy()
    else:
        df_filtered = df_raw.copy()

    # --- KPIS PRINCIPAIS ---
    c1, c2, c3 = st.columns(3)
    total_decolagens = len(df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO']) if 'Situacao_Voo' in df_filtered.columns else len(df_filtered)
    total_cancelados = len(df_filtered[df_filtered['Situacao_Voo'] == 'CANCELADO']) if 'Situacao_Voo' in df_filtered.columns else 0
    total_pax = int(df_filtered['Passageiros'].sum()) if 'Passageiros' in df_filtered.columns else 0

    c1.metric("Decolagens Realizadas", f"{total_decolagens:,}")
    c2.metric("Voos Cancelados", f"{total_cancelados:,}")
    c3.metric("Total de Passageiros", f"{total_pax:,}")

    st.markdown("---")

    # --- SESSÃO DE GRÁFICOS PLOTLY ---
    st.subheader("📊 Visualizações Interativas (Plotly Express)")

    col_chart1, col_chart2 = st.columns(2)

    # GRÁFICO 1: PIZZA (Distribuição de Faixas de Atraso)
    with col_chart1:
        voos_realizados = df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO'] if 'Situacao_Voo' in df_filtered.columns else df_filtered

        if 'Atraso_Minutos' in voos_realizados.columns and not voos_realizados.empty:
            def categorizar_atraso(minutos):
                if minutos <= 10:
                    return 'Pontual / Até 10 min'
                elif minutos <= 30:
                    return 'Atraso de 11 a 30 min'
                elif minutos <= 60:
                    return 'Atraso de 31 a 60 min'
                else:
                    return 'Atraso acima de 1 hora'

            voos_realizados['Faixa_Atraso'] = voos_realizados['Atraso_Minutos'].apply(categorizar_atraso)
            df_faixas = voos_realizados['Faixa_Atraso'].value_counts().reset_index()
            df_faixas.columns = ['Faixa', 'Quantidade']

            fig_pie = px.pie(
                df_faixas, 
                names='Faixa', 
                values='Quantidade',
                title="<b>Distribuição por Faixa de Atraso</b>",
                color='Faixa',
                color_discrete_map={
                    'Pontual / Até 10 min': '#2ecc71',
                    'Atraso de 11 a 30 min': '#f1c40f',
                    'Atraso de 31 a 60 min': '#e67e22',
                    'Atraso acima de 1 hora': '#e74c3c'
                },
                hole=0.4
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

    # GRÁFICO 2: BARRAS (Top Destinos por Volume de Passageiros)
    with col_chart2:
        if 'Aeroporto_Destino' in df_filtered.columns and 'Passageiros' in df_filtered.columns:
            df_destinos = df_filtered.groupby('Aeroporto_Destino')['Passageiros'].sum().reset_index()
            df_destinos = df_destinos.sort_values(by='Passageiros', ascending=False).head(10)

            fig_bar = px.bar(
                df_destinos,
                x='Passageiros',
                y='Aeroporto_Destino',
                orientation='h',
                title="<b>Top 10 Destinos com Mais Passageiros Saindo do Terminal</b>",
                labels={'Passageiros': 'Número de Passageiros', 'Aeroporto_Destino': 'Terminal de Destino'},
                color='Passageiros',
                color_continuous_scale='Blues'
            )
            fig_bar.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")
    st.dataframe(df_filtered.head(100), use_container_width=True)

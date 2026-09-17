import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import datetime

st.set_page_config(
    page_title="Dashboard Aviação Civil - ANAC",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ Painel de Monitoramento de Voos da ANAC")
st.markdown("Consulta interativa com integração ao Portal de Dados Abertos da ANAC.")

# --- GERADOR DE DADOS MOCK (CORRIGIDO PARA PANDAS RECENTE) ---
def generate_fallback_data(ano: int, mes: int) -> pd.DataFrame:
    """Gera uma estrutura válida de dados simulados caso o arquivo da ANAC retorne 404."""
    np.random.seed(ano + mes)
    # Correção: freq="h" minúsculo para compatibilidade com o Pandas 2.2+
    datas = pd.date_range(start=f"{ano}-{mes:02d}-01", periods=1000, freq="h")
    aeroportos = ['SBGR (Guarulhos)', 'SBSP (Congonhas)', 'SBRJ (Santos Dumont)', 'SBGL (Galeão)', 'SBFZ (Fortaleza)']
    
    df = pd.DataFrame({
        'Aeroporto_Origem': np.random.choice(aeroportos, size=1000),
        'Situacao_Voo': np.random.choice(['REALIZADO', 'CANCELADO'], size=1000, p=[0.92, 0.08]),
        'Partida_Prevista': datas,
        'Partida_Real': datas + pd.to_timedelta(np.random.exponential(scale=15, size=1000), unit='m'),
        'Passageiros': np.random.randint(50, 200, size=1000)
    })
    
    df.loc[df['Situacao_Voo'] == 'CANCELADO', 'Passageiros'] = 0
    df['Atraso_Minutos'] = (df['Partida_Real'] - df['Partida_Prevista']).dt.total_seconds() / 60
    df.loc[df['Situacao_Voo'] == 'CANCELADO', 'Atraso_Minutos'] = 0
    
    return df

# --- FUNÇÃO DE DOWNLOAD E TRATAMENTO DOS DADOS ---
@st.cache_data(ttl=86400)
def fetch_anac_data(ano: int, mes: int, allow_fallback: bool = True) -> tuple[pd.DataFrame, str]:
    """
    Tenta baixar o arquivo da ANAC. Se retornar 404 e allow_fallback=True, carrega a simulação.
    """
    url = f"https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20operacoes%20aereas/Voo%20Regular%20Ativo%20(VRA)/{ano}/VRA_{ano}{mes:02d}.csv"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            df = pd.read_csv(
                io.StringIO(response.content.decode('utf-8-sig', errors='ignore')), 
                sep=';', 
                on_bad_lines='skip'
            )
            
            # Padroniza colunas removendo espaços e convertendo para maiúsculo
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            col_map = {
                'ICAO AERÓDROMO ORIGEM': 'Aeroporto_Origem',
                'ICAO AERODROMO ORIGEM': 'Aeroporto_Origem',
                'SITUAÇÃO VOO': 'Situacao_Voo',
                'SITUACAO VOO': 'Situacao_Voo',
                'PARTIDA PREVISTA': 'Partida_Prevista',
                'PARTIDA REAL': 'Partida_Real',
                'NÚMERO PASSAGEIROS': 'Passageiros',
                'NUMERO PASSAGEIROS': 'Passageiros'
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

        elif response.status_code == 404:
            if allow_fallback:
                return generate_fallback_data(ano, mes), "simulado"
            else:
                return pd.DataFrame(), "nao_encontrado"
        else:
            if allow_fallback:
                return generate_fallback_data(ano, mes), "simulado"
            return pd.DataFrame(), "erro"

    except Exception as e:
        if allow_fallback:
            return generate_fallback_data(ano, mes), "simulado"
        return pd.DataFrame(), "erro"

# --- BARRA LATERAL (FILTROS) ---
st.sidebar.header("⚙️ Parâmetros de Busca")

hoje = datetime.date.today()

# Filtros de Ano e Mês
ano_selecionado = st.sidebar.number_input("Ano da Consulta", min_value=2020, max_value=hoje.year, value=2025)
mes_selecionado = st.sidebar.slider("Mês da Consulta", min_value=1, max_value=12, value=1)

usar_simulacao = st.sidebar.checkbox("Carregar dados simulados se o arquivo não existir na ANAC", value=True)

# EXECUÇÃO DO CARREGAMENTO
with st.spinner("Buscando dados na base da ANAC..."):
    df_raw, origem = fetch_anac_data(ano_selecionado, mes_selecionado, allow_fallback=usar_simulacao)

# --- ALERTAS E RENDERIZAÇÃO ---
if origem == "simulado":
    st.info(f"ℹ️ Os dados reais para **{mes_selecionado:02d}/{ano_selecionado}** não foram encontrados no servidor da ANAC. Exibindo **dados simulados** para demonstração.")
elif origem == "nao_encontrado":
    st.warning(f"⚠️ Não foram encontrados dados no servidor da ANAC para **{mes_selecionado:02d}/{ano_selecionado}**. Escolha outro período.")

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

    # KPIS
    c1, c2, c3 = st.columns(3)
    
    total_decolagens = len(df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO']) if 'Situacao_Voo' in df_filtered.columns else len(df_filtered)
    total_cancelados = len(df_filtered[df_filtered['Situacao_Voo'] == 'CANCELADO']) if 'Situacao_Voo' in df_filtered.columns else 0
    total_pax = int(df_filtered['Passageiros'].sum()) if 'Passageiros' in df_filtered.columns else 0

    c1.metric("Decolagens Realizadas", f"{total_decolagens:,}")
    c2.metric("Voos Cancelados", f"{total_cancelados:,}")
    c3.metric("Total de Passageiros", f"{total_pax:,}")

    st.markdown("---")

    # FAIXAS DE ATRASO
    st.subheader("⏱️ Faixas de Atraso (Voos Realizados)")
    voos_realizados = df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO'] if 'Situacao_Voo' in df_filtered.columns else df_filtered

    if 'Atraso_Minutos' in voos_realizados.columns:
        a10 = len(voos_realizados[(voos_realizados['Atraso_Minutos'] > 0) & (voos_realizados['Atraso_Minutos'] <= 10)])
        a30 = len(voos_realizados[(voos_realizados['Atraso_Minutos'] > 10) & (voos_realizados['Atraso_Minutos'] <= 30)])
        a60 = len(voos_realizados[(voos_realizados['Atraso_Minutos'] > 30) & (voos_realizados['Atraso_Minutos'] <= 60)])
        a180 = len(voos_realizados[voos_realizados['Atraso_Minutos'] > 60])

        ca, cb, cc, cd = st.columns(4)
        ca.warning(f"**Até 10 min:** {a10}")
        cb.warning(f"**11 a 30 min:** {a30}")
        cc.error(f"**31 min a 1 hora:** {a60}")
        cd.error(f"**Acima de 1 hora:** {a180}")

    st.markdown("---")
    st.dataframe(df_filtered.head(100), use_container_width=True)

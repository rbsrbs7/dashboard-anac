import streamlit as st
import pandas as pd
import requests
import io
import zipfile

st.set_page_config(
    page_title="Dashboard Aviação Civil - ANAC",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ Painel de Monitoramento de Voos da ANAC")
st.markdown("Consulta interativa com download em tempo real direto dos servidores da ANAC.")

# --- FUNÇÃO DE DOWNLOAD E TRATAMENTO DOS DADOS ---
@st.cache_data(ttl=86400)  # Cache armazenado por 24 horas para evitar requisições excessivas
def fetch_anac_data(ano: int, mes: int) -> pd.DataFrame:
    """
    Baixa e trata os microdados do VRA (Voo Regular Ativo) da ANAC para um ano e mês específicos.
    """
    # Padrão de URL da ANAC para arquivos VRA (CSV ou ZIP)
    url = f"https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20operacoes%20aereas/Voo%20Regular%20Ativo%20(VRA)/{ano}/VRA_{ano}{mes:02d}.csv"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        # Caso o arquivo esteja zipado no servidor
        if response.status_code == 200 and url.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                df = pd.read_csv(z.open(csv_filename), sep=';', encoding='utf-8-sig')
        # Caso o arquivo seja disponibilizado diretamente em CSV
        elif response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.content.decode('utf-8-sig', errors='ignore')), sep=';')
        else:
            st.warning(f"Não foram encontrados dados no portal da ANAC para {mes:02d}/{ano} (Status: {response.status_code}).")
            return pd.DataFrame()

        # Normalização dos nomes das colunas
        df.columns = [c.strip().upper() for c in df.columns]

        # Mapeamento de colunas padrão VRA/ANAC
        # Ajuste os nomes abaixo conforme a estrutura do arquivo retornado se necessário
        col_map = {
            'ICAO AERÓDROMO ORIGEM': 'Aeroporto_Origem',
            'ICAO AERÓDROMO DESTINO': 'Aeroporto_Destino',
            'SITUAÇÃO VOO': 'Situacao_Voo',
            'PARTIDA PREVISTA': 'Partida_Prevista',
            'PARTIDA REAL': 'Partida_Real',
            'NÚMERO PASSAGEIROS': 'Passageiros'
        }
        
        df = df.rename(columns=col_map)

        # Trata datas e calcula atrasos
        if 'Partida_Prevista' in df.columns and 'Partida_Real' in df.columns:
            df['Partida_Prevista'] = pd.to_datetime(df['Partida_Prevista'], errors='coerce')
            df['Partida_Real'] = pd.to_datetime(df['Partida_Real'], errors='coerce')
            
            # Cálculo de atraso em minutos
            df['Atraso_Minutos'] = (df['Partida_Real'] - df['Partida_Prevista']).dt.total_seconds() / 60
            df['Atraso_Minutos'] = df['Atraso_Minutos'].apply(lambda x: max(x, 0) if pd.notnull(x) else 0)

        if 'Passageiros' in df.columns:
            df['Passageiros'] = pd.to_numeric(df['Passageiros'], errors='coerce').fillna(0)

        return df

    except Exception as e:
        st.error(f"Erro ao conectar com o servidor da ANAC: {e}")
        return pd.DataFrame()


# --- FILTROS NA BARRA LATERAL ---
st.sidebar.header("⚙️ Parâmetros de Busca")

ano_selecionado = st.sidebar.number_input("Ano da Consulta", min_value=2020, max_value=2026, value=2025)
mes_selecionado = st.sidebar.slider("Mês da Consulta", min_value=1, max_value=12, value=1)

# Carrega os dados via API/URL
with st.spinner(f"Baixando dados da ANAC referentes a {mes_selecionado:02d}/{ano_selecionado}..."):
    df_raw = fetch_anac_data(ano_selecionado, mes_selecionado)

if not df_raw.empty:
    # Filtro de Terminal
    terminais = sorted(df_raw['Aeroporto_Origem'].dropna().unique())
    selected_terminal = st.sidebar.selectbox("Selecione o Aeroporto de Origem:", ["Todos"] + terminais)

    if selected_terminal != "Todos":
        df_filtered = df_raw[df_raw['Aeroporto_Origem'] == selected_terminal].copy()
    else:
        df_filtered = df_raw.copy()

    # --- EXIBIÇÃO DOS KPIS ---
    col1, col2, col3 = st.columns(3)
    
    total_decolagens = len(df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO'])
    total_cancelados = len(df_filtered[df_filtered['Situacao_Voo'] == 'CANCELADO'])
    total_pax = int(df_filtered['Passageiros'].sum()) if 'Passageiros' in df_filtered.columns else 0

    col1.metric("Decolagens Realizadas", f"{total_decolagens:,}")
    col2.metric("Voos Cancelados", f"{total_cancelados:,}")
    col3.metric("Passageiros Estimados", f"{total_pax:,}")

    st.markdown("---")

    # --- CLASSIFICAÇÃO DE ATRASOS ---
    st.subheader("⏱️ Faixas de Atraso (Voos Realizados)")
    voos_realizados = df_filtered[df_filtered['Situacao_Voo'] == 'REALIZADO']

    if 'Atraso_Minutos' in voos_realizados.columns:
        atraso_10 = len(voos_realizados[(voos_realizados['Atraso_Minutos'] > 0) & (voos_realizados['Atraso_Minutos'] <= 10)])
        atraso_30 = len(voos_realizados[(voos_realizados['Atraso_Minutos'] > 10) & (voos_realizados['Atraso_Minutos'] <= 30)])
        atraso_1h = len(voos_realizados[(voos_realizados['Atraso_Minutos'] > 30) & (voos_realizados['Atraso_Minutos'] <= 60)])
        atraso_3h = len(voos_realizados[voos_realizados['Atraso_Minutos'] > 60])

        ca, cb, cc, cd = st.columns(4)
        ca.warning(f"**Até 10 min:** {atraso_10}")
        cb.warning(f"**11 a 30 min:** {atraso_30}")
        cc.error(f"**31 min a 1 hora:** {atraso_1h}")
        cd.error(f"**Acima de 1 hora:** {atraso_3h}")

    st.markdown("---")
    st.dataframe(df_filtered.head(100), use_container_width=True)

else:
    st.info("Selecione um mês e ano válidos na barra lateral para carregar as informações.")

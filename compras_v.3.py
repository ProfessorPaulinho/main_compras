import io
import pandas as pd
import streamlit as st
from fpdf import FPDF

def gerar_pdf_compras(df_compras, total_estimado: float) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Título
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, "Lista de Compras", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Montagem da Tabela com pdf.table()
    pdf.set_font("Helvetica", size=10)
    
    # Cabeçalho e dados
    colunas = ["Qtd", "Produto", "Preço Atual", "Subtotal"]
    
    with pdf.table(col_widths=(15, 95, 30, 30), text_align=("CENTER", "LEFT", "RIGHT", "RIGHT")) as table:
        header = table.row()
        for col in colunas:
            header.cell(col)
            
        for _, row in df_compras.iterrows():
            linha = table.row()
            qtd = int(row.get("Quantidade", 1))
            preco = float(row.get("Preço_atual", 0.0))
            subtotal = qtd * preco
            
            linha.cell(f"[    ]  {qtd}")  # Já sai com um quadradinho para riscar!
            linha.cell(str(row["Produto"]))
            linha.cell(f"R$ {preco:.2f}")
            linha.cell(f"R$ {subtotal:.2f}")

    # Total geral
    pdf.ln(5)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 10, f"Total Estimado: R$ {total_estimado:.2f}", align="R")
    
    # Retorna os bytes prontos para o Streamlit
    return bytes(pdf.output())

# ---------------------------------------------------------
# CONFIGURAÇÕES INICIAIS DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestão de Lista de Compras",
    page_icon="🛒",
    layout="wide"
)

COLUNAS_BASE = ["Produto", "Preço_atual", "Preço_ant_1", "Preço_ant_2"]


def limpar_converter_moeda(serie: pd.Series, preencher_zero: bool = False) -> pd.Series:
    """Converte valores R$ para float mantendo valores nulos quando apropriado."""
    limpo = (
        serie.astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
    numerico = pd.to_numeric(limpo, errors="coerce")
    return numerico.fillna(0.0) if preencher_zero else numerico


def carregar_dados(arquivo) -> pd.DataFrame | None:
    """Lê o arquivo CSV tratando BOM, espaços em branco e preços opcionais."""
    try:
        # utf-8-sig consome o BOM nativamente
        df = pd.read_csv(arquivo, delimiter=";", encoding="utf-8-sig", dtype=str)
        
        # Limpa espaços nas pontas dos nomes de produtos e supermercados
        df["Produto"] = df["Produto"].astype(str).str.strip()
        if "Supermercado" in df.columns:
            df["Supermercado"] = df["Supermercado"].astype(str).str.strip()

        # Preço atual é obrigatório (preenche com 0.0 se faltar)
        if "Preço_atual" in df.columns:
            df["Preço_atual"] = limpar_converter_moeda(df["Preço_atual"], preencher_zero=True)

        # Históricos mantêm NaN/None para não mostrar 'R$ 0,00' na interface
        for col in ["Preço_ant_1", "Preço_ant_2"]:
            if col in df.columns:
                df[col] = limpar_converter_moeda(df[col], preencher_zero=False)

        # Colunas operacionais
        df.insert(0, "Selecionar", False)
        df.insert(1, "Quantidade", 1)
        
        return df

    except Exception as erro:
        st.error(f"Erro ao processar o arquivo CSV: {erro}")
        return None


# ---------------------------------------------------------
# CABEÇALHO E UPLOAD
# ---------------------------------------------------------
st.title("🛒 Gestão e Controle de Compras")

arquivo_enviado = st.file_uploader(
    "Selecione o arquivo CSV de produtos (delimitador: ';')", 
    type=["csv"]
)

if not arquivo_enviado:
    st.info("Aguardando upload do catálogo de produtos em formato CSV.")
    st.stop()

# Inicialização do dataframe no Session State para persistência
if "df_origem" not in st.session_state or st.session_state.get("nome_arquivo") != arquivo_enviado.name:
    dados_carregados = carregar_dados(arquivo_enviado)
    if dados_carregados is None:
        st.stop()
    st.session_state.df_origem = dados_carregados
    st.session_state.nome_arquivo = arquivo_enviado.name
    # Limpa estados de edições anteriores
    st.session_state.pop("editor_compras", None)

aba_produtos, aba_compras = st.tabs(["📋 Catálogo de Produtos", "🛍️ Carrinho de Compras"])

# ---------------------------------------------------------
# ABA 1: SELEÇÃO DE PRODUTOS
# ---------------------------------------------------------
with aba_produtos:
    st.subheader("Escolha os produtos e defina as quantidades")

    df_editado_produtos = st.data_editor(
        st.session_state.df_origem,
        hide_index=True,
        use_container_width=True,
        key="editor_catalogo",
        disabled=["Produto", "Preço_atual", "Preço_ant_1", "Preço_ant_2"],
        column_config={
            "Selecionar": st.column_config.CheckboxColumn("Comprar?", default=False, width="small"),
            "Quantidade": st.column_config.NumberColumn("Qtd", min_value=1, step=1, default=1, width="small"),
            "Produto": st.column_config.TextColumn("Descrição do Produto"),
            "Preço_atual": st.column_config.NumberColumn("Preço Atual", format="R$ %.2f"),
            "Preço_ant_1": st.column_config.NumberColumn("Preço Ant. 1", format="R$ %.2f"),
            "Preço_ant_2": st.column_config.NumberColumn("Preço Ant. 2", format="R$ %.2f"),
        }
    )

    # Filtra apenas o que foi marcado
    itens_selecionados = df_editado_produtos[df_editado_produtos["Selecionar"]].copy()

# ---------------------------------------------------------
# ABA 2: ITENS SELECIONADOS E CHECKLIST DE COMPRAS
# ---------------------------------------------------------
with aba_compras:
    st.subheader("Checklist da Lista de Compras")

    if itens_selecionados.empty:
        st.info("Nenhum item marcado no catálogo. Retorne à aba anterior para montar seu carrinho.")
    else:
        # Prepara a base da lista final
        itens_selecionados.drop(columns=["Selecionar"], inplace=True)
        if "Comprado" not in itens_selecionados.columns:
            itens_selecionados.insert(0, "Comprado", False)

        # Reordena as colunas
        ordem_exibicao = ["Comprado", "Quantidade", "Produto", "Preço_atual", "Preço_ant_1", "Preço_ant_2"]
        cols_finais = [c for c in ordem_exibicao if c in itens_selecionados.columns]
        df_carrinho_base = itens_selecionados[cols_finais]

        # Tabela com persistência dos checkboxes
        tabela_compras = st.data_editor(
            df_carrinho_base,
            hide_index=True,
            use_container_width=True,
            key="editor_compras",
            disabled=["Quantidade", "Produto", "Preço_atual", "Preço_ant_1", "Preço_ant_2"],
            column_config={
                "Comprado": st.column_config.CheckboxColumn("Comprado", default=False, width="small"),
                "Quantidade": st.column_config.NumberColumn("Qtd", width="small"),
                "Produto": st.column_config.TextColumn("Descrição"),
                "Preço_atual": st.column_config.NumberColumn("Preço Atual", format="R$ %.2f"),
                "Preço_ant_1": st.column_config.NumberColumn("Preço Ant. 1", format="R$ %.2f"),
                "Preço_ant_2": st.column_config.NumberColumn("Preço Ant. 2", format="R$ %.2f"),
            }
        )

        st.divider()

        # Métricas visuais
        total_itens = len(tabela_compras)
        itens_comprados = int(tabela_compras["Comprado"].sum())
        
        if "Preço_atual" in tabela_compras.columns:
            valor_estimado = (tabela_compras["Quantidade"] * tabela_compras["Preço_atual"]).sum()
            valor_concluido = (tabela_compras.loc[tabela_compras["Comprado"], "Quantidade"] * 
                               tabela_compras.loc[tabela_compras["Comprado"], "Preço_atual"]).sum()
        else:
            valor_estimado = 0.0
            valor_concluido = 0.0

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Itens no Carrinho", f"{itens_comprados}/{total_itens}")
        col_m2.metric("Total Estimado", f"R$ {valor_estimado:.2f}")
        col_m3.metric("Gasto Realizado", f"R$ {valor_concluido:.2f}")

        st.divider()

        # Botões de Download lado a lado dentro da aba e do else
        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            buffer_csv = tabela_compras.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
            st.download_button(
                label="💾 Baixar Lista Atualizada (CSV)",
                data=buffer_csv,
                file_name="lista_compras_finalizada.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_btn2:
            pdf_bytes = gerar_pdf_compras(tabela_compras, valor_estimado)
            st.download_button(
                label="📄 Baixar Lista em PDF",
                data=pdf_bytes,
                file_name="lista_de_compras.pdf",
                mime="application/pdf",
                use_container_width=True
            )
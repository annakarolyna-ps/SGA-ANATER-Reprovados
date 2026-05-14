"""
SGA ANATER - Verificador de Relatórios Reprovados
=================================================
Navega pelo SGA e coleta execuções reprovadas nas metas de
"Atendimento individual de Ater".

Saída por cidade:
  META | Cód. Execução | Nome Propriedade UFPA | Nome Proprietária | Data Execução | Motivo
"""

import asyncio
import getpass
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "https://sga.anater.org"
TERMO_BUSCA_META = "atendi"


# ─── helpers ──────────────────────────────────────────────────────────────────

def salvar_csv(registros, csv_path):
    """Salva CSV com ; como delimitador (compatível com Excel Brasil)."""
    import csv, os
    campos = ["meta","cod_execucao","cod_ufpa","nome_ufpa","proprietaria","data_execucao","cidade","motivo"]
    # Se o arquivo estiver aberto no Excel, salva com nome alternativo
    caminho_final = csv_path
    try:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore', delimiter=';')
            writer.writeheader()
            writer.writerows(registros)
    except PermissionError:
        # Arquivo aberto no Excel — salva com timestamp
        from datetime import datetime
        ts = datetime.now().strftime("%H%M%S")
        caminho_final = csv_path.replace(".csv", f"_{ts}.csv")
        with open(caminho_final, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore', delimiter=';')
            writer.writeheader()
            writer.writerows(registros)
        print(f"      ⚠️  Arquivo original em uso pelo Excel. Salvo como: {caminho_final}")
    return caminho_final


def tabela_resultados(registros, titulo=""):
    sep = f"{'─'*160}"
    if titulo:
        print(f"\n{sep}")
        print(f"  {titulo}")
    print(sep)
    print(f"{'Meta':<8} {'Cód.Exec':<10} {'Cód.UFPA':<10} {'Nome UFPA':<35} {'Proprietária':<32} {'Data Exec':<12} Motivo")
    print(sep)
    for r in registros:
        motivo_raw = r['motivo'] if r['motivo'] else "—"
        motivo_display = (motivo_raw[:70] + "...") if len(motivo_raw) > 73 else motivo_raw
        print(
            f"{r['meta']:<8} "
            f"{r['cod_execucao']:<10} "
            f"{r.get('cod_ufpa',''):<10} "
            f"{r.get('nome_ufpa','')[:34]:<35} "
            f"{r['proprietaria'][:31]:<32} "
            f"{r['data_execucao']:<12} "
            f"{motivo_display}"
        )
    print(sep)
    print(f"  Total: {len(registros)} registro(s)  |  Motivo completo no CSV")


async def navegar_para_painel(page):
    print("📊 Navegando para Painel Extensionista...")
    # Fecha modal se estiver aberto
    try:
        if await page.locator('.modal.in').count() > 0:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(700)
    except:
        pass

    # Sempre clica em Business Intelligence primeiro para garantir que o submenu está aberto
    for tentativa in range(3):
        try:
            await page.click('text=Business Intelligence', timeout=10000)
            await page.wait_for_timeout(600)
            await page.click('text=Painel Extensionista', timeout=10000)
            await page.wait_for_load_state("networkidle")
            print("✅ Painel Extensionista aberto!")
            return
        except:
            await page.wait_for_timeout(1000)

    raise Exception("Não conseguiu navegar para o Painel Extensionista")


async def abrir_metas(page):
    print("📋 Abrindo Metas Pactuadas...")
    btn = page.locator('a, button').filter(has_text="VER DETALHES")
    await btn.first.click()
    await page.wait_for_load_state("networkidle")
    print("✅ Página de metas aberta!")


async def filtrar_metas(page):
    # Rola a página para baixo para achar a tabela "Resultado: CTR..."
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except:
        pass
    await page.wait_for_timeout(1000)

    # Tenta preencher o campo de busca
    for _ in range(20):
        try:
            campos = page.locator('input[type="search"]')
            count = await campos.count()
            if count > 0:
                # Usa o último campo de busca (o da tabela de metas)
                await campos.last.fill(TERMO_BUSCA_META)
                await page.wait_for_timeout(1500)
                return
        except:
            pass
        await page.wait_for_timeout(1000)
    # Fallback
    try:
        await page.locator('input[type="search"]').last.fill(TERMO_BUSCA_META)
        await page.wait_for_timeout(1500)
    except:
        pass


async def voltar_para_metas(page):
    """Refaz navegação completa pois a URL é dinâmica e expira."""
    await navegar_para_painel(page)
    await abrir_metas(page)
    await filtrar_metas(page)


# ─── coleta de dados ───────────────────────────────────────────────────────────

async def coletar_metas(page):
    """Lê a tabela filtrada e retorna lista de metas com reprovações."""
    print(f"🔍 Buscando metas de '{TERMO_BUSCA_META}'...")
    await filtrar_metas(page)

    metas = []
    linhas = page.locator('table tbody tr')
    count = await linhas.count()
    print(f"   [DEBUG] Linhas na tabela: {count} | URL: {page.url[:60]}")

    for i in range(count):
        linha = linhas.nth(i)
        colunas = linha.locator('td')
        n = await colunas.count()
        if n < 5:
            continue

        rep = await pegar_reprovados(colunas.nth(n - 2))
        if rep == 0:
            continue

        # Código da meta (5 dígitos)
        cod = ""
        for j in range(n):
            t = (await colunas.nth(j).inner_text()).strip()
            if t.isdigit() and len(t) == 5:
                cod = t
                break

        metas.append({"cod": cod, "rep": rep, "idx": i})
        print(f"   📌 Meta {cod} — {rep} reprovado(s)")

    return metas


async def pegar_reprovados(celula):
    """
    Lê o número de reprovados de uma célula Apr/Ana/Rep.
    O HTML tem 3 spans: '0 /' | azul '330' | vermelho '9'
    Pega o span com color:red ou o último span da célula.
    """
    # Tenta pelo span vermelho
    span_vermelho = celula.locator('span[style*="red"]')
    if await span_vermelho.count() > 0:
        txt = (await span_vermelho.first.inner_text()).strip()
        try:
            return int(txt)
        except:
            pass

    # Fallback: split por "/"
    txt = (await celula.inner_text()).strip().replace("\n", "")
    partes = txt.split("/")
    if len(partes) >= 3:
        try:
            return int(partes[2].strip())
        except:
            pass
    return 0


async def achar_tabela(page, keywords):
    """
    Encontra uma tabela pela aria-label dos th ou pelo id/role.
    keywords: lista de strings para buscar (ex: ["munic"], ["ufpa"])
    """
    # Tenta pelo id contendo keyword
    for kw in keywords:
        tbl = page.locator(f'table[id*="{kw}"], table[role="grid"]').first
        if await tbl.count() > 0:
            return tbl

    # Tenta pelo aria-label dos th
    tabelas = page.locator('table')
    nt = await tabelas.count()
    for t in range(nt):
        tbl = tabelas.nth(t)
        ths = tbl.locator('th')
        nth = await ths.count()
        for h in range(nth):
            aria = (await ths.nth(h).get_attribute("aria-label") or "").lower()
            inner = (await ths.nth(h).inner_text()).lower()
            texto = aria + " " + inner
            if any(kw.lower() in texto for kw in keywords):
                return tbl

    # Fallback: última tabela da página
    nt = await page.locator('table').count()
    if nt > 0:
        return page.locator('table').last
    return None


async def coletar_cidades(page):
    """Na página de uma meta, encontra a tabela de municípios e retorna cidades com reprovações."""
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass
    await page.wait_for_timeout(2000)
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except:
        pass
    await page.wait_for_timeout(800)

    tbl = await achar_tabela(page, ["munic", "município"])
    if tbl is None:
        return []

    cidades = []
    linhas = tbl.locator('tbody tr')
    count = await linhas.count()
    for i in range(count):
        linha = linhas.nth(i)
        colunas = linha.locator('td')
        n = await colunas.count()
        if n < 4:
            continue
        rep = await pegar_reprovados(colunas.nth(n - 2))
        if rep == 0:
            continue
        nome = (await colunas.nth(1).inner_text()).strip()
        cidades.append({"nome": nome, "rep": rep, "idx": i})
        print(f"      🏙️  {nome} — {rep} reprovado(s)")

    return cidades


async def clicar_olho_cidade(page, idx):
    """Clica no olho azul da linha idx na tabela de municípios."""
    for tentativa in range(3):
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except:
            pass
        await page.wait_for_timeout(1000 + tentativa * 500)

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(500)
        except:
            pass

        tbl = await achar_tabela(page, ["munic", "município"])
        if tbl is None:
            await page.wait_for_timeout(1000)
            continue

        linhas = tbl.locator('tbody tr')
        linhas_com_olho = []
        count = await linhas.count()
        for i in range(count):
            if await linhas.nth(i).locator('a.btn-primary').count() > 0:
                linhas_com_olho.append(i)


        if idx < len(linhas_com_olho):
            olho = linhas.nth(linhas_com_olho[idx]).locator('a.btn-primary')
            await olho.first.click(no_wait_after=True)
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except:
                pass
            await page.wait_for_timeout(800)
            return True

        # Não encontrou na tentativa atual, tenta de novo
        await page.wait_for_timeout(1000)

    return False


async def coletar_propriedades(page):
    """Na página de uma cidade, retorna propriedades com reprovações.
    Exibe 100 resultados e faz uma única passagem sem paginação."""
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass
    await page.wait_for_timeout(1000)

    # Aumenta exibição para 100
    try:
        sel = page.locator('select').first
        await sel.select_option("100")
        await page.wait_for_timeout(800)
    except:
        pass

    # Pega a tabela correta (Nome da UFPA)
    tbl = await achar_tabela(page, ["ufpa", "nome da ufpa", "nome"])
    if tbl is None:
        tbl = page.locator('table').last

    props = []
    linhas = tbl.locator('tbody tr')
    count = await linhas.count()

    for i in range(count):
        linha = linhas.nth(i)
        colunas = linha.locator('td')
        n = await colunas.count()
        if n < 4:
            continue
        rep = await pegar_reprovados(colunas.nth(n - 2))
        nome = (await colunas.nth(0).inner_text()).strip()
        if rep > 0:
            print(f"         📋 {nome} — {rep} reprovado(s)")
            props.append({"nome": nome, "rep": rep, "idx": i})

    return props


async def fechar_modal_se_aberto(page):
    """Fecha qualquer modal aberto antes de interagir com a página."""
    try:
        modal = page.locator('.modal.in, .modal.show, [role="dialog"]:visible')
        if await modal.count() > 0:
            fechar = page.locator('button:has-text("Fechar"), .modal .btn-default, .modal .close')
            if await fechar.count() > 0:
                await fechar.first.click(no_wait_after=True)
                await page.wait_for_timeout(500)
            else:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
    except:
        pass


async def coletar_execucoes_reprovadas(page, nome_prop):
    """
    Na página da UFPA, encontra a tabela Execução e lê os botões .btn-danger.
    Extrai Cód.UFPA, Cód.Execução, Data, Proprietária (quem tem Sim em Responsável) e Motivo.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass
    await page.wait_for_timeout(2000)

    await fechar_modal_se_aberto(page)

    # Código da UFPA — fallback caso o modal não carregue
    # O valor principal vem do modal (mais confiável)
    cod_ufpa = ""
    nome_ufpa = nome_prop
    try:
        import re
        txt_pagina = await page.locator('body').inner_text()
        match = re.search(r'\((\d{4,6})\)\s*[-–]\s*(.+)', txt_pagina)
        if match:
            cod_ufpa = match.group(1)
            nome_ufpa = match.group(2).split('\n')[0].strip()
    except:
        pass

    # Proprietária = integrante com "Sim" na coluna Responsável
    nome_proprietaria = ""
    try:
        tabelas = page.locator('table')
        nt_tbls = await tabelas.count()
        for t in range(nt_tbls):
            ths = await tabelas.nth(t).locator('th').all_inner_texts()
            ths_lower = " ".join(ths).lower()
            if "respons" in ths_lower and "parentesco" in ths_lower:
                resp_col = next((i for i, h in enumerate(ths) if "respons" in h.lower()), -1)
                nome_col = next((i for i, h in enumerate(ths) if "nome" in h.lower()), 0)
                if resp_col >= 0:
                    linhas_int = tabelas.nth(t).locator('tbody tr')
                    nl = await linhas_int.count()
                    for li in range(nl):
                        tds = linhas_int.nth(li).locator('td')
                        # Lê o texto da célula incluindo spans coloridos
                        resp_txt = (await tds.nth(resp_col).inner_text()).strip().lower()
                        if "sim" in resp_txt:
                            nome_proprietaria = (await tds.nth(nome_col).inner_text()).strip()
                            break
                break
    except:
        pass


    # Rola até a seção Execução para garantir que carregou
    try:
        execucao_header = page.locator('h3:has-text("Execução"), h4:has-text("Execução"), .panel-title:has-text("Execução")')
        if await execucao_header.count() > 0:
            await execucao_header.first.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)
        else:
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except:
                pass
            await page.wait_for_timeout(1000)
    except:
        pass

    # Aguarda btn-danger aparecer (até 10s) — tabela de execuções pode demorar
    for _ in range(10):
        if await page.locator('a.btn-danger, button.btn-danger').count() > 0:
            break
        await page.wait_for_timeout(1000)

    # Encontra tabela de Execução (tem cabeçalho "Cód. Execução")
    tabelas = page.locator('table')
    nt = await tabelas.count()
    tbl_exec = None
    for t in range(nt):
        ths_list = await tabelas.nth(t).locator('th').all_inner_texts()
        ths_str = " ".join(ths_list).lower()
        if "execu" in ths_str and "planejamento" in ths_str:
            tbl_exec = tabelas.nth(t)
            break
    if tbl_exec is None and nt > 0:
        tbl_exec = tabelas.last

    if tbl_exec is None:
        return []

    resultados = []
    linhas_loc = tbl_exec.locator('tbody tr')
    count = await linhas_loc.count()

    for i in range(count):
        linha = linhas_loc.nth(i)
        # Verifica se tem .btn-danger na linha
        btn_danger = linha.locator('a.btn-danger, button.btn-danger')
        if await btn_danger.count() == 0:
            continue

        colunas = linha.locator('td')
        textos = []
        nc = await colunas.count()
        for c in range(nc):
            textos.append((await colunas.nth(c).inner_text()).strip())

        # Colunas: Cód.Planejamento | Cód.Execução | Ano | Data Execução | Data Cadastro | ...
        cod_exec = textos[1] if len(textos) > 1 else ""
        data_exec = textos[3] if len(textos) > 3 else ""

        # Clica no balão para pegar o motivo
        motivo = ""
        cod_ufpa_modal = ""
        cod_exec_modal = ""
        try:
            # Fecha modal anterior se ainda estiver aberto
            try:
                if await page.locator('.modal.in').count() > 0:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(800)
            except:
                pass

            await btn_danger.first.click(no_wait_after=True)
            await page.wait_for_timeout(800)
            modal_body = page.locator('.modal-body').nth(0)

            # Aguarda até o Cód. Execução aparecer E ser diferente do cod_exec da tabela
            # (garante que o modal atualizou com os dados deste balão específico)
            txt_completo = ""
            for _ in range(30):
                txt_completo = (await modal_body.inner_text()).strip()
                linhas_modal = [l.strip() for l in txt_completo.split("\n") if l.strip()]
                cod_exec_idx = next((i for i, l in enumerate(linhas_modal) if "execu" in l.lower()), -1)
                if cod_exec_idx >= 0 and cod_exec_idx + 1 < len(linhas_modal):
                    proximo = linhas_modal[cod_exec_idx + 1].strip()
                    # Verifica se é número E bate com o cod_exec da linha da tabela
                    if proximo.isdigit() and proximo == cod_exec:
                        break
                await page.wait_for_timeout(500)

            # Extrai cod_ufpa, cod_exec e motivo do modal
            # Formato: ["Cód. UFPA:", "131737", "Cód. Execução:", "616817", "Avaliação:", "texto"]
            linhas_modal = [l.strip() for l in txt_completo.split("\n") if l.strip()]
            for idx_l, linha_m in enumerate(linhas_modal):
                if "ufpa" in linha_m.lower() and "cód" in linha_m.lower():
                    if idx_l + 1 < len(linhas_modal) and linhas_modal[idx_l + 1].isdigit():
                        cod_ufpa_modal = linhas_modal[idx_l + 1]
                elif "execu" in linha_m.lower() and "cód" in linha_m.lower():
                    if idx_l + 1 < len(linhas_modal) and linhas_modal[idx_l + 1].isdigit():
                        cod_exec_modal = linhas_modal[idx_l + 1]
                elif "avalia" in linha_m.lower():
                    if ":" in linha_m:
                        parte = linha_m.split(":", 1)[-1].strip()
                        if parte:
                            motivo = parte
                        elif idx_l + 1 < len(linhas_modal):
                            motivo = linhas_modal[idx_l + 1]
                    elif idx_l + 1 < len(linhas_modal):
                        motivo = linhas_modal[idx_l + 1]
                    break

            # Usa valores do modal se encontrados
            if cod_ufpa_modal:
                cod_ufpa = cod_ufpa_modal
            if cod_exec_modal:
                cod_exec = cod_exec_modal
        except Exception as e:
            print(f"         [MODAL ERRO] {e}")
        finally:
            try:
                fechar = page.locator('.modal.in button:has-text("Fechar")').first
                if await fechar.count() > 0:
                    await fechar.click(no_wait_after=True)
                else:
                    await page.keyboard.press("Escape")
                await page.wait_for_timeout(600)
                if await page.locator('.modal.in').count() > 0:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(400)
            except:
                pass

        resultados.append({
            "cod_execucao": cod_exec,
            "data_execucao": data_exec,
            "cod_ufpa": cod_ufpa,
            "nome_ufpa": nome_ufpa,
            "proprietaria": nome_proprietaria,
            "motivo": motivo
        })

    return resultados


# ─── main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  SGA ANATER — Verificador de Relatórios Reprovados")
    print("=" * 60)

    usuario = input("\nDigite seu CPF/usuário: ").strip()
    senha = input("Digite sua senha: ").strip()

    todos_reprovados = []
    inicio_total = datetime.now()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Login
            print("\n🔐 Fazendo login...")
            await page.goto(f"{BASE_URL}/pages/login.xhtml", timeout=120000)
            await page.wait_for_selector('input[placeholder*="números"]')
            await page.fill('input[placeholder*="números"]', usuario)
            await page.fill('input[placeholder*="Senha"]', senha)
            await page.click('button:has-text("ENTRAR"), .btn-login, button.btn',
                           no_wait_after=True, timeout=10000)

            # Aguarda sair da página de login (até 2 minutos)
            for _ in range(240):
                await page.wait_for_timeout(500)
                url_atual = page.url
                if "login" not in url_atual:
                    break

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass

            if "login" in page.url:
                raise Exception("Login falhou. Verifique usuário e senha.")
            print("✅ Login realizado com sucesso!")

            await navegar_para_painel(page)
            await abrir_metas(page)
            metas = await coletar_metas(page)

            if not metas:
                print("\n⚠️  Nenhuma meta com reprovações encontrada.")
                return

            print(f"\n📦 Total de metas com reprovações: {len(metas)}")

            # ── LOOP PRINCIPAL — permite voltar ao menu de metas ────
            continuar_programa = True
            while continuar_programa:

                # ── SELEÇÃO DE METAS ────────────────────────────────
                print(f"\n   Selecione as metas a processar:")
                for mi, meta in enumerate(metas):
                    print(f"     {mi+1}. Meta {meta['cod']} — {meta['rep']} reprovado(s)")
                print(f"     0. Todas")
                sel_meta = input("   Digite os números separados por vírgula (ex: 1,3) ou 0 para todas: ").strip()
                if sel_meta == "0" or sel_meta == "":
                    metas_selecionadas = list(metas)
                else:
                    indices = [int(x.strip())-1 for x in sel_meta.split(",") if x.strip().isdigit()]
                    metas_selecionadas = [metas[i] for i in indices if 0 <= i < len(metas)]
                # ────────────────────────────────────────────────────

                voltar_menu_metas = False
                for meta in metas_selecionadas:
                    if voltar_menu_metas:
                        break
                    cod_meta = meta["cod"]
                print(f"\n{'='*60}")
                print(f"🎯 Processando Meta {cod_meta}...")

                # Volta sempre do zero (URL dinâmica)
                await voltar_para_metas(page)
                tbl_meta = await achar_tabela(page, ["meta", "instrumento"])
                if tbl_meta is None:
                    tbl_meta = page.locator('table').last

                linhas_tbl = tbl_meta.locator('tbody tr')
                linhas_com_olho = []
                total = await linhas_tbl.count()
                for li in range(total):
                    if await linhas_tbl.nth(li).locator('a.btn-primary').count() > 0:
                        linhas_com_olho.append(li)

                if meta["idx"] < len(linhas_com_olho):
                    olho = linhas_tbl.nth(linhas_com_olho[meta["idx"]]).locator('a.btn-primary')
                    await olho.first.click(no_wait_after=True)
                else:
                    print(f"   ⚠️  Não encontrou olho da meta {cod_meta}")
                    continue
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except:
                    pass
                await page.wait_for_timeout(800)
                url_meta = page.url

                cidades = await coletar_cidades(page)
                print(f"   🏙️  Cidades com reprovações: {len(cidades)}")

                # ── SELEÇÃO DE CIDADES ──────────────────────────────
                def selecionar_cidades(cidades):
                    print(f"\n   Selecione as cidades a processar:")
                    for ci, cidade in enumerate(cidades):
                        print(f"     {ci+1}. {cidade['nome']} — {cidade['rep']} reprovado(s)")
                    print(f"     0. Todas")
                    sel = input("   Digite os números separados por vírgula (ex: 1,3) ou 0 para todas: ").strip()
                    if sel == "0" or sel == "":
                        return list(cidades), True  # True = todas selecionadas
                    indices = [int(x.strip())-1 for x in sel.split(",") if x.strip().isdigit()]
                    return [cidades[i] for i in indices if 0 <= i < len(cidades)], False

                cidades_selecionadas, todas_selecionadas = selecionar_cidades(cidades)
                # ────────────────────────────────────────────────────

                continuar_meta = True
                while continuar_meta and cidades_selecionadas:
                    cidade = cidades_selecionadas.pop(0)
                    inicio_cidade = datetime.now()
                    print(f"\n   📍 Processando cidade: {cidade['nome']}...")

                    # Refaz navegação completa até a meta e clica no olho da cidade
                    await voltar_para_metas(page)
                    tbl_m = await achar_tabela(page, ["meta", "instrumento"])
                    if tbl_m is None:
                        tbl_m = page.locator('table').last
                    linhas_m = tbl_m.locator('tbody tr')
                    olhos_m = []
                    for li in range(await linhas_m.count()):
                        if await linhas_m.nth(li).locator('a.btn-primary').count() > 0:
                            olhos_m.append(li)
                    if meta["idx"] < len(olhos_m):
                        await linhas_m.nth(olhos_m[meta["idx"]]).locator('a.btn-primary').first.click(no_wait_after=True)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=12000)
                    except:
                        pass
                    await page.wait_for_timeout(1000)

                    ok = await clicar_olho_cidade(page, cidade["idx"])
                    if not ok:
                        print(f"      ⚠️  Não conseguiu abrir cidade {cidade['nome']}")
                        continue

                    # Aumenta exibição
                    try:
                        sel = page.locator('select').first
                        await sel.select_option("100")
                        await page.wait_for_timeout(600)
                    except:
                        pass

                    props = await coletar_propriedades(page)
                    print(f"\n      🏡 Propriedades com reprovações: {len(props)}")

                    registros_cidade = []

                    for prop in props:
                        print(f"         🔍 {prop['nome']}...")

                        # Fecha modal se aberto
                        await fechar_modal_se_aberto(page)
                        await page.wait_for_timeout(300)

                        # Navega do zero para a cidade — mais confiável que Voltar
                        await voltar_para_metas(page)
                        # Clica na meta
                        tbl_m2 = await achar_tabela(page, ["meta", "instrumento"])
                        if tbl_m2 is None:
                            tbl_m2 = page.locator('table').last
                        linhas_m2 = tbl_m2.locator('tbody tr')
                        olhos_m2 = []
                        for li in range(await linhas_m2.count()):
                            if await linhas_m2.nth(li).locator('a.btn-primary').count() > 0:
                                olhos_m2.append(li)
                        if meta["idx"] < len(olhos_m2):
                            await linhas_m2.nth(olhos_m2[meta["idx"]]).locator('a.btn-primary').first.click(no_wait_after=True)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=12000)
                        except:
                            pass
                        await page.wait_for_timeout(800)

                        # Clica na cidade
                        ok2 = await clicar_olho_cidade(page, cidade["idx"])
                        if not ok2:
                            print(f"         ⚠️  Não conseguiu reabrir cidade {cidade['nome']}")
                            continue

                        # Aumenta exibição para ver todas as propriedades
                        try:
                            sel = page.locator('select').first
                            await sel.select_option("100")
                            await page.wait_for_timeout(600)
                        except:
                            pass

                        # Clica no olho da propriedade pelo índice
                        tbl_prop = await achar_tabela(page, ["ufpa", "nome da ufpa", "nome"])
                        if tbl_prop is None:
                            tbl_prop = page.locator('table').last

                        # Encontra as linhas com olho (btn-primary) na ordem
                        linhas_tbl = tbl_prop.locator('tbody tr')
                        olhos_prop = []
                        for li in range(await linhas_tbl.count()):
                            if await linhas_tbl.nth(li).locator('a.btn-primary').count() > 0:
                                olhos_prop.append(li)

                        if prop["idx"] < len(olhos_prop):
                            linha_alvo = linhas_tbl.nth(olhos_prop[prop["idx"]])
                            olho = linha_alvo.locator('a.btn-primary')
                            await olho.first.click(no_wait_after=True)
                            try:
                                await page.wait_for_load_state("networkidle", timeout=12000)
                            except:
                                pass
                            await page.wait_for_timeout(600)
                        else:
                            print(f"         ⚠️  Não encontrou olho de {prop['nome']}")
                            continue

                        execucoes = await coletar_execucoes_reprovadas(page, prop["nome"])

                        for ex in execucoes:
                            reg = {
                                "meta": cod_meta,
                                "cod_execucao": ex["cod_execucao"],
                                "cod_ufpa": ex.get("cod_ufpa", ""),
                                "nome_ufpa": ex.get("nome_ufpa", prop["nome"]),
                                "propriedade": prop["nome"],
                                "proprietaria": ex["proprietaria"],
                                "data_execucao": ex["data_execucao"],
                                "cidade": cidade["nome"],
                                "motivo": ex["motivo"]
                            }
                            registros_cidade.append(reg)
                            todos_reprovados.append(reg)

                    # Exibe tabela da cidade
                    if registros_cidade:
                        tabela_resultados(
                            registros_cidade,
                            f"Meta {cod_meta} — {cidade['nome']} ({len(registros_cidade)} reprovado(s))"
                        )
                    else:
                        print(f"      ℹ️  Nenhuma execução reprovada encontrada em {cidade['nome']}")

                    # Salva CSV parcial após cada cidade
                    if todos_reprovados:
                        import os
                        csv_path = os.path.join(os.path.expanduser("~"), "Downloads", "relatorios_reprovados.csv")
                        caminho = salvar_csv(todos_reprovados, csv_path)
                        elapsed = datetime.now() - inicio_cidade
                        minutos, segundos = divmod(int(elapsed.total_seconds()), 60)
                        tempo_str = f"{minutos}min {segundos}s" if minutos > 0 else f"{segundos}s"
                        print(f"      💾 CSV salvo: {len(todos_reprovados)} registro(s) — {caminho}")
                        print(f"      ⏱️  Tempo de processamento: {tempo_str}")

                    # Verifica se ainda há cidades para processar
                    if todas_selecionadas and cidades_selecionadas:
                        # Selecionou todas — continua automaticamente sem perguntar
                        continue

                    tem_proxima = len(cidades_selecionadas) > 0

                    if tem_proxima:
                        print(f"\n   O que deseja fazer agora?")
                        print(f"     1. Continuar para próxima cidade ({cidades_selecionadas[0]['nome']})")
                        print(f"     2. Voltar ao menu de cidades")
                        print(f"     3. Voltar ao menu de metas")
                        print(f"     4. Encerrar")
                        opcao = input("   Escolha: ").strip()
                        if opcao == "4":
                            raise KeyboardInterrupt("usuario_encerrou")
                        elif opcao == "3":
                            continuar_meta = False
                            voltar_menu_metas = True
                        elif opcao == "2":
                            cidades_selecionadas, todas_selecionadas = selecionar_cidades(cidades)
                        # opcao 1: continua o while normalmente
                    else:
                        # Não há mais cidades selecionadas
                        # Verifica se há outras cidades disponíveis na meta que não foram selecionadas
                        ha_mais_cidades = len(cidades) > 1 or (len(cidades) == 1 and cidades[0]['nome'] != cidade['nome'])
                        print(f"\n   ✅ Cidades selecionadas processadas.")
                        print(f"   O que deseja fazer agora?")
                        if ha_mais_cidades:
                            print(f"     1. Escolher outras cidades desta meta")
                            print(f"     2. Voltar ao menu de metas")
                            print(f"     3. Encerrar")
                            opcao = input("   Escolha: ").strip()
                            if opcao == "3":
                                raise KeyboardInterrupt("usuario_encerrou")
                            elif opcao == "1":
                                cidades_selecionadas, todas_selecionadas = selecionar_cidades(cidades)
                            else:  # opcao 2
                                continuar_meta = False
                                voltar_menu_metas = True
                        else:
                            print(f"     1. Voltar ao menu de metas")
                            print(f"     2. Encerrar")
                            opcao = input("   Escolha: ").strip()
                            if opcao == "2":
                                raise KeyboardInterrupt("usuario_encerrou")
                            else:
                                continuar_meta = False
                                voltar_menu_metas = True

        except KeyboardInterrupt:
            print("\n⏹️  Encerrando e salvando resultados...")
        except Exception as e:
            print(f"\n❌ Erro: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

    # Relatório final
    print("\n" + "=" * 60)
    print("  RELATÓRIO FINAL COMPLETO")
    print("=" * 60)
    if todos_reprovados:
        tabela_resultados(todos_reprovados, "Todas as execuções reprovadas")

        # Salva CSV
        import os
        csv_path = os.path.join(os.path.expanduser("~"), "Downloads", "relatorios_reprovados.csv")
        caminho = salvar_csv(todos_reprovados, csv_path)
        elapsed_total = datetime.now() - inicio_total
        min_t, seg_t = divmod(int(elapsed_total.total_seconds()), 60)
        tempo_total = f"{min_t}min {seg_t}s" if min_t > 0 else f"{seg_t}s"
        print(f"\n💾 CSV salvo em: {caminho}")
        print(f"⏱️  Tempo total de execução: {tempo_total}")
    else:
        print("\n⚠️  Nenhuma execução reprovada encontrada.")

    print("\n✅ Processo concluído!")


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from DrissionPage import Chromium, ChromiumOptions


@dataclass
class Result:
    """Resultado da navegação, com caminhos relativos dos arquivos de evidência."""
    url: str
    status_code: int | None = None
    title: str = ""
    final_url: str = ""
    elapsed: float = 0
    error: str = ""
    screenshot: str = ""
    snapshot: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and (self.status_code is None or 200 <= self.status_code < 300)


def read_urls(path: Path) -> list[str]:
    """Lê URLs HTTP(S), ignorando linhas vazias e comentários iniciados por #."""
    urls = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    urls = [f"https://{url}" if url.startswith("www.") else url for url in urls]
    urls = [url for url in urls if url and not url.startswith("#")]
    invalid = [url for url in urls if urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc]
    if invalid:
        raise ValueError("URL(s) HTTP(S) inválida(s): " + ", ".join(invalid))
    return urls


def check_url(tab, url: str, index: int, output: Path, timeout: float, settle: float, timestamp: str, report_name: str) -> Result:
    """Carrega uma URL e salva captura de tela e HTML renderizado."""
    result = Result(url=url)
    started = time.monotonic()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", report_name).strip("_") or "relatorio"
    stem = f"{slug}_{timestamp}_{index:04d}"
    try:
        loaded = tab.get(url, timeout=timeout)
        if not loaded:
            result.error = f"Tempo esgotado após {timeout:g}s aguardando o carregamento"
        else:
            time.sleep(settle)
    except Exception as exc:
        result.error = str(exc) or type(exc).__name__
    try:
        result.final_url = tab.url or ""
        result.title = tab.title or ""
        result.status_code = tab.run_js(
            "performance.getEntriesByType('navigation')[0]?.responseStatus ?? null"
        )
        if result.final_url.startswith("chrome-error://"):
            result.error = result.error or "Página de erro do navegador"
    except Exception as exc:
        result.error = result.error or str(exc) or type(exc).__name__
    try:
        tab.get_screenshot(path=str(output / "snapshots"), name=f"{stem}.png", full_page=True)
        result.screenshot = f"snapshots/{stem}.png"
    except Exception as exc:
        result.error = result.error or f"Falha ao capturar a tela: {exc}"
    try:
        result.snapshot = f"snapshots/{stem}.html"
        (output / result.snapshot).write_text(tab.html or "", encoding="utf-8")
    except Exception as exc:
        result.snapshot = ""
        result.error = result.error or f"Falha ao salvar o HTML renderizado: {exc}"
    if result.status_code is not None and not 200 <= result.status_code < 300:
        result.error = result.error or f"HTTP {result.status_code}"
    result.elapsed = time.monotonic() - started
    return result


def render_report(results: list[Result], generated_at: datetime | None = None, report_name: str = "urls", origin_location: str | None = None) -> str:
    """Gera o relatório HTML em português brasileiro."""
    rows = []
    for item in results:
        verdict = "APROVADO" if item.ok else "REPROVADO"
        snapshot_links = ""
        links = []
        if item.screenshot:
            links.append(f'<a href="{html.escape(item.screenshot)}">Captura de tela</a>')
        if item.snapshot:
            links.append(f'<a href="{html.escape(item.snapshot)}">HTML renderizado</a>')
        snapshot_links = " · ".join(links)
        rows.append(
            f"<tr class='{verdict.lower()}'><td>{verdict}</td>"
            f"<td><a href='{html.escape(item.final_url or item.url)}'>{html.escape(item.url)}</a>"
            f"<small>{html.escape(item.title)}</small></td><td>{item.elapsed:.2f}s</td>"
            f"<td>{html.escape(item.error)}</td><td>{snapshot_links}</td></tr>"
        )
    passed = sum(item.ok for item in results)
    generated_at = generated_at or datetime.now().astimezone()
    return f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(report_name)} — Relatório de disponibilidade de URLs</title>
<style>
body{{font:15px system-ui,sans-serif;margin:2rem;color:#222}}h1{{margin-bottom:.3rem}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.7rem;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}}th{{background:#f4f4f4}}.aprovado td:first-child{{color:#08752b;font-weight:bold}}.reprovado td:first-child{{color:#b42318;font-weight:bold}}small{{display:block;color:#666;margin-top:.25rem}}a{{overflow-wrap:anywhere}}
</style>
<h1>{html.escape(report_name)} — Relatório de disponibilidade de URLs</h1><p>{passed} de {len(results)} URLs aprovadas · Gerado em {generated_at.isoformat(timespec='seconds')}</p><p>Origem estimada da conexão: {html.escape(origin_location or 'Indisponível')}</p>
<table><thead><tr><th>Resultado</th><th>URL / título</th><th>Tempo de carregamento</th><th>Erro</th><th>Evidências</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></html>"""


def get_origin_location() -> str | None:
    """Consulta uma localização aproximada pelo IP público; falhas não interrompem a execução."""
    try:
        with urlopen("https://ipapi.co/json/", timeout=5) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            return None
        location = [data.get(key) for key in ("city", "region", "country_name")]
        parts = [part for part in location if isinstance(part, str) and part.strip()]
        return ", ".join(parts) or None
    except (OSError, ValueError):
        return None


def run(input_file: Path, output: Path, concurrency: int, timeout: float, settle: float, browser_path: str | None, show_browser: bool = False) -> int:
    """Executa as verificações em abas paralelas e grava o relatório."""
    urls = read_urls(input_file)
    generated_at = datetime.now().astimezone()
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    report_name = input_file.stem or "urls"
    origin_location = get_origin_location()
    output.mkdir(parents=True, exist_ok=True)
    (output / "snapshots").mkdir(exist_ok=True)
    if not urls:
        raise ValueError(f"Nenhuma URL encontrada em {input_file}")

    options = ChromiumOptions().headless(not show_browser).auto_port()
    if browser_path:
        options.set_browser_path(browser_path)
    browser = Chromium(addr_or_opts=options)
    tabs = [browser.new_tab() for _ in range(min(concurrency, len(urls)))]
    results: list[Result | None] = [None] * len(urls)
    try:
        def check_batch(tab, indexed_urls):
            return [(index, check_url(tab, url, index + 1, output, timeout, settle, timestamp, report_name)) for index, url in indexed_urls]

        batches = [list(enumerate(urls))[i::len(tabs)] for i in range(len(tabs))]
        with ThreadPoolExecutor(max_workers=len(tabs)) as pool:
            futures = [pool.submit(check_batch, tab, batch) for tab, batch in zip(tabs, batches)]
            for future in as_completed(futures):
                for index, item in future.result():
                    results[index] = item
                    print(f"{'APROVADO' if item.ok else 'REPROVADO'} {item.url} ({item.elapsed:.2f}s)")
    finally:
        browser.quit()

    final_results = [result for result in results if result is not None]
    (output / "index.html").write_text(render_report(final_results, generated_at, report_name, origin_location), encoding="utf-8")
    print(f"Relatório: {output / 'index.html'}")
    return 0 if all(item.ok for item in final_results) else 1


def main() -> None:
    """Analisa argumentos, executa a verificação e define o código de saída."""
    parser = argparse.ArgumentParser(description="Verifica URLs no Chromium e gera um relatório HTML.")
    parser.add_argument("input", nargs="?", type=Path, default=Path("urls.txt"), help="um URL HTTP(S) por linha (padrão: urls.txt)")
    parser.add_argument("--output", type=Path, default=Path("report"), help="pasta do relatório (padrão: report)")
    parser.add_argument("--concurrency", type=int, default=4, help="quantidade de abas do navegador (padrão: 4)")
    parser.add_argument("--timeout", type=float, default=30, help="tempo limite de carregamento, em segundos (padrão: 30)")
    parser.add_argument("--settle", type=float, default=1, help="espera após o carregamento, em segundos (padrão: 1)")
    parser.add_argument("--browser", help="caminho opcional do executável Chrome/Chromium")
    parser.add_argument("--show-browser", action="store_true", help="exibe a janela do navegador (padrão: headless)")
    args = parser.parse_args()
    if args.concurrency < 1 or args.timeout <= 0 or args.settle < 0:
        parser.error("a concorrência e o tempo limite devem ser positivos; a espera não pode ser negativa")
    try:
        sys.exit(run(args.input, args.output, args.concurrency, args.timeout, args.settle, args.browser, args.show_browser))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

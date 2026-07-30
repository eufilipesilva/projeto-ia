# -*- coding: utf-8 -*-
"""
Converte o relatório HTML para PDF.
Tenta weasyprint primeiro (melhor qualidade), depois pdfkit (requer wkhtmltopdf).
"""
import os
import sys

HTML_IN  = os.path.join(os.path.dirname(__file__), "relatorio_omnivoice_comunidade.html")
PDF_OUT  = os.path.join(os.path.dirname(__file__), "RELATORIO_OMNIVOICE_COMUNIDADE.pdf")

def tentar_weasyprint():
    try:
        from weasyprint import HTML
        print("Usando weasyprint...")
        HTML(filename=HTML_IN).write_pdf(PDF_OUT)
        return True
    except ImportError:
        print("weasyprint não instalado. Tentando instalar...")
        os.system(f'"{sys.executable}" -m pip install weasyprint -q')
        try:
            from weasyprint import HTML
            HTML(filename=HTML_IN).write_pdf(PDF_OUT)
            return True
        except Exception as e:
            print(f"weasyprint falhou: {e}")
            return False

def tentar_pdfkit():
    try:
        import pdfkit
        print("Usando pdfkit...")
        pdfkit.from_file(HTML_IN, PDF_OUT)
        return True
    except ImportError:
        print("pdfkit não instalado.")
        return False
    except Exception as e:
        print(f"pdfkit falhou: {e}")
        return False

def abrir_no_browser():
    import webbrowser
    url = "file:///" + HTML_IN.replace("\\", "/")
    webbrowser.open(url)
    print(f"\nAberto no navegador: {HTML_IN}")
    print("Para salvar como PDF: Ctrl+P → Salvar como PDF → Salvar")

if __name__ == "__main__":
    print(f"HTML fonte: {HTML_IN}")
    print(f"PDF destino: {PDF_OUT}\n")

    if tentar_weasyprint():
        print(f"\n✅ PDF gerado com sucesso: {PDF_OUT}")
        os.startfile(PDF_OUT)
    elif tentar_pdfkit():
        print(f"\n✅ PDF gerado com sucesso: {PDF_OUT}")
        os.startfile(PDF_OUT)
    else:
        print("\n⚠️  Não foi possível gerar o PDF automaticamente.")
        print("Alternativa: abrindo no navegador para você imprimir como PDF...")
        abrir_no_browser()

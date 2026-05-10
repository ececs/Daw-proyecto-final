from fpdf import FPDF
import datetime
import os

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 102, 204)
        self.cell(0, 10, 'D4LAB.ES - TECHNICAL DOCUMENTATION', 0, 1, 'C')
        self.set_draw_color(0, 102, 204)
        self.line(10, 20, 200, 20)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()} | Confidential | Auth Policy V1.2', 0, 0, 'C')

def generate_pdf():
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Metadata
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(0)
    pdf.cell(40, 10, 'Date:')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, datetime.date.today().strftime("%B %d, %Y"))
    pdf.ln(7)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(40, 10, 'Subject:')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, 'Technical Specs: Stateless Auth Deployment')
    pdf.ln(15)

    # Introduction
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, '1. Arquitectura de Seguridad Cross-Domain', 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(50)
    pdf.multi_cell(0, 6, (
        "Esta directiva técnica define el estándar corporativo para la autenticación federada "
        "entre el clúster backend (Python) y el ecosistema de microfrontends basado en Vercel/Next.js.\n\n"
        "Se prohíbe explícitamente el uso de Session State pegajoso (sticky sessions) en el balanceador, "
        "adoptando un modelo 100% basado en JSON Web Tokens firmados criptográficamente."
    ))
    pdf.ln(5)

    # JWT Specs
    pdf.set_font('Arial', 'B', 13)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, '2. Especificación del Token JWT (HS256)', 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(50)
    pdf.multi_cell(0, 6, (
        "El servidor central emitirá un token firmado con HMAC-SHA256. El payload debe contener "
        "estrictamente los siguientes campos estandarizados para interoperabilidad:\n"
    ))
    pdf.set_font('Courier', '', 10)
    pdf.set_fill_color(240, 240, 240)
    claims_text = (
        "{\n"
        '  "sub": "uuid-v4-user-identifier",\n'
        '  "iss": "api.d4lab.es",\n'
        '  "aud": "app.d4lab.es",\n'
        '  "exp": 1735689600,  // Timestamp UTC + 24 Horas máx\n'
        '  "role": ["admin", "operator"],\n'
        '  "provider": "google_sso"\n'
        "}"
    )
    pdf.multi_cell(0, 5, claims_text, 0, 'L', fill=True)
    pdf.ln(5)

    # Middleware
    pdf.set_font('Arial', 'B', 13)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, '3. Despliegue en el Edge (Next.js Middleware)', 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(50)
    pdf.multi_cell(0, 6, (
        "La validación del ciclo de vida del token no debe esperar al backend. Se utilizará "
        "la API nativa del Edge Runtime para verificar la firma del JWT antes de que el renderizado "
        "del servidor comience.\n\n"
        "Flujo Crítico:\n"
        "1. El usuario solicita /dashboard/overview.\n"
        "2. El Middleware detecta la cookie de sesión.\n"
        "3. Si exp < now(), el middleware retorna una 307 Temporary Redirect instantánea a /login.\n"
        "4. Si es válido, propaga el userId en los headers HTTP internos."
    ))
    pdf.ln(5)

    # Output
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'docs_private'))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'D4Lab_Stateless_Auth_Specs.pdf')
    
    pdf.output(output_path)
    print(f"PDF created successfully at: {output_path}")

if __name__ == '__main__':
    generate_pdf()

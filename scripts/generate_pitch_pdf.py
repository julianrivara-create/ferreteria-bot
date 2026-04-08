#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate Client Pitch PDF
-------------------------
Converts CLIENT_PITCH.md to a styled PDF using markdown and xhtml2pdf.
"""

import os
import re
from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        # Logo or Title on every page
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(128)
        self.cell(0, 10, 'Bot de Ventas - Documentación', 0, 1, 'R')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def convert_md_to_pdf(source_md, output_pdf):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    with open(source_md, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.rstrip()
        # Clean emojis (simple ascii check or replacement)
        line = line.encode('ascii', 'ignore').decode('ascii').strip()
        
        # Headers
        if line.startswith('# '):
            pdf.set_font('Helvetica', 'B', 24)
            pdf.set_text_color(44, 62, 80) # Dark Blue
            pdf.cell(0, 15, line[2:], 0, 1, 'L')
            pdf.ln(5)
        elif line.startswith('## '):
            pdf.set_font('Helvetica', 'B', 16)
            pdf.set_text_color(231, 76, 60) # Red
            pdf.ln(5)
            pdf.cell(0, 10, line[3:], 0, 1, 'L')
            pdf.line(pdf.get_x(), pdf.get_y(), 190, pdf.get_y())
            pdf.ln(2)
        elif line.startswith('### '):
            pdf.set_font('Helvetica', 'B', 14)
            pdf.set_text_color(41, 128, 185) # Blue
            pdf.ln(3)
            pdf.cell(0, 8, line[4:], 0, 1, 'L')
        
        # Lists
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(0)
            pdf.set_x(20) # Indent
            content = line.strip()[2:]
            # Bold handling (**text**) - simplified
            parts = re.split(r'(\*\*.*?\*\*)', content)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    pdf.set_font('Helvetica', 'B', 11)
                    pdf.write(5, part[2:-2])
                else:
                    pdf.set_font('Helvetica', '', 11)
                    pdf.write(5, part)
            pdf.ln(6)
            
        # Numbered Lists
        elif re.match(r'^\d+\.', line.strip()):
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(0)
            pdf.set_x(20)
            content = line.strip()
            pdf.write(5, content)
            pdf.ln(6)
            
        # Horizontal Rule
        elif line.startswith('---'):
            pdf.ln(5)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(5)
            
        # Paragraphs
        elif line.strip():
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(50)
            
            # Simple bold parsing for paragraphs
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    pdf.set_font('Helvetica', 'B', 11)
                    pdf.write(5, part[2:-2])
                else:
                    pdf.set_font('Helvetica', '', 11)
                    pdf.write(5, part)
            pdf.ln(6)
        
        else:
            pdf.ln(5) # Empty line
            
    pdf.output(output_pdf)
    print(f"✅ PDF generated successfully: {output_pdf}")

if __name__ == "__main__":
    source = "docs/CLIENT_PITCH.md"
    output = "docs/CLIENT_PITCH.pdf"
    
    if not os.path.exists(source):
        print(f"Error: {source} not found")
        exit(1)
        
    convert_md_to_pdf(source, output)

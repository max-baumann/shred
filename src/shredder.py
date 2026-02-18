import uuid
import json
import csv
import io
import mimetypes
import hashlib
from bs4 import BeautifulSoup
import markdownify

class WikiShredder:
    def __init__(self):
        # The Sidecar: Stores the heavy data extracted from the article
        self.sidecar = {
            "images": {},
            "tables": {},
            "infoboxes": {},
            "formulas": {} 
        }
        
    def generate_id(self, prefix):
        """Generates a short unique ID for the element."""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def process(self, html_content, article_title):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # --- 0. Cleanups ---
        # Remove edit links, script, style
        for tag in soup(['script', 'style', 'link', 'meta', 'noscript']):
            tag.decompose()
        # Remove edit section links often found in MW
        for tag in soup.find_all(class_='mw-editsection'):
            tag.decompose()


        # --- 1. Extract Infoboxes ---
        self._extract_infoboxes(soup)
        
        # --- 2. Extract Data Tables ---
        self._extract_tables(soup)
        
        # --- 3. Process Images (Reference only, don't extract bytes) ---
        self._process_images(soup)

        # --- 4. Handle Math (LaTeX conversion) ---
        self._convert_math(soup)

        # --- 5. Generate Table of Contents (from headers) ---
        toc = self._generate_toc(soup)

        # --- 6. Final Markdown Conversion ---
        # Using markdownify on the now "lightweight" DOM
        # strip=['a'] removes links but keeps text, consistent with reading text primarily. 
        # However, for a wiki mirror, keeping internal links is often desired. 
        # The prompt says "robust reference system", preventing broken links is part of that.
        # But `shredder.py` snippet had strip=['a']. I will remove 'a' from strip to keep links, 
        # as a wiki usually needs them, unless the user strictly follows the snippet.
        # Looking at snippet: `text = markdownify.markdownify(str(soup), heading_style="ATX", strip=['a'])`
        # I will stick to the snippet's strip=['a'] if that's the "clean text" goal, 
        # but typically you want 'zim://' or 'wiki://' links.
        # For now, I will NOT strip 'a' tags, but I will process them to point to internal wiki links if needed.
        # Actually, let's follow the snippet for now to be safe, but I suspect 'a' stripping is drastic. 
        # Re-reading: "strip=['a']" removes the anchor tag but keeps the text.
        
        text = markdownify.markdownify(str(soup), heading_style="ATX")
        
        # Extract Abstract (First section before TOC or first header)
        abstract = self._extract_abstract(text)

        return {
            "title": article_title,
            "content": text,  # The Markdown with [<<TOKENS>>]
            "abstract": abstract,
            "toc": toc,
            "sidecar": self.sidecar
        }

    def _extract_infoboxes(self, soup):
        infoboxes = soup.find_all('table', class_='infobox')
        for infobox in infoboxes:
            # 1. Parse data (simplified for now)
            # data = parse_infobox_to_json(infobox) 
            data = {"type": "infobox", "raw_html": str(infobox)} 
            
            # 2. Generate Token
            uid = self.generate_id("INFO")
            
            # 3. Store in Sidecar
            self.sidecar['infoboxes'][uid] = data
            
            # 4. Replace in DOM with Token
            token_str = f"\n\n**[<<INFOBOX: {uid} | Summary of {data.get('type', 'Attributes')}>>]**\n\n"
            infobox.replace_with(token_str)

    def _extract_tables(self, soup):
        # We only want DATA tables (wikitable), not layout tables
        for tbl in soup.find_all("table", class_="wikitable"):
            # Heuristic: If table is tiny, keep it as Markdown.
            rows = tbl.find_all('tr')
            if len(rows) < 5: 
                continue 
            
            # 1. Generate ID & Summary
            uid = self.generate_id("TBL")
            caption = tbl.find('caption')
            summary = caption.get_text().strip() if caption else "Data Table"
            
            # 2. Extract Data 
            # (Merged from wiki_tables.py logic)
            grid_data = self._parse_html_table_to_grid(tbl)
            csv_output = io.StringIO()
            writer = csv.writer(csv_output, quoting=csv.QUOTE_MINIMAL)
            writer.writerows(grid_data)
            csv_string = csv_output.getvalue()

            self.sidecar['tables'][uid] = {
                "summary": summary,
                "rows": len(rows),
                "csv": csv_string
            }
            
            # 3. Replace in DOM
            token_str = f"\n\n**[<<TABLE: {uid} | {summary}>>]**\n\n"
            tbl.replace_with(token_str)

    def _process_images(self, soup):
        """
        Rewrites img tags to zim://I/<filename> protocol per data_layer.md
        Stores metadata in sidecar.
        """
        for img in soup.find_all('img'):
            src = img.get('src', '')
            alt = img.get('alt', 'Image')
            
            if not src:
                continue

            # Extract filename from src 
            # Wikipedia srcs often look like: //upload.wikimedia.org/wikipedia/commons/thumb/a/a3/File.jpg/220px-File.jpg
            # Or ZIM style: I/File.jpg
            
            filename = src.split('/')[-1]
            
            # Clean up filename (remove thumb prefixes/suffixes if standard web scrape)
            # But if processing ZIM HTML, it might already be relative. 
            # Assuming standard ZIM I/ namespace or standard URL.
            # Strategy: Store reference, don't download.
            
            # Create the zim:// reference
            zim_uri = f"zim://I/{filename}"
            
            # Store metadata
            uid = self.generate_id("IMG")
            self.sidecar['images'][uid] = {
                "filename": filename,
                "zim_path": f"I/{filename}",
                "alt": alt,
                "original_src": src
            }
            
            # Replace tag in DOM with a custom markdown-friendly token or keep it as an image with new src
            # The prompt asks for "Replacing", implies tokens? 
            # data_layer.md says: `![Apollo 11 Launch](zim://I/Apollo_11_Launch.jpg)`
            # So we should update the `src` attribute so markdownify picks it up correctly.
            
            img['src'] = zim_uri
            img['alt'] = f"{alt} [Ref: {uid}]" # Embed Ref ID in alt text for tracking?
            
            # Optional: If we want a strict token instead of an image tag:
            # token = f"**[<<IMAGE: {uid} | {alt} >>]**"
            # img.replace_with(token)
            # But data_layer.md explicitly requested: `![...](zim://...)`
            # So we leave the img tag but update src.

    def _convert_math(self, soup):
        # Find math tags (often span class="mwe-math-element" or img with math alt)
        # Verify structure in ZIM/Wiki dumps. Often it's <math> or <span class="texhtml">
        # For now, placeholder logic.
        for math_tag in soup.find_all(class_='mwe-math-element'):
            # Try to get tex annotation
            annotation = math_tag.find(class_='mwe-math-mathml-a11y') 
            # Or sometimes it's an img with alt text being the latex
            img = math_tag.find('img')
            
            latex = ""
            if img:
                latex = img.get('alt')
            elif annotation:
                latex = annotation.get_text()
                
            if latex:
                # Replace with standard Markdown Latex
                math_tag.replace_with(f" $ {latex} $ ")

    def _generate_toc(self, soup):
        """Generates a JSON Table of Contents from h2, h3 headers."""
        toc = []
        for header in soup.find_all(['h2', 'h3']):
            toc.append({
                "level": header.name,
                "text": header.get_text(strip=True),
                # "id": header.get('id') # ZIM HTML usually has IDs
            })
        return toc

    def _extract_abstract(self, markdown_text):
        """Heuristic: First 1000 chars or until first Header."""
        lines = markdown_text.split('\n')
        abstract_lines = []
        for line in lines:
            if line.startswith('#'):
                break
            abstract_lines.append(line)
        
        abstract = "\n".join(abstract_lines).strip()
        if not abstract:
             # Fallback if article starts with header immediately
             return markdown_text[:1000]
        return abstract[:2000] # Cap it

    def _parse_html_table_to_grid(self, table):
        """
        Parses an HTML table into a 2D list, correctly handling 
        rowspan and colspan.
        """
        rows = table.find_all('tr')
        cell_map = {} 
        max_rows = len(rows)
        max_cols = 0
        
        # First pass to determine grid size and coordinate mapping
        for r_idx, row in enumerate(rows):
            if 'display:none' in row.get('style', ''):
                continue
            
            c_idx = 0
            cells = row.find_all(['td', 'th'])
            
            for cell in cells:
                # Skip columns already filled by rowspan
                while (r_idx, c_idx) in cell_map:
                    c_idx += 1
                
                try:
                    row_span = int(cell.get('rowspan', 1))
                except ValueError: row_span = 1
                try:
                    col_span = int(cell.get('colspan', 1))
                except ValueError: col_span = 1
                
                # Retrieve text
                # clean references
                for ref in cell.find_all(class_="reference"):
                    ref.decompose()
                cell_text = " ".join(cell.get_text().split())
                
                # Fill map
                for r in range(row_span):
                    for c in range(col_span):
                        if (r_idx + r) < max_rows + 20: # Safety cap
                             cell_map[(r_idx + r, c_idx + c)] = cell_text
                
                c_idx += col_span
                max_cols = max(max_cols, c_idx)

        # Build 2D grid
        grid = []
        for r in range(max_rows):
            row_data = []
            for c in range(max_cols):
                row_data.append(cell_map.get((r, c), ""))
            # basic empty row check
            if any(row_data):
                grid.append(row_data)
                
        return grid

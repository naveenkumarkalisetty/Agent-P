from playwright.async_api import async_playwright, Page, Browser
from typing import Optional, List, Dict, Any

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def start(self, url: str):
        if not self.browser:
            print("Booting Persistent Browser...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.page = await self.browser.new_page(viewport={'width': 1024, 'height': 768})
            await self.page.goto(url, wait_until="networkidle")

    async def extract_form_fields(self) -> List[Dict[str, Any]]:
        """
        Injects JavaScript into the already-open browser tab to map the inputs.
        """
        if not self.page:
            return []

        js_extraction_script = """
        () => {
            const elements = document.querySelectorAll('input, select, textarea');
            const fieldList = [];
            let index = 0;

            elements.forEach((el) => {
                const type = el.getAttribute('type') || '';
                if (['hidden', 'submit', 'button', 'image'].includes(type.toLowerCase())) {
                    return;
                }

                let labelText = '';
                if (el.id) {
                    const explicitLabel = document.querySelector(`label[for="${el.id}"]`);
                    if (explicitLabel) labelText = explicitLabel.innerText.trim();
                }
                
                if (!labelText) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) labelText = parentLabel.innerText.trim();
                }
                
                if (!labelText) {
                    labelText = el.getAttribute('aria-label') || 
                                el.getAttribute('placeholder') || 
                                el.getAttribute('name') || 
                                'Unlabeled Field';
                }

                // File inputs often have hidden or detached labels (like Greenhouse's Resume/CV field)
                if (type === 'file' && (!labelText || labelText === 'Unlabeled Field')) {
                    const container = el.closest('.field, .application-field, div[class*="field"], div[class*="container"]');
                    if (container) {
                        const lbl = container.querySelector('label, h3, h4, .text');
                        if (lbl) labelText = lbl.innerText.trim();
                    }
                    if (!labelText || labelText === 'Unlabeled Field') {
                        labelText = 'Resume/CV Upload';
                    }
                }

                labelText = labelText.replace(/\\s+/g, ' ').replace(/\\*$/, '').trim();

                let selector = '';
                if (el.id) {
                    selector = `#${el.id}`;
                } else if (el.getAttribute('name')) {
                    selector = `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]`;
                } else {
                    selector = `${el.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
                }

                let tagType = 'text';
                if (el.tagName.toLowerCase() === 'select') tagType = 'select';
                else if (el.tagName.toLowerCase() === 'textarea') tagType = 'textarea';
                else if (type === 'file') tagType = 'file';
                else if (type === 'checkbox') tagType = 'checkbox';
                else if (type === 'radio') tagType = 'radio';
                
                // Detect combobox/autocomplete inputs that behave like selects
                if (tagType === 'text') {
                    const hasAriaCombobox = 
                        el.getAttribute('role') === 'combobox' ||
                        el.getAttribute('aria-autocomplete') ||
                        el.getAttribute('aria-haspopup') === 'listbox' ||
                        el.getAttribute('list');
                    
                    // Check parent containers for autocomplete/select widget wrappers
                    const wrapper = el.closest('[class*="autocomplete"], [class*="select"], [class*="combobox"], [class*="dropdown"], [data-autocomplete]');
                    
                    // Check if there's a hidden <select> nearby in the same field container
                    const fieldContainer = el.closest('.field, .application-field, [class*="field"]');
                    const hiddenSelect = fieldContainer ? fieldContainer.querySelector('select') : null;
                    
                    if (hasAriaCombobox || wrapper || hiddenSelect) {
                        tagType = 'combobox';
                    }
                }

                fieldList.push({
                    id: `element_${index}`,
                    label: labelText,
                    type: tagType,
                    selector: selector,
                    value: null,
                    status: 'queued'
                });
                
                index++;
            });

            return fieldList;
        }
        """
        print("🔍 Scanning DOM in persistent browser...")
        extracted_fields = await self.page.evaluate(js_extraction_script)
        return extracted_fields

    async def get_screenshot_b64(self) -> str:
        if self.page:
            screenshot_bytes = await self.page.screenshot(type="jpeg", quality=50)
            import base64
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        return ""

    async def stop(self):
        if self.browser and self.playwright:
            await self.browser.close()
            await self.playwright.stop()
            self.browser = None
            self.page = None

# Global instance
browser_manager = BrowserManager()
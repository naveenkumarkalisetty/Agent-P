from playwright.async_api import async_playwright, Page, Browser
from typing import Optional, List, Dict, Any

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def start(self, url: str):
        if not self.browser:
            print("🌐 Booting Persistent Browser...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.page = await self.browser.new_page()
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
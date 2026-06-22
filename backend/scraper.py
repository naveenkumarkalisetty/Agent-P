import asyncio
from playwright.async_api import async_playwright
from typing import List, Dict, Any
async def extract_form_fields(url: str) -> List[Dict[str, Any]]:
    """
    Launches a headless browser, navigates to the target URL,
    and extracts a clean inventory of interactive form fields.
    """
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print(f"Navigating browser to target form: {url}")
        await page.goto(url, wait_until='networkidle', timeout=60000)

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
                // finding label for respective input element
                if (el.id) {
                    const explicitLabel = document.querySelector(`label[for="${el.id}"]`);
                    if (explicitLabel) {
                        labelText = explicitLabel.innerText.trim();
                    }
                }
                
                // If not found, look upward for an implicit wrapping <label> parent
                if (!labelText) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) {
                        labelText = parentLabel.innerText.trim();
                    }
                }
                
                // Fall back to aria-label, placeholder, or HTML name attribute
                if (!labelText) {
                    labelText = el.getAttribute('aria-label') || 
                                el.getAttribute('placeholder') || 
                                el.getAttribute('name') || 
                                'Unlabeled Field';
                }

                // Clean up multi-line labels or trailing asterisks commonly found on required fields
                labelText = labelText.replace(/\\s+/g, ' ').replace(/\\*$/, '').trim();

                // 2. Build a highly reliable CSS selector for Playwright targeting
                let selector = '';
                if (el.id) {
                    selector = `#${el.id}`;
                } else if (el.getAttribute('name')) {
                    selector = `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]`;
                } else {
                    // Fail-safe positional structural fallback if attributes are missing
                    selector = `${el.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
                }

                // Determine programmatic element tag type
                let tagType = 'text';
                if (el.tagName.toLowerCase() === 'select') {
                    tagType = 'select';
                } else if (el.tagName.toLowerCase() === 'textarea') {
                    tagType = 'textarea';
                } else if (type === 'file') {
                    tagType = 'file';
                } else if (type === 'checkbox') {
                    tagType = 'checkbox';
                } else if (type === 'radio') {
                    tagType = 'radio';
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
        print("Executing layout analysis script inside target page context...")
        extracted_fields = await page.evaluate(js_extraction_script)
        await browser.close()
        print(f"Successfully mapped {len(extracted_fields)} structural from fields.")
        return extracted_fields

if __name__ == '__main__':
    target_url = "https://job-boards.greenhouse.io/thinkingmachines/jobs/5111543008"
    
    discovered_fields = asyncio.run(extract_form_fields(target_url))
    
    print("\n--- FIRST 5 EXTRACTED FIELDS SAMPLE ---")
    for field in discovered_fields[:5]:
        print(f"ID: {field['id']} | Label: {field['label']} | Type: {field['type']} | Selector: {field['selector']}")

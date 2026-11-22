export default defineContentScript({
  matches: ['https://solutions.sciquest.com/apps/Router/*'],
  main() {
    console.log('CruzBuy Extraction Script Active.');

    // ─── Product Title Extraction (existing, unchanged) ───
    function extractTitles(): string[] {
      const tiles = [...document.querySelectorAll("article")];
      const items = tiles.length
        ? tiles
        : [...document.querySelectorAll("[data-record-id]")];
        
      const titles = items.map(tile => {
        const a = tile.querySelector("a[title]");
        if (a) return a.getAttribute("title")?.trim();

        const a2 = tile.querySelector("a[class*='desc']");
        if (a2) return a2.textContent?.trim();

        const img = tile.querySelector("img[alt]") as HTMLImageElement | null;
        if (img) return img.alt.replace(/\s*\(opens.*\)\s*$/, "").trim();

        const btn = tile.querySelector("button[aria-label*='Add to Cart']");
        const m = btn?.getAttribute("aria-label")?.match(/\((.+)\)/);
        if (m) return m[1];

        return null;
      }).filter((t): t is string => Boolean(t));

      return titles;
    }

    // ─── Search Term Extraction (new) ───
    function extractSearchTerm(): string | null {
      // 1) #megaSearch — the framework binds JS to this ID
      //    (Material.Autocomplete.create('megaSearch', ...))
      const mega = document.getElementById("megaSearch") as HTMLInputElement | null;
      if (mega && mega.value.trim()) return mega.value.trim();

      // 2) input[name="Keywords"] — form field name used in POST
      const named = document.querySelector("input[name='Keywords']") as HTMLInputElement | null;
      if (named && named.value.trim()) return named.value.trim();

      // 3) input[type="search"] — HTML5 semantic type
      const searchType = document.querySelector("input[type='search']") as HTMLInputElement | null;
      if (searchType && searchType.value.trim()) return searchType.value.trim();

      // 4) input[aria-label*="Search"] — accessibility attribute
      const aria = document.querySelector("input[aria-label*='Search']") as HTMLInputElement | null;
      if (aria && aria.value.trim()) return aria.value.trim();

      // 5) #ShopAtTop_panel input — parent panel ID
      const panel = document.getElementById("ShopAtTop_panel");
      const panelInput = panel?.querySelector("input") as HTMLInputElement | null;
      if (panelInput && panelInput.value.trim()) return panelInput.value.trim();

      return null;
    }

    // ─── Storage Update (modified) ───
    async function updateStorage(titles: string[]) {
      const searchTerm = extractSearchTerm() ?? '';

      const data = await browser.storage.local.get('extracted_products');
      const existing = data.extracted_products as { search: string; items: string[] } | undefined;

      // If search term changed (or no prior data), reset the list
      if (!existing || existing.search !== searchTerm) {
        await browser.storage.local.set({
          extracted_products: { search: searchTerm, items: titles }
        });
        console.log(`New search "${searchTerm}": ${titles.length} product(s)`);
        return;
      }

      // Same search → merge (infinite scroll case)
      const existingItems = new Set<string>(existing.items);
      let changed = false;
      titles.forEach(t => {
        if (!existingItems.has(t)) {
          existingItems.add(t);
          changed = true;
        }
      });

      if (changed) {
        await browser.storage.local.set({
          extracted_products: { search: searchTerm, items: Array.from(existingItems) }
        });
        console.log(`Appended items. "${searchTerm}": ${existingItems.size} total`);
      }
    }

    // ─── Initial run ───
    const initialTitles = extractTitles();
    if (initialTitles.length > 0) {
      updateStorage(initialTitles).then(() => checkRelevanceNow());
    }

    async function checkRelevanceNow() {
      const data = await browser.storage.local.get(['extracted_products', 'idToken']);
      const stored = data.extracted_products as { search: string; items: string[] } | undefined;
      const token = data.idToken as string | undefined;
      const search = stored?.search ?? '';
      const items = stored?.items ?? [];
      if (!search || items.length === 0) {
        console.warn('[CruzBuy] No search/products to check.');
        return;
      }
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const res = await fetch('http://localhost:8000/api/relevance', {
          method: 'POST',
          headers,
          body: JSON.stringify({ search, items }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const result = await res.json();
        // ... rest unchanged
      } catch (err) {
        console.error('[CruzBuy] Relevance check failed:', err);
      }
    }

    (window as any).__checkRelevance = checkRelevanceNow;

    // ─── MutationObserver (infinite scroll / pagination) ───
    const observer = new MutationObserver(async () => {
      const newTitles = extractTitles();
      if (newTitles.length > 0) {
        try {
          await updateStorage(newTitles);
        } catch (err) {
          console.error("Failed to update storage during mutation:", err);
        }
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  },
});

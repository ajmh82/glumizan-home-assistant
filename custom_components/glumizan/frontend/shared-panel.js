class GluMizanSharedPanel extends HTMLElement {
  set hass(hass) { this._hass = hass; this._load(); }
  connectedCallback() { this._render(); }
  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true; this._render();
    try { this._context = await this._hass.callApi("POST", "glumizan/shared-viewer-context", {}); }
    catch (_error) { this._context = { exposureMode: null, patients: [] }; }
    finally { this._loading = false; this._render(); }
  }
  _render() {
    const language = this._hass?.language || "en";
    const arabic = language.startsWith("ar");
    const title = arabic ? "جلوميزان" : "GluMizan";
    const empty = arabic ? "لا توجد بيانات مشتركة متاحة لهذا الحساب." : "No shared data is available for this account.";
    const loading = arabic ? "جارٍ التحميل…" : "Loading…";
    const patients = Array.isArray(this._context?.patients) ? this._context.patients : [];
    const cards = patients.map((patient) => {
      const label = patient.label === "SELF" ? (arabic ? "بياناتي" : "My glucose") : this._escape(patient.label || "GluMizan");
      const glucose = patient.glucose;
      const value = glucose ? `${this._escape(String(glucose.value))} ${this._escape(glucose.unit)}` : (arabic ? "لا توجد قراءة حديثة" : "No current reading");
      const measured = glucose?.measuredAt ? new Intl.DateTimeFormat(language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(glucose.measuredAt)) : "";
      return `<article><h2>${label}</h2><p class="value">${value}</p><p>${this._escape(measured)}</p></article>`;
    }).join("");
    this.innerHTML = `<style>:host{display:block;max-width:760px;margin:0 auto;padding:24px;font-family:var(--primary-font-family,sans-serif)}h1{margin:0 0 20px}article{border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:16px;margin:12px 0;background:var(--card-background-color,#fff)}h2{font-size:1rem;margin:0 0 8px}.value{font-size:1.7rem;font-weight:600;margin:0 0 6px}p{color:var(--secondary-text-color,#666);margin:0}</style><h1>${title}</h1>${this._loading ? `<p>${loading}</p>` : cards || `<p>${empty}</p>`}`;
  }
  _escape(value) { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; }
}
customElements.define("glumizan-shared-panel", GluMizanSharedPanel);

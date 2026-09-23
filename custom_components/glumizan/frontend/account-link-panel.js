const REQUEST_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const COPY = {
  ar: {
    loading: "جارٍ التحقق من طلب الربط…",
    title: "ربط حساب جلوميزان",
    pending: "هل تريد ربط حساب جلوميزان بحساب Home Assistant الذي تستخدمه الآن؟",
    confirm: "تأكيد الربط",
    cancel: "إلغاء",
    linked: "تم ربط الحساب بنجاح.",
    expired: "انتهت صلاحية طلب الربط. ارجع إلى جلوميزان وحاول مرة أخرى.",
    unavailable: "طلب الربط غير متاح.",
    empty: "لا يوجد طلب ربط بانتظار التأكيد.",
  },
  en: {
    loading: "Checking the account link request…",
    title: "Connect GluMizan account",
    pending: "Connect this GluMizan account to the Home Assistant account you are using now?",
    confirm: "Confirm",
    cancel: "Cancel",
    linked: "Account linked successfully.",
    expired: "This link request has expired. Return to GluMizan and try again.",
    unavailable: "This account link request is not available.",
    empty: "No account link request is awaiting confirmation.",
  },
};

class GlumizanAccountLinkPanel extends HTMLElement {
  set hass(value) {
    this._hass = value;
    if (!this._started) {
      this._started = true;
      this._load();
    }
  }

  connectedCallback() {
    this._render();
  }

  _language() {
    return this._hass?.locale?.language?.toLowerCase().startsWith("ar") ? "ar" : "en";
  }

  _requestId() {
    const requestId = new URLSearchParams(window.location.search).get("request");
    return requestId && REQUEST_ID.test(requestId) ? requestId : null;
  }

  async _load() {
    this._requestIdValue = this._requestId();
    if (!this._requestIdValue) {
      this._state = "empty";
      this._render();
      return;
    }
    this._state = "loading";
    this._render();
    try {
      const response = await this._hass.callApi("GET", `glumizan/account-link/${this._requestIdValue}`);
      this._state = response?.status === "PENDING" ? "pending" : "unavailable";
    } catch (error) {
      this._state = error?.status === 410 ? "expired" : "unavailable";
    }
    this._render();
  }

  async _submit(action) {
    if (!this._requestIdValue || !this._hass) return;
    this._state = "loading";
    this._render();
    try {
      const response = await this._hass.callApi("POST", `glumizan/account-link/${this._requestIdValue}/${action}`, {});
      this._state = action === "complete" && response?.status === "LINKED" ? "linked"
        : action === "cancel" && response?.status === "CANCELLED" ? "unavailable"
          : "unavailable";
    } catch (error) {
      this._state = error?.status === 410 ? "expired" : "unavailable";
    }
    this._render();
  }

  _render() {
    const language = this._language();
    const copy = COPY[language];
    const state = this._state || "loading";
    const root = document.createElement("section");
    root.dir = language === "ar" ? "rtl" : "ltr";
    root.style.cssText = "max-width:560px;margin:48px auto;padding:28px;border-radius:12px;background:var(--card-background-color);color:var(--primary-text-color);font:var(--paper-font-body1_-_font-family);box-shadow:var(--ha-card-box-shadow,none);text-align:start;";
    const title = document.createElement("h1");
    title.textContent = copy.title;
    root.append(title);
    const message = document.createElement("p");
    message.textContent = copy[state] || copy.unavailable;
    root.append(message);
    if (state === "pending") {
      const actions = document.createElement("div");
      actions.style.cssText = "display:flex;gap:12px;margin-top:24px;";
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.textContent = copy.confirm;
      confirm.addEventListener("click", () => this._submit("complete"));
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = copy.cancel;
      cancel.addEventListener("click", () => this._submit("cancel"));
      actions.append(confirm, cancel);
      root.append(actions);
    }
    this.replaceChildren(root);
  }
}

customElements.define("glumizan-account-link-panel", GlumizanAccountLinkPanel);

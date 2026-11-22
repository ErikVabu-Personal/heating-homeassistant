(function () {
    'use strict';

    /**
     * @license
     * Copyright 2019 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     */
    const t$1=globalThis,e$2=t$1.ShadowRoot&&(void 0===t$1.ShadyCSS||t$1.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s$2=Symbol(),o$3=new WeakMap;let n$2 = class n{constructor(t,e,o){if(this._$cssResult$=true,o!==s$2)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e;}get styleSheet(){let t=this.o;const s=this.t;if(e$2&&void 0===t){const e=void 0!==s&&1===s.length;e&&(t=o$3.get(s)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),e&&o$3.set(s,t));}return t}toString(){return this.cssText}};const r$2=t=>new n$2("string"==typeof t?t:t+"",void 0,s$2),i$3=(t,...e)=>{const o=1===t.length?t[0]:e.reduce((e,s,o)=>e+(t=>{if(true===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+t[o+1],t[0]);return new n$2(o,t,s$2)},S$1=(s,o)=>{if(e$2)s.adoptedStyleSheets=o.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const e of o){const o=document.createElement("style"),n=t$1.litNonce;void 0!==n&&o.setAttribute("nonce",n),o.textContent=e.cssText,s.appendChild(o);}},c$2=e$2?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const s of t.cssRules)e+=s.cssText;return r$2(e)})(t):t;

    /**
     * @license
     * Copyright 2017 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     */const{is:i$2,defineProperty:e$1,getOwnPropertyDescriptor:h$1,getOwnPropertyNames:r$1,getOwnPropertySymbols:o$2,getPrototypeOf:n$1}=Object,a$1=globalThis,c$1=a$1.trustedTypes,l$1=c$1?c$1.emptyScript:"",p$1=a$1.reactiveElementPolyfillSupport,d$1=(t,s)=>t,u$1={toAttribute(t,s){switch(s){case Boolean:t=t?l$1:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t);}return t},fromAttribute(t,s){let i=t;switch(s){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t);}catch(t){i=null;}}return i}},f$1=(t,s)=>!i$2(t,s),b$1={attribute:true,type:String,converter:u$1,reflect:false,useDefault:false,hasChanged:f$1};Symbol.metadata??=Symbol("metadata"),a$1.litPropertyMetadata??=new WeakMap;let y$1 = class y extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t);}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,s=b$1){if(s.state&&(s.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((s=Object.create(s)).wrapped=true),this.elementProperties.set(t,s),!s.noAccessor){const i=Symbol(),h=this.getPropertyDescriptor(t,i,s);void 0!==h&&e$1(this.prototype,t,h);}}static getPropertyDescriptor(t,s,i){const{get:e,set:r}=h$1(this.prototype,t)??{get(){return this[s]},set(t){this[s]=t;}};return {get:e,set(s){const h=e?.call(this);r?.call(this,s),this.requestUpdate(t,h,i);},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??b$1}static _$Ei(){if(this.hasOwnProperty(d$1("elementProperties")))return;const t=n$1(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties);}static finalize(){if(this.hasOwnProperty(d$1("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(d$1("properties"))){const t=this.properties,s=[...r$1(t),...o$2(t)];for(const i of s)this.createProperty(i,t[i]);}const t=this[Symbol.metadata];if(null!==t){const s=litPropertyMetadata.get(t);if(void 0!==s)for(const[t,i]of s)this.elementProperties.set(t,i);}this._$Eh=new Map;for(const[t,s]of this.elementProperties){const i=this._$Eu(t,s);void 0!==i&&this._$Eh.set(i,t);}this.elementStyles=this.finalizeStyles(this.styles);}static finalizeStyles(s){const i=[];if(Array.isArray(s)){const e=new Set(s.flat(1/0).reverse());for(const s of e)i.unshift(c$2(s));}else void 0!==s&&i.push(c$2(s));return i}static _$Eu(t,s){const i=s.attribute;return  false===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev();}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this));}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.();}removeController(t){this._$EO?.delete(t);}_$E_(){const t=new Map,s=this.constructor.elementProperties;for(const i of s.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t);}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return S$1(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.());}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.());}attributeChangedCallback(t,s,i){this._$AK(t,i);}_$ET(t,s){const i=this.constructor.elementProperties.get(t),e=this.constructor._$Eu(t,i);if(void 0!==e&&true===i.reflect){const h=(void 0!==i.converter?.toAttribute?i.converter:u$1).toAttribute(s,i.type);this._$Em=t,null==h?this.removeAttribute(e):this.setAttribute(e,h),this._$Em=null;}}_$AK(t,s){const i=this.constructor,e=i._$Eh.get(t);if(void 0!==e&&this._$Em!==e){const t=i.getPropertyOptions(e),h="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:u$1;this._$Em=e;const r=h.fromAttribute(s,t.type);this[e]=r??this._$Ej?.get(e)??r,this._$Em=null;}}requestUpdate(t,s,i,e=false,h){if(void 0!==t){const r=this.constructor;if(false===e&&(h=this[t]),i??=r.getPropertyOptions(t),!((i.hasChanged??f$1)(h,s)||i.useDefault&&i.reflect&&h===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,i))))return;this.C(t,s,i);} false===this.isUpdatePending&&(this._$ES=this._$EP());}C(t,s,{useDefault:i,reflect:e,wrapped:h},r){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??s??this[t]),true!==h||void 0!==r)||(this._$AL.has(t)||(this.hasUpdated||i||(s=void 0),this._$AL.set(t,s)),true===e&&this._$Em!==t&&(this._$Eq??=new Set).add(t));}async _$EP(){this.isUpdatePending=true;try{await this._$ES;}catch(t){Promise.reject(t);}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,s]of this._$Ep)this[t]=s;this._$Ep=void 0;}const t=this.constructor.elementProperties;if(t.size>0)for(const[s,i]of t){const{wrapped:t}=i,e=this[s];true!==t||this._$AL.has(s)||void 0===e||this.C(s,void 0,i,e);}}let t=false;const s=this._$AL;try{t=this.shouldUpdate(s),t?(this.willUpdate(s),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(s)):this._$EM();}catch(s){throw t=false,this._$EM(),s}t&&this._$AE(s);}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t);}_$EM(){this._$AL=new Map,this.isUpdatePending=false;}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return  true}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM();}updated(t){}firstUpdated(t){}};y$1.elementStyles=[],y$1.shadowRootOptions={mode:"open"},y$1[d$1("elementProperties")]=new Map,y$1[d$1("finalized")]=new Map,p$1?.({ReactiveElement:y$1}),(a$1.reactiveElementVersions??=[]).push("2.1.2");

    /**
     * @license
     * Copyright 2017 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     */
    const t=globalThis,i$1=t=>t,s$1=t.trustedTypes,e=s$1?s$1.createPolicy("lit-html",{createHTML:t=>t}):void 0,h="$lit$",o$1=`lit$${Math.random().toFixed(9).slice(2)}$`,n="?"+o$1,r=`<${n}>`,l=document,c=()=>l.createComment(""),a=t=>null===t||"object"!=typeof t&&"function"!=typeof t,u=Array.isArray,d=t=>u(t)||"function"==typeof t?.[Symbol.iterator],f="[ \t\n\f\r]",v=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,_=/-->/g,m=/>/g,p=RegExp(`>|${f}(?:([^\\s"'>=/]+)(${f}*=${f}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),g=/'/g,$=/"/g,y=/^(?:script|style|textarea|title)$/i,x=t=>(i,...s)=>({_$litType$:t,strings:i,values:s}),b=x(1),w=x(2),E=Symbol.for("lit-noChange"),A=Symbol.for("lit-nothing"),C=new WeakMap,P=l.createTreeWalker(l,129);function V(t,i){if(!u(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==e?e.createHTML(i):i}const N=(t,i)=>{const s=t.length-1,e=[];let n,l=2===i?"<svg>":3===i?"<math>":"",c=v;for(let i=0;i<s;i++){const s=t[i];let a,u,d=-1,f=0;for(;f<s.length&&(c.lastIndex=f,u=c.exec(s),null!==u);)f=c.lastIndex,c===v?"!--"===u[1]?c=_:void 0!==u[1]?c=m:void 0!==u[2]?(y.test(u[2])&&(n=RegExp("</"+u[2],"g")),c=p):void 0!==u[3]&&(c=p):c===p?">"===u[0]?(c=n??v,d=-1):void 0===u[1]?d=-2:(d=c.lastIndex-u[2].length,a=u[1],c=void 0===u[3]?p:'"'===u[3]?$:g):c===$||c===g?c=p:c===_||c===m?c=v:(c=p,n=void 0);const x=c===p&&t[i+1].startsWith("/>")?" ":"";l+=c===v?s+r:d>=0?(e.push(a),s.slice(0,d)+h+s.slice(d)+o$1+x):s+o$1+(-2===d?i:x);}return [V(t,l+(t[s]||"<?>")+(2===i?"</svg>":3===i?"</math>":"")),e]};class S{constructor({strings:t,_$litType$:i},e){let r;this.parts=[];let l=0,a=0;const u=t.length-1,d=this.parts,[f,v]=N(t,i);if(this.el=S.createElement(f,e),P.currentNode=this.el.content,2===i||3===i){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes);}for(;null!==(r=P.nextNode())&&d.length<u;){if(1===r.nodeType){if(r.hasAttributes())for(const t of r.getAttributeNames())if(t.endsWith(h)){const i=v[a++],s=r.getAttribute(t).split(o$1),e=/([.?@])?(.*)/.exec(i);d.push({type:1,index:l,name:e[2],strings:s,ctor:"."===e[1]?I:"?"===e[1]?L:"@"===e[1]?z:H}),r.removeAttribute(t);}else t.startsWith(o$1)&&(d.push({type:6,index:l}),r.removeAttribute(t));if(y.test(r.tagName)){const t=r.textContent.split(o$1),i=t.length-1;if(i>0){r.textContent=s$1?s$1.emptyScript:"";for(let s=0;s<i;s++)r.append(t[s],c()),P.nextNode(),d.push({type:2,index:++l});r.append(t[i],c());}}}else if(8===r.nodeType)if(r.data===n)d.push({type:2,index:l});else {let t=-1;for(;-1!==(t=r.data.indexOf(o$1,t+1));)d.push({type:7,index:l}),t+=o$1.length-1;}l++;}}static createElement(t,i){const s=l.createElement("template");return s.innerHTML=t,s}}function M(t,i,s=t,e){if(i===E)return i;let h=void 0!==e?s._$Co?.[e]:s._$Cl;const o=a(i)?void 0:i._$litDirective$;return h?.constructor!==o&&(h?._$AO?.(false),void 0===o?h=void 0:(h=new o(t),h._$AT(t,s,e)),void 0!==e?(s._$Co??=[])[e]=h:s._$Cl=h),void 0!==h&&(i=M(t,h._$AS(t,i.values),h,e)),i}class R{constructor(t,i){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=i;}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:i},parts:s}=this._$AD,e=(t?.creationScope??l).importNode(i,true);P.currentNode=e;let h=P.nextNode(),o=0,n=0,r=s[0];for(;void 0!==r;){if(o===r.index){let i;2===r.type?i=new k(h,h.nextSibling,this,t):1===r.type?i=new r.ctor(h,r.name,r.strings,this,t):6===r.type&&(i=new Z(h,this,t)),this._$AV.push(i),r=s[++n];}o!==r?.index&&(h=P.nextNode(),o++);}return P.currentNode=l,e}p(t){let i=0;for(const s of this._$AV) void 0!==s&&(void 0!==s.strings?(s._$AI(t,s,i),i+=s.strings.length-2):s._$AI(t[i])),i++;}}class k{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,i,s,e){this.type=2,this._$AH=A,this._$AN=void 0,this._$AA=t,this._$AB=i,this._$AM=s,this.options=e,this._$Cv=e?.isConnected??true;}get parentNode(){let t=this._$AA.parentNode;const i=this._$AM;return void 0!==i&&11===t?.nodeType&&(t=i.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,i=this){t=M(this,t,i),a(t)?t===A||null==t||""===t?(this._$AH!==A&&this._$AR(),this._$AH=A):t!==this._$AH&&t!==E&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):d(t)?this.k(t):this._(t);}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t));}_(t){this._$AH!==A&&a(this._$AH)?this._$AA.nextSibling.data=t:this.T(l.createTextNode(t)),this._$AH=t;}$(t){const{values:i,_$litType$:s}=t,e="number"==typeof s?this._$AC(t):(void 0===s.el&&(s.el=S.createElement(V(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===e)this._$AH.p(i);else {const t=new R(e,this),s=t.u(this.options);t.p(i),this.T(s),this._$AH=t;}}_$AC(t){let i=C.get(t.strings);return void 0===i&&C.set(t.strings,i=new S(t)),i}k(t){u(this._$AH)||(this._$AH=[],this._$AR());const i=this._$AH;let s,e=0;for(const h of t)e===i.length?i.push(s=new k(this.O(c()),this.O(c()),this,this.options)):s=i[e],s._$AI(h),e++;e<i.length&&(this._$AR(s&&s._$AB.nextSibling,e),i.length=e);}_$AR(t=this._$AA.nextSibling,s){for(this._$AP?.(false,true,s);t!==this._$AB;){const s=i$1(t).nextSibling;i$1(t).remove(),t=s;}}setConnected(t){ void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t));}}class H{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,i,s,e,h){this.type=1,this._$AH=A,this._$AN=void 0,this.element=t,this.name=i,this._$AM=e,this.options=h,s.length>2||""!==s[0]||""!==s[1]?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=A;}_$AI(t,i=this,s,e){const h=this.strings;let o=false;if(void 0===h)t=M(this,t,i,0),o=!a(t)||t!==this._$AH&&t!==E,o&&(this._$AH=t);else {const e=t;let n,r;for(t=h[0],n=0;n<h.length-1;n++)r=M(this,e[s+n],i,n),r===E&&(r=this._$AH[n]),o||=!a(r)||r!==this._$AH[n],r===A?t=A:t!==A&&(t+=(r??"")+h[n+1]),this._$AH[n]=r;}o&&!e&&this.j(t);}j(t){t===A?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"");}}class I extends H{constructor(){super(...arguments),this.type=3;}j(t){this.element[this.name]=t===A?void 0:t;}}class L extends H{constructor(){super(...arguments),this.type=4;}j(t){this.element.toggleAttribute(this.name,!!t&&t!==A);}}class z extends H{constructor(t,i,s,e,h){super(t,i,s,e,h),this.type=5;}_$AI(t,i=this){if((t=M(this,t,i,0)??A)===E)return;const s=this._$AH,e=t===A&&s!==A||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,h=t!==A&&(s===A||e);e&&this.element.removeEventListener(this.name,this,s),h&&this.element.addEventListener(this.name,this,t),this._$AH=t;}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t);}}class Z{constructor(t,i,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=i,this.options=s;}get _$AU(){return this._$AM._$AU}_$AI(t){M(this,t);}}const B=t.litHtmlPolyfillSupport;B?.(S,k),(t.litHtmlVersions??=[]).push("3.3.3");const D=(t,i,s)=>{const e=s?.renderBefore??i;let h=e._$litPart$;if(void 0===h){const t=s?.renderBefore??null;e._$litPart$=h=new k(i.insertBefore(c(),t),t,void 0,s??{});}return h._$AI(t),h};

    /**
     * @license
     * Copyright 2017 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     */const s=globalThis;class i extends y$1{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0;}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const r=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=D(r,this.renderRoot,this.renderOptions);}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true);}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false);}render(){return E}}i._$litElement$=true,i["finalized"]=true,s.litElementHydrateSupport?.({LitElement:i});const o=s.litElementPolyfillSupport;o?.({LitElement:i});(s.litElementVersions??=[]).push("4.2.2");

    class HeatingClient {
        constructor(hass, entryId) {
            this.hass = hass;
            this.entryId = entryId;
        }
        static async entries(hass) { return (await hass.callWS({ type: 'central_heating/get' })).entries; }
        get() { return this.hass.callWS(this.message('get')); }
        subscribe(callback) { return this.hass.connection.subscribeMessage(callback, this.message('subscribe')); }
        write(command, fields = {}) { return this.hass.callWS(this.message(command, fields)); }
        message(command, fields = {}) { return { ...fields, type: `central_heating/${command}`, config_entry_id: this.entryId }; }
    }
    function overridePayload(roomId, temperature, duration, customMinutes) {
        if (!Number.isFinite(temperature) || temperature < 5 || temperature > 30 || !Number.isInteger(temperature * 2))
            throw new Error('Choose a target from 5 to 30 °C in 0.5° steps.');
        const data = { room_id: roomId, temperature };
        if (duration !== 'next_block') {
            const minutes = duration === 'custom' ? customMinutes : Number(duration);
            if (!minutes || !Number.isInteger(minutes) || minutes < 1 || minutes > 10080)
                throw new Error('Choose 1 to 10080 minutes.');
            data.minutes = minutes;
        }
        return data;
    }

    function temperature(value) { return value == null || !Number.isFinite(value) ? '—' : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}°`; }
    function time(value) { return value ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—'; }
    function localDateTime(value) { if (!value)
        return ''; const d = new Date(value); const pad = (n) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
    function defaultProfile(name = 'Default profile') { return { name, days: Object.fromEntries(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map(day => [day, [{ start: '00:00', target: 18 }]])) }; }

    const styles = i$3 `
:host{display:block;container-type:inline-size;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit);font-size:15px;line-height:1.5}*{box-sizing:border-box}[hidden]{display:none!important}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}ha-card{display:block;overflow:hidden;border:1px solid var(--divider-color);border-radius:var(--ha-card-border-radius,16px);background:var(--ha-card-background,var(--card-background-color))}header{padding:28px 28px 22px;display:flex;justify-content:space-between;gap:16px;align-items:center}.eyebrow{font-size:11px;letter-spacing:.14em;font-weight:700;text-transform:uppercase;color:var(--secondary-text-color)}h1{margin:4px 0;font-size:26px;line-height:1.2;letter-spacing:-.5px}h2{margin:0 0 16px;font-size:18px}h3{margin:0;font-size:16px}p{margin:6px 0 16px}.muted,small{color:var(--secondary-text-color)}small{font-size:12px}.badge{display:inline-flex;gap:6px;align-items:center;border-radius:20px;padding:5px 10px;font-size:12px;font-weight:600;white-space:nowrap;background:var(--secondary-background-color)}.shadow,.warning{color:var(--warning-color);background:color-mix(in srgb,var(--warning-color) 12%,transparent)}.heat{color:var(--state-climate-heat-color,var(--warning-color))}.badge svg{width:14px;height:14px}svg{display:inline-block;width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;vertical-align:middle;flex-shrink:0}nav{display:flex;gap:4px;padding:0 20px;border-bottom:1px solid var(--divider-color)}nav button{border:0;border-radius:0;background:none;color:var(--secondary-text-color);padding:12px 16px;border-bottom:3px solid transparent;min-height:50px}nav button[aria-selected=true]{border-bottom-color:var(--primary-color);color:var(--primary-color);font-weight:700}main{padding:24px 28px 28px;min-height:380px}.grid{display:grid;grid-template-columns:1.4fr 1fr;gap:20px}.panel{padding:22px;border:1px solid var(--divider-color);border-radius:12px}.boiler{background:var(--secondary-background-color)}.boiler-heading{display:flex;align-items:center;gap:14px;margin-bottom:28px}.flame{display:grid;place-items:center;width:50px;height:50px;border-radius:50%;color:var(--state-climate-heat-color,var(--warning-color));background:color-mix(in srgb,var(--warning-color) 12%,transparent)}.flame svg{width:28px;height:28px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.metric strong{font-size:28px;font-weight:500;line-height:1.2;display:block}.metric small{display:block;margin-top:7px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:24px 0 12px}.section-head h2{margin:0}.rooms{display:grid;gap:10px}.room{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 20px;border:1px solid var(--divider-color);border-radius:12px;width:100%;text-align:left;background:var(--ha-card-background,var(--card-background-color));color:var(--primary-text-color)}.room:hover{background:var(--secondary-background-color)}.room-name{display:flex;align-items:center;gap:10px;margin-bottom:5px}.room-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.room-temp{text-align:right;white-space:nowrap}.room-temp strong{font-size:26px;font-weight:500}.room-temp small{display:block}.empty{padding:32px;text-align:center;border:1px dashed var(--divider-color);border-radius:12px}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.toolbar p{margin:0}.actions{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;margin-top:20px}button,select,input{font:inherit}button{cursor:pointer;border:1px solid var(--divider-color);background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:8px;padding:9px 15px;min-height:44px}button.primary{background:var(--primary-color);color:var(--text-primary-color);border-color:var(--primary-color)}button.danger{color:var(--error-color)}button:disabled{opacity:.55;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--primary-color);outline-offset:3px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.field{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}.field:last-child{margin-bottom:0}label,.label{font-size:13px;font-weight:600}.hint{font-size:12px;color:var(--secondary-text-color)}input:not([type=checkbox]),select{width:100%;min-height:44px;padding:10px 12px;background:var(--ha-card-background,var(--card-background-color));color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:8px}input[type=checkbox]{width:20px;height:20px;accent-color:var(--primary-color)}.check{display:flex;align-items:center;gap:12px;min-height:44px;font-size:14px;font-weight:400}.entity-list{max-height:220px;overflow:auto;padding:8px 12px;border:1px solid var(--divider-color);border-radius:8px}.entity-list small{display:block}fieldset{border:0;margin:0;padding:0;min-width:0}legend{font-size:15px;font-weight:600;margin-bottom:14px}.setting-section+.setting-section{margin-top:24px;padding-top:24px;border-top:1px solid var(--divider-color)}.profile-row{padding:18px 0;border-bottom:1px solid var(--divider-color);display:flex;justify-content:space-between;gap:12px}.notice{padding:12px 28px;border-top:1px solid var(--divider-color);font-size:13px}.notice.error{color:var(--error-color);background:color-mix(in srgb,var(--error-color) 8%,transparent)}dialog{color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);border-radius:16px;width:min(480px,calc(100vw - 32px));padding:26px;max-height:90dvh;overflow:auto}dialog::backdrop{background:color-mix(in srgb,var(--primary-text-color) 40%,transparent)}.dialog-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.dialog-head h2{margin:0}.icon-button{padding:8px;display:grid;place-items:center;min-width:44px;background:none}.stepper{display:flex;justify-content:center;align-items:center;gap:28px;margin:24px 0}.stepper strong{font-size:42px;line-height:1}.stepper button{width:48px;font-size:24px}.split{display:flex;gap:8px;align-items:center}.wide{grid-column:1/-1}.delete-confirm{padding:18px;border:1px solid var(--error-color);border-radius:12px;margin-top:16px}
@container(max-width:600px){header{padding:22px 18px 18px;align-items:flex-start;flex-wrap:wrap}h1{font-size:24px}nav{padding:0 8px;gap:0}nav button{flex:1;padding:12px 6px;font-size:13px}main{padding:18px}.grid,.form-grid{grid-template-columns:1fr}.panel{padding:18px}.boiler-heading{margin-bottom:20px}.metric strong{font-size:25px}.room{padding:16px 14px;gap:8px}.room-temp strong{font-size:23px}.room .badge{font-size:11px;padding:4px 8px}.toolbar{align-items:flex-start}.toolbar p{max-width:210px}.notice{padding:12px 18px}.actions{justify-content:stretch}.actions button{flex:1}.wide{grid-column:auto}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
`;

    const tabs = ['Overview', 'Rooms', 'Schedules', 'Settings'];
    const flame = w `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 3c1 5-4 5-2 9 1-1 2-2 3-3 3 3 5 5 4 8a6 6 0 0 1-12-1c0-4 3-6 4-8 0 3 1 3 2 4"/></svg>`;
    const shield = w `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></svg>`;
    const close = w `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>`;
    class CentralHeatingCard extends i {
        constructor() {
            super(...arguments);
            this.tab = 'Overview';
            this.busy = false;
            this.error = '';
            this.notice = '';
            this.editing = null;
            this.filter = '';
            this.quickRoom = null;
            this.quickTarget = 21;
            this.duration = 'next_block';
            this.deleting = null;
            this.config = { type: 'custom:central-heating-card' };
            this.generation = 0;
            this.connecting = false;
            this.entries = [];
            this.saveMode = async (event) => { event.preventDefault(); const data = new FormData(event.target); const mode = String(data.get('mode')); const until = mode === 'away' && data.get('until') ? String(data.get('until')) : null; await this.write('mode/set', { mode, until }, 'Heating mode saved.'); };
            this.saveRoom = async (event) => { event.preventDefault(); if (!this.editing || !this.status)
                return; const form = new FormData(event.target); const trvs = form.getAll('trvs').map(String); if (!trvs.length) {
                this.error = 'Choose at least one thermostat.';
                return;
            } let profileId = String(form.get('profile_id')); if (!profileId) {
                if (!await this.write('profile/save', { profile: defaultProfile() }, 'Default profile created.'))
                    return;
                profileId = this.status.saved_id ?? '';
            } if (!profileId) {
                this.error = 'A heating profile is required.';
                return;
            } const room = { ...(this.editing.id ? { id: this.editing.id } : {}), name: String(form.get('name')).trim(), trvs, profile_id: profileId, area_id: String(form.get('area_id') ?? '') || null, enabled: form.has('enabled') }; if (await this.write('room/save', { room }, 'Room saved.'))
                this.editing = null; };
            this.saveSettings = async (event) => { event.preventDefault(); const data = new FormData(event.target); const settings = { frost_temperature: Number(data.get('frost_temperature')), hysteresis: Number(data.get('hysteresis')), away_temperature: Number(data.get('away_temperature')), override_default: String(data.get('override_default')), override_minutes: Number(data.get('override_minutes')), retry_seconds: Number(data.get('retry_seconds')), sync_rooms_on_knob_change: data.has('sync_rooms_on_knob_change') }; await this.write('settings/save', { settings, shadow: data.has('shadow') }, 'Heating settings saved.'); };
        }
        static { this.styles = styles; }
        static { this.properties = { status: { state: true }, tab: { state: true }, busy: { state: true }, error: { state: true }, notice: { state: true }, editing: { state: true }, filter: { state: true }, quickRoom: { state: true }, quickTarget: { state: true }, duration: { state: true }, deleting: { state: true } }; }
        set hass(value) { if (!value) {
            this.disconnect();
            this._hass = undefined;
            return;
        } const changed = this._hass?.connection !== value.connection; this._hass = value; this.requestUpdate(); if (changed || !this.client)
            void this.connect(); }
        get hass() { return this._hass; }
        setConfig(value) { if (!value || value.type !== 'custom:central-heating-card')
            throw new Error('Invalid Central Heating card configuration'); const changed = this.config.config_entry_id !== value.config_entry_id; this.config = { ...value }; if (changed) {
            this.disconnect();
            this.status = undefined;
        } this.requestUpdate(); void this.connect(); }
        connectedCallback() { super.connectedCallback(); void this.connect(); }
        disconnectedCallback() { super.disconnectedCallback(); this.disconnect(); }
        disconnect() { this.generation++; this.unsubscribe?.(); this.unsubscribe = undefined; this.client = undefined; this.connecting = false; }
        async connect() { if (!this._hass || !this.isConnected || this.connecting || this.client)
            return; this.connecting = true; const generation = this.generation; try {
            this.entries = await HeatingClient.entries(this._hass);
            const id = this.config.config_entry_id ?? (this.entries.length === 1 ? this.entries[0].entry_id : undefined);
            if (!id) {
                this.error = this.entries.length ? 'Choose a heating instance in the card editor.' : 'Add a Central Heating integration to get started.';
                return;
            }
            const client = new HeatingClient(this._hass, id);
            const status = await client.get();
            if (generation !== this.generation)
                return;
            this.client = client;
            this.status = status;
            const unsub = await client.subscribe(value => { if (generation === this.generation) {
                this.status = value;
                this.error = '';
            } });
            if (generation === this.generation)
                this.unsubscribe = unsub;
            else
                unsub();
        }
        catch (error) {
            if (generation === this.generation)
                this.error = this.message(error);
        }
        finally {
            if (generation === this.generation)
                this.connecting = false;
        } }
        message(error) { return error instanceof Error ? error.message : typeof error === 'object' && error !== null && 'message' in error ? String(error.message) : 'Unable to save. Please try again.'; }
        get writable() { return this._hass?.user?.is_admin === true; }
        async write(command, fields, success) { if (!this.client || this.busy)
            return false; this.busy = true; this.error = ''; this.notice = ''; try {
            this.status = await this.client.write(command, fields);
            this.notice = success;
            return true;
        }
        catch (error) {
            this.error = this.message(error);
            return false;
        }
        finally {
            this.busy = false;
        } }
        getCardSize() { return 7; }
        static getConfigElement() { return document.createElement('central-heating-card-editor'); }
        static getStubConfig() { return { type: 'custom:central-heating-card' }; }
        render() { const s = this.status; return b `<ha-card><header><div><div class="eyebrow">Climate control</div><h1>${this.config.title ?? 'Central Heating'}</h1><small>${s ? `${Object.keys(s.rooms).length} rooms · ${s.configuration.mode.value[0].toUpperCase() + s.configuration.mode.value.slice(1)}` : 'Your rooms, one comfortable home'}</small></div>${s?.configuration.shadow ? b `<span class="badge shadow">${shield} Shadow mode</span>` : A}</header><nav role="tablist" aria-label="Heating views">${tabs.map(tab => b `<button role="tab" id=${`tab-${tab}`} aria-selected=${this.tab === tab} aria-controls="view" @click=${() => { this.tab = tab; this.editing = null; this.deleting = null; }}>${tab}</button>`)}</nav><main id="view" role="tabpanel" aria-labelledby=${`tab-${this.tab}`}>${s ? this.tab === 'Overview' ? this.overview(s) : this.tab === 'Rooms' ? this.rooms(s) : this.tab === 'Settings' ? this.settings(s) : this.schedules(s) : b `<p class="muted">${this.error ? 'Heating information is unavailable.' : 'Connecting to Central Heating…'}</p>`}</main>${this.error ? b `<div class="notice error" role="alert">${this.error}</div>` : A}${this.notice ? b `<div class="notice" role="status">${this.notice}</div>` : A}${!this.writable && s ? b `<div class="notice muted">Read-only access. An administrator can change heating settings.</div>` : A}${this.quickDialog(s)}</ha-card>`; }
        overview(s) { return b `<div class="grid"><section class="panel boiler" aria-label="Boiler status"><div class="boiler-heading"><span class="flame">${flame}</span><div><h3>${s.global.command.heat ? 'Calling for heat' : 'Boiler resting'}</h3><small>${s.configuration.shadow ? 'Shadow mode · boiler output paused' : 'Following room demand'}</small></div></div><div class="metrics"><div class="metric"><strong>${s.global.demand_count}</strong><small>Demanding TRVs</small></div><div class="metric"><strong>${temperature(s.global.virtual_temp)}</strong><small>Virtual temperature</small></div><div class="metric"><strong>${temperature(s.global.virtual_setpoint)}</strong><small>Virtual setpoint</small></div></div></section><section class="panel"><h2>Heating mode</h2><form @submit=${this.saveMode}><fieldset ?disabled=${!this.writable || this.busy}><div class="field"><label for="mode">Mode</label><select id="mode" name="mode" @change=${(e) => { const form = e.target.form; const field = form.querySelector('[data-until]'); field.hidden = e.target.value !== 'away'; }}>${['auto', 'away', 'summer', 'manual'].map(mode => b `<option value=${mode} ?selected=${s.configuration.mode.value === mode}>${mode[0].toUpperCase() + mode.slice(1)}</option>`)}</select></div><div class="field" data-until ?hidden=${s.configuration.mode.value !== 'away'}><label for="until">Away until (optional)</label><input id="until" name="until" type="datetime-local" .value=${localDateTime(s.configuration.mode.until)}><small>Home Assistant’s local time.</small></div><button class="primary" type="submit">${this.busy ? 'Saving…' : 'Apply mode'}</button></fieldset></form></section></div><div class="section-head"><h2>Room comfort</h2><small>Tap a room to adjust</small></div><div class="rooms">${Object.entries(s.rooms).map(([id, room]) => b `<button class="room" @click=${() => this.openQuick(id)} aria-label=${`Adjust ${room.name}`}><div><div class="room-name">${room.demanding ? b `<span class="heat">${flame}</span>` : A}<h3>${room.name}</h3></div><small>${room.demanding ? 'Calling for heat' : 'Comfort on schedule'}</small><div class="room-tags">${room.override_until ? b `<span class="badge">${temperature(s.configuration.overrides[id]?.target)} until ${time(room.override_until)}</span>` : A}${room.sync_problem ? b `<span class="badge warning">Check thermostat sync</span>` : A}</div></div><div class="room-temp"><strong>${temperature(room.current)}</strong><small>Target ${temperature(room.desired)}</small></div></button>`)}</div>${!Object.keys(s.rooms).length ? b `<div class="empty"><h3>No rooms yet</h3><p class="muted">Add your first room to bring your thermostats together.</p><button @click=${() => { this.tab = 'Rooms'; }}>Set up rooms</button></div>` : A}`; }
        async openQuick(id) { const room = this.status?.rooms[id]; if (!room)
            return; this.quickRoom = id; this.quickTarget = room.desired ?? 21; this.duration = 'next_block'; await this.updateComplete; this.renderRoot.querySelector('#quick-dialog')?.showModal(); }
        closeQuick() { this.renderRoot.querySelector('#quick-dialog')?.close(); this.quickRoom = null; }
        quickDialog(s) { if (!this.quickRoom || !s)
            return A; const id = this.quickRoom; return b `<dialog id="quick-dialog" @close=${() => { this.quickRoom = null; }} @cancel=${() => { this.quickRoom = null; }}><div class="dialog-head"><div><h2>${s.rooms[id]?.name}</h2><small>Temporary room target</small></div><button class="icon-button" aria-label="Close room adjustment" @click=${() => this.closeQuick()}>${close}</button></div><form @submit=${async (e) => { e.preventDefault(); try {
        const data = new FormData(e.target);
        if (await this.write('override/set', overridePayload(id, this.quickTarget, this.duration, Number(data.get('minutes'))), 'Room override saved.'))
            this.closeQuick();
    }
    catch (error) {
        this.error = this.message(error);
    } }}><fieldset ?disabled=${!this.writable || this.busy}><div class="stepper"><button type="button" aria-label="Decrease target by half a degree" ?disabled=${this.quickTarget <= 5} @click=${() => { this.quickTarget = Math.max(5, this.quickTarget - .5); }}>−</button><strong aria-live="polite">${temperature(this.quickTarget)}</strong><button type="button" aria-label="Increase target by half a degree" ?disabled=${this.quickTarget >= 30} @click=${() => { this.quickTarget = Math.min(30, this.quickTarget + .5); }}>+</button></div><div class="field"><label for="duration">Keep this target</label><select id="duration" .value=${this.duration} @change=${(e) => { this.duration = e.target.value; }}><option value="next_block">Until the next change</option><option value="60">1 hour</option><option value="120">2 hours</option><option value="180">3 hours</option><option value="custom">Custom length</option></select></div>${this.duration === 'custom' ? b `<div class="field"><label for="minutes">Minutes</label><input id="minutes" name="minutes" type="number" min="1" max="10080" step="1" value="120" required></div>` : A}<div class="actions"><button type="button" @click=${async () => { if (await this.write('override/clear', { room_id: id }, 'Room returned to schedule.'))
        this.closeQuick(); }}>Back to schedule</button><button class="primary" type="submit">${this.busy ? 'Saving…' : 'Apply target'}</button></div></fieldset></form>${this.error ? b `<p role="alert">${this.error}</p>` : A}</dialog>`; }
        rooms(s) { return b `<div class="toolbar"><div><h2>Rooms & thermostats</h2><p class="muted">Group thermostats that share a target.</p></div><button class="primary" ?disabled=${!this.writable || this.busy} @click=${() => this.editRoom()}>Add room</button></div>${this.editing ? this.roomForm(s) : b `<div class="rooms">${Object.entries(s.configuration.rooms).map(([id, room]) => b `<div class="room"><div><h3>${room.name}</h3><small>${room.trvs.length} thermostat${room.trvs.length === 1 ? '' : 's'} · ${s.configuration.profiles[room.profile_id]?.name ?? 'No profile'}${room.enabled ? '' : ' · Disabled'}</small><div class="room-tags">${room.trvs.map(trv => b `<span class="badge">${String(this.hass?.states[trv]?.attributes.friendly_name ?? trv)}</span>`)}</div></div><button ?disabled=${!this.writable} @click=${() => this.editRoom(id)}>Edit<span class="sr-only"> ${room.name}</span></button></div>`)}</div>${!Object.keys(s.configuration.rooms).length ? b `<div class="empty">No rooms have been configured.</div>` : A}`}`; }
        editRoom(id) { const room = id ? this.status?.configuration.rooms[id] : undefined; this.editing = { id, room: room ? { ...room, trvs: [...room.trvs] } : { name: '', trvs: [], profile_id: Object.keys(this.status?.configuration.profiles ?? {})[0] ?? '', area_id: null, enabled: true } }; this.filter = ''; this.deleting = null; }
        roomForm(s) { const draft = this.editing; const used = new Set(Object.entries(s.configuration.rooms).filter(([id]) => id !== draft.id).flatMap(([, room]) => room.trvs)); const entities = Object.entries(this.hass?.states ?? {}).filter(([id]) => id.startsWith('climate.') && !used.has(id) && !Object.keys(s.configuration.rooms).some(roomId => id.endsWith(`_room_${roomId}`))); const profiles = Object.entries(s.configuration.profiles); return b `<form class="panel" @submit=${this.saveRoom}><h2>${draft.id ? 'Edit room' : 'Add a room'}</h2><fieldset ?disabled=${this.busy || !this.writable}><div class="form-grid"><div class="field"><label for="room-name">Room name</label><input id="room-name" name="name" required maxlength="120" .value=${draft.room.name}></div><div class="field"><label for="room-profile">Heating profile</label><select id="room-profile" name="profile_id" .value=${draft.room.profile_id}>${profiles.length ? profiles.map(([id, p]) => b `<option value=${id}>${p.name}</option>`) : b `<option value="">Create default · 18° all week</option>`}</select>${!profiles.length ? b `<small>A simple 00:00 → 18° profile will be created when you save.</small>` : A}</div><div class="field wide"><label for="trv-filter">Radiator thermostats</label><input id="trv-filter" type="search" placeholder="Find a climate entity" .value=${this.filter} @input=${(e) => { this.filter = e.target.value; }}><div class="entity-list">${entities.map(([id, state]) => b `<label class="check" ?hidden=${!`${id} ${state.attributes.friendly_name ?? ''}`.toLowerCase().includes(this.filter.toLowerCase())}><input type="checkbox" name="trvs" value=${id} .checked=${draft.room.trvs.includes(id)}><span>${String(state.attributes.friendly_name ?? id)}<small>${id}</small></span></label>`)}</div><small>Climate entities already assigned to another room are excluded.</small></div><div class="field"><label for="area">Area (optional)</label><input id="area" name="area_id" list="areas" .value=${draft.room.area_id ?? ''} placeholder="No area"><datalist id="areas">${Object.entries(this.hass?.areas ?? {}).map(([id, area]) => b `<option value=${id}>${area.name}</option>`)}</datalist></div><div class="field"><span class="label">Room control</span><label class="check"><input type="checkbox" name="enabled" .checked=${draft.room.enabled}>Enabled</label></div></div><div class="actions">${draft.id ? b `<button class="danger" type="button" @click=${() => { this.deleting = draft.id ?? null; }}>Delete room</button>` : A}<button type="button" @click=${() => { this.editing = null; this.deleting = null; }}>Cancel</button><button class="primary" type="submit">${this.busy ? 'Saving…' : 'Save room'}</button></div></fieldset>${this.deleting ? b `<div class="delete-confirm" role="alert"><p>Delete ${draft.room.name}? Its thermostats will no longer be scheduled by this room.</p><div class="actions"><button type="button" @click=${() => { this.deleting = null; }}>Keep room</button><button type="button" class="danger" @click=${async () => { if (await this.write('room/delete', { room_id: draft.id }, 'Room deleted.')) {
        this.editing = null;
        this.deleting = null;
    } }}>Confirm delete</button></div></div>` : A}</form>`; }
        schedules(s) { return b `<div class="toolbar"><div><h2>Weekly profiles</h2><p class="muted">A clear plan for every room.</p></div><span class="badge">Preview</span></div><div class="panel"><p>The week-grid editor is coming in the next update. Your existing profiles keep running.</p>${Object.entries(s.configuration.profiles).map(([id, profile]) => b `<div class="profile-row"><div><h3>${profile.name}</h3><small>${Object.values(s.configuration.rooms).filter(room => room.profile_id === id).map(room => room.name).join(', ') || 'No rooms assigned'}</small></div><span class="badge">Weekly schedule</span></div>`)}${!Object.keys(s.configuration.profiles).length ? b `<p class="muted">No profiles yet. Add a room to create a simple default profile.</p>` : A}</div>`; }
        settings(s) { const settings = s.configuration.settings; return b `<h2>Heating settings</h2><p class="muted">Fine-tune comfort and thermostat synchronization.</p><form class="panel" @submit=${this.saveSettings}><fieldset ?disabled=${!this.writable || this.busy}><section class="setting-section"><legend>Temperature controls</legend><div class="form-grid">${this.numberField('frost_temperature', 'Frost temperature', settings.frost_temperature, 5, 18, .5, '°C · used in summer and as the boiler fallback')}${this.numberField('hysteresis', 'Demand hysteresis', settings.hysteresis, .1, 1, .1, '°C · gap before a thermostat calls for heat')}${this.numberField('away_temperature', 'Away temperature', settings.away_temperature, 5, 30, .5, '°C · room target while away')}</div></section><section class="setting-section"><legend>Overrides & synchronization</legend><div class="form-grid"><div class="field"><label for="override_default">Default override length</label><select id="override_default" name="override_default"><option value="next_block" ?selected=${settings.override_default === 'next_block'}>Until the next change</option><option value="duration" ?selected=${settings.override_default === 'duration'}>Fixed duration</option></select></div>${this.numberField('override_minutes', 'Default duration', settings.override_minutes, 1, 10080, 1, 'Minutes · when fixed duration is selected')}${this.numberField('retry_seconds', 'Retry interval', settings.retry_seconds, 1, undefined, 1, 'Seconds · wait for a battery thermostat to report')}<label class="check"><input type="checkbox" name="sync_rooms_on_knob_change" .checked=${settings.sync_rooms_on_knob_change}>Sync the room after a thermostat knob change</label></div></section><section class="setting-section"><legend>Boiler output</legend><label class="check"><input type="checkbox" name="shadow" .checked=${s.configuration.shadow}>Shadow mode</label><small>Computes boiler demand without sending boiler commands. Room schedules still apply; use manual mode to pause them.</small></section><div class="actions"><button class="primary" type="submit">${this.busy ? 'Saving…' : 'Save settings'}</button></div></fieldset></form>`; }
        numberField(name, label, value, min, max, step, hint) { return b `<div class="field"><label for=${name}>${label}</label><input id=${name} name=${name} type="number" min=${min} max=${max ?? A} step=${step} required .value=${String(value)}><span class="hint">${hint}</span></div>`; }
    }
    class CentralHeatingEditor extends i {
        constructor() {
            super(...arguments);
            this.config = { type: 'custom:central-heating-card' };
            this.entries = [];
            this.error = '';
            this.loaded = false;
        }
        static { this.properties = { entries: { state: true }, config: { state: true }, error: { state: true } }; }
        static { this.styles = styles; }
        set hass(value) { if (!this.loaded) {
            this.loaded = true;
            void HeatingClient.entries(value).then(entries => { this.entries = entries; }).catch(() => { this.error = 'Could not load heating instances.'; this.loaded = false; });
        } }
        setConfig(value) { this.config = { ...value }; }
        render() { return b `<div class="field"><label for="entry">Heating instance</label><select id="entry" .value=${this.config.config_entry_id ?? ''} @change=${(e) => this.change({ config_entry_id: e.target.value || undefined })}><option value="">${this.entries.length === 1 ? 'Use the only instance' : 'Choose an instance'}</option>${this.entries.map(entry => b `<option value=${entry.entry_id}>${entry.title}</option>`)}</select><label for="title">Title (optional)</label><input id="title" .value=${this.config.title ?? ''} @change=${(e) => this.change({ title: e.target.value || undefined })}>${this.error ? b `<p role="alert">${this.error}</p>` : A}</div>`; }
        change(values) { this.config = { ...this.config, ...values }; this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: this.config }, bubbles: true, composed: true })); }
    }
    if (!customElements.get('central-heating-card'))
        customElements.define('central-heating-card', CentralHeatingCard);
    if (!customElements.get('central-heating-card-editor'))
        customElements.define('central-heating-card-editor', CentralHeatingEditor);
    const registry = window;
    registry.customCards ??= [];
    if (!registry.customCards.some(card => card.type === 'central-heating-card'))
        registry.customCards.push({ type: 'central-heating-card', name: 'Central Heating', description: 'Room comfort, boiler demand and heating schedules.' });

    const configuration = { settings: { frost_temperature: 16, hysteresis: .3, away_temperature: 15, override_default: 'next_block', override_minutes: 120, sync_rooms_on_knob_change: true, retry_seconds: 300 }, mode: { value: 'auto', until: null }, shadow: true, profiles: { profile_a: defaultProfile('Weekday comfort') }, rooms: { room_a: { name: 'Room A', trvs: ['climate.trv_a'], profile_id: 'profile_a', area_id: 'area_a', enabled: true }, room_b: { name: 'Room B', trvs: ['climate.trv_b'], profile_id: 'profile_a', area_id: null, enabled: true } }, overrides: { room_b: { target: 22, until: '2026-11-22T18:00:00Z', source: 'card' } } };
    function fixture() { return structuredClone({ config_entry_id: 'demo_entry_a', configuration, global: { demand_count: 1, virtual_temp: 19.4, virtual_temp_raw: 19.4, virtual_setpoint: 21, command: { heat: true, room_temperature: 19.4, setpoint: 21 }, last_sent: '2026-11-22T16:30:00Z', shadow: true, mode: configuration.mode }, rooms: { room_a: { name: 'Room A', current: 19.4, desired: 21, trvs: { 'climate.trv_a': 21 }, demanding: true, sync_problem: false, override_until: null, next_change: '2026-11-22T22:00:00Z', next_target: 18 }, room_b: { name: 'Room B', current: 21.8, desired: 22, trvs: { 'climate.trv_b': 20 }, demanding: false, sync_problem: true, override_until: '2026-11-22T18:00:00Z', next_change: '2026-11-22T22:00:00Z', next_target: 18 } } }); }

    let status = fixture();
    let nextId = 1;
    const listeners = new Set();
    function notify() { for (const listener of listeners)
        listener(structuredClone(status)); }
    function recalculate() { status.global.shadow = status.configuration.shadow; status.global.mode = status.configuration.mode; for (const [id, room] of Object.entries(status.configuration.rooms)) {
        const override = status.configuration.overrides[id];
        const old = status.rooms[id];
        const target = override?.target ?? 18;
        status.rooms[id] = { ...old, name: room.name, current: old?.current ?? 18, desired: target, trvs: Object.fromEntries(room.trvs.map(trv => [trv, target])), demanding: old?.demanding ?? false, sync_problem: old?.sync_problem ?? false, override_until: override?.until ?? null, next_change: old?.next_change ?? null, next_target: old?.next_target ?? null };
    } }
    function respond(message) {
        const command = message.type.replace('central_heating/', '');
        if (command === 'get')
            return message.config_entry_id ? structuredClone(status) : { entries: [{ entry_id: 'demo_entry_a', title: 'Demo boiler A' }, { entry_id: 'demo_entry_b', title: 'Demo boiler B' }] };
        let savedId;
        if (command === 'mode/set') {
            status.configuration.mode = { value: message.mode, until: message.until };
        }
        else if (command === 'override/set') {
            const room = String(message.room_id);
            status.configuration.overrides[room] = { target: Number(message.temperature), until: new Date(Date.now() + Number(message.minutes ?? 120) * 60000).toISOString(), source: 'card' };
        }
        else if (command === 'override/clear')
            delete status.configuration.overrides[String(message.room_id)];
        else if (command === 'room/save') {
            const room = message.room;
            savedId = room.id ?? `room_${nextId++}`;
            const copy = { ...room };
            delete copy.id;
            status.configuration.rooms[savedId] = copy;
        }
        else if (command === 'room/delete') {
            delete status.configuration.rooms[String(message.room_id)];
            delete status.rooms[String(message.room_id)];
            delete status.configuration.overrides[String(message.room_id)];
        }
        else if (command === 'profile/save') {
            const profile = message.profile;
            savedId = profile.id ?? `profile_${nextId++}`;
            const copy = { ...profile };
            delete copy.id;
            status.configuration.profiles[savedId] = copy;
        }
        else if (command === 'profile/delete')
            delete status.configuration.profiles[String(message.profile_id)];
        else if (command === 'settings/save') {
            Object.assign(status.configuration.settings, message.settings ?? {});
            if (message.shadow !== undefined)
                status.configuration.shadow = Boolean(message.shadow);
        }
        else
            throw new Error('Unknown demo command');
        recalculate();
        notify();
        return { ...structuredClone(status), ...(savedId ? { saved_id: savedId } : {}) };
    }
    const hass = { async callWS(message) { return respond(message); }, connection: { async subscribeMessage(callback) { const listener = (value) => callback(value); listeners.add(listener); return () => { listeners.delete(listener); }; } }, states: { 'climate.trv_a': { state: 'heat', attributes: { friendly_name: 'Thermostat A' } }, 'climate.trv_b': { state: 'heat', attributes: { friendly_name: 'Thermostat B' } }, 'climate.trv_c': { state: 'heat', attributes: { friendly_name: 'Thermostat C' } } }, areas: { area_a: { name: 'Area A' }, area_b: { name: 'Area B' } }, user: { is_admin: true } };
    const query = new URLSearchParams(location.search);
    const width = query.get('width') === '390' ? '390px' : '1080px';
    document.documentElement.dataset.theme = query.get('theme') === 'dark' ? 'dark' : 'light';
    document.querySelector('#preview').style.width = width;
    const card = document.querySelector('central-heating-card');
    card.setConfig({ type: 'custom:central-heating-card', config_entry_id: 'demo_entry_a' });
    card.hass = hass;
    const selected = query.get('tab');
    if (selected && ['Overview', 'Rooms', 'Schedules', 'Settings'].includes(selected))
        card.tab = selected;
    document.querySelector('#theme').value = document.documentElement.dataset.theme;
    document.querySelector('#theme').addEventListener('change', e => { document.documentElement.dataset.theme = e.target.value; });
    document.querySelector('#width').addEventListener('change', e => { document.querySelector('#preview').style.width = e.target.value; });
    document.querySelector('#width').value = width;
    document.querySelector('#reset').addEventListener('click', () => { status = fixture(); notify(); });

})();

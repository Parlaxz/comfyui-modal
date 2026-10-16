/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function Do(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const Ne = {}, Rs = [], Dt = () => {
}, Ha = () => !1, pr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), hr = (e) => e.startsWith("onUpdate:"), Xe = Object.assign, Vo = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, tu = Object.prototype.hasOwnProperty, Se = (e, t) => tu.call(e, t), Q = Array.isArray, ps = (e) => Tn(e) === "[object Map]", ss = (e) => Tn(e) === "[object Set]", yi = (e) => Tn(e) === "[object Date]", de = (e) => typeof e == "function", Ve = (e) => typeof e == "string", gt = (e) => typeof e == "symbol", Ae = (e) => e !== null && typeof e == "object", Ga = (e) => (Ae(e) || de(e)) && de(e.then) && de(e.catch), Za = Object.prototype.toString, Tn = (e) => Za.call(e), su = (e) => Tn(e).slice(8, -1), qa = (e) => Tn(e) === "[object Object]", gr = (e) => Ve(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, un = /* @__PURE__ */ Do(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), vr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, nu = /-\w/g, lt = vr(
  (e) => e.replace(nu, (t) => t.slice(1).toUpperCase())
), ru = /\B([A-Z])/g, _s = vr(
  (e) => e.replace(ru, "-$1").toLowerCase()
), yr = vr((e) => e.charAt(0).toUpperCase() + e.slice(1)), jr = vr(
  (e) => e ? `on${yr(e)}` : ""
), $t = (e, t) => !Object.is(e, t), Gn = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Ka = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, br = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let bi;
const _r = () => bi || (bi = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Lo(e) {
  if (Q(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = Ve(n) ? lu(n) : Lo(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (Ve(e) || Ae(e))
    return e;
}
const ou = /;(?![^(]*\))/g, iu = /:([^]+)/, au = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function lu(e) {
  const t = {};
  return e.replace(au, (s) => s.startsWith("/*") ? "" : s).split(ou).forEach((s) => {
    if (s) {
      const n = s.split(iu);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function ft(e) {
  let t = "";
  if (Ve(e))
    t = e;
  else if (Q(e))
    for (let s = 0; s < e.length; s++) {
      const n = ft(e[s]);
      n && (t += n + " ");
    }
  else if (Ae(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const cu = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", uu = /* @__PURE__ */ Do(cu);
function Ja(e) {
  return !!e || e === "";
}
function du(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = ns(e[r], t[r], s);
  return n;
}
function _i(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < n.length; a++)
      if (!r[a] && ns(o, n[a], s)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function fu(e, t, s) {
  let n = ps(e), r = ps(t);
  if (n || r || (n = ss(e), r = ss(t), n || r))
    return n && r ? _i(e, t, s) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !ns(e[a], t[a], s))
      return !1;
  }
  return String(e) === String(t);
}
function wi(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = n(e, t, s);
  return r.delete(e), o.delete(t), i;
}
function ns(e, t, s) {
  if (e === t) return !0;
  let n = yi(e), r = yi(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = gt(e), r = gt(t), n || r ? e === t : (n = Q(e), r = Q(t), n || r ? n && r ? wi(e, t, s, du) : !1 : (n = Ae(e), r = Ae(t), n || r ? !n || !r ? !1 : wi(e, t, s, fu) : String(e) === String(t))));
}
function Fo(e, t) {
  return e.findIndex((s) => ns(s, t));
}
const Qa = (e) => !!(e && e.__v_isRef === !0), re = (e) => Ve(e) ? e : e == null ? "" : Q(e) || Ae(e) && (e.toString === Za || !de(e.toString)) ? Qa(e) ? re(e.value) : JSON.stringify(e, Ya, 2) : String(e), Ya = (e, t) => Qa(t) ? Ya(e, t.value) : ps(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[$r(n, o) + " =>"] = r, s),
    {}
  )
} : ss(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => $r(s))
} : gt(t) ? $r(t) : Ae(t) && !Q(t) && !qa(t) ? String(t) : t, $r = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    gt(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Ze;
class Xa {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && Ze && (Ze.active ? (this.parent = Ze, this.index = (Ze.scopes || (Ze.scopes = [])).push(
      this
    ) - 1) : (this._active = !1, this._warnOnRun = !1));
  }
  get active() {
    return this._active;
  }
  pause() {
    if (this._active) {
      this._isPaused = !0;
      let t, s;
      if (this.scopes) {
        const n = this.scopes.slice();
        for (t = 0, s = n.length; t < s; t++)
          n[t].pause();
      }
      for (t = 0, s = this.effects.length; t < s; t++)
        this.effects[t].pause();
    }
  }
  /**
   * Resumes the effect scope, including all child scopes and effects.
   */
  resume() {
    if (this._active && this._isPaused) {
      this._isPaused = !1;
      let t, s;
      if (this.scopes) {
        const r = this.scopes.slice();
        for (t = 0, s = r.length; t < s; t++)
          r[t].resume();
      }
      const n = this.effects.slice();
      for (t = 0, s = n.length; t < s; t++)
        n[t].resume();
    }
  }
  run(t) {
    if (this._active) {
      const s = Ze;
      try {
        return Ze = this, t();
      } finally {
        Ze = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = Ze, Ze = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (Ze === this)
        Ze = this.prevScope;
      else {
        let t = Ze;
        for (; t; ) {
          if (t.prevScope === this) {
            t.prevScope = this.prevScope;
            break;
          }
          t = t.prevScope;
        }
      }
      this.prevScope = void 0;
    }
  }
  stop(t) {
    if (this._active) {
      this._active = !1;
      let s, n;
      for (s = 0, n = this.effects.length; s < n; s++)
        this.effects[s].stop();
      for (this.effects.length = 0, s = 0, n = this.cleanups.length; s < n; s++)
        this.cleanups[s]();
      if (this.cleanups.length = 0, this.scopes) {
        const r = this.scopes.slice();
        for (s = 0, n = r.length; s < n; s++)
          r[s].stop(!0);
        this.scopes.length = 0;
      }
      if (!this.detached && this.parent && !t) {
        const r = this.parent.scopes.pop();
        r && r !== this && (this.parent.scopes[this.index] = r, r.index = this.index);
      }
      this.parent = void 0;
    }
  }
}
function el(e) {
  return new Xa(e);
}
function Uo() {
  return Ze;
}
function tl(e, t = !1) {
  Ze && Ze.cleanups.push(e);
}
let Me;
const zr = /* @__PURE__ */ new WeakSet();
class sl {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, Ze && (Ze.active ? Ze.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, zr.has(this) && (zr.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || rl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, xi(this), ol(this);
    const t = Me, s = St;
    Me = this, St = !0;
    try {
      return this.fn();
    } finally {
      il(this), Me = t, St = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        Ho(t);
      this.deps = this.depsTail = void 0, xi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? zr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    fo(this) && this.run();
  }
  get dirty() {
    return fo(this);
  }
}
let nl = 0, dn, fn;
function rl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = fn, fn = e;
    return;
  }
  e.next = dn, dn = e;
}
function Wo() {
  nl++;
}
function Bo() {
  if (--nl > 0)
    return;
  if (fn) {
    let t = fn;
    for (fn = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; dn; ) {
    let t = dn;
    for (dn = void 0; t; ) {
      const s = t.next;
      if (t.next = void 0, t.flags &= -9, t.flags & 1)
        try {
          t.trigger();
        } catch (n) {
          e || (e = n);
        }
      t = s;
    }
  }
  if (e) throw e;
}
function ol(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function il(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), Ho(n), mu(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function fo(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (al(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function al(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === yn) || (e.globalVersion = yn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !fo(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = Me, n = St;
  Me = e, St = !0;
  try {
    ol(e);
    const r = e.fn(e._value);
    (t.version === 0 || $t(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Me = s, St = n, il(e), e.flags &= -3;
  }
}
function Ho(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      Ho(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function mu(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let St = !0;
const ll = [];
function Ft() {
  ll.push(St), St = !1;
}
function Ut() {
  const e = ll.pop();
  St = e === void 0 ? !0 : e;
}
function xi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = Me;
    Me = void 0;
    try {
      t();
    } finally {
      Me = s;
    }
  }
}
let yn = 0;
class pu {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Go {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!Me || !St || Me === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== Me)
      s = this.activeLink = new pu(Me, this), Me.deps ? (s.prevDep = Me.depsTail, Me.depsTail.nextDep = s, Me.depsTail = s) : Me.deps = Me.depsTail = s, cl(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = Me.depsTail, s.nextDep = void 0, Me.depsTail.nextDep = s, Me.depsTail = s, Me.deps === s && (Me.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, yn++, this.notify(t);
  }
  notify(t) {
    Wo();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      Bo();
    }
  }
}
function cl(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        cl(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const Jn = /* @__PURE__ */ new WeakMap(), Os = /* @__PURE__ */ Symbol(
  ""
), mo = /* @__PURE__ */ Symbol(
  ""
), bn = /* @__PURE__ */ Symbol(
  ""
);
function tt(e, t, s) {
  if (St && Me) {
    let n = Jn.get(e);
    n || Jn.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new Go()), r.map = n, r.key = s), r.track();
  }
}
function Jt(e, t, s, n, r, o) {
  const i = Jn.get(e);
  if (!i) {
    yn++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (Wo(), t === "clear")
    i.forEach(a);
  else {
    const l = Q(e), c = l && gr(s);
    if (l && s === "length") {
      const u = Number(n);
      i.forEach((d, m) => {
        (m === "length" || m === bn || !gt(m) && m >= u) && a(d);
      });
    } else
      switch ((s !== void 0 || i.has(void 0)) && a(i.get(s)), c && a(i.get(bn)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(Os)), ps(e) && a(i.get(mo)));
          break;
        case "delete":
          l || (a(i.get(Os)), ps(e) && a(i.get(mo)));
          break;
        case "set":
          ps(e) && a(i.get(Os));
          break;
      }
  }
  Bo();
}
function hu(e, t) {
  const s = Jn.get(e);
  return s && s.get(t);
}
function Ps(e) {
  const t = /* @__PURE__ */ _e(e);
  return t === e || (tt(t, "iterate", bn), /* @__PURE__ */ ht(e)) ? t : /* @__PURE__ */ Wt(e) ? /* @__PURE__ */ Vt(e) ? t.map((s) => vs(yt(s))) : t.map(vs) : t.map(yt);
}
function wr(e) {
  return tt(e = /* @__PURE__ */ _e(e), "iterate", bn), e;
}
function Pt(e, t) {
  return /* @__PURE__ */ Wt(e) ? vs(/* @__PURE__ */ Vt(e) ? yt(t) : t) : yt(t);
}
const gu = {
  __proto__: null,
  [Symbol.iterator]() {
    return Dr(this, Symbol.iterator, (e) => Pt(this, e));
  },
  concat(...e) {
    return Ps(this).concat(
      ...e.map((t) => Q(t) ? Ps(t) : t)
    );
  },
  entries() {
    return Dr(this, "entries", (e) => (e[1] = Pt(this, e[1]), e));
  },
  every(e, t) {
    return Ht(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return Ht(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => Pt(this, n)),
      arguments
    );
  },
  find(e, t) {
    return Ht(
      this,
      "find",
      e,
      t,
      (s) => Pt(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return Ht(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return Ht(
      this,
      "findLast",
      e,
      t,
      (s) => Pt(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return Ht(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return Ht(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return Vr(this, "includes", e);
  },
  indexOf(...e) {
    return Vr(this, "indexOf", e);
  },
  join(e) {
    return Ps(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return Vr(this, "lastIndexOf", e);
  },
  map(e, t) {
    return Ht(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return tn(this, "pop");
  },
  push(...e) {
    return tn(this, "push", e);
  },
  reduce(e, ...t) {
    return Si(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return Si(this, "reduceRight", e, t);
  },
  shift() {
    return tn(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return Ht(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return tn(this, "splice", e);
  },
  toReversed() {
    return Ps(this).toReversed();
  },
  toSorted(e) {
    return Ps(this).toSorted(e);
  },
  toSpliced(...e) {
    return Ps(this).toSpliced(...e);
  },
  unshift(...e) {
    return tn(this, "unshift", e);
  },
  values() {
    return Dr(this, "values", (e) => Pt(this, e));
  }
};
function Dr(e, t, s) {
  const n = wr(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ ht(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => ki(o.next(), s), r !== ul[t] && Object.defineProperties(i, {
        return: {
          get() {
            const a = o.return;
            return typeof a == "function" ? a.bind(o) : a;
          }
        },
        throw: {
          get() {
            const a = o.throw;
            return typeof a == "function" ? a.bind(o) : a;
          }
        }
      }), i;
    }
    o._next = o.next, o.next = () => ki(o._next(), s);
  }
  return o;
}
function ki(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const ul = Array.prototype;
function Ht(e, t, s, n, r, o) {
  const i = wr(e), a = i !== e && !/* @__PURE__ */ ht(e), l = i[t];
  if (l !== ul[t]) {
    const d = l.apply(e, o);
    return a ? yt(d) : d;
  }
  let c = s;
  i !== e && (a ? c = function(d, m) {
    return s.call(this, Pt(e, d), m, e);
  } : s.length > 2 && (c = function(d, m) {
    return s.call(this, d, m, e);
  }));
  const u = l.call(i, c, n);
  return a && r ? r(u) : u;
}
function Si(e, t, s, n) {
  const r = wr(e), o = r !== e && !/* @__PURE__ */ ht(e);
  let i = s, a = !1;
  r !== e && (o ? (a = n.length === 0, i = function(c, u, d) {
    return a && (a = !1, c = Pt(e, c)), s.call(this, c, Pt(e, u), d, e);
  }) : s.length > 3 && (i = function(c, u, d) {
    return s.call(this, c, u, d, e);
  }));
  const l = r[t](i, ...n);
  return a ? Pt(e, l) : l;
}
function Vr(e, t, s) {
  const n = /* @__PURE__ */ _e(e);
  tt(n, "iterate", bn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ xr(s[0]) ? (s[0] = /* @__PURE__ */ _e(s[0]), n[t](...s)) : r;
}
function tn(e, t, s = []) {
  Ft(), Wo();
  const n = (/* @__PURE__ */ _e(e))[t].apply(e, s);
  return Bo(), Ut(), n;
}
const vu = /* @__PURE__ */ Do("__proto__,__v_isRef,__isVue"), dl = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(gt)
);
function yu(e) {
  gt(e) || (e = String(e));
  const t = /* @__PURE__ */ _e(this);
  return tt(t, "has", e), t.hasOwnProperty(e);
}
class fl {
  constructor(t = !1, s = !1) {
    this._isReadonly = t, this._isShallow = s;
  }
  get(t, s, n) {
    if (s === "__v_skip") return t.__v_skip;
    const r = this._isReadonly, o = this._isShallow;
    if (s === "__v_isReactive")
      return !r;
    if (s === "__v_isReadonly")
      return r;
    if (s === "__v_isShallow")
      return o;
    if (s === "__v_raw")
      return n === (r ? o ? Eu : gl : o ? hl : pl).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const i = Q(t);
    if (!r) {
      let l;
      if (i && (l = gu[s]))
        return l;
      if (s === "hasOwnProperty")
        return yu;
    }
    const a = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ Fe(t) ? t : n
    );
    if ((gt(s) ? dl.has(s) : vu(s)) || (r || tt(t, "get", s), o))
      return a;
    if (/* @__PURE__ */ Fe(a)) {
      const l = i && gr(s) ? a : a.value;
      return r && Ae(l) ? /* @__PURE__ */ ho(l) : l;
    }
    return Ae(a) ? r ? /* @__PURE__ */ ho(a) : /* @__PURE__ */ In(a) : a;
  }
}
class ml extends fl {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const i = Q(t) && gr(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ Wt(o);
      if (!/* @__PURE__ */ ht(n) && !/* @__PURE__ */ Wt(n) && (o = /* @__PURE__ */ _e(o), n = /* @__PURE__ */ _e(n)), !i && /* @__PURE__ */ Fe(o) && !/* @__PURE__ */ Fe(n))
        return c || (o.value = n), !0;
    }
    const a = i ? Number(s) < t.length : Se(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ Fe(t) ? t : r
    );
    return t === /* @__PURE__ */ _e(r) && l && (a ? $t(n, o) && Jt(t, "set", s, n) : Jt(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = Se(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && Jt(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!gt(s) || !dl.has(s)) && tt(t, "has", s), n;
  }
  ownKeys(t) {
    return tt(
      t,
      "iterate",
      Q(t) ? "length" : Os
    ), Reflect.ownKeys(t);
  }
}
class bu extends fl {
  constructor(t = !1) {
    super(!0, t);
  }
  set(t, s) {
    return !0;
  }
  deleteProperty(t, s) {
    return !0;
  }
}
const _u = /* @__PURE__ */ new ml(), wu = /* @__PURE__ */ new bu(), xu = /* @__PURE__ */ new ml(!0);
const po = (e) => e, jn = (e) => Reflect.getPrototypeOf(e);
function ku(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ _e(r), i = ps(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...n), u = s ? po : t ? vs : yt;
    return !t && tt(
      o,
      "iterate",
      l ? mo : Os
    ), Xe(
      // inheriting all iterator properties
      Object.create(c),
      {
        // iterator protocol
        next() {
          const { value: d, done: m } = c.next();
          return m ? { value: d, done: m } : {
            value: a ? [u(d[0]), u(d[1])] : u(d),
            done: m
          };
        }
      }
    );
  };
}
function $n(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function Su(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ _e(o), a = /* @__PURE__ */ _e(r);
      e || ($t(r, a) && tt(i, "get", r), tt(i, "get", a));
      const { has: l } = jn(i), c = t ? po : e ? vs : yt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && tt(/* @__PURE__ */ _e(r), "iterate", Os), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ _e(o), a = /* @__PURE__ */ _e(r);
      return e || ($t(r, a) && tt(i, "has", r), tt(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ _e(a), c = t ? po : e ? vs : yt;
      return !e && tt(l, "iterate", Os), a.forEach((u, d) => r.call(o, c(u), c(d), i));
    }
  };
  return Xe(
    s,
    e ? {
      add: $n("add"),
      set: $n("set"),
      delete: $n("delete"),
      clear: $n("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ _e(this), i = jn(o), a = /* @__PURE__ */ _e(r), l = !t && !/* @__PURE__ */ ht(r) && !/* @__PURE__ */ Wt(r) ? a : r;
        return i.has.call(o, l) || $t(r, l) && i.has.call(o, r) || $t(a, l) && i.has.call(o, a) || (o.add(l), Jt(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ ht(o) && !/* @__PURE__ */ Wt(o) && (o = /* @__PURE__ */ _e(o));
        const i = /* @__PURE__ */ _e(this), { has: a, get: l } = jn(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ _e(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? $t(o, u) && Jt(i, "set", r, o) : Jt(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ _e(this), { has: i, get: a } = jn(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ _e(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && Jt(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ _e(this), o = r.size !== 0, i = r.clear();
        return o && Jt(
          r,
          "clear",
          void 0,
          void 0
        ), i;
      }
    }
  ), [
    "keys",
    "values",
    "entries",
    Symbol.iterator
  ].forEach((r) => {
    s[r] = ku(r, e, t);
  }), s;
}
function Zo(e, t) {
  const s = Su(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    Se(s, r) && r in n ? s : n,
    r,
    o
  );
}
const Cu = {
  get: /* @__PURE__ */ Zo(!1, !1)
}, Au = {
  get: /* @__PURE__ */ Zo(!1, !0)
}, Ru = {
  get: /* @__PURE__ */ Zo(!0, !1)
};
const pl = /* @__PURE__ */ new WeakMap(), hl = /* @__PURE__ */ new WeakMap(), gl = /* @__PURE__ */ new WeakMap(), Eu = /* @__PURE__ */ new WeakMap();
function Ou(e) {
  switch (e) {
    case "Object":
    case "Array":
      return 1;
    case "Map":
    case "Set":
    case "WeakMap":
    case "WeakSet":
      return 2;
    default:
      return 0;
  }
}
// @__NO_SIDE_EFFECTS__
function In(e) {
  return /* @__PURE__ */ Wt(e) ? e : qo(
    e,
    !1,
    _u,
    Cu,
    pl
  );
}
// @__NO_SIDE_EFFECTS__
function vl(e) {
  return qo(
    e,
    !1,
    xu,
    Au,
    hl
  );
}
// @__NO_SIDE_EFFECTS__
function ho(e) {
  return qo(
    e,
    !0,
    wu,
    Ru,
    gl
  );
}
function qo(e, t, s, n, r) {
  if (!Ae(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = Ou(su(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? n : s
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Vt(e) {
  return /* @__PURE__ */ Wt(e) ? /* @__PURE__ */ Vt(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function Wt(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function ht(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function xr(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function _e(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ _e(t) : e;
}
function Ko(e) {
  return !Se(e, "__v_skip") && Object.isExtensible(e) && Ka(e, "__v_skip", !0), e;
}
const yt = (e) => Ae(e) ? /* @__PURE__ */ In(e) : e, vs = (e) => Ae(e) ? /* @__PURE__ */ ho(e) : e;
// @__NO_SIDE_EFFECTS__
function Fe(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function G(e) {
  return yl(e, !1);
}
// @__NO_SIDE_EFFECTS__
function mn(e) {
  return yl(e, !0);
}
function yl(e, t) {
  return /* @__PURE__ */ Fe(e) ? e : new Tu(e, t);
}
class Tu {
  constructor(t, s) {
    this.dep = new Go(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ _e(t), this._value = s ? t : yt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ ht(t) || /* @__PURE__ */ Wt(t);
    t = n ? t : /* @__PURE__ */ _e(t), $t(t, s) && (this._rawValue = t, this._value = n ? t : yt(t), this.dep.trigger());
  }
}
function C(e) {
  return /* @__PURE__ */ Fe(e) ? e.value : e;
}
function Vs(e) {
  return de(e) ? e() : C(e);
}
const Iu = {
  get: (e, t, s) => t === "__v_raw" ? e : C(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ Fe(r) && !/* @__PURE__ */ Fe(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function bl(e) {
  return /* @__PURE__ */ Vt(e) ? e : new Proxy(e, Iu);
}
// @__NO_SIDE_EFFECTS__
function Nu(e) {
  const t = Q(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = Mu(e, s);
  return t;
}
class Pu {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = gt(s) ? s : String(s), this._raw = /* @__PURE__ */ _e(t);
    let r = !0, o = t;
    if (!Q(t) || gt(this._key) || !gr(this._key))
      do
        r = !/* @__PURE__ */ xr(o) || /* @__PURE__ */ ht(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = C(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ Fe(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ Fe(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return hu(this._raw, this._key);
  }
}
function Mu(e, t, s) {
  return new Pu(e, t, s);
}
class ju {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new Go(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = yn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Me !== this)
      return rl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return al(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function $u(e, t, s = !1) {
  let n, r;
  return de(e) ? n = e : (n = e.get, r = e.set), new ju(n, r, s);
}
const zn = {}, Qn = /* @__PURE__ */ new WeakMap();
let As;
function zu(e, t = !1, s = As) {
  if (s) {
    let n = Qn.get(s);
    n || Qn.set(s, n = []), n.push(e);
  }
}
function Du(e, t, s = Ne) {
  const { immediate: n, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = s, c = (P) => r ? P : /* @__PURE__ */ ht(P) || r === !1 || r === 0 ? Qt(P, 1) : Qt(P);
  let u, d, m, h, k = !1, w = !1;
  if (/* @__PURE__ */ Fe(e) ? (d = () => e.value, k = /* @__PURE__ */ ht(e)) : /* @__PURE__ */ Vt(e) ? (d = () => c(e), k = !0) : Q(e) ? (w = !0, k = e.some((P) => /* @__PURE__ */ Vt(P) || /* @__PURE__ */ ht(P)), d = () => e.map((P) => {
    if (/* @__PURE__ */ Fe(P))
      return P.value;
    if (/* @__PURE__ */ Vt(P))
      return c(P);
    if (de(P))
      return l ? l(P, 2) : P();
  })) : de(e) ? t ? d = l ? () => l(e, 2) : e : d = () => {
    if (m) {
      Ft();
      try {
        m();
      } finally {
        Ut();
      }
    }
    const P = As;
    As = u;
    try {
      return l ? l(e, 3, [h]) : e(h);
    } finally {
      As = P;
    }
  } : d = Dt, t && r) {
    const P = d, J = r === !0 ? 1 / 0 : r;
    d = () => Qt(P(), J);
  }
  const z = Uo(), N = () => {
    u.stop(), z && z.active && Vo(z.effects, u);
  };
  if (o && t) {
    const P = t;
    t = (...J) => {
      try {
        return P(...J);
      } finally {
        N();
      }
    };
  }
  let g = w ? new Array(e.length).fill(zn) : zn;
  const E = (P) => {
    if (!(!(u.flags & 1) || !u.dirty && !P))
      if (t) {
        const J = u.run();
        if (P || r || k || (w ? J.some((ve, oe) => $t(ve, g[oe])) : $t(J, g))) {
          const ve = As;
          Ft();
          try {
            m && m(), As = u;
            const oe = [
              J,
              // pass undefined as the old value when it's changed for the first time
              g === zn ? void 0 : w && g[0] === zn ? [] : g,
              h
            ];
            g = J, l ? l(t, 3, oe) : (
              // @ts-expect-error
              t(...oe)
            );
          } finally {
            As = ve, Ut();
          }
        }
      } else
        u.run();
  };
  return a && a(E), u = new sl(d), u.scheduler = i ? () => i(E, !1) : E, h = (P) => zu(P, !1, u), m = u.onStop = () => {
    const P = Qn.get(u);
    if (P) {
      if (l)
        l(P, 4);
      else
        for (const J of P) J();
      Qn.delete(u);
    }
  }, t ? n ? E(!0) : g = u.run() : i ? i(E.bind(null, !0), !0) : u.run(), N.pause = u.pause.bind(u), N.resume = u.resume.bind(u), N.stop = N, N;
}
function Qt(e, t = 1 / 0, s) {
  if (t <= 0 || !Ae(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ Fe(e))
    Qt(e.value, t, s);
  else if (Q(e))
    for (let n = 0; n < e.length; n++)
      Qt(e[n], t, s);
  else if (ss(e) || ps(e))
    e.forEach((n) => {
      Qt(n, t, s);
    });
  else if (qa(e)) {
    for (const n in e)
      Qt(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && Qt(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function Nn(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (r) {
    kr(r, t, s);
  }
}
function Ct(e, t, s, n) {
  if (de(e)) {
    const r = Nn(e, t, s, n);
    return r && Ga(r) && r.catch((o) => {
      kr(o, t, s);
    }), r;
  }
  if (Q(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(Ct(e[o], t, s, n));
    return r;
  }
}
function kr(e, t, s, n = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || Ne;
  if (t) {
    let a = t.parent;
    const l = t.proxy, c = `https://vuejs.org/error-reference/#runtime-${s}`;
    for (; a; ) {
      const u = a.ec;
      if (u) {
        for (let d = 0; d < u.length; d++)
          if (u[d](e, l, c) === !1)
            return;
      }
      a = a.parent;
    }
    if (o) {
      Ft(), Nn(o, null, 10, [
        e,
        l,
        c
      ]), Ut();
      return;
    }
  }
  Vu(e, s, r, n, i);
}
function Vu(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const it = [];
let kt = -1;
const Mt = [];
let us = null, $s = 0;
const _l = /* @__PURE__ */ Promise.resolve();
let Yn = null;
function Sr(e) {
  const t = Yn || _l;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function Lu(e) {
  let t = kt + 1, s = it.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = it[n], o = _n(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function Jo(e) {
  if (!(e.flags & 1)) {
    const t = _n(e), s = it[it.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= _n(s) ? it.push(e) : it.splice(Lu(t), 0, e), e.flags |= 1, wl();
  }
}
function wl() {
  Yn || (Yn = _l.then(Sl));
}
function Fu(e) {
  if (!Q(e))
    us && e.id === -1 ? us.splice($s + 1, 0, e) : e.flags & 1 || (Mt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Mt.push(e[t]);
  wl();
}
function xl(e, t, s, n = kt + 1) {
  for (; n < it.length; n++) {
    const r = it[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      it.splice(n, 1), n = e ? n - 1 : kt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function kl(e, t, s = 0) {
  if (Mt.length) {
    let n = Mt, r = 0;
    if (t) {
      n = [];
      for (let i = 0; i < Mt.length; i++) {
        const a = Mt[i];
        (a.i !== void 0 ? !a.i || a.i.uid < s : t.has(a)) ? Mt[r++] = a : n.push(a);
      }
    }
    const o = [...new Set(n)].sort((i, a) => _n(i) - _n(a));
    if (Mt.length = r, us) {
      for (let i = 0; i < o.length; i++)
        us.push(o[i]);
      return;
    }
    for (us = o, $s = 0; $s < us.length; $s++) {
      const i = us[$s];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    us = null, $s = 0;
  }
}
let Lr = !1;
function Uu(e, t) {
  if (Lr) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Mt);
  e(), Lr = !0;
  try {
    xl(void 0, t), kl(void 0, s, t);
  } finally {
    Lr = !1;
  }
}
const _n = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function Sl(e) {
  try {
    for (kt = 0; kt < it.length; kt++) {
      const t = it[kt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), Nn(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; kt < it.length; kt++) {
      const t = it[kt];
      t && (t.flags &= -2);
    }
    kt = -1, it.length = 0, kl(), Yn = null, (it.length || Mt.length) && Sl();
  }
}
let Qe = null, Cl = null;
function Xn(e) {
  const t = Qe;
  return Qe = e, Cl = e && e.type.__scopeId || null, t;
}
function ae(e, t = Qe, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && nr(-1);
    const o = Xn(t), i = ts.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = ts.length; l > i; l--) si();
      Xn(o), n._d && nr(1);
    }
    return a;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Xt(e, t) {
  if (Qe === null)
    return e;
  const s = Tr(Qe), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = Ne] = t[r];
    o && (de(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && Qt(i), n.push({
      dir: o,
      instance: s,
      value: i,
      oldValue: void 0,
      arg: a,
      modifiers: l
    }));
  }
  return e;
}
function xs(e, t, s, n) {
  const r = e.dirs, o = t && t.dirs;
  for (let i = 0; i < r.length; i++) {
    const a = r[i];
    o && (a.oldValue = o[i].value);
    let l = a.dir[n];
    l && (Ft(), Ct(l, s, 8, [
      e.el,
      a,
      e,
      t
    ]), Ut());
  }
}
function Zn(e, t) {
  if (st) {
    let s = st.provides;
    const n = st.parent && st.parent.provides;
    n === s && (s = st.provides = Object.create(n)), s[e] = t;
  }
}
function dt(e, t, s = !1) {
  const n = Or();
  if (n || Ts) {
    let r = Ts ? Ts._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && de(t) ? t.call(n && n.proxy) : t;
  }
}
function Qo() {
  return !!(Or() || Ts);
}
const Wu = /* @__PURE__ */ Symbol.for("v-scx"), Bu = () => dt(Wu);
function Hu(e, t) {
  return Yo(e, null, t);
}
function es(e, t, s) {
  return Yo(e, t, s);
}
function Yo(e, t, s = Ne) {
  const { immediate: n, deep: r, flush: o, once: i } = s, a = Xe({}, s), l = t && n || !t && o !== "post";
  let c;
  if (kn) {
    if (o === "sync") {
      const h = Bu();
      c = h.__watcherHandles || (h.__watcherHandles = []);
    } else if (!l) {
      const h = () => {
      };
      return h.stop = Dt, h.resume = Dt, h.pause = Dt, h;
    }
  }
  const u = st;
  a.call = (h, k, w) => Ct(h, u, k, w);
  let d = !1;
  o === "post" ? a.scheduler = (h) => {
    h.i = u, ut(h, u && u.suspense);
  } : o !== "sync" && (d = !0, a.scheduler = (h, k) => {
    k ? h() : Jo(h);
  }), a.augmentJob = (h) => {
    t && (h.flags |= 4), d && (h.flags |= 2, u && (h.id = u.uid, h.i = u));
  };
  const m = Du(e, t, a);
  return kn && (c ? c.push(m) : l && m()), m;
}
function Gu(e, t, s) {
  const n = this.proxy, r = Ve(e) ? e.includes(".") ? Al(n, e) : () => n[e] : e.bind(n, n);
  let o;
  de(t) ? o = t : (o = t.handler, s = t);
  const i = Pn(this), a = Yo(r, o.bind(n), s);
  return i(), a;
}
function Al(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const Zu = /* @__PURE__ */ Symbol("_vte"), Cr = (e) => e.__isTeleport, Fr = /* @__PURE__ */ Symbol("_leaveCb");
function qu(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const s of e)
      if (s.type !== bt) {
        t = s;
        break;
      }
  }
  return t;
}
function Rl(e) {
  if (!Xo(e))
    return Cr(e.type) && e.children ? qu(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && de(s.default))
      return s.default();
  }
}
function er(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    er(
      Cr(s.type) && Rl(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === ze && Q(e.children)) {
    const s = Dl(e.children, !1);
    s && er(s, t);
  }
}
function go(e) {
  if (e.component)
    return go(e.component.subTree);
  if (e.type === ze) {
    const t = Q(e.children) && Dl(e.children, !1);
    return t ? go(t) : void 0;
  }
  if (e.type !== bt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function vt(e, t) {
  return de(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    Xe({ name: e.name }, t, { setup: e })
  ) : e;
}
function El(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function Ci(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const tr = /* @__PURE__ */ new WeakMap();
function pn(e, t, s, n, r = !1) {
  if (Q(e)) {
    e.forEach(
      (w, z) => pn(
        w,
        t && (Q(t) ? t[z] : t),
        s,
        n,
        r
      )
    );
    return;
  }
  if (Ls(n) && !r) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && pn(e, t, s, n.component.subTree);
    return;
  }
  const o = n.shapeFlag & 4 ? Tr(n.component) : n.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === Ne ? a.refs = {} : a.refs, d = a.setupState, m = /* @__PURE__ */ _e(d), h = d === Ne ? Ha : (w) => Ci(u, w) ? !1 : Se(m, w), k = (w, z) => !(z && Ci(u, z));
  if (c != null && c !== l) {
    if (Ai(t), Ve(c))
      u[c] = null, h(c) && (d[c] = null);
    else if (/* @__PURE__ */ Fe(c)) {
      const w = t;
      k(c, w.k) && (c.value = null), w.k && (u[w.k] = null);
    }
  }
  if (de(l))
    Nn(l, a, 12, [i, u]);
  else {
    const w = Ve(l), z = /* @__PURE__ */ Fe(l);
    if (w || z) {
      const N = () => {
        if (e.f) {
          const g = w ? h(l) ? d[l] : u[l] : k() || !e.k ? l.value : u[e.k];
          if (r)
            Q(g) && Vo(g, o);
          else if (Q(g))
            g.includes(o) || g.push(o);
          else if (w)
            u[l] = [o], h(l) && (d[l] = u[l]);
          else {
            const E = [o];
            k(l, e.k) && (l.value = E), e.k && (u[e.k] = E);
          }
        } else w ? (u[l] = i, h(l) && (d[l] = i)) : z && (k(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const g = () => {
          N(), tr.delete(e);
        };
        g.id = -1, tr.set(e, g), ut(g, s);
      } else
        Ai(e), N();
    }
  }
}
function Ai(e) {
  const t = tr.get(e);
  t && (t.flags |= 8, tr.delete(e));
}
_r().requestIdleCallback;
_r().cancelIdleCallback;
const Ls = (e) => !!e.type.__asyncLoader, Xo = (e) => e.type.__isKeepAlive;
function Ku(e, t) {
  Ol(e, "a", t);
}
function Ju(e, t) {
  Ol(e, "da", t);
}
function Ol(e, t, s = st) {
  const n = e.__wdc || (e.__wdc = () => {
    let r = s;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (Ar(t, n, s), s) {
    let r = s.parent;
    for (; r && r.parent; )
      Xo(r.parent.vnode) && Qu(n, t, s, r), r = r.parent;
  }
}
function Qu(e, t, s, n) {
  const r = Ar(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  Tl(() => {
    Vo(n[t], r);
  }, s);
}
function Ar(e, t, s = st, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Ft();
      const a = Pn(s), l = Ct(t, s, e, i);
      return a(), Ut(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const os = (e) => (t, s = st) => {
  (!kn || e === "sp") && Ar(e, (...n) => t(...n), s);
}, Yu = os("bm"), Qs = os("m"), Xu = os(
  "bu"
), ed = os("u"), td = os(
  "bum"
), Tl = os("um"), sd = os(
  "sp"
), nd = os("rtg"), rd = os("rtc");
function od(e, t = st) {
  Ar("ec", e, t);
}
const id = "components", Il = /* @__PURE__ */ Symbol.for("v-ndc");
function ad(e) {
  return Ve(e) ? ld(id, e, !1) || e : e || Il;
}
function ld(e, t, s = !0, n = !1) {
  const r = Qe || st;
  if (r) {
    const o = r.type;
    {
      const a = Hd(
        o,
        !1
      );
      if (a && (a === t || a === lt(t) || a === yr(lt(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      Ri(r[e] || o[e], t) || // global registration
      Ri(r.appContext[e], t)
    );
    return !i && n ? o : i;
  }
}
function Ri(e, t) {
  return e && (e[t] || e[lt(t)] || e[yr(lt(t))]);
}
function Ys(e, t, s, n) {
  let r;
  const o = s, i = Q(e);
  if (i || Ve(e)) {
    const a = i && /* @__PURE__ */ Vt(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ ht(e), c = /* @__PURE__ */ Wt(e), e = wr(e)), r = new Array(e.length);
    for (let u = 0, d = e.length; u < d; u++)
      r[u] = t(
        l ? c ? vs(yt(e[u])) : yt(e[u]) : e[u],
        u,
        void 0,
        o
      );
  } else if (typeof e == "number")
    if (!Number.isInteger(e) || e < 0)
      r = [];
    else {
      r = new Array(e);
      for (let a = 0; a < e; a++)
        r[a] = t(a + 1, a, void 0, o);
    }
  else if (Ae(e))
    if (e[Symbol.iterator])
      r = Array.from(
        e,
        (a, l) => t(a, l, void 0, o)
      );
    else {
      const a = Object.keys(e);
      r = new Array(a.length);
      for (let l = 0, c = a.length; l < c; l++) {
        const u = a[l];
        r[l] = t(e[u], u, l, o);
      }
    }
  else
    r = [];
  return r;
}
function Nl(e, t, s, n, r, o) {
  if (s == null && (s = {}), Qe.ce || Qe.parent && Ls(Qe.parent) && Qe.parent.ce) {
    const c = s, u = Object.keys(c).length > 0;
    return X(), at(
      ze,
      null,
      [W("slot", c, n)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = ts.length;
  X();
  let l;
  try {
    const c = i && Pl(i(s)), u = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = at(
      ze,
      {
        key: (u && !gt(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = ts.length; u > a; u--) si();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function Pl(e) {
  return e.some((t) => Fs(t) ? !(t.type === bt || t.type === ze && !Pl(t.children)) : !0) ? e : null;
}
const vo = (e) => e ? ec(e) ? Tr(e) : vo(e.parent) : null, hn = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ Xe(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => vo(e.parent),
    $root: (e) => vo(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => jl(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      Jo(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = Sr.bind(e.proxy)),
    $watch: (e) => Gu.bind(e)
  })
), Ur = (e, t) => e !== Ne && !e.__isScriptSetup && Se(e, t), cd = {
  get({ _: e }, t) {
    if (t === "__v_skip")
      return !0;
    const { ctx: s, setupState: n, data: r, props: o, accessCache: i, type: a, appContext: l } = e;
    if (t[0] !== "$") {
      const m = i[t];
      if (m !== void 0)
        switch (m) {
          case 1:
            return n[t];
          case 2:
            return r[t];
          case 4:
            return s[t];
          case 3:
            return o[t];
        }
      else {
        if (Ur(n, t))
          return i[t] = 1, n[t];
        if (r !== Ne && Se(r, t))
          return i[t] = 2, r[t];
        if (Se(o, t))
          return i[t] = 3, o[t];
        if (s !== Ne && Se(s, t))
          return i[t] = 4, s[t];
        yo && (i[t] = 0);
      }
    }
    const c = hn[t];
    let u, d;
    if (c)
      return t === "$attrs" && tt(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (u = a.__cssModules) && (u = u[t])
    )
      return u;
    if (s !== Ne && Se(s, t))
      return i[t] = 4, s[t];
    if (
      // global properties
      d = l.config.globalProperties, Se(d, t)
    )
      return d[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: r, ctx: o } = e;
    return Ur(r, t) ? (r[t] = s, !0) : n !== Ne && Se(n, t) ? (n[t] = s, !0) : Se(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(s[a] || e !== Ne && a[0] !== "$" && Se(e, a) || Ur(t, a) || Se(o, a) || Se(n, a) || Se(hn, a) || Se(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : Se(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function Ei(e) {
  return Q(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let yo = !0;
function ud(e) {
  const t = jl(e), s = e.proxy, n = e.ctx;
  yo = !1, t.beforeCreate && Oi(t.beforeCreate, e, "bc");
  const {
    // state
    data: r,
    computed: o,
    methods: i,
    watch: a,
    provide: l,
    inject: c,
    // lifecycle
    created: u,
    beforeMount: d,
    mounted: m,
    beforeUpdate: h,
    updated: k,
    activated: w,
    deactivated: z,
    beforeDestroy: N,
    beforeUnmount: g,
    destroyed: E,
    unmounted: P,
    render: J,
    renderTracked: ve,
    renderTriggered: oe,
    errorCaptured: _,
    serverPrefetch: V,
    // public API
    expose: ce,
    inheritAttrs: xe,
    // assets
    components: ke,
    directives: Te,
    filters: D
  } = t;
  if (c && dd(c, n, null), i)
    for (const q in i) {
      const fe = i[q];
      de(fe) && (n[q] = fe.bind(s));
    }
  if (r) {
    const q = r.call(s, s);
    Ae(q) && (e.data = /* @__PURE__ */ In(q));
  }
  if (yo = !0, o)
    for (const q in o) {
      const fe = o[q], Pe = de(fe) ? fe.bind(s, s) : de(fe.get) ? fe.get.bind(s, s) : Dt, $ = !de(fe) && de(fe.set) ? fe.set.bind(s) : Dt, nt = Oe({
        get: Pe,
        set: $
      });
      Object.defineProperty(n, q, {
        enumerable: !0,
        configurable: !0,
        get: () => nt.value,
        set: (Ue) => nt.value = Ue
      });
    }
  if (a)
    for (const q in a)
      Ml(a[q], n, s, q);
  if (l) {
    const q = de(l) ? l.call(s) : l;
    Reflect.ownKeys(q).forEach((fe) => {
      Zn(fe, q[fe]);
    });
  }
  u && Oi(u, e, "c");
  function ne(q, fe) {
    Q(fe) ? fe.forEach((Pe) => q(Pe.bind(s))) : fe && q(fe.bind(s));
  }
  if (ne(Yu, d), ne(Qs, m), ne(Xu, h), ne(ed, k), ne(Ku, w), ne(Ju, z), ne(od, _), ne(rd, ve), ne(nd, oe), ne(td, g), ne(Tl, P), ne(sd, V), Q(ce))
    if (ce.length) {
      const q = e.exposed || (e.exposed = {});
      ce.forEach((fe) => {
        Object.defineProperty(q, fe, {
          get: () => s[fe],
          set: (Pe) => s[fe] = Pe,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  J && e.render === Dt && (e.render = J), xe != null && (e.inheritAttrs = xe), ke && (e.components = ke), Te && (e.directives = Te), V && El(e);
}
function dd(e, t, s = Dt) {
  Q(e) && (e = bo(e));
  for (const n in e) {
    const r = e[n];
    let o;
    Ae(r) ? "default" in r ? o = dt(
      r.from || n,
      r.default,
      !0
    ) : o = dt(r.from || n) : o = dt(r), /* @__PURE__ */ Fe(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[n] = o;
  }
}
function Oi(e, t, s) {
  Ct(
    Q(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function Ml(e, t, s, n) {
  let r = n.includes(".") ? Al(s, n) : () => s[n];
  if (Ve(e)) {
    const o = t[e];
    de(o) && es(r, o);
  } else if (de(e))
    es(r, e.bind(s));
  else if (Ae(e))
    if (Q(e))
      e.forEach((o) => Ml(o, t, s, n));
    else {
      const o = de(e.handler) ? e.handler.bind(s) : t[e.handler];
      de(o) && es(r, o, e);
    }
}
function jl(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !s && !n ? l = t : (l = {}, r.length && r.forEach(
    (c) => sr(l, c, i, !0)
  ), sr(l, t, i)), Ae(t) && o.set(t, l), l;
}
function sr(e, t, s, n = !1) {
  const { mixins: r, extends: o } = t;
  o && sr(e, o, s, !0), r && r.forEach(
    (i) => sr(e, i, s, !0)
  );
  for (const i in t)
    if (!(n && i === "expose")) {
      const a = fd[i] || s && s[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const fd = {
  data: Ti,
  props: Ii,
  emits: Ii,
  // objects
  methods: an,
  computed: an,
  // lifecycle
  beforeCreate: rt,
  created: rt,
  beforeMount: rt,
  mounted: rt,
  beforeUpdate: rt,
  updated: rt,
  beforeDestroy: rt,
  beforeUnmount: rt,
  destroyed: rt,
  unmounted: rt,
  activated: rt,
  deactivated: rt,
  errorCaptured: rt,
  serverPrefetch: rt,
  // assets
  components: an,
  directives: an,
  // watch
  watch: pd,
  // provide / inject
  provide: Ti,
  inject: md
};
function Ti(e, t) {
  return t ? e ? function() {
    return Xe(
      de(e) ? e.call(this, this) : e,
      de(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function md(e, t) {
  return an(bo(e), bo(t));
}
function bo(e) {
  if (Q(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function rt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function an(e, t) {
  return e ? Xe(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function Ii(e, t) {
  return e ? Q(e) && Q(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : Xe(
    /* @__PURE__ */ Object.create(null),
    Ei(e),
    Ei(t ?? {})
  ) : t;
}
function pd(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = Xe(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = rt(e[n], t[n]);
  return s;
}
function $l() {
  return {
    app: null,
    config: {
      isNativeTag: Ha,
      performance: !1,
      globalProperties: {},
      optionMergeStrategies: {},
      errorHandler: void 0,
      warnHandler: void 0,
      compilerOptions: {}
    },
    mixins: [],
    components: {},
    directives: {},
    provides: /* @__PURE__ */ Object.create(null),
    optionsCache: /* @__PURE__ */ new WeakMap(),
    propsCache: /* @__PURE__ */ new WeakMap(),
    emitsCache: /* @__PURE__ */ new WeakMap()
  };
}
let hd = 0;
function gd(e, t) {
  return function(n, r = null) {
    de(n) || (n = Xe({}, n)), r != null && !Ae(r) && (r = null);
    const o = $l(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: hd++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: Zd,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...d) {
        return i.has(u) || (u && de(u.install) ? (i.add(u), u.install(c, ...d)) : de(u) && (i.add(u), u(c, ...d))), c;
      },
      mixin(u) {
        return o.mixins.includes(u) || o.mixins.push(u), c;
      },
      component(u, d) {
        return d ? (o.components[u] = d, c) : o.components[u];
      },
      directive(u, d) {
        return d ? (o.directives[u] = d, c) : o.directives[u];
      },
      mount(u, d, m) {
        if (!l) {
          const h = c._ceVNode || W(n, r);
          return h.appContext = o, m === !0 ? m = "svg" : m === !1 && (m = void 0), e(h, u, m), l = !0, c._container = u, u.__vue_app__ = c, Tr(h.component);
        }
      },
      onUnmount(u) {
        a.push(u);
      },
      unmount() {
        l && (Ct(
          a,
          c._instance,
          16
        ), e(null, c._container), delete c._container.__vue_app__);
      },
      provide(u, d) {
        return o.provides[u] = d, c;
      },
      runWithContext(u) {
        const d = Ts;
        Ts = c;
        try {
          return u();
        } finally {
          Ts = d;
        }
      }
    };
    return c;
  };
}
let Ts = null;
const vd = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${lt(t)}Modifiers`] || e[`${_s(t)}Modifiers`];
function yd(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || Ne;
  let r = s;
  const o = t.startsWith("update:"), i = o && vd(n, t.slice(7));
  i && (i.trim && (r = s.map((u) => Ve(u) ? u.trim() : u)), i.number && (r = r.map(br)));
  let a, l = n[a = jr(t)] || // also try camelCase event handler (#2249)
  n[a = jr(lt(t))];
  !l && o && (l = n[a = jr(_s(t))]), l && Ct(
    l,
    e,
    6,
    r
  );
  const c = n[a + "Once"];
  if (c) {
    if (!e.emitted)
      e.emitted = {};
    else if (e.emitted[a])
      return;
    e.emitted[a] = !0, Ct(
      c,
      e,
      6,
      r
    );
  }
}
const bd = /* @__PURE__ */ new WeakMap();
function zl(e, t, s = !1) {
  const n = s ? bd : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!de(e)) {
    const l = (c) => {
      const u = zl(c, t, !0);
      u && (a = !0, Xe(i, u));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (Ae(e) && n.set(e, null), null) : (Q(o) ? o.forEach((l) => i[l] = null) : Xe(i, o), Ae(e) && n.set(e, i), i);
}
function Rr(e, t) {
  return !e || !pr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), Se(e, t[0].toLowerCase() + t.slice(1)) || Se(e, _s(t)) || Se(e, t));
}
function Ni(e) {
  const {
    type: t,
    vnode: s,
    proxy: n,
    withProxy: r,
    propsOptions: [o],
    slots: i,
    attrs: a,
    emit: l,
    render: c,
    renderCache: u,
    props: d,
    data: m,
    setupState: h,
    ctx: k,
    inheritAttrs: w
  } = e, z = Xn(e);
  let N, g;
  try {
    if (s.shapeFlag & 4) {
      const P = r || n, J = P;
      N = jt(
        c.call(
          J,
          P,
          u,
          d,
          h,
          m,
          k
        )
      ), g = a;
    } else {
      const P = t;
      N = jt(
        P.length > 1 ? P(
          d,
          { attrs: a, slots: i, emit: l }
        ) : P(
          d,
          null
        )
      ), g = t.props ? a : _d(a);
    }
  } catch (P) {
    ts.length = 0, kr(P, e, 1), N = W(bt);
  }
  let E = N;
  if (g && w !== !1) {
    const P = Object.keys(g), { shapeFlag: J } = E;
    P.length && J & 7 && (o && P.some(hr) && (g = wd(
      g,
      o
    )), E = Us(E, g, !1, !0));
  }
  if (s.dirs && (E = Us(E, null, !1, !0), E.dirs = E.dirs ? E.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const P = Cr(E.type) && Rl(E) || E;
    er(P, s.transition);
  }
  return N = E, Xn(z), N;
}
function Dl(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const r = e[n];
    if (Fs(r)) {
      if (r.type !== bt || r.children === "v-if") {
        if (s)
          return;
        s = r;
      }
    } else
      return;
  }
  return s;
}
const _d = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || pr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, wd = (e, t) => {
  const s = {};
  for (const n in e)
    (!hr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function xd(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? Pi(n, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let d = 0; d < u.length; d++) {
        const m = u[d];
        if (Vl(i, n, m) && !Rr(c, m))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : n === i ? !1 : n ? i ? Pi(n, i, c) : !0 : !!i;
  return !1;
}
function Pi(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!Se(e, o) || Vl(t, e, o) && !Rr(s, o))
      return !0;
  }
  return !1;
}
function Vl(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && Ae(n) && Ae(r) ? !ns(n, r) : n !== r;
}
function kd({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const Ll = {}, Fl = () => Object.create(Ll), Ul = (e) => Object.getPrototypeOf(e) === Ll;
function Sd(e, t, s, n = !1) {
  const r = {}, o = Fl();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), Wl(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ vl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function Cd(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ _e(r), [l] = e.propsOptions;
  let c = !1;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (n || i > 0) && !(i & 16)
  ) {
    if (i & 8) {
      const u = e.vnode.dynamicProps;
      for (let d = 0; d < u.length; d++) {
        let m = u[d];
        if (Rr(e.emitsOptions, m))
          continue;
        const h = t[m];
        if (l)
          if (Se(o, m))
            h !== o[m] && (o[m] = h, c = !0);
          else {
            const k = lt(m);
            r[k] = _o(
              l,
              a,
              k,
              h,
              e,
              !1
            );
          }
        else
          h !== o[m] && (o[m] = h, c = !0);
      }
    }
  } else {
    Wl(e, t, r, o) && (c = !0);
    let u;
    for (const d in a)
      (!t || // for camelCase
      !Se(t, d) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = _s(d)) === d || !Se(t, u))) && (l ? s && // for camelCase
      (s[d] !== void 0 || // for kebab-case
      s[u] !== void 0) && (r[d] = _o(
        l,
        a,
        d,
        void 0,
        e,
        !0
      )) : delete r[d]);
    if (o !== a)
      for (const d in o)
        (!t || !Se(t, d)) && (delete o[d], c = !0);
  }
  c && Jt(e.attrs, "set", "");
}
function Wl(e, t, s, n) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (un(l))
        continue;
      const c = t[l];
      let u;
      r && Se(r, u = lt(l)) ? !o || !o.includes(u) ? s[u] = c : (a || (a = {}))[u] = c : Rr(e.emitsOptions, l) || (!(l in n) || c !== n[l]) && (n[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ _e(s), c = a || Ne;
    for (let u = 0; u < o.length; u++) {
      const d = o[u];
      s[d] = _o(
        r,
        l,
        d,
        c[d],
        e,
        !Se(c, d)
      );
    }
  }
  return i;
}
function _o(e, t, s, n, r, o) {
  const i = e[s];
  if (i != null) {
    const a = Se(i, "default");
    if (a && n === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && de(l)) {
        const { propsDefaults: c } = r;
        if (s in c)
          n = c[s];
        else {
          const u = Pn(r);
          n = c[s] = l.call(
            null,
            t
          ), u();
        }
      } else
        n = l;
      r.ce && r.ce._setProp(s, n);
    }
    i[
      0
      /* shouldCast */
    ] && (o && !a ? n = !1 : i[
      1
      /* shouldCastTrue */
    ] && (n === "" || n === _s(s)) && (n = !0));
  }
  return n;
}
const Ad = /* @__PURE__ */ new WeakMap();
function Bl(e, t, s = !1) {
  const n = s ? Ad : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!de(e)) {
    const u = (d) => {
      l = !0;
      const [m, h] = Bl(d, t, !0);
      Xe(i, m), h && a.push(...h);
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return Ae(e) && n.set(e, Rs), Rs;
  if (Q(o))
    for (let u = 0; u < o.length; u++) {
      const d = lt(o[u]);
      Mi(d) && (i[d] = Ne);
    }
  else if (o)
    for (const u in o) {
      const d = lt(u);
      if (Mi(d)) {
        const m = o[u], h = i[d] = Q(m) || de(m) ? { type: m } : Xe({}, m), k = h.type;
        let w = !1, z = !0;
        if (Q(k))
          for (let N = 0; N < k.length; ++N) {
            const g = k[N], E = de(g) && g.name;
            if (E === "Boolean") {
              w = !0;
              break;
            } else E === "String" && (z = !1);
          }
        else
          w = de(k) && k.name === "Boolean";
        h[
          0
          /* shouldCast */
        ] = w, h[
          1
          /* shouldCastTrue */
        ] = z, (w || Se(h, "default")) && a.push(d);
      }
    }
  const c = [i, a];
  return Ae(e) && n.set(e, c), c;
}
function Mi(e) {
  return e[0] !== "$" && !un(e);
}
const ei = (e) => e === "_" || e === "_ctx" || e === "$stable", ti = (e) => Q(e) ? e.map(jt) : [jt(e)], Rd = (e, t, s) => {
  if (t._n)
    return t;
  const n = ae((...r) => ti(t(...r)), s);
  return n._c = !1, n;
}, Hl = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (ei(r)) continue;
    const o = e[r];
    if (de(o))
      t[r] = Rd(r, o, n);
    else if (o != null) {
      const i = ti(o);
      t[r] = () => i;
    }
  }
}, Gl = (e, t) => {
  const s = ti(t);
  e.slots.default = () => s;
}, Zl = (e, t, s) => {
  for (const n in t)
    (s || !ei(n)) && (e[n] = t[n]);
}, Ed = (e, t, s) => {
  const n = e.slots = Fl();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (Zl(n, t, s), s && Ka(n, "_", r, !0)) : Hl(t, n);
  } else t && Gl(e, t);
}, Od = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, i = Ne;
  if (n.shapeFlag & 32) {
    const a = t._;
    a ? s && a === 1 ? o = !1 : Zl(r, t, s) : (o = !t.$stable, Hl(t, r)), i = t;
  } else t && (Gl(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !ei(a) && i[a] == null && delete r[a];
}, ut = Md;
function Td(e) {
  return Id(e);
}
function Id(e, t) {
  const s = _r();
  s.__VUE__ = !0;
  const {
    insert: n,
    remove: r,
    patchProp: o,
    createElement: i,
    createText: a,
    createComment: l,
    setText: c,
    setElementText: u,
    parentNode: d,
    nextSibling: m,
    setScopeId: h = Dt,
    insertStaticContent: k
  } = e, w = (f, p, v, b = null, x = null, A = null, O = void 0, j = null, M = !!p.dynamicChildren) => {
    if (f === p)
      return;
    f && !sn(f, p) && (b = S(f), Ue(f, x, A, !0), f = null), p.patchFlag === -2 && (M = !1, p.dynamicChildren = null), p.dynamicChildren && f && f.dynamicChildren && f.dynamicChildren.hasOnce && (p.dynamicChildren === Rs && (p.dynamicChildren = []), p.dynamicChildren.hasOnce = !0);
    const { type: R, ref: Y, shapeFlag: L } = p;
    switch (R) {
      case Er:
        z(f, p, v, b);
        break;
      case bt:
        N(f, p, v, b);
        break;
      case Br:
        f == null && g(p, v, b, O);
        break;
      case ze:
        ke(
          f,
          p,
          v,
          b,
          x,
          A,
          O,
          j,
          M
        );
        break;
      default:
        L & 1 ? J(
          f,
          p,
          v,
          b,
          x,
          A,
          O,
          j,
          M
        ) : L & 6 ? Te(
          f,
          p,
          v,
          b,
          x,
          A,
          O,
          j,
          M
        ) : (L & 64 || L & 128) && R.process(
          f,
          p,
          v,
          b,
          x,
          A,
          O,
          j,
          M,
          T
        );
    }
    Y != null && x ? pn(Y, f && f.ref, A, p || f, !p) : Y == null && f && f.ref != null && pn(f.ref, null, A, f, !0);
  }, z = (f, p, v, b) => {
    if (f == null)
      n(
        p.el = a(p.children),
        v,
        b
      );
    else {
      const x = p.el = f.el;
      p.children !== f.children && c(x, p.children);
    }
  }, N = (f, p, v, b) => {
    f == null ? n(
      p.el = l(p.children || ""),
      v,
      b
    ) : p.el = f.el;
  }, g = (f, p, v, b) => {
    [f.el, f.anchor] = k(
      f.children,
      p,
      v,
      b,
      f.el,
      f.anchor
    );
  }, E = ({ el: f, anchor: p }, v, b) => {
    let x;
    for (; f && f !== p; )
      x = m(f), n(f, v, b), f = x;
    n(p, v, b);
  }, P = ({ el: f, anchor: p }) => {
    let v;
    for (; f && f !== p; )
      v = m(f), r(f), f = v;
    r(p);
  }, J = (f, p, v, b, x, A, O, j, M) => {
    if (p.type === "svg" ? O = "svg" : p.type === "math" && (O = "mathml"), f == null)
      ve(
        p,
        v,
        b,
        x,
        A,
        O,
        j,
        M
      );
    else {
      const R = f.el && f.el._isVueCE ? f.el : null;
      try {
        R && R._beginPatch(), V(
          f,
          p,
          x,
          A,
          O,
          j,
          M
        );
      } finally {
        R && R._endPatch();
      }
    }
  }, ve = (f, p, v, b, x, A, O, j) => {
    let M, R;
    const { props: Y, shapeFlag: L, transition: ee, dirs: ie } = f;
    if (M = f.el = i(
      f.type,
      A,
      Y && Y.is,
      Y
    ), L & 8 ? u(M, f.children) : L & 16 && _(
      f.children,
      M,
      null,
      b,
      x,
      Wr(f, A),
      O,
      j
    ), ie && xs(f, null, b, "created"), oe(M, f, f.scopeId, O, b), Y) {
      for (const Ie in Y)
        Ie !== "value" && !un(Ie) && o(M, Ie, null, Y[Ie], A, b);
      "value" in Y && o(M, "value", null, Y.value, A), (R = Y.onVnodeBeforeMount) && It(R, b, f);
    }
    ie && xs(f, null, b, "beforeMount");
    const be = Nd(x, ee);
    be && ee.beforeEnter(M), n(M, p, v), ((R = Y && Y.onVnodeMounted) || be || ie) && ut(() => {
      try {
        R && It(R, b, f), be && ee.enter(M), ie && xs(f, null, b, "mounted");
      } finally {
      }
    }, x);
  }, oe = (f, p, v, b, x) => {
    if (v && h(f, v), b)
      for (let A = 0; A < b.length; A++)
        h(f, b[A]);
    if (x) {
      let A = x.subTree;
      if (p === A || Jl(A.type) && (A.ssContent === p || A.ssFallback === p)) {
        const O = x.vnode;
        oe(
          f,
          O,
          O.scopeId,
          O.slotScopeIds,
          x.parent
        );
      }
    }
  }, _ = (f, p, v, b, x, A, O, j, M = 0) => {
    for (let R = M; R < f.length; R++) {
      const Y = f[R] = j ? Kt(f[R]) : jt(f[R]);
      w(
        null,
        Y,
        p,
        v,
        b,
        x,
        A,
        O,
        j
      );
    }
  }, V = (f, p, v, b, x, A, O) => {
    const j = p.el = f.el;
    let { patchFlag: M, dynamicChildren: R, dirs: Y } = p;
    M |= f.patchFlag & 16;
    const L = f.props || Ne, ee = p.props || Ne;
    let ie;
    if (v && ks(v, !1), (ie = ee.onVnodeBeforeUpdate) && It(ie, v, p, f), Y && xs(p, f, v, "beforeUpdate"), v && ks(v, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    R && (!f.dynamicChildren || f.dynamicChildren.length !== R.length) && (M = 0, O = !1, R = null), (L.innerHTML && ee.innerHTML == null || L.textContent && ee.textContent == null) && u(j, ""), R ? ce(
      f.dynamicChildren,
      R,
      j,
      v,
      b,
      Wr(p, x),
      A
    ) : O || fe(
      f,
      p,
      j,
      null,
      v,
      b,
      Wr(p, x),
      A,
      !1
    ), M > 0) {
      if (M & 16)
        xe(j, L, ee, v, x);
      else if (M & 2 && L.class !== ee.class && o(j, "class", null, ee.class, x), M & 4 && o(j, "style", L.style, ee.style, x), M & 8) {
        const be = p.dynamicProps;
        for (let Ie = 0; Ie < be.length; Ie++) {
          const Ee = be[Ie], We = L[Ee], Ke = ee[Ee];
          (Ke !== We || Ee === "value") && o(j, Ee, We, Ke, x, v);
        }
      }
      M & 1 && f.children !== p.children && u(j, p.children);
    } else !O && R == null && xe(j, L, ee, v, x);
    ((ie = ee.onVnodeUpdated) || Y) && ut(() => {
      ie && It(ie, v, p, f), Y && xs(p, f, v, "updated");
    }, b);
  }, ce = (f, p, v, b, x, A, O) => {
    for (let j = 0; j < p.length; j++) {
      const M = f[j], R = p[j], Y = M.el || wo(M), L = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        Y && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (M.type === ze || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !sn(M, R) || // - In the case of a component, it could contain anything.
        M.shapeFlag & 198) ? d(Y) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          v
        )
      );
      w(
        M,
        R,
        L,
        null,
        b,
        x,
        A,
        O,
        !0
      );
    }
  }, xe = (f, p, v, b, x) => {
    if (p !== v) {
      if (p !== Ne)
        for (const A in p)
          !un(A) && !(A in v) && o(
            f,
            A,
            p[A],
            null,
            x,
            b
          );
      for (const A in v) {
        if (un(A)) continue;
        const O = v[A], j = p[A];
        O !== j && A !== "value" && o(f, A, j, O, x, b);
      }
      "value" in v && o(f, "value", p.value, v.value, x);
    }
  }, ke = (f, p, v, b, x, A, O, j, M) => {
    const R = p.el = f ? f.el : a(""), Y = p.anchor = f ? f.anchor : a("");
    let { patchFlag: L, dynamicChildren: ee, slotScopeIds: ie } = p;
    ie && (j = j ? j.concat(ie) : ie), f == null ? (n(R, v, b), n(Y, v, b), _(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      p.children || [],
      v,
      Y,
      x,
      A,
      O,
      j,
      M
    )) : L > 0 && L & 64 && ee && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    f.dynamicChildren && f.dynamicChildren.length === ee.length ? (ce(
      f.dynamicChildren,
      ee,
      v,
      x,
      A,
      O,
      j
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (p.key != null || x && p === x.subTree) && ql(
      f,
      p,
      !0
      /* shallow */
    )) : fe(
      f,
      p,
      v,
      Y,
      x,
      A,
      O,
      j,
      M
    );
  }, Te = (f, p, v, b, x, A, O, j, M) => {
    p.slotScopeIds = j, f == null ? p.shapeFlag & 512 ? x.ctx.activate(
      p,
      v,
      b,
      O,
      M
    ) : D(
      p,
      v,
      b,
      x,
      A,
      O,
      M
    ) : me(f, p, M);
  }, D = (f, p, v, b, x, A, O) => {
    const j = f.component = Ld(
      f,
      b,
      x
    );
    if (Xo(f) && (j.ctx.renderer = T), Fd(j, !1, O), j.asyncDep) {
      if (x && x.registerDep(
        j,
        ne,
        O,
        A
      ), !f.el) {
        const M = j.subTree = W(bt);
        N(null, M, p, v), f.placeholder = M.el;
      }
    } else
      ne(
        j,
        f,
        p,
        v,
        x,
        A,
        O
      );
  }, me = (f, p, v) => {
    const b = p.component = f.component;
    if (xd(f, p, v))
      if (b.asyncDep && !b.asyncResolved) {
        p.el = f.el, p.placeholder = f.placeholder, q(b, p, v);
        return;
      } else
        b.next = p, b.update();
    else
      p.el = f.el, p.placeholder = f.placeholder, b.vnode = p;
  }, ne = (f, p, v, b, x, A, O) => {
    const j = () => {
      if (f.isMounted) {
        let { next: L, bu: ee, u: ie, parent: be, vnode: Ie } = f;
        {
          const Ot = Kl(f);
          if (Ot) {
            L && (L.el = Ie.el, q(f, L, O)), Ot.asyncDep.then(() => {
              ut(() => {
                f.isUnmounted || R();
              }, x);
            });
            return;
          }
        }
        let Ee = L, We;
        ks(f, !1), L ? (L.el = Ie.el, q(f, L, O)) : L = Ie, ee && Gn(ee), (We = L.props && L.props.onVnodeBeforeUpdate) && It(We, be, L, Ie), ks(f, !0);
        const Ke = Ni(f), Et = f.subTree;
        f.subTree = Ke, w(
          Et,
          Ke,
          // parent may have changed if it's in a teleport
          d(Et.el),
          // anchor may have changed if it's in a fragment
          S(Et),
          f,
          x,
          A
        ), L.el = Ke.el, Ee === null && kd(f, Ke.el), ie && ut(ie, x), (We = L.props && L.props.onVnodeUpdated) && ut(
          () => It(We, be, L, Ie),
          x
        );
      } else {
        let L;
        const { el: ee, props: ie } = p, { bm: be, m: Ie, parent: Ee, root: We, type: Ke } = f, Et = Ls(p);
        ks(f, !1), be && Gn(be), !Et && (L = ie && ie.onVnodeBeforeMount) && It(L, Ee, p), ks(f, !0);
        {
          We.ce && We.ce._hasShadowRoot() && We.ce._injectChildStyle(
            Ke,
            f.parent ? f.parent.type : void 0
          );
          const Ot = f.subTree = Ni(f);
          w(
            null,
            Ot,
            v,
            b,
            f,
            x,
            A
          ), p.el = Ot.el;
        }
        if (Ie && ut(Ie, x), !Et && (L = ie && ie.onVnodeMounted)) {
          const Ot = p;
          ut(
            () => It(L, Ee, Ot),
            x
          );
        }
        (p.shapeFlag & 256 || Ee && Ls(Ee.vnode) && Ee.vnode.shapeFlag & 256) && f.a && ut(f.a, x), f.isMounted = !0, p = v = b = null;
      }
    };
    f.scope.on();
    const M = f.effect = new sl(j);
    f.scope.off();
    const R = f.update = M.run.bind(M), Y = f.job = M.runIfDirty.bind(M);
    Y.i = f, Y.id = f.uid, M.scheduler = () => Jo(Y), ks(f, !0), R();
  }, q = (f, p, v) => {
    p.component = f;
    const b = f.vnode.props;
    f.vnode = p, f.next = null, Cd(f, p.props, b, v), Od(f, p.children, v), Ft(), xl(f), Ut();
  }, fe = (f, p, v, b, x, A, O, j, M = !1) => {
    const R = f && f.children, Y = f ? f.shapeFlag : 0, L = p.children, { patchFlag: ee, shapeFlag: ie } = p;
    if (ee > 0) {
      if (ee & 128) {
        $(
          R,
          L,
          v,
          b,
          x,
          A,
          O,
          j,
          M
        );
        return;
      } else if (ee & 256) {
        Pe(
          R,
          L,
          v,
          b,
          x,
          A,
          O,
          j,
          M
        );
        return;
      }
    }
    ie & 8 ? (Y & 16 && Re(R, x, A), L !== R && u(v, L)) : Y & 16 ? ie & 16 ? $(
      R,
      L,
      v,
      b,
      x,
      A,
      O,
      j,
      M
    ) : Re(R, x, A, !0) : (Y & 8 && u(v, ""), ie & 16 && _(
      L,
      v,
      b,
      x,
      A,
      O,
      j,
      M
    ));
  }, Pe = (f, p, v, b, x, A, O, j, M) => {
    f = f || Rs, p = p || Rs;
    const R = f.length, Y = p.length, L = Math.min(R, Y);
    let ee;
    for (ee = 0; ee < L; ee++) {
      const ie = p[ee] = M ? Kt(p[ee]) : jt(p[ee]);
      w(
        f[ee],
        ie,
        v,
        null,
        x,
        A,
        O,
        j,
        M
      );
    }
    R > Y ? Re(
      f,
      x,
      A,
      !0,
      !1,
      L
    ) : _(
      p,
      v,
      b,
      x,
      A,
      O,
      j,
      M,
      L
    );
  }, $ = (f, p, v, b, x, A, O, j, M) => {
    let R = 0;
    const Y = p.length;
    let L = f.length - 1, ee = Y - 1;
    for (; R <= L && R <= ee; ) {
      const ie = f[R], be = p[R] = M ? Kt(p[R]) : jt(p[R]);
      if (sn(ie, be))
        w(
          ie,
          be,
          v,
          null,
          x,
          A,
          O,
          j,
          M
        );
      else
        break;
      R++;
    }
    for (; R <= L && R <= ee; ) {
      const ie = f[L], be = p[ee] = M ? Kt(p[ee]) : jt(p[ee]);
      if (sn(ie, be))
        w(
          ie,
          be,
          v,
          null,
          x,
          A,
          O,
          j,
          M
        );
      else
        break;
      L--, ee--;
    }
    if (R > L) {
      if (R <= ee) {
        const ie = ee + 1, be = ie < Y ? p[ie].el : b;
        for (; R <= ee; )
          w(
            null,
            p[R] = M ? Kt(p[R]) : jt(p[R]),
            v,
            be,
            x,
            A,
            O,
            j,
            M
          ), R++;
      }
    } else if (R > ee)
      for (; R <= L; )
        Ue(f[R], x, A, !0), R++;
    else {
      const ie = R, be = R, Ie = /* @__PURE__ */ new Map();
      for (R = be; R <= ee; R++) {
        const mt = p[R] = M ? Kt(p[R]) : jt(p[R]);
        mt.key != null && Ie.set(mt.key, R);
      }
      let Ee, We = 0;
      const Ke = ee - be + 1;
      let Et = !1, Ot = 0;
      const en = new Array(Ke);
      for (R = 0; R < Ke; R++) en[R] = 0;
      for (R = ie; R <= L; R++) {
        const mt = f[R];
        if (We >= Ke) {
          Ue(mt, x, A, !0);
          continue;
        }
        let Tt;
        if (mt.key != null)
          Tt = Ie.get(mt.key);
        else
          for (Ee = be; Ee <= ee; Ee++)
            if (en[Ee - be] === 0 && sn(mt, p[Ee])) {
              Tt = Ee;
              break;
            }
        Tt === void 0 ? Ue(mt, x, A, !0) : (en[Tt - be] = R + 1, Tt >= Ot ? Ot = Tt : Et = !0, w(
          mt,
          p[Tt],
          v,
          null,
          x,
          A,
          O,
          j,
          M
        ), We++);
      }
      const hi = Et ? Pd(en) : Rs;
      for (Ee = hi.length - 1, R = Ke - 1; R >= 0; R--) {
        const mt = be + R, Tt = p[mt], gi = p[mt + 1], vi = mt + 1 < Y ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          gi.el || wo(gi)
        ) : b;
        en[R] === 0 ? w(
          null,
          Tt,
          v,
          vi,
          x,
          A,
          O,
          j,
          M
        ) : Et && (Ee < 0 || R !== hi[Ee] ? nt(Tt, v, vi, 2) : Ee--);
      }
    }
  }, nt = (f, p, v, b, x = null) => {
    const { el: A, type: O, transition: j, children: M, shapeFlag: R } = f;
    if (R & 6) {
      nt(f.component.subTree, p, v, b);
      return;
    }
    if (R & 128) {
      f.suspense.move(p, v, b);
      return;
    }
    if (R & 64) {
      O.move(f, p, v, T);
      return;
    }
    if (O === ze) {
      n(A, p, v);
      for (let L = 0; L < M.length; L++)
        nt(M[L], p, v, b);
      n(f.anchor, p, v);
      return;
    }
    if (O === Br) {
      E(f, p, v);
      return;
    }
    if (b !== 2 && R & 1 && j)
      if (b === 0)
        j.persisted && !A[Fr] ? n(A, p, v) : (j.beforeEnter(A), n(A, p, v), ut(() => j.enter(A), x));
      else {
        const { leave: L, delayLeave: ee, afterLeave: ie } = j, be = () => {
          f.ctx.isUnmounted ? r(A) : n(A, p, v);
        }, Ie = () => {
          const Ee = A._isLeaving || !!A[Fr];
          A._isLeaving && A[Fr](
            !0
            /* cancelled */
          ), j.persisted && !Ee ? be() : L(A, () => {
            be(), ie && ie();
          });
        };
        ee ? ee(A, be, Ie) : Ie();
      }
    else
      n(A, p, v);
  }, Ue = (f, p, v, b = !1, x = !1) => {
    const {
      type: A,
      props: O,
      ref: j,
      children: M,
      dynamicChildren: R,
      shapeFlag: Y,
      patchFlag: L,
      dirs: ee,
      cacheIndex: ie,
      memo: be
    } = f;
    if ((L === -2 || R && R.hasOnce) && (x = !1), j != null && (Ft(), pn(j, null, v, f, !0), Ut()), ie != null && (!f.ctx || f.ctx === p) && (p.renderCache[ie] = void 0), Y & 256) {
      p.ctx.deactivate(f);
      return;
    }
    const Ie = Y & 1 && ee, Ee = !Ls(f);
    let We;
    if (Ee && (We = O && O.onVnodeBeforeUnmount) && It(We, p, f), Y & 6)
      De(f.component, v, b);
    else {
      if (Y & 128) {
        f.suspense.unmount(v, b);
        return;
      }
      Ie && xs(f, null, p, "beforeUnmount"), Y & 64 ? f.type.remove(
        f,
        p,
        v,
        T,
        b
      ) : R && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !R.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (A !== ze || L > 0 && L & 64) ? Re(
        R,
        p,
        v,
        !1,
        !0
      ) : (A === ze && L & 384 || !x && Y & 16) && Re(M, p, v), b && wt(f);
    }
    const Ke = be != null && ie == null;
    (Ee && (We = O && O.onVnodeUnmounted) || Ie || Ke) && ut(() => {
      We && It(We, p, f), Ie && xs(f, null, p, "unmounted"), Ke && (f.el = null);
    }, v);
  }, wt = (f) => {
    const { type: p, el: v, anchor: b, transition: x } = f, A = p === ze;
    if (A && !x) {
      xt(v, b);
      return;
    }
    if (p === Br) {
      P(f), x && !x.persisted && x.afterLeave && x.afterLeave();
      return;
    }
    const O = A ? go(f) : f, j = () => {
      A ? d(v) && xt(v, b) : r(v), x && !x.persisted && x.afterLeave && x.afterLeave();
    };
    if (O && O.shapeFlag & 1 && x && !x.persisted) {
      const { leave: M, delayLeave: R } = x, Y = O.el, L = () => M(Y, j);
      R ? R(Y, j, L) : L();
    } else
      j();
  }, xt = (f, p) => {
    let v;
    for (; f !== p; )
      v = m(f), r(f), f = v;
    r(p);
  }, De = (f, p, v) => {
    const { bum: b, scope: x, job: A, subTree: O, um: j, m: M, a: R } = f;
    ji(M), ji(R), b && Gn(b), x.stop(), A ? (A.flags |= 8, Ue(O, f, p, v)) : f.vnode.el && O && (O.transition = f.vnode.transition, Ue(O, f, p, v)), j && ut(j, p), ut(() => {
      f.isUnmounted = !0;
    }, p);
  }, Re = (f, p, v, b = !1, x = !1, A = 0) => {
    for (let O = A; O < f.length; O++)
      Ue(f[O], p, v, b, x);
  }, S = (f) => {
    if (f.shapeFlag & 6)
      return S(f.component.subTree);
    if (f.shapeFlag & 128)
      return f.suspense.next();
    const p = m(f.anchor || f.el), v = p && p[Zu];
    return v ? m(v) : p;
  }, B = (f, p, v) => {
    const b = f && p._vnode ? void 0 : f && f.component ? f.component.uid : Vd();
    Uu(() => {
      f == null ? p._vnode && Ue(p._vnode, null, null, !0) : w(
        p._vnode || null,
        f,
        p,
        null,
        null,
        null,
        v
      ), p._vnode = f;
    }, b);
  }, T = {
    p: w,
    um: Ue,
    m: nt,
    r: wt,
    mt: D,
    mc: _,
    pc: fe,
    pbc: ce,
    n: S,
    o: e
  };
  return {
    render: B,
    hydrate: void 0,
    createApp: gd(B)
  };
}
function Wr({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function ks({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function Nd(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function ql(e, t, s = !1) {
  const n = e.children, r = t.children;
  if (Q(n) && Q(r))
    for (let o = 0; o < n.length; o++) {
      const i = n[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = Kt(r[o]), a.el = i.el), !s && a.patchFlag !== -2 && ql(i, a)), a.type === Er && (a.patchFlag === -1 && (a = r[o] = Kt(a)), a.el = i.el), a.type === bt && !a.el && (a.el = i.el);
    }
}
function Pd(e) {
  const t = e.slice(), s = [0];
  let n, r, o, i, a;
  const l = e.length;
  for (n = 0; n < l; n++) {
    const c = e[n];
    if (c !== 0) {
      if (r = s[s.length - 1], e[r] < c) {
        t[n] = r, s.push(n);
        continue;
      }
      for (o = 0, i = s.length - 1; o < i; )
        a = o + i >> 1, e[s[a]] < c ? o = a + 1 : i = a;
      c < e[s[o]] && (o > 0 && (t[n] = s[o - 1]), s[o] = n);
    }
  }
  for (o = s.length, i = s[o - 1]; o-- > 0; )
    s[o] = i, i = t[i];
  return s;
}
function Kl(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : Kl(t);
}
function ji(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function wo(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? wo(t.subTree) : null;
}
const Jl = (e) => e.__isSuspense;
function Md(e, t) {
  t && t.pendingBranch ? Q(e) ? t.effects.push(...e) : t.effects.push(e) : Fu(e);
}
const ze = /* @__PURE__ */ Symbol.for("v-fgt"), Er = /* @__PURE__ */ Symbol.for("v-txt"), bt = /* @__PURE__ */ Symbol.for("v-cmt"), Br = /* @__PURE__ */ Symbol.for("v-stc"), ts = [];
let pt = null;
function X(e = !1) {
  ts.push(pt = e ? null : []);
}
function si() {
  ts.pop(), pt = ts[ts.length - 1] || null;
}
let wn = 1;
function nr(e, t = !1) {
  wn += e, e < 0 && pt && t && (pt.hasOnce = !0);
}
function Ql(e) {
  return e.dynamicChildren = wn > 0 ? pt || Rs : null, si(), wn > 0 && pt && pt.push(e), e;
}
function ge(e, t, s, n, r, o) {
  return Ql(
    y(
      e,
      t,
      s,
      n,
      r,
      o,
      !0
    )
  );
}
function at(e, t, s, n, r) {
  return Ql(
    W(
      e,
      t,
      s,
      n,
      r,
      !0
    )
  );
}
function Fs(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function sn(e, t) {
  return e.type === t.type && e.key === t.key;
}
const Yl = ({ key: e }) => e ?? null, qn = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? Ve(e) || /* @__PURE__ */ Fe(e) || de(e) ? { i: Qe, r: e, k: t, f: !!s } : e : null);
function y(e, t = null, s = null, n = 0, r = null, o = e === ze ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Yl(t),
    ref: t && qn(t),
    scopeId: Cl,
    slotScopeIds: null,
    children: s,
    component: null,
    suspense: null,
    ssContent: null,
    ssFallback: null,
    dirs: null,
    transition: null,
    el: null,
    anchor: null,
    target: null,
    targetStart: null,
    targetAnchor: null,
    staticCount: 0,
    shapeFlag: o,
    patchFlag: n,
    dynamicProps: r,
    dynamicChildren: null,
    appContext: null,
    ctx: Qe
  };
  return a ? (rr(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= Ve(s) ? 8 : 16), wn > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  pt && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && pt.push(l), l;
}
const W = jd;
function jd(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === Il) && (e = bt), Fs(e)) {
    const a = Us(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && rr(a, s), wn > 0 && !o && pt && (a.shapeFlag & 6 ? pt[pt.indexOf(e)] = a : pt.push(a)), a.patchFlag = -2, a;
  }
  if (Gd(e) && (e = e.__vccOpts), t) {
    t = $d(t);
    let { class: a, style: l } = t;
    a && !Ve(a) && (t.class = ft(a)), Ae(l) && (/* @__PURE__ */ xr(l) && !Q(l) && (l = Xe({}, l)), t.style = Lo(l));
  }
  const i = Ve(e) ? 1 : Jl(e) ? 128 : Cr(e) ? 64 : Ae(e) ? 4 : de(e) ? 2 : 0;
  return y(
    e,
    t,
    s,
    n,
    r,
    i,
    o,
    !0
  );
}
function $d(e) {
  return e ? /* @__PURE__ */ xr(e) || Ul(e) ? Xe({}, e) : e : null;
}
function Us(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? zd(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Yl(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? Q(o) ? o.concat(qn(t)) : [o, qn(t)] : qn(t)
    ) : o,
    scopeId: e.scopeId,
    slotScopeIds: e.slotScopeIds,
    children: a,
    target: e.target,
    targetStart: e.targetStart,
    targetAnchor: e.targetAnchor,
    staticCount: e.staticCount,
    shapeFlag: e.shapeFlag,
    // if the vnode is cloned with extra props, we can no longer assume its
    // existing patch flag to be reliable and need to add the FULL_PROPS flag.
    // note: preserve flag for fragments since they use the flag for children
    // fast paths only.
    patchFlag: t && e.type !== ze ? i === -1 ? 16 : i | 16 : i,
    dynamicProps: e.dynamicProps,
    dynamicChildren: e.dynamicChildren,
    appContext: e.appContext,
    dirs: e.dirs,
    transition: l,
    // These should technically only be non-null on mounted VNodes. However,
    // they *should* be copied for kept-alive vnodes. So we just always copy
    // them since them being non-null during a mount doesn't affect the logic as
    // they will simply be overwritten.
    component: e.component,
    suspense: e.suspense,
    ssContent: e.ssContent && Us(e.ssContent),
    ssFallback: e.ssFallback && Us(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && er(
    u,
    l.clone(u)
  ), u;
}
function te(e = " ", t = 0) {
  return W(Er, null, e, t);
}
function Ye(e = "", t = !1) {
  return t ? (X(), at(bt, null, e)) : W(bt, null, e);
}
function jt(e) {
  return e == null || typeof e == "boolean" ? W(bt) : Q(e) ? W(
    ze,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : Fs(e) ? Kt(e) : W(Er, null, String(e));
}
function Kt(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : Us(e);
}
function rr(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (Q(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), rr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !Ul(t) ? t._ctx = Qe : r === 3 && Qe && (Qe.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (de(t)) {
    if (n & 65) {
      rr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: Qe }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [te(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function zd(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = ft([t.class, n.class]));
      else if (r === "style")
        t.style = Lo([t.style, n.style]);
      else if (pr(r)) {
        const o = t[r], i = n[r];
        i && o !== i && !(Q(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !hr(r) && (t[r] = i);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function It(e, t, s, n = null) {
  Ct(e, t, 7, [
    s,
    n
  ]);
}
const Dd = $l();
let Xl = 0;
function Vd() {
  return Xl;
}
function Ld(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || Dd, o = {
    uid: Xl++,
    vnode: e,
    type: n,
    parent: t,
    appContext: r,
    root: null,
    // to be immediately set
    next: null,
    subTree: null,
    // will be set synchronously right after creation
    effect: null,
    update: null,
    // will be set synchronously right after creation
    job: null,
    scope: new Xa(
      !0
      /* detached */
    ),
    render: null,
    proxy: null,
    exposed: null,
    exposeProxy: null,
    withProxy: null,
    provides: t ? t.provides : Object.create(r.provides),
    ids: t ? t.ids : ["", 0, 0],
    accessCache: null,
    renderCache: [],
    // local resolved assets
    components: null,
    directives: null,
    // resolved props and emits options
    propsOptions: Bl(n, r),
    emitsOptions: zl(n, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: Ne,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: Ne,
    data: Ne,
    props: Ne,
    attrs: Ne,
    slots: Ne,
    refs: Ne,
    setupState: Ne,
    setupContext: null,
    // suspense related
    suspense: s,
    suspenseId: s ? s.pendingId : 0,
    asyncDep: null,
    asyncResolved: !1,
    // lifecycle hooks
    // not using enums here because it results in computed properties
    isMounted: !1,
    isUnmounted: !1,
    isDeactivated: !1,
    bc: null,
    c: null,
    bm: null,
    m: null,
    bu: null,
    u: null,
    um: null,
    bum: null,
    da: null,
    a: null,
    rtg: null,
    rtc: null,
    ec: null,
    sp: null
  };
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = yd.bind(null, o), e.ce && e.ce(o), o;
}
let st = null;
const Or = () => st || Qe;
let or, xn;
{
  const e = _r(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  or = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => st = s
  ), xn = t(
    "__VUE_SSR_SETTERS__",
    (s) => kn = s
  );
}
const Pn = (e) => {
  const t = st;
  return or(e), e.scope.on(), () => {
    e.scope.off(), or(t);
  };
}, $i = () => {
  st && st.scope.off(), or(null);
};
function ec(e) {
  return e.vnode.shapeFlag & 4;
}
let kn = !1;
function Fd(e, t = !1, s = !1) {
  t && xn(t);
  const { props: n, children: r } = e.vnode, o = ec(e);
  Sd(e, n, o, t), Ed(e, r, s || t);
  const i = o ? Ud(e, t) : void 0;
  return t && xn(!1), i;
}
function Ud(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, cd);
  const { setup: n } = s;
  if (n) {
    Ft();
    const r = e.setupContext = n.length > 1 ? Bd(e) : null, o = Pn(e), i = Nn(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = Ga(i);
    if (Ut(), o(), (a || e.sp) && !Ls(e) && El(e), a) {
      if (i.then($i, $i), t)
        return i.then((l) => {
          xn(!0);
          try {
            zi(e, l, t);
          } finally {
            xn(!1);
          }
        }).catch((l) => {
          kr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      zi(e, i);
  } else
    tc(e);
}
function zi(e, t, s) {
  de(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : Ae(t) && (e.setupState = bl(t)), tc(e);
}
function tc(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || Dt);
  {
    const r = Pn(e);
    Ft();
    try {
      ud(e);
    } finally {
      Ut(), r();
    }
  }
}
const Wd = {
  get(e, t) {
    return tt(e, "get", ""), e[t];
  }
};
function Bd(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Wd),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Tr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(bl(Ko(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in hn)
        return hn[s](e);
    },
    has(t, s) {
      return s in t || s in hn;
    }
  })) : e.proxy;
}
function Hd(e, t = !0) {
  return de(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function Gd(e) {
  return de(e) && "__vccOpts" in e;
}
const Oe = (e, t) => /* @__PURE__ */ $u(e, t, kn);
function Sn(e, t, s) {
  try {
    nr(-1);
    const n = arguments.length;
    return n === 2 ? Ae(t) && !Q(t) ? Fs(t) ? W(e, null, [t]) : W(e, t) : W(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && Fs(s) && (s = [s]), W(e, t, s));
  } finally {
    nr(1);
  }
}
const Zd = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let xo;
const Di = typeof window < "u" && window.trustedTypes;
if (Di)
  try {
    xo = /* @__PURE__ */ Di.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const sc = xo ? (e) => xo.createHTML(e) : (e) => e, qd = "http://www.w3.org/2000/svg", Kd = "http://www.w3.org/1998/Math/MathML", qt = typeof document < "u" ? document : null, Vi = qt && /* @__PURE__ */ qt.createElement("template"), Jd = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? qt.createElementNS(qd, e) : t === "mathml" ? qt.createElementNS(Kd, e) : s ? qt.createElement(e, { is: s }) : qt.createElement(e);
    return e === "select" && n && n.multiple != null && r.setAttribute("multiple", n.multiple), r;
  },
  createText: (e) => qt.createTextNode(e),
  createComment: (e) => qt.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => qt.querySelector(e),
  setScopeId(e, t) {
    e.setAttribute(t, "");
  },
  // __UNSAFE__
  // Reason: innerHTML.
  // Static content here can only come from compiled templates.
  // As long as the user only uses trusted templates, this is safe.
  insertStaticContent(e, t, s, n, r, o) {
    const i = s ? s.previousSibling : t.lastChild;
    if (r && (r === o || r.nextSibling))
      for (; t.insertBefore(r.cloneNode(!0), s), !(r === o || !(r = r.nextSibling)); )
        ;
    else {
      Vi.innerHTML = sc(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const a = Vi.content;
      if (n === "svg" || n === "mathml") {
        const l = a.firstChild;
        for (; l.firstChild; )
          a.appendChild(l.firstChild);
        a.removeChild(l);
      }
      t.insertBefore(a, s);
    }
    return [
      // first
      i ? i.nextSibling : t.firstChild,
      // last
      s ? s.previousSibling : t.lastChild
    ];
  }
}, Qd = /* @__PURE__ */ Symbol("_vtc");
function Yd(e, t, s) {
  const n = e[Qd];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const Li = /* @__PURE__ */ Symbol("_vod"), Xd = /* @__PURE__ */ Symbol("_vsh"), ef = /* @__PURE__ */ Symbol(""), tf = /(?:^|;)\s*display\s*:/;
function sf(e, t, s) {
  const n = e.style, r = Ve(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (Ve(t))
        for (const i of t.split(";")) {
          const a = i.slice(0, i.indexOf(":")).trim();
          s[a] == null && ln(n, a, "");
        }
      else
        for (const i in t)
          s[i] == null && ln(n, i, "");
    for (const i in s) {
      i === "display" && (o = !0);
      const a = s[i];
      a != null ? rf(
        e,
        i,
        !Ve(t) && t ? t[i] : void 0,
        a
      ) || ln(n, i, a) : ln(n, i, "");
    }
  } else if (r) {
    if (t !== s) {
      const i = n[ef];
      i && (s += ";" + i), n.cssText = s, o = tf.test(s);
    }
  } else t && e.removeAttribute("style");
  Li in e && ((!r || t !== s) && (e[Li] = o ? n.display : ""), e[Xd] && (n.display = "none"));
}
const Dn = /\s*!important$/;
function ln(e, t, s) {
  if (Q(s))
    s.forEach((n) => ln(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    Dn.test(s) ? e.setProperty(t, s.replace(Dn, ""), "important") : e.setProperty(t, s);
  else {
    const n = nf(e, t);
    Dn.test(s) ? e.setProperty(
      _s(n),
      s.replace(Dn, ""),
      "important"
    ) : e[n] = s;
  }
}
const Fi = ["Webkit", "Moz", "ms"], Hr = {};
function nf(e, t) {
  const s = Hr[t];
  if (s)
    return s;
  let n = lt(t);
  if (n !== "filter" && n in e)
    return Hr[t] = n;
  n = yr(n);
  for (let r = 0; r < Fi.length; r++) {
    const o = Fi[r] + n;
    if (o in e)
      return Hr[t] = o;
  }
  return t;
}
function rf(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && Ve(n) && s === n;
}
const Ui = "http://www.w3.org/1999/xlink";
function Wi(e, t, s, n, r, o = uu(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(Ui, t.slice(6, t.length)) : e.setAttributeNS(Ui, t, s) : s == null || o && !Ja(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : gt(s) ? String(s) : s
  );
}
function Bi(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? sc(s) : s);
    return;
  }
  const o = e.tagName;
  if (t === "value" && o !== "PROGRESS" && // custom elements may use _value internally
  !o.includes("-")) {
    const a = o === "OPTION" ? e.getAttribute("value") || "" : e.value, l = s == null ? (
      // #11647: value should be set as empty string for null and undefined,
      // but <input type="checkbox"> should be set as 'on'.
      e.type === "checkbox" ? "on" : ""
    ) : String(s);
    (a !== l || !("_value" in e)) && (e.value = l), s == null && e.removeAttribute(t), e._value = s;
    return;
  }
  let i = !1;
  if (s === "" || s == null) {
    const a = typeof e[t];
    a === "boolean" ? s = Ja(s) : s == null && a === "string" ? (s = "", i = !0) : a === "number" && (s = 0, i = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function ms(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function of(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const Hi = /* @__PURE__ */ Symbol("_vei");
function af(e, t, s, n, r = null) {
  const o = e[Hi] || (e[Hi] = {}), i = o[t];
  if (n && i)
    i.value = n;
  else {
    const [a, l] = uf(t);
    if (n) {
      const c = o[t] = mf(
        n,
        r
      );
      ms(e, a, c, l);
    } else i && (of(e, a, i, l), o[t] = void 0);
  }
}
const lf = /(Once|Passive|Capture)$/, cf = /^on:?(?:Once|Passive|Capture)$/;
function uf(e) {
  let t, s;
  for (; (s = e.match(lf)) && !cf.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : _s(e.slice(2)), t];
}
let Gr = 0;
const df = /* @__PURE__ */ Promise.resolve(), ff = () => Gr || (df.then(() => Gr = 0), Gr = Date.now());
function mf(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if (Q(r)) {
      const o = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        o.call(n), n._stopped = !0;
      };
      const i = r.slice(), a = [n];
      for (let l = 0; l < i.length && !n._stopped; l++) {
        const c = i[l];
        c && Ct(
          c,
          t,
          5,
          a
        );
      }
    } else
      Ct(
        r,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = ff(), s;
}
const Gi = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, pf = (e, t, s, n, r, o) => {
  const i = r === "svg";
  t === "class" ? Yd(e, n, i) : t === "style" ? sf(e, s, n) : pr(t) ? hr(t) || af(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : hf(e, t, n, i)) ? (Bi(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && Wi(e, t, n, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (gf(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !Ve(n))) ? Bi(e, lt(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), Wi(e, t, n, i));
};
function hf(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && Gi(t) && de(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return Gi(t) && Ve(s) ? !1 : t in e;
}
function gf(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = lt(t);
  return Array.isArray(s) ? s.some((r) => lt(r) === n) : Object.keys(s).some((r) => lt(r) === n);
}
const Ws = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return Q(t) ? (s) => Gn(t, s) : t;
};
function vf(e) {
  e.target.composing = !0;
}
function Zi(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const zt = /* @__PURE__ */ Symbol("_assign"), Vn = /* @__PURE__ */ Symbol("_initialValue");
function Zr(e, t, s) {
  return t && (e = e.trim()), s && (e = br(e)), e;
}
const Cn = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[Vn] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[Vn] = e.defaultValue.replace(/\r\n?/g, `
`))), e[zt] = Ws(r);
    const o = n || r.props && r.props.type === "number";
    ms(e, t ? "change" : "input", (i) => {
      i.target.composing || e[zt](Zr(e.value, s, o));
    }), (s || o) && ms(e, "change", () => {
      e.value = Zr(e.value, s, o);
    }), t || (ms(e, "compositionstart", vf), ms(e, "compositionend", Zi), ms(e, "change", Zi));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[Vn];
    delete e[Vn], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[zt](Zr(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, i) {
    if (e[zt] = Ws(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? br(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, yf = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[zt] = Ws(s), ms(e, "change", () => {
      const n = e._modelValue, r = An(e), o = e.checked, i = e[zt];
      if (Q(n)) {
        const a = Fo(n, r), l = a !== -1;
        if (o && !l)
          i(n.concat(r));
        else if (!o && l) {
          const c = [...n];
          c.splice(a, 1), i(c);
        }
      } else if (ss(n)) {
        const a = new Set(n);
        o ? a.add(r) : a.delete(r), i(a);
      } else
        i(nc(e, o));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: qi,
  beforeUpdate(e, t, s) {
    e[zt] = Ws(s), qi(e, t, s);
  }
};
function qi(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let r;
  if (Q(t))
    r = Fo(t, n.props.value) > -1;
  else if (ss(t))
    r = t.has(n.props.value);
  else {
    if (t === s) return;
    r = ns(t, nc(e, !0));
  }
  e.checked !== r && (e.checked = r);
}
const ni = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, ms(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? br(An(l)) : An(l)
      ), o = e.multiple, i = o ? ss(e._modelValue) ? new Set(r) : r : r[0], a = e._pendingValue = [
        o,
        o ? Q(i) ? r.slice() : r : i
      ];
      try {
        e[zt](i);
      } finally {
        Sr(() => {
          e._pendingValue === a && (e._pendingValue = void 0);
        });
      }
    }), e[zt] = Ws(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    Ki(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[zt] = Ws(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !bf(t, s[1], s[0])) && Ki(e, t);
  }
};
function bf(e, t, s) {
  if (!s || Q(e)) return ns(e, t);
  if (ss(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function Ki(e, t) {
  const s = e.multiple, n = Q(t);
  if (!(s && !n && !ss(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const i = e.options[r], a = An(i);
      if (s)
        if (n) {
          const l = typeof a;
          l === "string" || l === "number" ? i.selected = t.some((c) => String(c) === String(a)) : i.selected = Fo(t, a) > -1;
        } else
          i.selected = t.has(a);
      else if (ns(An(i), t)) {
        e.selectedIndex !== r && (e.selectedIndex = r);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function An(e) {
  return "_value" in e ? e._value : e.value;
}
function nc(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const _f = ["ctrl", "shift", "alt", "meta"], wf = {
  stop: (e) => e.stopPropagation(),
  prevent: (e) => e.preventDefault(),
  self: (e) => e.target !== e.currentTarget,
  ctrl: (e) => !e.ctrlKey,
  shift: (e) => !e.shiftKey,
  alt: (e) => !e.altKey,
  meta: (e) => !e.metaKey,
  left: (e) => "button" in e && e.button !== 0,
  middle: (e) => "button" in e && e.button !== 1,
  right: (e) => "button" in e && e.button !== 2,
  exact: (e, t) => _f.some((s) => e[`${s}Key`] && !t.includes(s))
}, xf = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = wf[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, kf = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
}, Sf = (e, t) => {
  const s = e._withKeys || (e._withKeys = {}), n = t.join(".");
  return s[n] || (s[n] = ((r) => {
    if (!("key" in r))
      return;
    const o = _s(r.key);
    if (t.some(
      (i) => i === o || kf[i] === o
    ))
      return e(r);
  }));
}, Cf = /* @__PURE__ */ Xe({ patchProp: pf }, Jd);
let Ji;
function Af() {
  return Ji || (Ji = Td(Cf));
}
const Rf = ((...e) => {
  const t = Af().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = Of(n);
    if (!r) return;
    const o = t._component;
    !de(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = s(r, !1, Ef(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function Ef(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function Of(e) {
  return Ve(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let rc;
const Ir = (e) => rc = e, oc = (
  /* istanbul ignore next */
  Symbol()
);
function ko(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var gn;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(gn || (gn = {}));
function Tf() {
  const e = el(!0), t = e.run(() => /* @__PURE__ */ G({}));
  let s = [], n = [];
  const r = Ko({
    install(o) {
      Ir(r), r._a = o, o.provide(oc, r), o.config.globalProperties.$pinia = r, n.forEach((i) => s.push(i)), n = [];
    },
    use(o) {
      return this._a ? s.push(o) : n.push(o), this;
    },
    _p: s,
    // it's actually undefined here
    // @ts-expect-error
    _a: null,
    _e: e,
    _s: /* @__PURE__ */ new Map(),
    state: t
  });
  return r;
}
const ic = () => {
};
function Qi(e, t, s, n = ic) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && Uo() && tl(r), r;
}
function Ms(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const If = (e) => e(), Yi = Symbol(), qr = Symbol();
function So(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    ko(r) && ko(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ Fe(n) && !/* @__PURE__ */ Vt(n) ? e[s] = So(r, n) : e[s] = n;
  }
  return e;
}
const Nf = (
  /* istanbul ignore next */
  Symbol()
);
function Pf(e) {
  return !ko(e) || !Object.prototype.hasOwnProperty.call(e, Nf);
}
const { assign: ls } = Object;
function Mf(e) {
  return !!(/* @__PURE__ */ Fe(e) && e.effect);
}
function jf(e, t, s, n) {
  const { state: r, actions: o, getters: i } = t, a = s.state.value[e];
  let l;
  function c() {
    a || (s.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ Nu(s.state.value[e]);
    return ls(u, o, Object.keys(i || {}).reduce((d, m) => (d[m] = Ko(Oe(() => {
      Ir(s);
      const h = s._s.get(e);
      return i[m].call(h, h);
    })), d), {}));
  }
  return l = ac(e, c, t, s, n, !0), l;
}
function ac(e, t, s = {}, n, r, o) {
  let i;
  const a = ls({ actions: {} }, s), l = { deep: !0 };
  let c, u, d = /* @__PURE__ */ new Set(), m = /* @__PURE__ */ new Set(), h;
  const k = n.state.value[e];
  !o && !k && (n.state.value[e] = {});
  let w;
  function z(_) {
    let V;
    c = u = !1, typeof _ == "function" ? (_(n.state.value[e]), V = {
      type: gn.patchFunction,
      storeId: e,
      events: h
    }) : (So(n.state.value[e], _), V = {
      type: gn.patchObject,
      payload: _,
      storeId: e,
      events: h
    });
    const ce = w = Symbol();
    Sr().then(() => {
      w === ce && (c = !0);
    }), u = !0, Ms(d, V, n.state.value[e]);
  }
  const N = o ? function() {
    const { state: V } = s, ce = V ? V() : {};
    this.$patch((xe) => {
      ls(xe, ce);
    });
  } : (
    /* istanbul ignore next */
    ic
  );
  function g() {
    i.stop(), d.clear(), m.clear(), n._s.delete(e);
  }
  const E = (_, V = "") => {
    if (Yi in _)
      return _[qr] = V, _;
    const ce = function() {
      Ir(n);
      const xe = Array.from(arguments), ke = /* @__PURE__ */ new Set(), Te = /* @__PURE__ */ new Set();
      function D(q) {
        ke.add(q);
      }
      function me(q) {
        Te.add(q);
      }
      Ms(m, {
        args: xe,
        name: ce[qr],
        store: J,
        after: D,
        onError: me
      });
      let ne;
      try {
        ne = _.apply(this && this.$id === e ? this : J, xe);
      } catch (q) {
        throw Ms(Te, q), q;
      }
      return ne instanceof Promise ? ne.then((q) => (Ms(ke, q), q)).catch((q) => (Ms(Te, q), Promise.reject(q))) : (Ms(ke, ne), ne);
    };
    return ce[Yi] = !0, ce[qr] = V, ce;
  }, P = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: Qi.bind(null, m),
    $patch: z,
    $reset: N,
    $subscribe(_, V = {}) {
      const ce = Qi(d, _, V.detached, () => xe()), xe = i.run(() => es(() => n.state.value[e], (ke) => {
        (V.flush === "sync" ? u : c) && _({
          storeId: e,
          type: gn.direct,
          events: h
        }, ke);
      }, ls({}, l, V)));
      return ce;
    },
    $dispose: g
  }, J = /* @__PURE__ */ In(P);
  n._s.set(e, J);
  const oe = (n._a && n._a.runWithContext || If)(() => n._e.run(() => (i = el()).run(() => t({ action: E }))));
  for (const _ in oe) {
    const V = oe[_];
    if (/* @__PURE__ */ Fe(V) && !Mf(V) || /* @__PURE__ */ Vt(V))
      o || (k && Pf(V) && (/* @__PURE__ */ Fe(V) ? V.value = k[_] : So(V, k[_])), n.state.value[e][_] = V);
    else if (typeof V == "function") {
      const ce = E(V, _);
      oe[_] = ce, a.actions[_] = V;
    }
  }
  return ls(J, oe), ls(/* @__PURE__ */ _e(J), oe), Object.defineProperty(J, "$state", {
    get: () => n.state.value[e],
    set: (_) => {
      z((V) => {
        ls(V, _);
      });
    }
  }), n._p.forEach((_) => {
    ls(J, i.run(() => _({
      store: J,
      app: n._a,
      pinia: n,
      options: a
    })));
  }), k && o && s.hydrate && s.hydrate(J.$state, k), c = !0, u = !0, J;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function Xs(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(i, a) {
    const l = Qo();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? dt(oc, null) : null), i && Ir(i), i = rc, i._s.has(e) || (r ? ac(e, t, n, i) : jf(e, n, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const zs = typeof document < "u";
function lc(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function $f(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && lc(e.default);
}
const je = Object.assign;
function Kr(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = At(r) ? r.map(e) : e(r);
  }
  return s;
}
const vn = () => {
}, At = Array.isArray;
function Xi(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const cc = /#/g, zf = /&/g, Df = /\//g, Vf = /=/g, Lf = /\?/g, uc = /\+/g, Ff = /%5B/g, Uf = /%5D/g, dc = /%5E/g, Wf = /%60/g, fc = /%7B/g, Bf = /%7C/g, mc = /%7D/g, Hf = /%20/g;
function ri(e) {
  return e == null ? "" : encodeURI("" + e).replace(Bf, "|").replace(Ff, "[").replace(Uf, "]");
}
function Gf(e) {
  return ri(e).replace(fc, "{").replace(mc, "}").replace(dc, "^");
}
function Co(e) {
  return ri(e).replace(uc, "%2B").replace(Hf, "+").replace(cc, "%23").replace(zf, "%26").replace(Wf, "`").replace(fc, "{").replace(mc, "}").replace(dc, "^");
}
function Zf(e) {
  return Co(e).replace(Vf, "%3D");
}
function qf(e) {
  return ri(e).replace(cc, "%23").replace(Lf, "%3F");
}
function Kf(e) {
  return qf(e).replace(Df, "%2F");
}
function Rn(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const Jf = /\/$/, Qf = (e) => e.replace(Jf, "");
function Jr(e, t, s = "/") {
  let n, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (n = n || t.slice(0, a), i = t.slice(a, t.length)), n = tm(n ?? t, s), {
    fullPath: n + o + i,
    path: n,
    query: r,
    hash: Rn(i)
  };
}
function Yf(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Xf(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && Bs(t.matched[n], s.matched[r]) && pc(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function Bs(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function pc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!em(e[s], t[s])) return !1;
  return !0;
}
function em(e, t) {
  return At(e) ? ea(e, t) : At(t) ? ea(t, e) : e?.valueOf() === t?.valueOf();
}
function ea(e, t) {
  return At(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function tm(e, t) {
  if (e.startsWith("/")) return e;
  if (!e) return t;
  const s = t.split("/"), n = e.split("/"), r = n[n.length - 1];
  (r === ".." || r === ".") && n.push("");
  let o = s.length - 1, i, a;
  for (i = 0; i < n.length; i++)
    if (a = n[i], a !== ".")
      if (a === "..")
        o > 1 && o--;
      else break;
  return s.slice(0, o).join("/") + "/" + n.slice(i).join("/");
}
const is = {
  path: "/",
  name: void 0,
  params: {},
  query: {},
  hash: "",
  fullPath: "/",
  matched: [],
  meta: {},
  redirectedFrom: void 0
};
let Ao = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), ta = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const Qr = "";
function sm(e) {
  if (!e) if (zs) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), Qf(e);
}
const nm = /^[^#]+#/;
function rm(e, t) {
  return e.replace(nm, "#") + t;
}
function om(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const im = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function am(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = om(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function sa(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Ro = /* @__PURE__ */ new Map();
function lm(e, t) {
  Ro.set(e, t);
}
function cm(e) {
  const t = Ro.get(e);
  return Ro.delete(e), t;
}
function um(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function hc(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let Le = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const gc = Symbol("");
Le.MATCHER_NOT_FOUND + "", Le.NAVIGATION_GUARD_REDIRECT + "", Le.NAVIGATION_ABORTED + "", Le.NAVIGATION_CANCELLED + "", Le.NAVIGATION_DUPLICATED + "";
function Hs(e, t) {
  return je(/* @__PURE__ */ new Error(), {
    type: e,
    [gc]: !0
  }, t);
}
function Gt(e, t) {
  return e instanceof Error && gc in e && (t == null || !!(e.type & t));
}
const dm = [
  "params",
  "query",
  "hash"
];
function fm(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of dm) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function mm(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(uc, " "), o = r.indexOf("="), i = Rn(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : Rn(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      At(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function na(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Zf(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (At(n) ? n.map((r) => r && Co(r)) : [n && Co(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function pm(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = At(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const hm = Symbol(""), ra = Symbol(""), Nr = Symbol(""), oi = Symbol(""), Eo = Symbol("");
function nn() {
  let e = [];
  function t(n) {
    return e.push(n), () => {
      const r = e.indexOf(n);
      r > -1 && e.splice(r, 1);
    };
  }
  function s() {
    e = [];
  }
  return {
    add: t,
    list: () => e.slice(),
    reset: s
  };
}
function ds(e, t, s, n, r, o = (i) => i()) {
  const i = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (m) => {
      m === !1 ? l(Hs(Le.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : m instanceof Error ? l(m) : um(m) ? l(Hs(Le.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: m
      })) : (i && n.enterCallbacks[r] === i && typeof m == "function" && i.push(m), a());
    }, u = o(() => e.call(n && n.instances[r], t, s, c));
    let d = Promise.resolve(u);
    e.length < 3 && (d = d.then(c)), d.catch((m) => l(m));
  });
}
function Yr(e, t, s, n, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (lc(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(ds(c, s, n, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const d = $f(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = d;
            const m = (d.__vccOpts || d)[t];
            return m && ds(m, s, n, i, a, r)();
          }));
        }
    }
  return o;
}
function gm(e, t) {
  const s = [], n = [], r = [], o = Math.max(t.matched.length, e.matched.length);
  for (let i = 0; i < o; i++) {
    const a = t.matched[i];
    a && (e.matched.find((c) => Bs(c, a)) ? n.push(a) : s.push(a));
    const l = e.matched[i];
    l && (t.matched.find((c) => Bs(c, l)) || r.push(l));
  }
  return [
    s,
    n,
    r
  ];
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
function vm(e = "") {
  let t = [], s = [[Qr, {}]], n = 0;
  e = sm(e);
  function r(a, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const d = {
      direction: c,
      delta: u,
      type: Ao.pop
    };
    for (const m of t) m(a, l, d);
  }
  const i = {
    location: Qr,
    state: {},
    base: e,
    createHref: rm.bind(null, e),
    replace(a, l) {
      s.splice(n--, 1), r(a, l);
    },
    push(a, l) {
      r(a, l);
    },
    listen(a) {
      return t.push(a), () => {
        const l = t.indexOf(a);
        l > -1 && t.splice(l, 1);
      };
    },
    destroy() {
      t = [], s = [[Qr, {}]], n = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? ta.back : ta.forward;
      n = Math.max(0, Math.min(n + a, s.length - 1)), l && o(this.location, c, {
        direction: u,
        delta: a
      });
    }
  };
  return Object.defineProperty(i, "location", {
    enumerable: !0,
    get: () => s[n][0]
  }), Object.defineProperty(i, "state", {
    enumerable: !0,
    get: () => s[n][1]
  }), i;
}
let Es = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var Ge = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(Ge || {});
const ym = {
  type: Es.Static,
  value: ""
}, bm = /[a-zA-Z0-9_]/;
function _m(e) {
  if (!e) return [[]];
  if (e === "/") return [[ym]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(h) {
    throw new Error(`ERR (${s})/"${c}": ${h}`);
  }
  let s = Ge.Static, n = s;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function d() {
    c && (s === Ge.Static ? o.push({
      type: Es.Static,
      value: c
    }) : s === Ge.Param || s === Ge.ParamRegExp || s === Ge.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: Es.Param,
      value: c,
      regexp: u,
      repeatable: l === "*" || l === "+",
      optional: l === "*" || l === "?"
    })) : t("Invalid state to consume buffer"), c = "");
  }
  function m() {
    c += l;
  }
  for (; a < e.length; ) {
    if (l = e[a++], l === "\\" && s !== Ge.ParamRegExp) {
      n = s, s = Ge.EscapeNext;
      continue;
    }
    switch (s) {
      case Ge.Static:
        l === "/" ? (c && d(), i()) : l === ":" ? (d(), s = Ge.Param) : m();
        break;
      case Ge.EscapeNext:
        m(), s = n;
        break;
      case Ge.Param:
        l === "(" ? s = Ge.ParamRegExp : bm.test(l) ? m() : (d(), s = Ge.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case Ge.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : s = Ge.ParamRegExpEnd : u += l;
        break;
      case Ge.ParamRegExpEnd:
        d(), s = Ge.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === Ge.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), d(), i(), r;
}
const oa = "[^/]+?", wm = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var ot = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(ot || {});
const xm = /[.+*?^${}()[\]/\\]/g;
function km(e, t) {
  const s = je({}, wm, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [ot.Root];
    s.strict && !c.length && (r += "/");
    for (let d = 0; d < c.length; d++) {
      const m = c[d];
      let h = ot.Segment + (s.sensitive ? ot.BonusCaseSensitive : 0);
      if (m.type === Es.Static)
        d || (r += "/"), r += m.value.replace(xm, "\\$&"), h += ot.Static;
      else if (m.type === Es.Param) {
        const { value: k, repeatable: w, optional: z, regexp: N } = m;
        o.push({
          name: k,
          repeatable: w,
          optional: z
        });
        const g = N || oa;
        if (g !== oa) {
          h += ot.BonusCustomRegExp;
          try {
            `${g}`;
          } catch (P) {
            throw new Error(`Invalid custom RegExp for param "${k}" (${g}): ` + P.message);
          }
        }
        let E = w ? `((?:${g})(?:/(?:${g}))*)` : `(${g})`;
        d || (E = z && c.length < 2 ? `(?:/${E})` : "/" + E), z && (E += "?"), r += E, h += ot.Dynamic, z && (h += ot.BonusOptional), w && (h += ot.BonusRepeatable), g === ".*" && (h += ot.BonusWildcard);
      }
      u.push(h);
    }
    n.push(u);
  }
  if (s.strict && s.end) {
    const c = n.length - 1;
    n[c][n[c].length - 1] += ot.BonusStrict;
  }
  s.strict || (r += "/?"), s.end ? r += "$" : s.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const i = new RegExp(r, s.sensitive ? "" : "i");
  function a(c) {
    const u = c.match(i), d = {};
    if (!u) return null;
    for (let m = 1; m < u.length; m++) {
      const h = u[m] || "", k = o[m - 1];
      d[k.name] = h && k.repeatable ? h.split("/") : h;
    }
    return d;
  }
  function l(c) {
    let u = "", d = !1;
    for (const m of e) {
      (!d || !u.endsWith("/")) && (u += "/"), d = !1;
      for (const h of m) if (h.type === Es.Static) u += h.value;
      else if (h.type === Es.Param) {
        const { value: k, repeatable: w, optional: z } = h, N = k in c ? c[k] : "";
        if (At(N) && !w) throw new Error(`Provided param "${k}" is an array but it is not repeatable (* or + modifiers)`);
        const g = At(N) ? N.join("/") : N;
        if (!g) if (z)
          m.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : d = !0);
        else throw new Error(`Missing required param "${k}"`);
        u += g;
      }
    }
    return u || "/";
  }
  return {
    re: i,
    score: n,
    keys: o,
    parse: a,
    stringify: l
  };
}
function Sm(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === ot.Static + ot.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === ot.Static + ot.Segment ? 1 : -1 : 0;
}
function vc(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = Sm(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (ia(n)) return 1;
    if (ia(r)) return -1;
  }
  return r.length - n.length;
}
function ia(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const Cm = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function Am(e, t, s) {
  const n = km(_m(e.path), s), r = je(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function Rm(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = Xi(Cm, t);
  function r(d) {
    return n.get(d);
  }
  function o(d, m, h) {
    const k = !h, w = la(d);
    w.aliasOf = h && h.record;
    const z = Xi(t, d), N = [w];
    if ("alias" in d) {
      const P = typeof d.alias == "string" ? [d.alias] : d.alias;
      for (const J of P) N.push(la(je({}, w, {
        components: h ? h.record.components : w.components,
        path: J,
        aliasOf: h ? h.record : w
      })));
    }
    let g, E;
    for (const P of N) {
      const { path: J } = P;
      if (m && J[0] !== "/") {
        const ve = m.record.path, oe = ve[ve.length - 1] === "/" ? "" : "/";
        P.path = m.record.path + (J && oe + J);
      }
      if (g = Am(P, m, z), h ? h.alias.push(g) : (E = E || g, E !== g && E.alias.push(g), k && d.name && !ca(g) && i(d.name)), yc(g) && l(g), w.children) {
        const ve = w.children;
        for (let oe = 0; oe < ve.length; oe++) o(ve[oe], g, h && h.children[oe]);
      }
      h = h || g;
    }
    return E ? () => {
      i(E);
    } : vn;
  }
  function i(d) {
    if (hc(d)) {
      const m = n.get(d);
      m && (n.delete(d), s.splice(s.indexOf(m), 1), m.children.forEach(i), m.alias.forEach(i));
    } else {
      const m = s.indexOf(d);
      m > -1 && (s.splice(m, 1), d.record.name && n.delete(d.record.name), d.children.forEach(i), d.alias.forEach(i));
    }
  }
  function a() {
    return s;
  }
  function l(d) {
    const m = Tm(d, s);
    s.splice(m, 0, d), d.record.name && !ca(d) && n.set(d.record.name, d);
  }
  function c(d, m) {
    let h, k = {}, w, z;
    if ("name" in d && d.name) {
      if (h = n.get(d.name), !h) throw Hs(Le.MATCHER_NOT_FOUND, { location: d });
      z = h.record.name, k = je(aa(m.params, h.keys.filter((E) => !E.optional).concat(h.parent ? h.parent.keys.filter((E) => E.optional) : []).map((E) => E.name)), d.params && aa(d.params, h.keys.map((E) => E.name))), w = h.stringify(k);
    } else if (d.path != null)
      w = d.path, h = s.find((E) => E.re.test(w)), h && (k = h.parse(w), z = h.record.name);
    else {
      if (h = m.name ? n.get(m.name) : s.find((E) => E.re.test(m.path)), !h) throw Hs(Le.MATCHER_NOT_FOUND, {
        location: d,
        currentLocation: m
      });
      z = h.record.name, k = je({}, m.params, d.params), w = h.stringify(k);
    }
    const N = [];
    let g = h;
    for (; g; )
      N.unshift(g.record), g = g.parent;
    return {
      name: z,
      path: w,
      params: k,
      matched: N,
      meta: Om(N)
    };
  }
  e.forEach((d) => o(d));
  function u() {
    s.length = 0, n.clear();
  }
  return {
    addRoute: o,
    resolve: c,
    removeRoute: i,
    clearRoutes: u,
    getRoutes: a,
    getRecordMatcher: r
  };
}
function aa(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function la(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: Em(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function Em(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function ca(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function Om(e) {
  return e.reduce((t, s) => je(t, s.meta), {});
}
function Tm(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    vc(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = Im(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function Im(e) {
  let t = e;
  for (; t = t.parent; ) if (yc(t) && vc(e, t) === 0) return t;
}
function yc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function ua(e) {
  const t = dt(Nr), s = dt(oi), n = Oe(() => {
    const l = C(e.to);
    return t.resolve(l);
  }), r = Oe(() => {
    const { matched: l } = n.value, { length: c } = l, u = l[c - 1], d = s.matched;
    if (!u || !d.length) return -1;
    const m = d.findIndex(Bs.bind(null, u));
    if (m > -1) return m;
    const h = da(l[c - 2]);
    return c > 1 && da(u) === h && d[d.length - 1].path !== h ? d.findIndex(Bs.bind(null, l[c - 2])) : m;
  }), o = Oe(() => r.value > -1 && jm(s.params, n.value.params)), i = Oe(() => r.value > -1 && r.value === s.matched.length - 1 && pc(s.params, n.value.params));
  function a(l = {}) {
    if (Mm(l)) {
      const c = t[C(e.replace) ? "replace" : "push"](C(e.to)).catch(vn);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: Oe(() => n.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function Nm(e) {
  return e.length === 1 ? e[0] : e;
}
const Pm = /* @__PURE__ */ vt({
  name: "RouterLink",
  compatConfig: { MODE: 3 },
  props: {
    to: {
      type: [String, Object],
      required: !0
    },
    replace: Boolean,
    activeClass: String,
    exactActiveClass: String,
    custom: Boolean,
    ariaCurrentValue: {
      type: String,
      default: "page"
    },
    viewTransition: Boolean
  },
  useLink: ua,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ In(ua(e)), { options: n } = dt(Nr), r = Oe(() => ({
      [fa(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [fa(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && Nm(t.default(s));
      return e.custom ? o : Sn("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), bc = Pm;
function Mm(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function jm(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!At(r) || r.length !== n.length || n.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function da(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const fa = (e, t, s) => e ?? t ?? s, $m = /* @__PURE__ */ vt({
  name: "RouterView",
  inheritAttrs: !1,
  props: {
    name: {
      type: String,
      default: "default"
    },
    route: Object
  },
  compatConfig: { MODE: 3 },
  setup(e, { attrs: t, slots: s }) {
    const n = dt(Eo), r = Oe(() => e.route || n.value), o = dt(ra, 0), i = Oe(() => {
      let c = C(o);
      const { matched: u } = r.value;
      let d;
      for (; (d = u[c]) && !d.components; ) c++;
      return c;
    }), a = Oe(() => r.value.matched[i.value]);
    Zn(ra, Oe(() => i.value + 1)), Zn(hm, a), Zn(Eo, r);
    const l = /* @__PURE__ */ G();
    return es(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, d], [m, h, k]) => {
      u && (u.instances[d] = c, h && h !== u && c && c === m && (u.leaveGuards.size || (u.leaveGuards = h.leaveGuards), u.updateGuards.size || (u.updateGuards = h.updateGuards))), c && u && (!h || !Bs(u, h) || !m) && (u.enterCallbacks[d] || []).forEach((w) => w(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, d = a.value, m = d && d.components[u];
      if (!m) return ma(s.default, {
        Component: m,
        route: c
      });
      const h = d.props[u], k = h ? h === !0 ? c.params : typeof h == "function" ? h(c) : h : null, z = Sn(m, je({}, k, t, {
        onVnodeUnmounted: (N) => {
          N.component.isUnmounted && (d.instances[u] = null);
        },
        ref: l
      }));
      return ma(s.default, {
        Component: z,
        route: c
      }) || z;
    };
  }
});
function ma(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const _c = $m;
function zm(e) {
  const t = Rm(e.routes, e), s = e.parseQuery || mm, n = e.stringifyQuery || na, r = e.history, o = nn(), i = nn(), a = nn(), l = /* @__PURE__ */ mn(is);
  let c = is;
  zs && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = Kr.bind(null, (S) => "" + S), d = Kr.bind(null, Kf), m = Kr.bind(null, Rn);
  function h(S, B) {
    let T, se;
    return hc(S) ? (T = t.getRecordMatcher(S), se = B) : se = S, t.addRoute(se, T);
  }
  function k(S) {
    const B = t.getRecordMatcher(S);
    B && t.removeRoute(B);
  }
  function w() {
    return t.getRoutes().map((S) => S.record);
  }
  function z(S) {
    return !!t.getRecordMatcher(S);
  }
  function N(S, B) {
    if (B = je({}, B || l.value), typeof S == "string") {
      const b = Jr(s, S, B.path), x = t.resolve({ path: b.path }, B), A = r.createHref(b.fullPath);
      return je(b, x, {
        params: m(x.params),
        hash: Rn(b.hash),
        redirectedFrom: void 0,
        href: A
      });
    }
    let T;
    if (S.path != null)
      T = je({}, S, { path: Jr(s, S.path, B.path).path });
    else {
      const b = je({}, S.params);
      for (const x in b) b[x] == null && delete b[x];
      T = je({}, S, { params: d(b) }), B.params = d(B.params);
    }
    const se = t.resolve(T, B), f = S.hash || "";
    se.params = u(m(se.params));
    const p = Yf(n, je({}, S, {
      hash: Gf(f),
      path: se.path
    })), v = r.createHref(p);
    return je({
      fullPath: p,
      hash: f,
      query: n === na ? pm(S.query) : S.query || {}
    }, se, {
      redirectedFrom: void 0,
      href: v
    });
  }
  function g(S) {
    return typeof S == "string" ? Jr(s, S, l.value.path) : je({}, S);
  }
  function E(S, B) {
    if (c !== S) return Hs(Le.NAVIGATION_CANCELLED, {
      from: B,
      to: S
    });
  }
  function P(S) {
    return oe(S);
  }
  function J(S) {
    return P(je(g(S), { replace: !0 }));
  }
  function ve(S, B) {
    const T = S.matched[S.matched.length - 1];
    if (T && T.redirect) {
      const { redirect: se } = T;
      let f = typeof se == "function" ? se(S, B) : se;
      return typeof f == "string" && (f = f.includes("?") || f.includes("#") ? f = g(f) : { path: f }, f.params = {}), je({
        query: S.query,
        hash: S.hash,
        params: f.path != null ? {} : S.params
      }, f);
    }
  }
  function oe(S, B) {
    const T = c = N(S), se = l.value, f = S.state, p = S.force, v = S.replace === !0, b = ve(T, se);
    if (b) return oe(je(g(b), {
      state: typeof b == "object" ? je({}, f, b.state) : f,
      force: p,
      replace: v
    }), B || T);
    const x = T;
    x.redirectedFrom = B;
    let A;
    return !p && Xf(n, se, T) && (A = Hs(Le.NAVIGATION_DUPLICATED, {
      to: x,
      from: se
    }), nt(se, se, !0, !1)), (A ? Promise.resolve(A) : ce(x, se)).catch((O) => Gt(O) ? Gt(O, Le.NAVIGATION_GUARD_REDIRECT) ? O : $(O) : fe(O, x, se)).then((O) => {
      if (O) {
        if (Gt(O, Le.NAVIGATION_GUARD_REDIRECT))
          return oe(je({ replace: v }, g(O.to), {
            state: typeof O.to == "object" ? je({}, f, O.to.state) : f,
            force: p
          }), B || x);
      } else O = ke(x, se, !0, v, f);
      return xe(x, se, O), O;
    });
  }
  function _(S, B) {
    const T = E(S, B);
    return T ? Promise.reject(T) : Promise.resolve();
  }
  function V(S) {
    const B = xt.values().next().value;
    return B && typeof B.runWithContext == "function" ? B.runWithContext(S) : S();
  }
  function ce(S, B) {
    let T;
    const [se, f, p] = gm(S, B);
    T = Yr(se.reverse(), "beforeRouteLeave", S, B);
    for (const b of se) b.leaveGuards.forEach((x) => {
      T.push(ds(x, S, B));
    });
    const v = _.bind(null, S, B);
    return T.push(v), Re(T).then(() => {
      T = [];
      for (const b of o.list()) T.push(ds(b, S, B));
      return T.push(v), Re(T);
    }).then(() => {
      T = Yr(f, "beforeRouteUpdate", S, B);
      for (const b of f) b.updateGuards.forEach((x) => {
        T.push(ds(x, S, B));
      });
      return T.push(v), Re(T);
    }).then(() => {
      T = [];
      for (const b of p) if (b.beforeEnter) if (At(b.beforeEnter)) for (const x of b.beforeEnter) T.push(ds(x, S, B));
      else T.push(ds(b.beforeEnter, S, B));
      return T.push(v), Re(T);
    }).then(() => (S.matched.forEach((b) => b.enterCallbacks = {}), T = Yr(p, "beforeRouteEnter", S, B, V), T.push(v), Re(T))).then(() => {
      T = [];
      for (const b of i.list()) T.push(ds(b, S, B));
      return T.push(v), Re(T);
    }).catch((b) => Gt(b, Le.NAVIGATION_CANCELLED) ? b : Promise.reject(b));
  }
  function xe(S, B, T) {
    a.list().forEach((se) => V(() => se(S, B, T)));
  }
  function ke(S, B, T, se, f) {
    const p = E(S, B);
    if (p) return p;
    const v = B === is, b = zs ? history.state : {};
    T && (se || v ? r.replace(S.fullPath, je({ scroll: v && b && b.scroll }, f)) : r.push(S.fullPath, f)), l.value = S, nt(S, B, T, v), $();
  }
  let Te;
  function D() {
    Te || (Te = r.listen((S, B, T) => {
      if (!De.listening) return;
      const se = N(S), f = ve(se, De.currentRoute.value);
      if (f) {
        oe(je(f, {
          replace: !0,
          force: !0
        }), se).catch(vn);
        return;
      }
      c = se;
      const p = l.value;
      zs && lm(sa(p.fullPath, T.delta), im()), ce(se, p).catch((v) => Gt(v, Le.NAVIGATION_ABORTED | Le.NAVIGATION_CANCELLED) ? v : Gt(v, Le.NAVIGATION_GUARD_REDIRECT) ? (oe(je(g(v.to), { force: !0 }), se).then((b) => {
        Gt(b, Le.NAVIGATION_ABORTED | Le.NAVIGATION_DUPLICATED) && !T.delta && T.type === Ao.pop && r.go(-1, !1);
      }).catch(vn), Promise.reject()) : (T.delta && r.go(-T.delta, !1), fe(v, se, p))).then((v) => {
        v = v || ke(se, p, !1), v && (T.delta && !Gt(v, Le.NAVIGATION_CANCELLED) ? r.go(-T.delta, !1) : T.type === Ao.pop && Gt(v, Le.NAVIGATION_ABORTED | Le.NAVIGATION_DUPLICATED) && r.go(-1, !1)), xe(se, p, v);
      }).catch(vn);
    }));
  }
  let me = nn(), ne = nn(), q;
  function fe(S, B, T) {
    $(S);
    const se = ne.list();
    return se.length ? se.forEach((f) => f(S, B, T)) : console.error(S), Promise.reject(S);
  }
  function Pe() {
    return q && l.value !== is ? Promise.resolve() : new Promise((S, B) => {
      me.add([S, B]);
    });
  }
  function $(S) {
    return q || (q = !S, D(), me.list().forEach(([B, T]) => S ? T(S) : B()), me.reset()), S;
  }
  function nt(S, B, T, se) {
    const { scrollBehavior: f } = e;
    if (!zs || !f) return Promise.resolve();
    const p = !T && cm(sa(S.fullPath, 0)) || (se || !T) && history.state && history.state.scroll || null;
    return Sr().then(() => f(S, B, p)).then((v) => v && am(v)).catch((v) => fe(v, S, B));
  }
  const Ue = (S) => r.go(S);
  let wt;
  const xt = /* @__PURE__ */ new Set(), De = {
    currentRoute: l,
    listening: !0,
    addRoute: h,
    removeRoute: k,
    clearRoutes: t.clearRoutes,
    hasRoute: z,
    getRoutes: w,
    resolve: N,
    options: e,
    push: P,
    replace: J,
    go: Ue,
    back: () => Ue(-1),
    forward: () => Ue(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: ne.add,
    isReady: Pe,
    install(S) {
      S.component("RouterLink", bc), S.component("RouterView", _c), S.config.globalProperties.$router = De, Object.defineProperty(S.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => C(l)
      }), zs && !wt && l.value === is && (wt = !0, P(r.location).catch((se) => {
      }));
      const B = {};
      for (const se in is) Object.defineProperty(B, se, {
        get: () => l.value[se],
        enumerable: !0
      });
      S.provide(Nr, De), S.provide(oi, /* @__PURE__ */ vl(B)), S.provide(Eo, l);
      const T = S.unmount;
      xt.add(S), S.unmount = function() {
        xt.delete(S), xt.size < 1 && (c = is, Te && Te(), Te = null, l.value = is, wt = !1, q = !1), T();
      };
    }
  };
  function Re(S) {
    return S.reduce((B, T) => B.then(() => V(T)), Promise.resolve());
  }
  return De;
}
function Dm() {
  return dt(Nr);
}
function wc(e) {
  return dt(oi);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ss = {
  xmlns: "http://www.w3.org/2000/svg",
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  "stroke-width": 2,
  "stroke-linecap": "round",
  "stroke-linejoin": "round"
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const pa = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Xr(e) {
  return e != null;
}
function Vm(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (m) => s[m] ?? m, r = e.size ?? e.width ?? Ss.width, o = e.size ?? e.height ?? Ss.height, i = e.aliases?.filter((m) => typeof m == "string" && m.trim() !== "").map((m) => `lucide-${m}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? pa(...l) : pa("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? Ss["stroke-width"]) * Number(e.size ?? e.width ?? Ss.width) / Number(t.size ?? t.width ?? Ss.width) : t.strokeWidth ?? Ss["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(Ss).reduce((m, [h, k]) => (m[n(h)] = k, m), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && Xr(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && Xr(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && Xr(t.height) && {
        [n("height")]: t.height
      },
      [n("stroke-width")]: u,
      ...c && {
        [n("class")]: c
      },
      [n("viewBox")]: `0 0 ${r} ${o}`,
      ...t.hasA11yProp === !1 ? {
        [n("aria-hidden")]: "true"
      } : {},
      ..."attributes" in t && t.attributes
    },
    e.node.map((m) => {
      const [h, k, w] = m, z = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...k } : k;
      return w ? [h, z, w] : [h, z];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Lm = (e) => {
  for (const t in e)
    if (t.startsWith("aria-") || t === "role" || t === "title")
      return !0;
  return !1;
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ln = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Fm = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Um = /* @__PURE__ */ Symbol("lucide-icons");
function Wm() {
  return dt(Um, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Bm = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && Fm(e),
    node: t ?? s ?? [],
    size: 24,
    aliases: []
  },
  absoluteStrokeWidth: r,
  "absolute-stroke-width": o,
  nonScalingStroke: i,
  "non-scaling-stroke": a,
  strokeWidth: l,
  "stroke-width": c,
  size: u,
  width: d = u,
  height: m = u,
  color: h,
  ...k
}, { slots: w }) => {
  const {
    size: z,
    color: N,
    strokeWidth: g = 2,
    absoluteStrokeWidth: E = !1,
    nonScalingStroke: P = !1,
    class: J = ""
  } = Wm(), ve = Ln(r) || Ln(o) || r === !0 || o === !0 || E === !0, oe = Ln(i) || Ln(a) || i === !0 || a === !0 || P === !0;
  delete k.class;
  const _ = w.default?.(), [, V, ce = []] = Vm(n, {
    color: h ?? N,
    width: d ?? u ?? z,
    height: m ?? u ?? z,
    strokeWidth: l ?? c ?? g,
    absoluteStrokeWidth: ve,
    nonScalingStroke: oe,
    className: J,
    hasA11yProp: _ != null && _.length > 0 || Lm(k),
    attributes: k
  });
  return Sn("svg", V, [
    ...ce.map(([xe, ke]) => Sn(xe, ke)),
    ..._ ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Rt(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => Sn(
    Bm,
    {
      ...n,
      icon: s
    },
    r.default ? { default: r.default } : void 0
  );
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Hm = {
  name: "database",
  size: 24,
  node: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]
}, Gm = Rt(Hm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Zm = {
  name: "flask-conical",
  size: 24,
  node: [
    [
      "path",
      {
        d: "M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2",
        key: "18mbvz"
      }
    ],
    ["path", { d: "M6.453 15h11.094", key: "3shlmq" }],
    ["path", { d: "M8.5 2h7", key: "csnxdl" }]
  ]
}, xc = Rt(Zm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const qm = {
  name: "layers",
  size: 24,
  node: [
    [
      "path",
      {
        d: "M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z",
        key: "zw3jo"
      }
    ],
    [
      "path",
      {
        d: "M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12",
        key: "1wduqc"
      }
    ],
    [
      "path",
      {
        d: "M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17",
        key: "kqbvx6"
      }
    ]
  ],
  aliases: ["layers-3"]
}, Oo = Rt(qm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Km = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, Jm = Rt(Km);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Qm = {
  name: "play",
  size: 24,
  node: [
    [
      "path",
      {
        d: "M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z",
        key: "10ikf1"
      }
    ]
  ]
}, Ym = Rt(Qm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Xm = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, Pr = Rt(Xm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ep = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, kc = Rt(ep);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const tp = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, sp = Rt(tp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const np = {
  name: "server-cog",
  size: 24,
  node: [
    ["path", { d: "m10.852 14.772-.383.923", key: "11vil6" }],
    ["path", { d: "M13.148 14.772a3 3 0 1 0-2.296-5.544l-.383-.923", key: "1v3clb" }],
    ["path", { d: "m13.148 9.228.383-.923", key: "t2zzyc" }],
    ["path", { d: "m13.53 15.696-.382-.924a3 3 0 1 1-2.296-5.544", key: "1bxfiv" }],
    ["path", { d: "m14.772 10.852.923-.383", key: "k9m8cz" }],
    ["path", { d: "m14.772 13.148.923.383", key: "1xvhww" }],
    [
      "path",
      {
        d: "M4.5 10H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-.5",
        key: "tn8das"
      }
    ],
    [
      "path",
      {
        d: "M4.5 14H4a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2h-.5",
        key: "1g2pve"
      }
    ],
    ["path", { d: "M6 18h.01", key: "uhywen" }],
    ["path", { d: "M6 6h.01", key: "1utrut" }],
    ["path", { d: "m9.228 10.852-.923-.383", key: "1wtb30" }],
    ["path", { d: "m9.228 13.148-.923.383", key: "1a830x" }]
  ]
}, Sc = Rt(np);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const rp = {
  name: "settings",
  size: 24,
  node: [
    [
      "path",
      {
        d: "M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915",
        key: "1i5ecw"
      }
    ],
    ["circle", { cx: "12", cy: "12", r: "3", key: "1v7zrd" }]
  ]
}, Cc = Rt(rp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const op = {
  name: "wand-sparkles",
  size: 24,
  node: [
    [
      "path",
      {
        d: "m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72",
        key: "ul74o6"
      }
    ],
    ["path", { d: "m14 7 3 3", key: "1r5n42" }],
    ["path", { d: "M5 6v4", key: "ilb8ba" }],
    ["path", { d: "M19 14v4", key: "blhpug" }],
    ["path", { d: "M10 2v2", key: "7u0qdc" }],
    ["path", { d: "M7 8H3", key: "zfb6yr" }],
    ["path", { d: "M21 16h-4", key: "1cnmox" }],
    ["path", { d: "M11 3H9", key: "1obp7u" }]
  ],
  aliases: ["wand-2"]
}, ip = Rt(op);
function ap(e) {
  return Uo() ? (tl(e), !0) : !1;
}
const eo = /* @__PURE__ */ new WeakMap(), lp = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const s = e[0], n = (t = Or()) == null ? void 0 : t.proxy;
  if (n == null && !Qo())
    throw new Error("injectLocal must be called in setup");
  return n && eo.has(n) && s in eo.get(n) ? eo.get(n)[s] : dt(...e);
}, cp = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const up = Object.prototype.toString, dp = (e) => up.call(e) === "[object Object]";
function ha(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function to(e) {
  return Array.isArray(e) ? e : [e];
}
function fp(e, t, s) {
  return es(
    e,
    t,
    {
      ...s,
      immediate: !0
    }
  );
}
const Ac = cp ? window : void 0;
function mp(e) {
  var t;
  const s = Vs(e);
  return (t = s?.$el) != null ? t : s;
}
function pp(...e) {
  const t = [], s = () => {
    t.forEach((a) => a()), t.length = 0;
  }, n = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = Oe(() => {
    const a = to(Vs(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = fp(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => mp(c))) != null ? l : [Ac].filter((c) => c != null),
        to(Vs(r.value ? e[1] : e[0])),
        to(C(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Vs(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (s(), !a?.length || !l?.length || !c?.length)
        return;
      const d = dp(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (m) => l.flatMap(
            (h) => c.map((k) => n(m, h, k, d))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), s();
  };
  return ap(s), i;
}
// @__NO_SIDE_EFFECTS__
function hp() {
  const e = /* @__PURE__ */ mn(!1), t = Or();
  return t && Qs(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function gp(e) {
  const t = /* @__PURE__ */ hp();
  return Oe(() => (t.value, !!e()));
}
const vp = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function yp() {
  const e = Qo() ? /* @__PURE__ */ lp(vp, null) : null;
  return typeof e == "number" ? e : void 0;
}
function bp(e, t = {}) {
  const { window: s = Ac, ssrWidth: n = /* @__PURE__ */ yp() } = t, r = /* @__PURE__ */ gp(() => s && "matchMedia" in s && typeof s.matchMedia == "function"), o = /* @__PURE__ */ mn(typeof n == "number"), i = /* @__PURE__ */ mn(), a = /* @__PURE__ */ mn(!1), l = (c) => {
    a.value = c.matches;
  };
  return Hu(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Vs(e).split(",");
      a.value = c.some((u) => {
        const d = u.includes("not all"), m = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), h = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let k = !!(m || h);
        return m && k && (k = n >= ha(m[1])), h && k && (k = n <= ha(h[1])), d ? !k : k;
      });
      return;
    }
    r.value && (i.value = s.matchMedia(Vs(e)), a.value = i.value.matches);
  }), pp(i, "change", l, { passive: !0 }), Oe(() => a.value);
}
const Rc = "comfymodal", ii = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], _p = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function ys(e) {
  return typeof e == "string" && ii.indexOf(e) !== -1;
}
function Fn(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function Ec(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || Fn(r.slice(0, o)) !== Rc) return t;
  const i = Fn(r.slice(o + 1));
  if (!ys(i)) return t;
  let a = null;
  for (let l = 1; l < n.length; l++) {
    const c = n[l], u = c.indexOf("=");
    if (u === -1 || Fn(c.slice(0, u)) !== "focus") continue;
    const d = Fn(c.slice(u + 1));
    a = d === null || d === "" ? null : d;
    break;
  }
  return { matched: !0, page: i, focus: a };
}
function Oc(e) {
  if (!ys(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + Rc + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function ga(e, t) {
  if (!t || !ys(t.page)) return "none";
  if (!e || !ys(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function wp(e, t) {
  if (e && ys(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = Ec(t);
  return s.matched && ys(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
const xp = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function so(e) {
  return xp.has(e);
}
let va = 0;
function kp() {
  return va += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${va}`;
}
const ai = /* @__PURE__ */ Xs("studio-operations", () => {
  const e = /* @__PURE__ */ G(/* @__PURE__ */ new Map()), t = Oe(() => [...e.value.values()]), s = Oe(
    () => t.value.filter((m) => m.status === "pending" || m.status === "running")
  );
  function n(m) {
    return e.value.get(m);
  }
  function r(m) {
    const h = Date.now(), k = kp(), w = m.status === "pending" ? "pending" : "running";
    return e.value.set(k, {
      id: k,
      kind: m.kind,
      label: m.label,
      status: w,
      progress: m.progress,
      message: m.message,
      startedAt: h,
      finishedAt: void 0,
      workspaceId: m.workspaceId
    }), k;
  }
  function o(m, h) {
    const k = e.value.get(m);
    if (!k) return;
    const { status: w, ...z } = h, N = { ...k, ...z };
    !so(k.status) && w !== void 0 && !so(w) && (N.status = w), e.value.set(m, N);
  }
  function i(m, h, k) {
    const w = e.value.get(m);
    !w || so(w.status) || e.value.set(m, {
      ...w,
      status: h,
      message: k === void 0 ? w.message : k,
      finishedAt: Date.now()
    });
  }
  function a(m, h) {
    i(m, "completed", h);
  }
  function l(m, h) {
    i(m, "failed", h);
  }
  function c(m, h) {
    i(m, "canceled", h);
  }
  function u(m) {
    e.value.delete(m);
  }
  function d() {
    e.value.clear();
  }
  return {
    byId: e,
    all: t,
    active: s,
    get: n,
    start: r,
    patch: o,
    finish: a,
    fail: l,
    cancel: c,
    remove: u,
    clear: d
  };
});
var we;
(function(e) {
  e.assertEqual = (r) => {
  };
  function t(r) {
  }
  e.assertIs = t;
  function s(r) {
    throw new Error();
  }
  e.assertNever = s, e.arrayToEnum = (r) => {
    const o = {};
    for (const i of r)
      o[i] = i;
    return o;
  }, e.getValidEnumValues = (r) => {
    const o = e.objectKeys(r).filter((a) => typeof r[r[a]] != "number"), i = {};
    for (const a of o)
      i[a] = r[a];
    return e.objectValues(i);
  }, e.objectValues = (r) => e.objectKeys(r).map(function(o) {
    return r[o];
  }), e.objectKeys = typeof Object.keys == "function" ? (r) => Object.keys(r) : (r) => {
    const o = [];
    for (const i in r)
      Object.prototype.hasOwnProperty.call(r, i) && o.push(i);
    return o;
  }, e.find = (r, o) => {
    for (const i of r)
      if (o(i))
        return i;
  }, e.isInteger = typeof Number.isInteger == "function" ? (r) => Number.isInteger(r) : (r) => typeof r == "number" && Number.isFinite(r) && Math.floor(r) === r;
  function n(r, o = " | ") {
    return r.map((i) => typeof i == "string" ? `'${i}'` : i).join(o);
  }
  e.joinValues = n, e.jsonStringifyReplacer = (r, o) => typeof o == "bigint" ? o.toString() : o;
})(we || (we = {}));
var ya;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(ya || (ya = {}));
const Z = we.arrayToEnum([
  "string",
  "nan",
  "number",
  "integer",
  "float",
  "boolean",
  "date",
  "bigint",
  "symbol",
  "function",
  "undefined",
  "null",
  "array",
  "object",
  "unknown",
  "promise",
  "void",
  "never",
  "map",
  "set"
]), fs = (e) => {
  switch (typeof e) {
    case "undefined":
      return Z.undefined;
    case "string":
      return Z.string;
    case "number":
      return Number.isNaN(e) ? Z.nan : Z.number;
    case "boolean":
      return Z.boolean;
    case "function":
      return Z.function;
    case "bigint":
      return Z.bigint;
    case "symbol":
      return Z.symbol;
    case "object":
      return Array.isArray(e) ? Z.array : e === null ? Z.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? Z.promise : typeof Map < "u" && e instanceof Map ? Z.map : typeof Set < "u" && e instanceof Set ? Z.set : typeof Date < "u" && e instanceof Date ? Z.date : Z.object;
    default:
      return Z.unknown;
  }
}, I = we.arrayToEnum([
  "invalid_type",
  "invalid_literal",
  "custom",
  "invalid_union",
  "invalid_union_discriminator",
  "invalid_enum_value",
  "unrecognized_keys",
  "invalid_arguments",
  "invalid_return_type",
  "invalid_date",
  "invalid_string",
  "too_small",
  "too_big",
  "invalid_intersection_types",
  "not_multiple_of",
  "not_finite"
]);
class rs extends Error {
  get errors() {
    return this.issues;
  }
  constructor(t) {
    super(), this.issues = [], this.addIssue = (n) => {
      this.issues = [...this.issues, n];
    }, this.addIssues = (n = []) => {
      this.issues = [...this.issues, ...n];
    };
    const s = new.target.prototype;
    Object.setPrototypeOf ? Object.setPrototypeOf(this, s) : this.__proto__ = s, this.name = "ZodError", this.issues = t;
  }
  format(t) {
    const s = t || function(o) {
      return o.message;
    }, n = { _errors: [] }, r = (o) => {
      for (const i of o.issues)
        if (i.code === "invalid_union")
          i.unionErrors.map(r);
        else if (i.code === "invalid_return_type")
          r(i.returnTypeError);
        else if (i.code === "invalid_arguments")
          r(i.argumentsError);
        else if (i.path.length === 0)
          n._errors.push(s(i));
        else {
          let a = n, l = 0;
          for (; l < i.path.length; ) {
            const c = i.path[l];
            l === i.path.length - 1 ? (a[c] = a[c] || { _errors: [] }, a[c]._errors.push(s(i))) : a[c] = a[c] || { _errors: [] }, a = a[c], l++;
          }
        }
    };
    return r(this), n;
  }
  static assert(t) {
    if (!(t instanceof rs))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, we.jsonStringifyReplacer, 2);
  }
  get isEmpty() {
    return this.issues.length === 0;
  }
  flatten(t = (s) => s.message) {
    const s = {}, n = [];
    for (const r of this.issues)
      if (r.path.length > 0) {
        const o = r.path[0];
        s[o] = s[o] || [], s[o].push(t(r));
      } else
        n.push(t(r));
    return { formErrors: n, fieldErrors: s };
  }
  get formErrors() {
    return this.flatten();
  }
}
rs.create = (e) => new rs(e);
const To = (e, t) => {
  let s;
  switch (e.code) {
    case I.invalid_type:
      e.received === Z.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case I.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, we.jsonStringifyReplacer)}`;
      break;
    case I.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${we.joinValues(e.keys, ", ")}`;
      break;
    case I.invalid_union:
      s = "Invalid input";
      break;
    case I.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${we.joinValues(e.options)}`;
      break;
    case I.invalid_enum_value:
      s = `Invalid enum value. Expected ${we.joinValues(e.options)}, received '${e.received}'`;
      break;
    case I.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case I.invalid_return_type:
      s = "Invalid function return type";
      break;
    case I.invalid_date:
      s = "Invalid date";
      break;
    case I.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : we.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case I.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case I.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case I.custom:
      s = "Invalid input";
      break;
    case I.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case I.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case I.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, we.assertNever(e);
  }
  return { message: s };
};
let Sp = To;
function Cp() {
  return Sp;
}
const Ap = (e) => {
  const { data: t, path: s, errorMaps: n, issueData: r } = e, o = [...s, ...r.path || []], i = {
    ...r,
    path: o
  };
  if (r.message !== void 0)
    return {
      ...r,
      path: o,
      message: r.message
    };
  let a = "";
  const l = n.filter((c) => !!c).slice().reverse();
  for (const c of l)
    a = c(i, { data: t, defaultError: a }).message;
  return {
    ...r,
    path: o,
    message: a
  };
};
function F(e, t) {
  const s = Cp(), n = Ap({
    issueData: t,
    data: e.data,
    path: e.path,
    errorMaps: [
      e.common.contextualErrorMap,
      // contextual error map is first priority
      e.schemaErrorMap,
      // then schema-bound map if available
      s,
      // then global override map
      s === To ? void 0 : To
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(n);
}
class ct {
  constructor() {
    this.value = "valid";
  }
  dirty() {
    this.value === "valid" && (this.value = "dirty");
  }
  abort() {
    this.value !== "aborted" && (this.value = "aborted");
  }
  static mergeArray(t, s) {
    const n = [];
    for (const r of s) {
      if (r.status === "aborted")
        return ue;
      r.status === "dirty" && t.dirty(), n.push(r.value);
    }
    return { status: t.value, value: n };
  }
  static async mergeObjectAsync(t, s) {
    const n = [];
    for (const r of s) {
      const o = await r.key, i = await r.value;
      n.push({
        key: o,
        value: i
      });
    }
    return ct.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const r of s) {
      const { key: o, value: i } = r;
      if (o.status === "aborted" || i.status === "aborted")
        return ue;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (n[o.value] = i.value);
    }
    return { status: t.value, value: n };
  }
}
const ue = Object.freeze({
  status: "aborted"
}), cn = (e) => ({ status: "dirty", value: e }), _t = (e) => ({ status: "valid", value: e }), ba = (e) => e.status === "aborted", _a = (e) => e.status === "dirty", Gs = (e) => e.status === "valid", ir = (e) => typeof Promise < "u" && e instanceof Promise;
var K;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(K || (K = {}));
class Bt {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const wa = (e, t) => {
  if (Gs(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new rs(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function pe(e) {
  if (!e)
    return {};
  const { errorMap: t, invalid_type_error: s, required_error: n, description: r } = e;
  if (t && (s || n))
    throw new Error(`Can't use "invalid_type_error" or "required_error" in conjunction with custom error map.`);
  return t ? { errorMap: t, description: r } : { errorMap: (i, a) => {
    const { message: l } = e;
    return i.code === "invalid_enum_value" ? { message: l ?? a.defaultError } : typeof a.data > "u" ? { message: l ?? n ?? a.defaultError } : i.code !== "invalid_type" ? { message: a.defaultError } : { message: l ?? s ?? a.defaultError };
  }, description: r };
}
class ye {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return fs(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: fs(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new ct(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: fs(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (ir(s))
      throw new Error("Synchronous parse encountered promise.");
    return s;
  }
  _parseAsync(t) {
    const s = this._parse(t);
    return Promise.resolve(s);
  }
  parse(t, s) {
    const n = this.safeParse(t, s);
    if (n.success)
      return n.data;
    throw n.error;
  }
  safeParse(t, s) {
    const n = {
      common: {
        issues: [],
        async: s?.async ?? !1,
        contextualErrorMap: s?.errorMap
      },
      path: s?.path || [],
      schemaErrorMap: this._def.errorMap,
      parent: null,
      data: t,
      parsedType: fs(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return wa(n, r);
  }
  "~validate"(t) {
    const s = {
      common: {
        issues: [],
        async: !!this["~standard"].async
      },
      path: [],
      schemaErrorMap: this._def.errorMap,
      parent: null,
      data: t,
      parsedType: fs(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return Gs(n) ? {
          value: n.value
        } : {
          issues: s.common.issues
        };
      } catch (n) {
        n?.message?.toLowerCase()?.includes("encountered") && (this["~standard"].async = !0), s.common = {
          issues: [],
          async: !0
        };
      }
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => Gs(n) ? {
      value: n.value
    } : {
      issues: s.common.issues
    });
  }
  async parseAsync(t, s) {
    const n = await this.safeParseAsync(t, s);
    if (n.success)
      return n.data;
    throw n.error;
  }
  async safeParseAsync(t, s) {
    const n = {
      common: {
        issues: [],
        contextualErrorMap: s?.errorMap,
        async: !0
      },
      path: s?.path || [],
      schemaErrorMap: this._def.errorMap,
      parent: null,
      data: t,
      parsedType: fs(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (ir(r) ? r : Promise.resolve(r));
    return wa(n, o);
  }
  refine(t, s) {
    const n = (r) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(r) : s;
    return this._refinement((r, o) => {
      const i = t(r), a = () => o.addIssue({
        code: I.custom,
        ...n(r)
      });
      return typeof Promise < "u" && i instanceof Promise ? i.then((l) => l ? !0 : (a(), !1)) : i ? !0 : (a(), !1);
    });
  }
  refinement(t, s) {
    return this._refinement((n, r) => t(n) ? !0 : (r.addIssue(typeof s == "function" ? s(n, r) : s), !1));
  }
  _refinement(t) {
    return new Ks({
      schema: this,
      typeName: le.ZodEffects,
      effect: { type: "refinement", refinement: t }
    });
  }
  superRefine(t) {
    return this._refinement(t);
  }
  constructor(t) {
    this.spa = this.safeParseAsync, this._def = t, this.parse = this.parse.bind(this), this.safeParse = this.safeParse.bind(this), this.parseAsync = this.parseAsync.bind(this), this.safeParseAsync = this.safeParseAsync.bind(this), this.spa = this.spa.bind(this), this.refine = this.refine.bind(this), this.refinement = this.refinement.bind(this), this.superRefine = this.superRefine.bind(this), this.optional = this.optional.bind(this), this.nullable = this.nullable.bind(this), this.nullish = this.nullish.bind(this), this.array = this.array.bind(this), this.promise = this.promise.bind(this), this.or = this.or.bind(this), this.and = this.and.bind(this), this.transform = this.transform.bind(this), this.brand = this.brand.bind(this), this.default = this.default.bind(this), this.catch = this.catch.bind(this), this.describe = this.describe.bind(this), this.pipe = this.pipe.bind(this), this.readonly = this.readonly.bind(this), this.isNullable = this.isNullable.bind(this), this.isOptional = this.isOptional.bind(this), this["~standard"] = {
      version: 1,
      vendor: "zod",
      validate: (s) => this["~validate"](s)
    };
  }
  optional() {
    return hs.create(this, this._def);
  }
  nullable() {
    return Js.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return Lt.create(this);
  }
  promise() {
    return dr.create(this, this._def);
  }
  or(t) {
    return lr.create([this, t], this._def);
  }
  and(t) {
    return cr.create(this, t, this._def);
  }
  transform(t) {
    return new Ks({
      ...pe(this._def),
      schema: this,
      typeName: le.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Po({
      ...pe(this._def),
      innerType: this,
      defaultValue: s,
      typeName: le.ZodDefault
    });
  }
  brand() {
    return new Kp({
      typeName: le.ZodBranded,
      type: this,
      ...pe(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Mo({
      ...pe(this._def),
      innerType: this,
      catchValue: s,
      typeName: le.ZodCatch
    });
  }
  describe(t) {
    const s = this.constructor;
    return new s({
      ...this._def,
      description: t
    });
  }
  pipe(t) {
    return li.create(this, t);
  }
  readonly() {
    return jo.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const Rp = /^c[^\s-]{8,}$/i, Ep = /^[0-9a-z]+$/, Op = /^[0-9A-HJKMNP-TV-Z]{26}$/i, Tp = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, Ip = /^[a-z0-9_-]{21}$/i, Np = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, Pp = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Mp = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, jp = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let no;
const $p = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, zp = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, Dp = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, Vp = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, Lp = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, Fp = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, Tc = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", Up = new RegExp(`^${Tc}$`);
function Ic(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function Wp(e) {
  return new RegExp(`^${Ic(e)}$`);
}
function Bp(e) {
  let t = `${Tc}T${Ic(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function Hp(e, t) {
  return !!((t === "v4" || !t) && $p.test(e) || (t === "v6" || !t) && Dp.test(e));
}
function Gp(e, t) {
  if (!Np.test(e))
    return !1;
  try {
    const [s] = e.split(".");
    if (!s)
      return !1;
    const n = s.replace(/-/g, "+").replace(/_/g, "/").padEnd(s.length + (4 - s.length % 4) % 4, "="), r = JSON.parse(atob(n));
    return !(typeof r != "object" || r === null || "typ" in r && r?.typ !== "JWT" || !r.alg || t && r.alg !== t);
  } catch {
    return !1;
  }
}
function Zp(e, t) {
  return !!((t === "v4" || !t) && zp.test(e) || (t === "v6" || !t) && Vp.test(e));
}
class Yt extends ye {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== Z.string) {
      const o = this._getOrReturnCtx(t);
      return F(o, {
        code: I.invalid_type,
        expected: Z.string,
        received: o.parsedType
      }), ue;
    }
    const n = new ct();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), F(r, {
          code: I.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), F(r, {
          code: I.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? F(r, {
          code: I.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && F(r, {
          code: I.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        Mp.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "email",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        no || (no = new RegExp(jp, "u")), no.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "emoji",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        Tp.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "uuid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        Ip.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "nanoid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        Rp.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "cuid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        Ep.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "cuid2",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        Op.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
          validation: "ulid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), F(r, {
            validation: "url",
            code: I.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "regex",
        code: I.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? Bp(o).test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? Up.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? Wp(o).test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? Pp.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "duration",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? Hp(t.data, o.version) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "ip",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? Gp(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "jwt",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Zp(t.data, o.version) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "cidr",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? Lp.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "base64",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? Fp.test(t.data) || (r = this._getOrReturnCtx(t, r), F(r, {
        validation: "base64url",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : we.assertNever(o);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((r) => t.test(r), {
      validation: s,
      code: I.invalid_string,
      ...K.errToObj(n)
    });
  }
  _addCheck(t) {
    return new Yt({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...K.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...K.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...K.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...K.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...K.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...K.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...K.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...K.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...K.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...K.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...K.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...K.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...K.errToObj(t) });
  }
  datetime(t) {
    return typeof t == "string" ? this._addCheck({
      kind: "datetime",
      precision: null,
      offset: !1,
      local: !1,
      message: t
    }) : this._addCheck({
      kind: "datetime",
      precision: typeof t?.precision > "u" ? null : t?.precision,
      offset: t?.offset ?? !1,
      local: t?.local ?? !1,
      ...K.errToObj(t?.message)
    });
  }
  date(t) {
    return this._addCheck({ kind: "date", message: t });
  }
  time(t) {
    return typeof t == "string" ? this._addCheck({
      kind: "time",
      precision: null,
      message: t
    }) : this._addCheck({
      kind: "time",
      precision: typeof t?.precision > "u" ? null : t?.precision,
      ...K.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...K.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...K.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...K.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...K.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...K.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...K.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...K.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...K.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, K.errToObj(t));
  }
  trim() {
    return new Yt({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new Yt({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new Yt({
      ...this._def,
      checks: [...this._def.checks, { kind: "toUpperCase" }]
    });
  }
  get isDatetime() {
    return !!this._def.checks.find((t) => t.kind === "datetime");
  }
  get isDate() {
    return !!this._def.checks.find((t) => t.kind === "date");
  }
  get isTime() {
    return !!this._def.checks.find((t) => t.kind === "time");
  }
  get isDuration() {
    return !!this._def.checks.find((t) => t.kind === "duration");
  }
  get isEmail() {
    return !!this._def.checks.find((t) => t.kind === "email");
  }
  get isURL() {
    return !!this._def.checks.find((t) => t.kind === "url");
  }
  get isEmoji() {
    return !!this._def.checks.find((t) => t.kind === "emoji");
  }
  get isUUID() {
    return !!this._def.checks.find((t) => t.kind === "uuid");
  }
  get isNANOID() {
    return !!this._def.checks.find((t) => t.kind === "nanoid");
  }
  get isCUID() {
    return !!this._def.checks.find((t) => t.kind === "cuid");
  }
  get isCUID2() {
    return !!this._def.checks.find((t) => t.kind === "cuid2");
  }
  get isULID() {
    return !!this._def.checks.find((t) => t.kind === "ulid");
  }
  get isIP() {
    return !!this._def.checks.find((t) => t.kind === "ip");
  }
  get isCIDR() {
    return !!this._def.checks.find((t) => t.kind === "cidr");
  }
  get isBase64() {
    return !!this._def.checks.find((t) => t.kind === "base64");
  }
  get isBase64url() {
    return !!this._def.checks.find((t) => t.kind === "base64url");
  }
  get minLength() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "min" && (t === null || s.value > t) && (t = s.value);
    return t;
  }
  get maxLength() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "max" && (t === null || s.value < t) && (t = s.value);
    return t;
  }
}
Yt.create = (e) => new Yt({
  checks: [],
  typeName: le.ZodString,
  coerce: e?.coerce ?? !1,
  ...pe(e)
});
function qp(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class Zs extends ye {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== Z.number) {
      const o = this._getOrReturnCtx(t);
      return F(o, {
        code: I.invalid_type,
        expected: Z.number,
        received: o.parsedType
      }), ue;
    }
    let n;
    const r = new ct();
    for (const o of this._def.checks)
      o.kind === "int" ? we.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? qp(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.not_finite,
        message: o.message
      }), r.dirty()) : we.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, K.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, K.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, K.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, K.toString(s));
  }
  setLimit(t, s, n, r) {
    return new Zs({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: K.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Zs({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: K.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: K.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: K.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: K.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: K.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: K.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: K.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: K.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: K.toString(t)
    });
  }
  get minValue() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "min" && (t === null || s.value > t) && (t = s.value);
    return t;
  }
  get maxValue() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "max" && (t === null || s.value < t) && (t = s.value);
    return t;
  }
  get isInt() {
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && we.isInteger(t.value));
  }
  get isFinite() {
    let t = null, s = null;
    for (const n of this._def.checks) {
      if (n.kind === "finite" || n.kind === "int" || n.kind === "multipleOf")
        return !0;
      n.kind === "min" ? (s === null || n.value > s) && (s = n.value) : n.kind === "max" && (t === null || n.value < t) && (t = n.value);
    }
    return Number.isFinite(s) && Number.isFinite(t);
  }
}
Zs.create = (e) => new Zs({
  checks: [],
  typeName: le.ZodNumber,
  coerce: e?.coerce || !1,
  ...pe(e)
});
class En extends ye {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte;
  }
  _parse(t) {
    if (this._def.coerce)
      try {
        t.data = BigInt(t.data);
      } catch {
        return this._getInvalidInput(t);
      }
    if (this._getType(t) !== Z.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new ct();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), F(n, {
        code: I.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : we.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return F(s, {
      code: I.invalid_type,
      expected: Z.bigint,
      received: s.parsedType
    }), ue;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, K.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, K.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, K.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, K.toString(s));
  }
  setLimit(t, s, n, r) {
    return new En({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: K.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new En({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: K.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: K.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: K.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: K.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: K.toString(s)
    });
  }
  get minValue() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "min" && (t === null || s.value > t) && (t = s.value);
    return t;
  }
  get maxValue() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "max" && (t === null || s.value < t) && (t = s.value);
    return t;
  }
}
En.create = (e) => new En({
  checks: [],
  typeName: le.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...pe(e)
});
class Io extends ye {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== Z.boolean) {
      const n = this._getOrReturnCtx(t);
      return F(n, {
        code: I.invalid_type,
        expected: Z.boolean,
        received: n.parsedType
      }), ue;
    }
    return _t(t.data);
  }
}
Io.create = (e) => new Io({
  typeName: le.ZodBoolean,
  coerce: e?.coerce || !1,
  ...pe(e)
});
class ar extends ye {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== Z.date) {
      const o = this._getOrReturnCtx(t);
      return F(o, {
        code: I.invalid_type,
        expected: Z.date,
        received: o.parsedType
      }), ue;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return F(o, {
        code: I.invalid_date
      }), ue;
    }
    const n = new ct();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), F(r, {
        code: I.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), n.dirty()) : we.assertNever(o);
    return {
      status: n.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new ar({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: K.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: K.toString(s)
    });
  }
  get minDate() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "min" && (t === null || s.value > t) && (t = s.value);
    return t != null ? new Date(t) : null;
  }
  get maxDate() {
    let t = null;
    for (const s of this._def.checks)
      s.kind === "max" && (t === null || s.value < t) && (t = s.value);
    return t != null ? new Date(t) : null;
  }
}
ar.create = (e) => new ar({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: le.ZodDate,
  ...pe(e)
});
class xa extends ye {
  _parse(t) {
    if (this._getType(t) !== Z.symbol) {
      const n = this._getOrReturnCtx(t);
      return F(n, {
        code: I.invalid_type,
        expected: Z.symbol,
        received: n.parsedType
      }), ue;
    }
    return _t(t.data);
  }
}
xa.create = (e) => new xa({
  typeName: le.ZodSymbol,
  ...pe(e)
});
class ka extends ye {
  _parse(t) {
    if (this._getType(t) !== Z.undefined) {
      const n = this._getOrReturnCtx(t);
      return F(n, {
        code: I.invalid_type,
        expected: Z.undefined,
        received: n.parsedType
      }), ue;
    }
    return _t(t.data);
  }
}
ka.create = (e) => new ka({
  typeName: le.ZodUndefined,
  ...pe(e)
});
class Sa extends ye {
  _parse(t) {
    if (this._getType(t) !== Z.null) {
      const n = this._getOrReturnCtx(t);
      return F(n, {
        code: I.invalid_type,
        expected: Z.null,
        received: n.parsedType
      }), ue;
    }
    return _t(t.data);
  }
}
Sa.create = (e) => new Sa({
  typeName: le.ZodNull,
  ...pe(e)
});
class Ca extends ye {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return _t(t.data);
  }
}
Ca.create = (e) => new Ca({
  typeName: le.ZodAny,
  ...pe(e)
});
class Aa extends ye {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return _t(t.data);
  }
}
Aa.create = (e) => new Aa({
  typeName: le.ZodUnknown,
  ...pe(e)
});
class bs extends ye {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return F(s, {
      code: I.invalid_type,
      expected: Z.never,
      received: s.parsedType
    }), ue;
  }
}
bs.create = (e) => new bs({
  typeName: le.ZodNever,
  ...pe(e)
});
class Ra extends ye {
  _parse(t) {
    if (this._getType(t) !== Z.undefined) {
      const n = this._getOrReturnCtx(t);
      return F(n, {
        code: I.invalid_type,
        expected: Z.void,
        received: n.parsedType
      }), ue;
    }
    return _t(t.data);
  }
}
Ra.create = (e) => new Ra({
  typeName: le.ZodVoid,
  ...pe(e)
});
class Lt extends ye {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== Z.array)
      return F(s, {
        code: I.invalid_type,
        expected: Z.array,
        received: s.parsedType
      }), ue;
    if (r.exactLength !== null) {
      const i = s.data.length > r.exactLength.value, a = s.data.length < r.exactLength.value;
      (i || a) && (F(s, {
        code: i ? I.too_big : I.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (F(s, {
      code: I.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (F(s, {
      code: I.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((i, a) => r.type._parseAsync(new Bt(s, i, s.path, a)))).then((i) => ct.mergeArray(n, i));
    const o = [...s.data].map((i, a) => r.type._parseSync(new Bt(s, i, s.path, a)));
    return ct.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new Lt({
      ...this._def,
      minLength: { value: t, message: K.toString(s) }
    });
  }
  max(t, s) {
    return new Lt({
      ...this._def,
      maxLength: { value: t, message: K.toString(s) }
    });
  }
  length(t, s) {
    return new Lt({
      ...this._def,
      exactLength: { value: t, message: K.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Lt.create = (e, t) => new Lt({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: le.ZodArray,
  ...pe(t)
});
function Ds(e) {
  if (e instanceof Be) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = hs.create(Ds(n));
    }
    return new Be({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof Lt ? new Lt({
    ...e._def,
    type: Ds(e.element)
  }) : e instanceof hs ? hs.create(Ds(e.unwrap())) : e instanceof Js ? Js.create(Ds(e.unwrap())) : e instanceof Is ? Is.create(e.items.map((t) => Ds(t))) : e;
}
class Be extends ye {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = we.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== Z.object) {
      const c = this._getOrReturnCtx(t);
      return F(c, {
        code: I.invalid_type,
        expected: Z.object,
        received: c.parsedType
      }), ue;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof bs && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], d = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new Bt(r, d, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof bs) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && (F(r, {
          code: I.unrecognized_keys,
          keys: a
        }), n.dirty());
      else if (c !== "strip") throw new Error("Internal ZodObject error: invalid unknownKeys value.");
    } else {
      const c = this._def.catchall;
      for (const u of a) {
        const d = r.data[u];
        l.push({
          key: { status: "valid", value: u },
          value: c._parse(
            new Bt(r, d, r.path, u)
            //, ctx.child(key), value, getParsedType(value)
          ),
          alwaysSet: u in r.data
        });
      }
    }
    return r.common.async ? Promise.resolve().then(async () => {
      const c = [];
      for (const u of l) {
        const d = await u.key, m = await u.value;
        c.push({
          key: d,
          value: m,
          alwaysSet: u.alwaysSet
        });
      }
      return c;
    }).then((c) => ct.mergeObjectSync(n, c)) : ct.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return K.errToObj, new Be({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: K.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new Be({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new Be({
      ...this._def,
      unknownKeys: "passthrough"
    });
  }
  // const AugmentFactory =
  //   <Def extends ZodObjectDef>(def: Def) =>
  //   <Augmentation extends ZodRawShape>(
  //     augmentation: Augmentation
  //   ): ZodObject<
  //     extendShape<ReturnType<Def["shape"]>, Augmentation>,
  //     Def["unknownKeys"],
  //     Def["catchall"]
  //   > => {
  //     return new ZodObject({
  //       ...def,
  //       shape: () => ({
  //         ...def.shape(),
  //         ...augmentation,
  //       }),
  //     }) as any;
  //   };
  extend(t) {
    return new Be({
      ...this._def,
      shape: () => ({
        ...this._def.shape(),
        ...t
      })
    });
  }
  /**
   * Prior to zod@1.0.12 there was a bug in the
   * inferred type of merged objects. Please
   * upgrade if you are experiencing issues.
   */
  merge(t) {
    return new Be({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: le.ZodObject
    });
  }
  // merge<
  //   Incoming extends AnyZodObject,
  //   Augmentation extends Incoming["shape"],
  //   NewOutput extends {
  //     [k in keyof Augmentation | keyof Output]: k extends keyof Augmentation
  //       ? Augmentation[k]["_output"]
  //       : k extends keyof Output
  //       ? Output[k]
  //       : never;
  //   },
  //   NewInput extends {
  //     [k in keyof Augmentation | keyof Input]: k extends keyof Augmentation
  //       ? Augmentation[k]["_input"]
  //       : k extends keyof Input
  //       ? Input[k]
  //       : never;
  //   }
  // >(
  //   merging: Incoming
  // ): ZodObject<
  //   extendShape<T, ReturnType<Incoming["_def"]["shape"]>>,
  //   Incoming["_def"]["unknownKeys"],
  //   Incoming["_def"]["catchall"],
  //   NewOutput,
  //   NewInput
  // > {
  //   const merged: any = new ZodObject({
  //     unknownKeys: merging._def.unknownKeys,
  //     catchall: merging._def.catchall,
  //     shape: () =>
  //       objectUtil.mergeShapes(this._def.shape(), merging._def.shape()),
  //     typeName: ZodFirstPartyTypeKind.ZodObject,
  //   }) as any;
  //   return merged;
  // }
  setKey(t, s) {
    return this.augment({ [t]: s });
  }
  // merge<Incoming extends AnyZodObject>(
  //   merging: Incoming
  // ): //ZodObject<T & Incoming["_shape"], UnknownKeys, Catchall> = (merging) => {
  // ZodObject<
  //   extendShape<T, ReturnType<Incoming["_def"]["shape"]>>,
  //   Incoming["_def"]["unknownKeys"],
  //   Incoming["_def"]["catchall"]
  // > {
  //   // const mergedShape = objectUtil.mergeShapes(
  //   //   this._def.shape(),
  //   //   merging._def.shape()
  //   // );
  //   const merged: any = new ZodObject({
  //     unknownKeys: merging._def.unknownKeys,
  //     catchall: merging._def.catchall,
  //     shape: () =>
  //       objectUtil.mergeShapes(this._def.shape(), merging._def.shape()),
  //     typeName: ZodFirstPartyTypeKind.ZodObject,
  //   }) as any;
  //   return merged;
  // }
  catchall(t) {
    return new Be({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of we.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new Be({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of we.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new Be({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return Ds(this);
  }
  partial(t) {
    const s = {};
    for (const n of we.objectKeys(this.shape)) {
      const r = this.shape[n];
      t && !t[n] ? s[n] = r : s[n] = r.optional();
    }
    return new Be({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of we.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let o = this.shape[n];
        for (; o instanceof hs; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new Be({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return Nc(we.objectKeys(this.shape));
  }
}
Be.create = (e, t) => new Be({
  shape: () => e,
  unknownKeys: "strip",
  catchall: bs.create(),
  typeName: le.ZodObject,
  ...pe(t)
});
Be.strictCreate = (e, t) => new Be({
  shape: () => e,
  unknownKeys: "strict",
  catchall: bs.create(),
  typeName: le.ZodObject,
  ...pe(t)
});
Be.lazycreate = (e, t) => new Be({
  shape: e,
  unknownKeys: "strip",
  catchall: bs.create(),
  typeName: le.ZodObject,
  ...pe(t)
});
class lr extends ye {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return s.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new rs(a.ctx.common.issues));
      return F(s, {
        code: I.invalid_union,
        unionErrors: i
      }), ue;
    }
    if (s.common.async)
      return Promise.all(n.map(async (o) => {
        const i = {
          ...s,
          common: {
            ...s.common,
            issues: []
          },
          parent: null
        };
        return {
          result: await o._parseAsync({
            data: s.data,
            path: s.path,
            parent: i
          }),
          ctx: i
        };
      })).then(r);
    {
      let o;
      const i = [];
      for (const l of n) {
        const c = {
          ...s,
          common: {
            ...s.common,
            issues: []
          },
          parent: null
        }, u = l._parseSync({
          data: s.data,
          path: s.path,
          parent: c
        });
        if (u.status === "valid")
          return u;
        u.status === "dirty" && !o && (o = { result: u, ctx: c }), c.common.issues.length && i.push(c.common.issues);
      }
      if (o)
        return s.common.issues.push(...o.ctx.common.issues), o.result;
      const a = i.map((l) => new rs(l));
      return F(s, {
        code: I.invalid_union,
        unionErrors: a
      }), ue;
    }
  }
  get options() {
    return this._def.options;
  }
}
lr.create = (e, t) => new lr({
  options: e,
  typeName: le.ZodUnion,
  ...pe(t)
});
function No(e, t) {
  const s = fs(e), n = fs(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === Z.object && n === Z.object) {
    const r = we.objectKeys(t), o = we.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = No(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (s === Z.array && n === Z.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = No(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === Z.date && n === Z.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class cr extends ye {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, i) => {
      if (ba(o) || ba(i))
        return ue;
      const a = No(o.value, i.value);
      return a.valid ? ((_a(o) || _a(i)) && s.dirty(), { status: s.value, value: a.data }) : (F(n, {
        code: I.invalid_intersection_types
      }), ue);
    };
    return n.common.async ? Promise.all([
      this._def.left._parseAsync({
        data: n.data,
        path: n.path,
        parent: n
      }),
      this._def.right._parseAsync({
        data: n.data,
        path: n.path,
        parent: n
      })
    ]).then(([o, i]) => r(o, i)) : r(this._def.left._parseSync({
      data: n.data,
      path: n.path,
      parent: n
    }), this._def.right._parseSync({
      data: n.data,
      path: n.path,
      parent: n
    }));
  }
}
cr.create = (e, t, s) => new cr({
  left: e,
  right: t,
  typeName: le.ZodIntersection,
  ...pe(s)
});
class Is extends ye {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Z.array)
      return F(n, {
        code: I.invalid_type,
        expected: Z.array,
        received: n.parsedType
      }), ue;
    if (n.data.length < this._def.items.length)
      return F(n, {
        code: I.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), ue;
    !this._def.rest && n.data.length > this._def.items.length && (F(n, {
      code: I.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new Bt(n, i, n.path, a)) : null;
    }).filter((i) => !!i);
    return n.common.async ? Promise.all(o).then((i) => ct.mergeArray(s, i)) : ct.mergeArray(s, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Is({
      ...this._def,
      rest: t
    });
  }
}
Is.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Is({
    items: e,
    typeName: le.ZodTuple,
    rest: null,
    ...pe(t)
  });
};
class ur extends ye {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Z.object)
      return F(n, {
        code: I.invalid_type,
        expected: Z.object,
        received: n.parsedType
      }), ue;
    const r = [], o = this._def.keyType, i = this._def.valueType;
    for (const a in n.data)
      r.push({
        key: o._parse(new Bt(n, a, n.path, a)),
        value: i._parse(new Bt(n, n.data[a], n.path, a)),
        alwaysSet: a in n.data
      });
    return n.common.async ? ct.mergeObjectAsync(s, r) : ct.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof ye ? new ur({
      keyType: t,
      valueType: s,
      typeName: le.ZodRecord,
      ...pe(n)
    }) : new ur({
      keyType: Yt.create(),
      valueType: t,
      typeName: le.ZodRecord,
      ...pe(s)
    });
  }
}
class Ea extends ye {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Z.map)
      return F(n, {
        code: I.invalid_type,
        expected: Z.map,
        received: n.parsedType
      }), ue;
    const r = this._def.keyType, o = this._def.valueType, i = [...n.data.entries()].map(([a, l], c) => ({
      key: r._parse(new Bt(n, a, n.path, [c, "key"])),
      value: o._parse(new Bt(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return ue;
          (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
        }
        return { status: s.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return ue;
        (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
      }
      return { status: s.value, value: a };
    }
  }
}
Ea.create = (e, t, s) => new Ea({
  valueType: t,
  keyType: e,
  typeName: le.ZodMap,
  ...pe(s)
});
class On extends ye {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Z.set)
      return F(n, {
        code: I.invalid_type,
        expected: Z.set,
        received: n.parsedType
      }), ue;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (F(n, {
      code: I.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (F(n, {
      code: I.too_big,
      maximum: r.maxSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.maxSize.message
    }), s.dirty());
    const o = this._def.valueType;
    function i(l) {
      const c = /* @__PURE__ */ new Set();
      for (const u of l) {
        if (u.status === "aborted")
          return ue;
        u.status === "dirty" && s.dirty(), c.add(u.value);
      }
      return { status: s.value, value: c };
    }
    const a = [...n.data.values()].map((l, c) => o._parse(new Bt(n, l, n.path, c)));
    return n.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, s) {
    return new On({
      ...this._def,
      minSize: { value: t, message: K.toString(s) }
    });
  }
  max(t, s) {
    return new On({
      ...this._def,
      maxSize: { value: t, message: K.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
On.create = (e, t) => new On({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: le.ZodSet,
  ...pe(t)
});
class Oa extends ye {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
Oa.create = (e, t) => new Oa({
  getter: e,
  typeName: le.ZodLazy,
  ...pe(t)
});
class Ta extends ye {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return F(s, {
        received: s.data,
        code: I.invalid_literal,
        expected: this._def.value
      }), ue;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Ta.create = (e, t) => new Ta({
  value: e,
  typeName: le.ZodLiteral,
  ...pe(t)
});
function Nc(e, t) {
  return new qs({
    values: e,
    typeName: le.ZodEnum,
    ...pe(t)
  });
}
class qs extends ye {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return F(s, {
        expected: we.joinValues(n),
        received: s.parsedType,
        code: I.invalid_type
      }), ue;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return F(s, {
        received: s.data,
        code: I.invalid_enum_value,
        options: n
      }), ue;
    }
    return _t(t.data);
  }
  get options() {
    return this._def.values;
  }
  get enum() {
    const t = {};
    for (const s of this._def.values)
      t[s] = s;
    return t;
  }
  get Values() {
    const t = {};
    for (const s of this._def.values)
      t[s] = s;
    return t;
  }
  get Enum() {
    const t = {};
    for (const s of this._def.values)
      t[s] = s;
    return t;
  }
  extract(t, s = this._def) {
    return qs.create(t, {
      ...this._def,
      ...s
    });
  }
  exclude(t, s = this._def) {
    return qs.create(this.options.filter((n) => !t.includes(n)), {
      ...this._def,
      ...s
    });
  }
}
qs.create = Nc;
class Ia extends ye {
  _parse(t) {
    const s = we.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== Z.string && n.parsedType !== Z.number) {
      const r = we.objectValues(s);
      return F(n, {
        expected: we.joinValues(r),
        received: n.parsedType,
        code: I.invalid_type
      }), ue;
    }
    if (this._cache || (this._cache = new Set(we.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = we.objectValues(s);
      return F(n, {
        received: n.data,
        code: I.invalid_enum_value,
        options: r
      }), ue;
    }
    return _t(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
Ia.create = (e, t) => new Ia({
  values: e,
  typeName: le.ZodNativeEnum,
  ...pe(t)
});
class dr extends ye {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== Z.promise && s.common.async === !1)
      return F(s, {
        code: I.invalid_type,
        expected: Z.promise,
        received: s.parsedType
      }), ue;
    const n = s.parsedType === Z.promise ? s.data : Promise.resolve(s.data);
    return _t(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
dr.create = (e, t) => new dr({
  type: e,
  typeName: le.ZodPromise,
  ...pe(t)
});
class Ks extends ye {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === le.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (i) => {
        F(n, i), i.fatal ? s.abort() : s.dirty();
      },
      get path() {
        return n.path;
      }
    };
    if (o.addIssue = o.addIssue.bind(o), r.type === "preprocess") {
      const i = r.transform(n.data, o);
      if (n.common.async)
        return Promise.resolve(i).then(async (a) => {
          if (s.value === "aborted")
            return ue;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? ue : l.status === "dirty" || s.value === "dirty" ? cn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return ue;
        const a = this._def.schema._parseSync({
          data: i,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? ue : a.status === "dirty" || s.value === "dirty" ? cn(a.value) : a;
      }
    }
    if (r.type === "refinement") {
      const i = (a) => {
        const l = r.refinement(a, o);
        if (n.common.async)
          return Promise.resolve(l);
        if (l instanceof Promise)
          throw new Error("Async refinement encountered during synchronous parse operation. Use .parseAsync instead.");
        return a;
      };
      if (n.common.async === !1) {
        const a = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? ue : (a.status === "dirty" && s.dirty(), i(a.value), { status: s.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => a.status === "aborted" ? ue : (a.status === "dirty" && s.dirty(), i(a.value).then(() => ({ status: s.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!Gs(i))
          return ue;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => Gs(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: s.value,
          value: a
        })) : ue);
    we.assertNever(r);
  }
}
Ks.create = (e, t, s) => new Ks({
  schema: e,
  typeName: le.ZodEffects,
  effect: t,
  ...pe(s)
});
Ks.createWithPreprocess = (e, t, s) => new Ks({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: le.ZodEffects,
  ...pe(s)
});
class hs extends ye {
  _parse(t) {
    return this._getType(t) === Z.undefined ? _t(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
hs.create = (e, t) => new hs({
  innerType: e,
  typeName: le.ZodOptional,
  ...pe(t)
});
class Js extends ye {
  _parse(t) {
    return this._getType(t) === Z.null ? _t(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Js.create = (e, t) => new Js({
  innerType: e,
  typeName: le.ZodNullable,
  ...pe(t)
});
class Po extends ye {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === Z.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
Po.create = (e, t) => new Po({
  innerType: e,
  typeName: le.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...pe(t)
});
class Mo extends ye {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = {
      ...s,
      common: {
        ...s.common,
        issues: []
      }
    }, r = this._def.innerType._parse({
      data: n.data,
      path: n.path,
      parent: {
        ...n
      }
    });
    return ir(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new rs(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new rs(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
Mo.create = (e, t) => new Mo({
  innerType: e,
  typeName: le.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...pe(t)
});
class Na extends ye {
  _parse(t) {
    if (this._getType(t) !== Z.nan) {
      const n = this._getOrReturnCtx(t);
      return F(n, {
        code: I.invalid_type,
        expected: Z.nan,
        received: n.parsedType
      }), ue;
    }
    return { status: "valid", value: t.data };
  }
}
Na.create = (e) => new Na({
  typeName: le.ZodNaN,
  ...pe(e)
});
class Kp extends ye {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = s.data;
    return this._def.type._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  unwrap() {
    return this._def.type;
  }
}
class li extends ye {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? ue : o.status === "dirty" ? (s.dirty(), cn(o.value)) : this._def.out._parseAsync({
          data: o.value,
          path: n.path,
          parent: n
        });
      })();
    {
      const r = this._def.in._parseSync({
        data: n.data,
        path: n.path,
        parent: n
      });
      return r.status === "aborted" ? ue : r.status === "dirty" ? (s.dirty(), {
        status: "dirty",
        value: r.value
      }) : this._def.out._parseSync({
        data: r.value,
        path: n.path,
        parent: n
      });
    }
  }
  static create(t, s) {
    return new li({
      in: t,
      out: s,
      typeName: le.ZodPipeline
    });
  }
}
class jo extends ye {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (Gs(r) && (r.value = Object.freeze(r.value)), r);
    return ir(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
jo.create = (e, t) => new jo({
  innerType: e,
  typeName: le.ZodReadonly,
  ...pe(t)
});
var le;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(le || (le = {}));
const Je = Yt.create, ro = Zs.create, Un = Io.create;
bs.create;
const Jp = Lt.create, ci = Be.create;
lr.create;
cr.create;
Is.create;
const Qp = ur.create, $o = qs.create;
dr.create;
hs.create;
Js.create;
const Yp = "comfymodal.studio.vue.";
function Xp() {
  const e = /* @__PURE__ */ new Map();
  return {
    getItem: (t) => e.has(t) ? e.get(t) : null,
    setItem: (t, s) => {
      e.set(t, s);
    },
    removeItem: (t) => {
      e.delete(t);
    }
  };
}
function eh() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return Xp();
}
function Pc(e, t, s, n) {
  const r = Yp + e, o = eh();
  return {
    key: r,
    read() {
      let i = null;
      try {
        i = o.getItem(r);
      } catch {
        return t;
      }
      if (i === null) return t;
      let a;
      try {
        a = JSON.parse(i);
      } catch {
        return t;
      }
      if (!s) return a ?? t;
      const l = s.safeParse(a);
      return l.success ? l.data : t;
    },
    write(i) {
      try {
        o.setItem(r, JSON.stringify(i));
      } catch {
      }
    },
    remove() {
      try {
        o.removeItem(r);
      } catch {
      }
    }
  };
}
const th = "/comfymodal";
class sh extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function nh(e, t) {
  if (typeof e == "string" && e.trim() !== "") return e;
  if (e && typeof e == "object") {
    const s = e;
    for (const r of ["message", "error"]) {
      const o = s[r];
      if (typeof o == "string" && o.trim() !== "") return o;
    }
    const n = s.detail;
    if (typeof n == "string" && n.trim() !== "") return n;
    if (n && typeof n == "object") {
      const r = n;
      for (const o of ["message", "code"]) {
        const i = r[o];
        if (typeof i == "string" && i.trim() !== "") return i;
      }
    }
  }
  return t;
}
function rh(e, t) {
  if (t === void 0)
    return e ? { signal: e, cleanup: () => {
    } } : { signal: void 0, cleanup: () => {
    } };
  const s = new AbortController(), n = setTimeout(
    () => s.abort(new DOMException("Request timed out", "TimeoutError")),
    t
  ), r = () => s.abort(e?.reason);
  return e && (e.aborted ? s.abort(e.reason) : e.addEventListener("abort", r, { once: !0 })), {
    signal: s.signal,
    cleanup: () => {
      clearTimeout(n), e?.removeEventListener("abort", r);
    }
  };
}
async function Ce(e, t = {}, s = fetch) {
  const {
    method: n = "GET",
    body: r,
    signal: o,
    timeoutMs: i,
    headers: a = {}
  } = t, { signal: l, cleanup: c } = rh(o, i);
  try {
    if (l && l.aborted) throw l.reason;
    const u = await s(th + e, {
      method: n,
      headers: {
        "Content-Type": "application/json",
        ...a
      },
      body: r === void 0 ? void 0 : JSON.stringify(r),
      signal: l
    }), d = await u.text();
    let m = null;
    if (d !== "")
      try {
        m = JSON.parse(d);
      } catch {
        m = d;
      }
    if (!u.ok)
      throw new sh(
        u.status,
        nh(m, `Request failed with status ${u.status}`),
        m
      );
    return m;
  } finally {
    c();
  }
}
const oh = ci({ value: Je(), label: Je() }).passthrough(), ih = ci({
  gpu: Je().default(""),
  default_gpu: Je().default(""),
  available_gpus: Jp(oh).default([]),
  persisted_gpu: Je().default(""),
  output_format: Je().default("original"),
  quality: ro().default(75),
  webp_lossless_compression: Je().default("balanced"),
  auto_save_local: Un().default(!1),
  save_folder: Je().default(""),
  save_metadata_sidecar: Un().default(!0),
  preview_default: $o(["off", "on"]).default("off"),
  preview_codec: Je().default("webp"),
  preview_quality: ro().default(70),
  data_saver_default: $o(["off", "on"]).default("off"),
  data_saver_codec: Je().default("webp"),
  data_saver_quality: ro().default(70),
  execution_mode: Je().default("v2"),
  execution_mode_source: Je().default(""),
  execution_mode_locked: Un().default(!1),
  engine_migration_notice: Je().nullable().default(null),
  skip_plan_validation: Un().default(!1),
  golden_gpu_order: Qp(Je()).default({})
}).passthrough(), ah = ci({ status: Je().optional(), level: Je().default("off"), effective: Je().default("off") }).passthrough();
async function Pa() {
  return ih.parse(await Ce("/config"));
}
async function lh(e) {
  return Ce("/config", { method: "POST", body: e });
}
async function ch() {
  return ah.parse(await Ce("/profile/level"));
}
async function uh(e) {
  return Ce("/profile/level", { method: "POST", body: { level: e } });
}
const rn = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function Ma(e) {
  const t = {
    outputFormat: String(e.output_format ?? "original"),
    quality: typeof e.quality == "number" ? e.quality : null,
    webpLosslessCompression: String(e.webp_lossless_compression ?? "balanced"),
    autoSaveLocal: e.auto_save_local === !0,
    saveFolder: String(e.save_folder ?? ""),
    saveMetadataSidecar: e.save_metadata_sidecar !== !1,
    dataSaverDefault: e.data_saver_default === "on" ? "on" : "off",
    dataSaverCodec: String(e.data_saver_codec ?? e.preview_codec ?? "webp"),
    dataSaverQuality: typeof e.data_saver_quality == "number" ? e.data_saver_quality : typeof e.preview_quality == "number" ? e.preview_quality : null
  };
  if (typeof window > "u") return t;
  const s = {
    output_format: t.outputFormat,
    quality: t.quality ?? 75,
    webp_lossless_compression: t.webpLosslessCompression,
    auto_save_local: t.autoSaveLocal,
    save_folder: t.saveFolder,
    save_metadata_sidecar: t.saveMetadataSidecar,
    preview_default: t.dataSaverDefault,
    preview_codec: t.dataSaverCodec,
    preview_quality: t.dataSaverQuality ?? 70,
    data_saver_default: t.dataSaverDefault,
    data_saver_codec: t.dataSaverCodec,
    data_saver_quality: t.dataSaverQuality ?? 70
  };
  window._comfyModalOutputOptions = s;
  try {
    localStorage.setItem(rn.outputFormat, s.output_format), localStorage.setItem(rn.quality, String(s.quality)), localStorage.setItem(rn.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(rn.saveFolder, s.save_folder), localStorage.setItem(rn.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const Mc = "comfymodal-studio";
function Mr(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(Mc), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function gs(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(Mc);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
const dh = $o(["comfortable", "compact"]), oo = Pc(
  "shell.density",
  "comfortable",
  dh
), jc = /* @__PURE__ */ Xs("studio-settings", () => {
  const e = /* @__PURE__ */ G("studio"), t = /* @__PURE__ */ G(oo.read()), s = /* @__PURE__ */ G(null), n = /* @__PURE__ */ G("off"), r = /* @__PURE__ */ G(!1), o = /* @__PURE__ */ G(!1), i = /* @__PURE__ */ G(null), a = /* @__PURE__ */ G(!1);
  let l = null;
  const c = Oe(() => s.value?.gpu ?? ""), u = Oe(() => s.value ? {
    output_format: s.value.output_format,
    quality: s.value.quality,
    webp_lossless_compression: s.value.webp_lossless_compression,
    auto_save_local: s.value.auto_save_local,
    save_folder: s.value.save_folder,
    save_metadata_sidecar: s.value.save_metadata_sidecar,
    data_saver_default: s.value.data_saver_default,
    data_saver_codec: s.value.data_saver_codec,
    data_saver_quality: s.value.data_saver_quality
  } : null);
  async function d() {
    r.value = !0, i.value = null;
    try {
      const [g, E] = await Promise.all([Pa(), ch()]);
      s.value = g, n.value = E.effective || E.level, Ma(g), a.value = !0;
    } catch (g) {
      throw i.value = g instanceof Error ? g.message : "Could not load Settings", g;
    } finally {
      r.value = !1;
    }
  }
  async function m(g) {
    o.value = !0, i.value = null;
    try {
      await lh(g);
      const E = await Pa();
      s.value = E, Ma(E), gs("settings");
    } catch (E) {
      throw i.value = E instanceof Error ? E.message : "Could not save Settings", E;
    } finally {
      o.value = !1;
    }
  }
  async function h(g) {
    await uh(g), n.value = g, gs("settings");
  }
  async function k() {
    l || (l = Mr((g) => {
      g === "settings" && !r.value && d();
    })), a.value || await d();
  }
  function w(g) {
    e.value = g;
  }
  function z(g) {
    t.value = g, oo.write(g);
  }
  function N() {
    e.value = "studio", t.value = "comfortable", oo.write("comfortable");
  }
  return {
    activeSection: e,
    density: t,
    config: s,
    profileLevel: n,
    loading: r,
    saving: o,
    error: i,
    bootstrapped: a,
    gpu: c,
    outputPreferences: u,
    load: d,
    initialize: k,
    save: m,
    setProfile: h,
    setSection: w,
    setDensity: z,
    reset: N
  };
});
function fh(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const r = String(n.id ?? "");
    return { id: r, label: String(n.label ?? r), isActive: r !== "" && r === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function $c(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function mh(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function ph() {
  return Ce("/workspaces");
}
async function hh(e) {
  return Ce("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function ja() {
  return $c(await Ce("/deploy/status"));
}
async function gh() {
  return Ce("/deploy", { method: "POST" });
}
async function vh() {
  return Ce("/deploy/log");
}
async function yh(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return Ce(`/studio/inventory/refresh${t}`);
}
async function bh(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return Ce(`/studio/models${s}`);
}
async function _h(e = !1) {
  return Ce("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function wh() {
  return Ce("/studio/custom-nodes");
}
async function xh() {
  return Ce("/studio/custom-nodes/refresh", { method: "POST" });
}
function fr() {
  let e = 0, t = null;
  return {
    run: (n) => {
      e += 1;
      const r = e, o = t;
      o && (o.superseded = !0, o.controller.abort());
      const i = new AbortController(), a = { controller: i, superseded: !1 };
      let l;
      const c = new Promise((m) => {
        l = () => m({ stale: !0 });
      }), u = () => l();
      i.signal.addEventListener("abort", u, { once: !0 }), t = a;
      const d = () => {
        i.signal.removeEventListener("abort", u), t === a && (t = null);
      };
      return (async () => {
        try {
          return await Promise.race([
            n(i.signal).then((m) => r !== e || a.superseded || i.signal.aborted ? { stale: !0 } : { stale: !1, value: m }),
            c
          ]);
        } catch (m) {
          if (a.superseded || r !== e || i.signal.aborted)
            return { stale: !0 };
          throw m;
        } finally {
          d();
        }
      })();
    },
    abort: (n) => {
      t?.controller.abort(n);
    },
    get pending() {
      return t !== null;
    }
  };
}
function kh(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function Sh(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function Ch(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    kh(s), i += 1, o && o(i);
    const a = await n(s, i);
    if (r(a)) return a;
    await Sh(t, s);
  }
}
const ui = /* @__PURE__ */ Xs("studio-infrastructure", () => {
  const e = /* @__PURE__ */ G("unknown"), t = /* @__PURE__ */ G(null), s = /* @__PURE__ */ G(null), n = /* @__PURE__ */ G([]), r = /* @__PURE__ */ G(null), o = /* @__PURE__ */ G($c(null)), i = /* @__PURE__ */ G(null), a = /* @__PURE__ */ G([]), l = /* @__PURE__ */ G([]), c = /* @__PURE__ */ G(!1), u = /* @__PURE__ */ G(null), d = fr(), m = /* @__PURE__ */ G(null), h = /* @__PURE__ */ G(null);
  let k = null;
  const w = Oe(() => n.value.find((D) => D.isActive) ?? null);
  function z(D, me) {
    e.value = D, t.value = me ?? null;
  }
  function N(D) {
    s.value = D;
  }
  function g() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  async function E() {
    const D = fh(await ph());
    n.value = D.rows, r.value = D.activeId;
  }
  async function P() {
    o.value = await ja(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function J() {
    const D = await d.run(async (me) => {
      const [ne, q] = await Promise.all([bh(), wh()]);
      return me.aborted ? null : { modelResult: ne, nodeResult: q };
    });
    D.stale || !D.value || (a.value = D.value.modelResult.models ?? [], l.value = D.value.nodeResult.custom_nodes ?? []);
  }
  async function ve() {
    c.value = !0, u.value = null;
    try {
      await Promise.all([E(), P(), J()]), s.value = "server inventory loaded";
    } catch (D) {
      throw u.value = D instanceof Error ? D.message : "Could not load infrastructure", D;
    } finally {
      c.value = !1;
    }
  }
  async function oe() {
    k || (k = Mr((D) => {
      D === "workspace" && !c.value && ve();
    })), n.value.length || await ve();
  }
  async function _(D) {
    if (h.value) throw new Error("Cannot change workspace while deployment is active");
    await hh(D), await E(), gs("workspace");
  }
  async function V() {
    const D = ai();
    if (h.value) return h.value;
    const me = r.value ?? void 0, ne = D.start({ kind: "deploy", label: "Deploy workspace" });
    h.value = ne;
    const q = new AbortController();
    m.value = q;
    const fe = window.setTimeout(() => q.abort(new DOMException("Deployment polling timed out", "TimeoutError")), 600 * 1e3);
    try {
      await gh(), D.patch(ne, { status: "running", message: "Deployment started" });
      const Pe = await Ch({
        intervalMs: 3e3,
        signal: q.signal,
        run: async () => {
          const $ = await ja();
          return o.value = $, e.value = $.state, t.value = $.message || null, D.patch(ne, { message: $.message || `Deployment: ${$.state}` }), $;
        },
        done: ($) => $.state === "ready" || $.state === "deployed_unwarmed" || $.state !== "deploying" && $.state !== "starting" && $.state !== "unknown"
      });
      if (!mh(Pe.state)) throw new Error(Pe.message || `Deployment ended in ${Pe.state}`);
      if (me && r.value !== me) throw new Error("Deployment target workspace changed");
      D.finish(ne, Pe.message || "Deployment completed");
    } catch (Pe) {
      const $ = Pe instanceof Error ? Pe.message : "Deployment failed";
      throw D.fail(ne, $), Pe;
    } finally {
      window.clearTimeout(fe), m.value = null, h.value = null;
    }
    return ne;
  }
  async function ce() {
    await yh(0), await J(), s.value = "inventory refreshed", gs("workspace");
  }
  async function xe() {
    const D = await _h(!0);
    a.value = D.models ?? a.value, await J();
  }
  async function ke() {
    const D = await xh();
    l.value = D.custom_nodes ?? l.value, await J();
  }
  async function Te() {
    i.value = await vh();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: r,
    activeWorkspace: w,
    deployStatus: o,
    deployLog: i,
    models: a,
    customNodes: l,
    loading: c,
    error: u,
    deploymentOperationId: h,
    setDeploy: z,
    setSyncSummary: N,
    reset: g,
    load: ve,
    initialize: oe,
    loadWorkspaces: E,
    loadDeployment: P,
    loadInventory: J,
    selectWorkspace: _,
    deploy: V,
    refreshRemoteInventoryNow: ce,
    rescanModelsNow: xe,
    refreshCustomNodesNow: ke,
    loadLog: Te
  };
});
function zc(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = zc(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function Dc() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = zc(e)) && (n && (n += " "), n += t);
  return n;
}
const Ah = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, Rh = (e, t) => ({
  classGroupId: e,
  validator: t
}), Vc = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), mr = "-", $a = [], Eh = "arbitrary..", Oh = (e) => {
  const t = Ih(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return Th(i);
      const a = i.split(mr), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return Lc(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = n[i], c = s[i];
        return l ? c ? Ah(c, l) : l : c || $a;
      }
      return s[i] || $a;
    }
  };
}, Lc = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const r = e[t], o = s.nextPart.get(r);
  if (o) {
    const c = Lc(e, t + 1, o);
    if (c) return c;
  }
  const i = s.validators;
  if (i === null)
    return;
  const a = t === 0 ? e.join(mr) : e.slice(t).join(mr), l = i.length;
  for (let c = 0; c < l; c++) {
    const u = i[c];
    if (u.validator(a))
      return u.classGroupId;
  }
}, Th = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? Eh + n : void 0;
})(), Ih = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return Nh(s, t);
}, Nh = (e, t) => {
  const s = Vc();
  for (const n in e) {
    const r = e[n];
    di(r, s, n, t);
  }
  return s;
}, di = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    Ph(i, t, s, n);
  }
}, Ph = (e, t, s, n) => {
  if (typeof e == "string") {
    Mh(e, t, s);
    return;
  }
  if (typeof e == "function") {
    jh(e, t, s, n);
    return;
  }
  $h(e, t, s, n);
}, Mh = (e, t, s) => {
  const n = e === "" ? t : Fc(t, e);
  n.classGroupId = s;
}, jh = (e, t, s, n) => {
  if (zh(e)) {
    di(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(Rh(s, e));
}, $h = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    di(l, Fc(t, a), s, n);
  }
}, Fc = (e, t) => {
  let s = e;
  const n = t.split(mr), r = n.length;
  for (let o = 0; o < r; o++) {
    const i = n[o];
    let a = s.nextPart.get(i);
    a || (a = Vc(), s.nextPart.set(i, a)), s = a;
  }
  return s;
}, zh = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Dh = (e) => {
  if (e < 1)
    return {
      get: () => {
      },
      set: () => {
      }
    };
  let t = 0, s = /* @__PURE__ */ Object.create(null), n = /* @__PURE__ */ Object.create(null);
  const r = (o, i) => {
    s[o] = i, t++, t > e && (t = 0, n = s, s = /* @__PURE__ */ Object.create(null));
  };
  return {
    get(o) {
      let i = s[o];
      if (i !== void 0)
        return i;
      if ((i = n[o]) !== void 0)
        return r(o, i), i;
    },
    set(o, i) {
      o in s ? s[o] = i : r(o, i);
    }
  };
}, zo = "!", za = ":", Vh = [], Da = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), Lh = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let w = 0; w < u; w++) {
      const z = r[w];
      if (i === 0 && a === 0) {
        if (z === za) {
          o.push(r.slice(l, w)), l = w + 1;
          continue;
        }
        if (z === "/") {
          c = w;
          continue;
        }
      }
      z === "[" ? i++ : z === "]" ? i-- : z === "(" ? a++ : z === ")" && a--;
    }
    const d = o.length === 0 ? r : r.slice(l);
    let m = d, h = !1;
    d.endsWith(zo) ? (m = d.slice(0, -1), h = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      d.startsWith(zo) && (m = d.slice(1), h = !0)
    );
    const k = c && c > l ? c - l : void 0;
    return Da(o, h, m, k);
  };
  if (t) {
    const r = t + za, o = n;
    n = (i) => i.startsWith(r) ? o(i.slice(r.length)) : Da(Vh, !1, i, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, Fh = (e) => {
  const t = /* @__PURE__ */ new Map();
  return e.orderSensitiveModifiers.forEach((s, n) => {
    t.set(s, 1e6 + n);
  }), (s) => {
    const n = [];
    let r = [];
    for (let o = 0; o < s.length; o++) {
      const i = s[o], a = i[0] === "[", l = t.has(i);
      a || l ? (r.length > 0 && (r.sort(), n.push(...r), r = []), n.push(i)) : r.push(i);
    }
    return r.length > 0 && (r.sort(), n.push(...r)), n;
  };
}, Uh = (e) => ({
  cache: Dh(e.cacheSize),
  parseClassName: Lh(e),
  sortModifiers: Fh(e),
  postfixLookupClassGroupIds: Wh(e),
  ...Oh(e)
}), Wh = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, Bh = /\s+/, Hh = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Bh);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const d = l[u], {
      isExternal: m,
      modifiers: h,
      hasImportantModifier: k,
      baseClassName: w,
      maybePostfixModifierPosition: z
    } = s(d);
    if (m) {
      c = d + (c.length > 0 ? " " + c : c);
      continue;
    }
    let N = !!z, g;
    if (N) {
      const oe = w.substring(0, z);
      g = n(oe);
      const _ = g && i[g] ? n(w) : void 0;
      _ && _ !== g && (g = _, N = !1);
    } else
      g = n(w);
    if (!g) {
      if (!N) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (g = n(w), !g) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      N = !1;
    }
    const E = h.length === 0 ? "" : h.length === 1 ? h[0] : o(h).join(":"), P = k ? E + zo : E, J = P + g;
    if (a.indexOf(J) > -1)
      continue;
    a.push(J);
    const ve = r(g, N);
    for (let oe = 0; oe < ve.length; ++oe) {
      const _ = ve[oe];
      a.push(P + _);
    }
    c = d + (c.length > 0 ? " " + c : c);
  }
  return c;
}, Gh = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = Uc(s)) && (r && (r += " "), r += n);
  return r;
}, Uc = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = Uc(e[n])) && (s && (s += " "), s += t);
  return s;
}, Zh = (e, ...t) => {
  let s, n, r, o;
  const i = (l) => {
    const c = t.reduce((u, d) => d(u), e());
    return s = Uh(c), n = s.cache.get, r = s.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = n(l);
    if (c)
      return c;
    const u = Hh(l, s);
    return r(l, u), u;
  };
  return o = i, (...l) => o(Gh(...l));
}, qh = [], He = (e) => {
  const t = (s) => s[e] || qh;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, Wc = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, Bc = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Kh = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, Jh = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, Qh = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Yh = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Xh = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, eg = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, as = (e) => Kh.test(e), he = (e) => !!e && !Number.isNaN(Number(e)), Nt = (e) => !!e && Number.isInteger(Number(e)), io = (e) => e.endsWith("%") && he(e.slice(0, -1)), Zt = (e) => Jh.test(e), Hc = () => !0, tg = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  Qh.test(e) && !Yh.test(e)
), fi = () => !1, sg = (e) => Xh.test(e), ng = (e) => eg.test(e), rg = (e) => !U(e) && !H(e), og = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), ig = (e) => ws(e, qc, fi), U = (e) => Wc.test(e), Cs = (e) => ws(e, Kc, tg), Va = (e) => ws(e, pg, he), ag = (e) => ws(e, Qc, Hc), lg = (e) => ws(e, Jc, fi), La = (e) => ws(e, Gc, fi), cg = (e) => ws(e, Zc, ng), Wn = (e) => ws(e, Yc, sg), H = (e) => Bc.test(e), on = (e) => Ns(e, Kc), ug = (e) => Ns(e, Jc), Fa = (e) => Ns(e, Gc), dg = (e) => Ns(e, qc), fg = (e) => Ns(e, Zc), Bn = (e) => Ns(e, Yc, !0), mg = (e) => Ns(e, Qc, !0), ws = (e, t, s) => {
  const n = Wc.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, Ns = (e, t, s = !1) => {
  const n = Bc.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, Gc = (e) => e === "position" || e === "percentage", Zc = (e) => e === "image" || e === "url", qc = (e) => e === "length" || e === "size" || e === "bg-size", Kc = (e) => e === "length", pg = (e) => e === "number", Jc = (e) => e === "family-name", Qc = (e) => e === "number" || e === "weight", Yc = (e) => e === "shadow", hg = () => {
  const e = He("color"), t = He("font"), s = He("text"), n = He("font-weight"), r = He("tracking"), o = He("leading"), i = He("breakpoint"), a = He("container"), l = He("spacing"), c = He("radius"), u = He("shadow"), d = He("inset-shadow"), m = He("text-shadow"), h = He("drop-shadow"), k = He("blur"), w = He("perspective"), z = He("aspect"), N = He("ease"), g = He("animate"), E = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], P = () => [
    "center",
    "top",
    "bottom",
    "left",
    "right",
    "top-left",
    // Deprecated since Tailwind CSS v4.1.0, see https://github.com/tailwindlabs/tailwindcss/pull/17378
    "left-top",
    "top-right",
    // Deprecated since Tailwind CSS v4.1.0, see https://github.com/tailwindlabs/tailwindcss/pull/17378
    "right-top",
    "bottom-right",
    // Deprecated since Tailwind CSS v4.1.0, see https://github.com/tailwindlabs/tailwindcss/pull/17378
    "right-bottom",
    "bottom-left",
    // Deprecated since Tailwind CSS v4.1.0, see https://github.com/tailwindlabs/tailwindcss/pull/17378
    "left-bottom"
  ], J = () => [...P(), H, U], ve = () => ["auto", "hidden", "clip", "visible", "scroll"], oe = () => ["auto", "contain", "none"], _ = () => [H, U, l], V = () => [as, "full", "auto", ..._()], ce = () => [Nt, "none", "subgrid", H, U], xe = () => ["auto", {
    span: ["full", Nt, H, U]
  }, Nt, H, U], ke = () => [Nt, "auto", H, U], Te = () => ["auto", "min", "max", "fr", H, U], D = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], me = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], ne = () => ["auto", ..._()], q = () => [as, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ..._()], fe = () => [a, as, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ..._()], Pe = () => [as, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ..._()], $ = () => [e, H, U], nt = () => [...P(), Fa, La, {
    position: [H, U]
  }], Ue = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], wt = () => ["auto", "cover", "contain", dg, ig, {
    size: [H, U]
  }], xt = () => [io, on, Cs], De = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    H,
    U
  ], Re = () => ["", he, on, Cs], S = () => ["solid", "dashed", "dotted", "double"], B = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], T = () => [he, io, Fa, La], se = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    k,
    H,
    U
  ], f = () => ["none", he, H, U], p = () => ["none", he, H, U], v = () => [he, H, U], b = () => [as, "full", ..._()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [Zt],
      breakpoint: [Zt],
      color: [Hc],
      container: [Zt],
      "drop-shadow": [Zt],
      ease: ["in", "out", "in-out"],
      font: [rg],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [Zt],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [Zt],
      shadow: [Zt],
      spacing: ["px", he],
      text: [Zt],
      "text-shadow": [Zt],
      tracking: ["tighter", "tight", "normal", "wide", "wider", "widest"]
    },
    classGroups: {
      // --------------
      // --- Layout ---
      // --------------
      /**
       * Aspect Ratio
       * @see https://tailwindcss.com/docs/aspect-ratio
       */
      aspect: [{
        aspect: ["auto", "square", as, U, H, z]
      }],
      /**
       * Container
       * @see https://tailwindcss.com/docs/container
       * @deprecated since Tailwind CSS v4.0.0
       */
      container: ["container"],
      /**
       * Container Type
       * @see https://tailwindcss.com/docs/responsive-design#container-queries
       */
      "container-type": [{
        "@container": ["", "normal", "size", H, U]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [og],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [he, "auto", U, H, a]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": E()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": E()
      }],
      /**
       * Break Inside
       * @see https://tailwindcss.com/docs/break-inside
       */
      "break-inside": [{
        "break-inside": ["auto", "avoid", "avoid-page", "avoid-column"]
      }],
      /**
       * Box Decoration Break
       * @see https://tailwindcss.com/docs/box-decoration-break
       */
      "box-decoration": [{
        "box-decoration": ["slice", "clone"]
      }],
      /**
       * Box Sizing
       * @see https://tailwindcss.com/docs/box-sizing
       */
      box: [{
        box: ["border", "content"]
      }],
      /**
       * Display
       * @see https://tailwindcss.com/docs/display
       */
      display: ["block", "inline-block", "inline", "flex", "inline-flex", "table", "inline-table", "table-caption", "table-cell", "table-column", "table-column-group", "table-footer-group", "table-header-group", "table-row-group", "table-row", "flow-root", "grid", "inline-grid", "contents", "list-item", "hidden"],
      /**
       * Screen Reader Only
       * @see https://tailwindcss.com/docs/display#screen-reader-only
       */
      sr: ["sr-only", "not-sr-only"],
      /**
       * Floats
       * @see https://tailwindcss.com/docs/float
       */
      float: [{
        float: ["right", "left", "none", "start", "end"]
      }],
      /**
       * Clear
       * @see https://tailwindcss.com/docs/clear
       */
      clear: [{
        clear: ["left", "right", "both", "none", "start", "end"]
      }],
      /**
       * Isolation
       * @see https://tailwindcss.com/docs/isolation
       */
      isolation: ["isolate", "isolation-auto"],
      /**
       * Object Fit
       * @see https://tailwindcss.com/docs/object-fit
       */
      "object-fit": [{
        object: ["contain", "cover", "fill", "none", "scale-down"]
      }],
      /**
       * Object Position
       * @see https://tailwindcss.com/docs/object-position
       */
      "object-position": [{
        object: J()
      }],
      /**
       * Overflow
       * @see https://tailwindcss.com/docs/overflow
       */
      overflow: [{
        overflow: ve()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": ve()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": ve()
      }],
      /**
       * Overscroll Behavior
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      overscroll: [{
        overscroll: oe()
      }],
      /**
       * Overscroll Behavior X
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-x": [{
        "overscroll-x": oe()
      }],
      /**
       * Overscroll Behavior Y
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-y": [{
        "overscroll-y": oe()
      }],
      /**
       * Position
       * @see https://tailwindcss.com/docs/position
       */
      position: ["static", "fixed", "absolute", "relative", "sticky"],
      /**
       * Inset
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      inset: [{
        inset: V()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": V()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": V()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": V(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: V()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": V(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: V()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": V()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": V()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: V()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: V()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: V()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: V()
      }],
      /**
       * Visibility
       * @see https://tailwindcss.com/docs/visibility
       */
      visibility: ["visible", "invisible", "collapse"],
      /**
       * Z-Index
       * @see https://tailwindcss.com/docs/z-index
       */
      z: [{
        z: [Nt, "auto", H, U]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [as, "full", "auto", a, ..._()]
      }],
      /**
       * Flex Direction
       * @see https://tailwindcss.com/docs/flex-direction
       */
      "flex-direction": [{
        flex: ["row", "row-reverse", "col", "col-reverse"]
      }],
      /**
       * Flex Wrap
       * @see https://tailwindcss.com/docs/flex-wrap
       */
      "flex-wrap": [{
        flex: ["nowrap", "wrap", "wrap-reverse"]
      }],
      /**
       * Flex
       * @see https://tailwindcss.com/docs/flex
       */
      flex: [{
        flex: [he, as, "auto", "initial", "none", U]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", he, H, U]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", he, H, U]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [Nt, "first", "last", "none", H, U]
      }],
      /**
       * Grid Template Columns
       * @see https://tailwindcss.com/docs/grid-template-columns
       */
      "grid-cols": [{
        "grid-cols": ce()
      }],
      /**
       * Grid Column Start / End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start-end": [{
        col: xe()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": ke()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": ke()
      }],
      /**
       * Grid Template Rows
       * @see https://tailwindcss.com/docs/grid-template-rows
       */
      "grid-rows": [{
        "grid-rows": ce()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: xe()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": ke()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": ke()
      }],
      /**
       * Grid Auto Flow
       * @see https://tailwindcss.com/docs/grid-auto-flow
       */
      "grid-flow": [{
        "grid-flow": ["row", "col", "dense", "row-dense", "col-dense"]
      }],
      /**
       * Grid Auto Columns
       * @see https://tailwindcss.com/docs/grid-auto-columns
       */
      "auto-cols": [{
        "auto-cols": Te()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": Te()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: _()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": _()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": _()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...D(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...me(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...me()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...D()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...me(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...me(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": D()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...me(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...me()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: _()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: _()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: _()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: _()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: _()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: _()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: _()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: _()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: _()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: _()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: _()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: ne()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: ne()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: ne()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: ne()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: ne()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: ne()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: ne()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: ne()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: ne()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: ne()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: ne()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": _()
      }],
      /**
       * Space Between X Reverse
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x-reverse": ["space-x-reverse"],
      /**
       * Space Between Y
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-y": [{
        "space-y": _()
      }],
      /**
       * Space Between Y Reverse
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-y-reverse": ["space-y-reverse"],
      // --------------
      // --- Sizing ---
      // --------------
      /**
       * Size
       * @see https://tailwindcss.com/docs/width#setting-both-width-and-height
       */
      size: [{
        size: q()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ...fe()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...fe()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...fe()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...Pe()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...Pe()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...Pe()]
      }],
      /**
       * Width
       * @see https://tailwindcss.com/docs/width
       */
      w: [{
        w: [a, "screen", ...q()]
      }],
      /**
       * Min-Width
       * @see https://tailwindcss.com/docs/min-width
       */
      "min-w": [{
        "min-w": [
          a,
          "screen",
          /** Deprecated. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          "none",
          ...q()
        ]
      }],
      /**
       * Max-Width
       * @see https://tailwindcss.com/docs/max-width
       */
      "max-w": [{
        "max-w": [
          a,
          "screen",
          "none",
          /** Deprecated since Tailwind CSS v4.0.0. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          "prose",
          /** Deprecated since Tailwind CSS v4.0.0. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          {
            screen: [i]
          },
          ...q()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...q()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...q()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...q()]
      }],
      // ------------------
      // --- Typography ---
      // ------------------
      /**
       * Font Size
       * @see https://tailwindcss.com/docs/font-size
       */
      "font-size": [{
        text: ["base", s, on, Cs]
      }],
      /**
       * Font Smoothing
       * @see https://tailwindcss.com/docs/font-smoothing
       */
      "font-smoothing": ["antialiased", "subpixel-antialiased"],
      /**
       * Font Style
       * @see https://tailwindcss.com/docs/font-style
       */
      "font-style": ["italic", "not-italic"],
      /**
       * Font Weight
       * @see https://tailwindcss.com/docs/font-weight
       */
      "font-weight": [{
        font: [n, mg, ag]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", io, U]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [ug, lg, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [U]
      }],
      /**
       * Font Variant Numeric
       * @see https://tailwindcss.com/docs/font-variant-numeric
       */
      "fvn-normal": ["normal-nums"],
      /**
       * Font Variant Numeric
       * @see https://tailwindcss.com/docs/font-variant-numeric
       */
      "fvn-ordinal": ["ordinal"],
      /**
       * Font Variant Numeric
       * @see https://tailwindcss.com/docs/font-variant-numeric
       */
      "fvn-slashed-zero": ["slashed-zero"],
      /**
       * Font Variant Numeric
       * @see https://tailwindcss.com/docs/font-variant-numeric
       */
      "fvn-figure": ["lining-nums", "oldstyle-nums"],
      /**
       * Font Variant Numeric
       * @see https://tailwindcss.com/docs/font-variant-numeric
       */
      "fvn-spacing": ["proportional-nums", "tabular-nums"],
      /**
       * Font Variant Numeric
       * @see https://tailwindcss.com/docs/font-variant-numeric
       */
      "fvn-fraction": ["diagonal-fractions", "stacked-fractions"],
      /**
       * Letter Spacing
       * @see https://tailwindcss.com/docs/letter-spacing
       */
      tracking: [{
        tracking: [r, H, U]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [he, "none", H, Va]
      }],
      /**
       * Line Height
       * @see https://tailwindcss.com/docs/line-height
       */
      leading: [{
        leading: [
          "none",
          /** Deprecated since Tailwind CSS v4.0.0. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          o,
          ..._()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", H, U]
      }],
      /**
       * List Style Position
       * @see https://tailwindcss.com/docs/list-style-position
       */
      "list-style-position": [{
        list: ["inside", "outside"]
      }],
      /**
       * List Style Type
       * @see https://tailwindcss.com/docs/list-style-type
       */
      "list-style-type": [{
        list: ["disc", "decimal", "none", H, U]
      }],
      /**
       * Text Alignment
       * @see https://tailwindcss.com/docs/text-align
       */
      "text-alignment": [{
        text: ["left", "center", "right", "justify", "start", "end"]
      }],
      /**
       * Placeholder Color
       * @deprecated since Tailwind CSS v3.0.0
       * @see https://v3.tailwindcss.com/docs/placeholder-color
       */
      "placeholder-color": [{
        placeholder: $()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: $()
      }],
      /**
       * Text Decoration
       * @see https://tailwindcss.com/docs/text-decoration
       */
      "text-decoration": ["underline", "overline", "line-through", "no-underline"],
      /**
       * Text Decoration Style
       * @see https://tailwindcss.com/docs/text-decoration-style
       */
      "text-decoration-style": [{
        decoration: [...S(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [he, "from-font", "auto", H, Cs]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: $()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [he, "auto", H, U]
      }],
      /**
       * Text Transform
       * @see https://tailwindcss.com/docs/text-transform
       */
      "text-transform": ["uppercase", "lowercase", "capitalize", "normal-case"],
      /**
       * Text Overflow
       * @see https://tailwindcss.com/docs/text-overflow
       */
      "text-overflow": ["truncate", "text-ellipsis", "text-clip"],
      /**
       * Text Wrap
       * @see https://tailwindcss.com/docs/text-wrap
       */
      "text-wrap": [{
        text: ["wrap", "nowrap", "balance", "pretty"]
      }],
      /**
       * Text Indent
       * @see https://tailwindcss.com/docs/text-indent
       */
      indent: [{
        indent: _()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [Nt, H, U]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", H, U]
      }],
      /**
       * Whitespace
       * @see https://tailwindcss.com/docs/whitespace
       */
      whitespace: [{
        whitespace: ["normal", "nowrap", "pre", "pre-line", "pre-wrap", "break-spaces"]
      }],
      /**
       * Word Break
       * @see https://tailwindcss.com/docs/word-break
       */
      break: [{
        break: ["normal", "words", "all", "keep"]
      }],
      /**
       * Overflow Wrap
       * @see https://tailwindcss.com/docs/overflow-wrap
       */
      wrap: [{
        wrap: ["break-word", "anywhere", "normal"]
      }],
      /**
       * Hyphens
       * @see https://tailwindcss.com/docs/hyphens
       */
      hyphens: [{
        hyphens: ["none", "manual", "auto"]
      }],
      /**
       * Content
       * @see https://tailwindcss.com/docs/content
       */
      content: [{
        content: ["none", H, U]
      }],
      // -------------------
      // --- Backgrounds ---
      // -------------------
      /**
       * Background Attachment
       * @see https://tailwindcss.com/docs/background-attachment
       */
      "bg-attachment": [{
        bg: ["fixed", "local", "scroll"]
      }],
      /**
       * Background Clip
       * @see https://tailwindcss.com/docs/background-clip
       */
      "bg-clip": [{
        "bg-clip": ["border", "padding", "content", "text"]
      }],
      /**
       * Background Origin
       * @see https://tailwindcss.com/docs/background-origin
       */
      "bg-origin": [{
        "bg-origin": ["border", "padding", "content"]
      }],
      /**
       * Background Position
       * @see https://tailwindcss.com/docs/background-position
       */
      "bg-position": [{
        bg: nt()
      }],
      /**
       * Background Repeat
       * @see https://tailwindcss.com/docs/background-repeat
       */
      "bg-repeat": [{
        bg: Ue()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: wt()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, Nt, H, U],
          radial: ["", H, U],
          conic: ["", Nt, H, U]
        }, fg, cg]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: $()
      }],
      /**
       * Gradient Color Stops From Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from-pos": [{
        from: xt()
      }],
      /**
       * Gradient Color Stops Via Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via-pos": [{
        via: xt()
      }],
      /**
       * Gradient Color Stops To Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to-pos": [{
        to: xt()
      }],
      /**
       * Gradient Color Stops From
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from": [{
        from: $()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: $()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: $()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: De()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": De()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": De()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": De()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": De()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": De()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": De()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": De()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": De()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": De()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": De()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": De()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": De()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": De()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": De()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: Re()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": Re()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": Re()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": Re()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": Re()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": Re()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": Re()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": Re()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": Re()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": Re()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": Re()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": Re()
      }],
      /**
       * Divide Width X Reverse
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x-reverse": ["divide-x-reverse"],
      /**
       * Divide Width Y
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-y": [{
        "divide-y": Re()
      }],
      /**
       * Divide Width Y Reverse
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-y-reverse": ["divide-y-reverse"],
      /**
       * Border Style
       * @see https://tailwindcss.com/docs/border-style
       */
      "border-style": [{
        border: [...S(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...S(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: $()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": $()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": $()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": $()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": $()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": $()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": $()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": $()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": $()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": $()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": $()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: $()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [...S(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [he, H, U]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", he, on, Cs]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: $()
      }],
      // ---------------
      // --- Effects ---
      // ---------------
      /**
       * Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow
       */
      shadow: [{
        shadow: [
          // Deprecated since Tailwind CSS v4.0.0
          "",
          // Deprecated since Tailwind CSS v4.0.0
          "inner",
          "none",
          u,
          Bn,
          Wn
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: $()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", d, Bn, Wn]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": $()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: Re()
      }],
      /**
       * Ring Width Inset
       * @see https://v3.tailwindcss.com/docs/ring-width#inset-rings
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-w-inset": ["ring-inset"],
      /**
       * Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-ring-color
       */
      "ring-color": [{
        ring: $()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [he, Cs]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": $()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": Re()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": $()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", m, Bn, Wn]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": $()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [he, H, U]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...B(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": B()
      }],
      /**
       * Mask Clip
       * @see https://tailwindcss.com/docs/mask-clip
       */
      "mask-clip": [{
        "mask-clip": ["border", "padding", "content", "fill", "stroke", "view"]
      }, "mask-no-clip"],
      /**
       * Mask Composite
       * @see https://tailwindcss.com/docs/mask-composite
       */
      "mask-composite": [{
        mask: ["add", "subtract", "intersect", "exclude"]
      }],
      /**
       * Mask Image
       * @see https://tailwindcss.com/docs/mask-image
       */
      "mask-image-linear-pos": [{
        "mask-linear": [he]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": T()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": T()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": $()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": $()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": T()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": T()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": $()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": $()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": T()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": T()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": $()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": $()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": T()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": T()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": $()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": $()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": T()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": T()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": $()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": $()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": T()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": T()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": $()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": $()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": T()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": T()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": $()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": $()
      }],
      "mask-image-radial": [{
        "mask-radial": [H, U]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": T()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": T()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": $()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": $()
      }],
      "mask-image-radial-shape": [{
        "mask-radial": ["circle", "ellipse"]
      }],
      "mask-image-radial-size": [{
        "mask-radial": [{
          closest: ["side", "corner"],
          farthest: ["side", "corner"]
        }]
      }],
      "mask-image-radial-pos": [{
        "mask-radial-at": P()
      }],
      "mask-image-conic-pos": [{
        "mask-conic": [he]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": T()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": T()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": $()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": $()
      }],
      /**
       * Mask Mode
       * @see https://tailwindcss.com/docs/mask-mode
       */
      "mask-mode": [{
        mask: ["alpha", "luminance", "match"]
      }],
      /**
       * Mask Origin
       * @see https://tailwindcss.com/docs/mask-origin
       */
      "mask-origin": [{
        "mask-origin": ["border", "padding", "content", "fill", "stroke", "view"]
      }],
      /**
       * Mask Position
       * @see https://tailwindcss.com/docs/mask-position
       */
      "mask-position": [{
        mask: nt()
      }],
      /**
       * Mask Repeat
       * @see https://tailwindcss.com/docs/mask-repeat
       */
      "mask-repeat": [{
        mask: Ue()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: wt()
      }],
      /**
       * Mask Type
       * @see https://tailwindcss.com/docs/mask-type
       */
      "mask-type": [{
        "mask-type": ["alpha", "luminance"]
      }],
      /**
       * Mask Image
       * @see https://tailwindcss.com/docs/mask-image
       */
      "mask-image": [{
        mask: ["none", H, U]
      }],
      // ---------------
      // --- Filters ---
      // ---------------
      /**
       * Filter
       * @see https://tailwindcss.com/docs/filter
       */
      filter: [{
        filter: [
          // Deprecated since Tailwind CSS v3.0.0
          "",
          "none",
          H,
          U
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: se()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [he, H, U]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [he, H, U]
      }],
      /**
       * Drop Shadow
       * @see https://tailwindcss.com/docs/drop-shadow
       */
      "drop-shadow": [{
        "drop-shadow": [
          // Deprecated since Tailwind CSS v4.0.0
          "",
          "none",
          h,
          Bn,
          Wn
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": $()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", he, H, U]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [he, H, U]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", he, H, U]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [he, H, U]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", he, H, U]
      }],
      /**
       * Backdrop Filter
       * @see https://tailwindcss.com/docs/backdrop-filter
       */
      "backdrop-filter": [{
        "backdrop-filter": [
          // Deprecated since Tailwind CSS v3.0.0
          "",
          "none",
          H,
          U
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": se()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [he, H, U]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [he, H, U]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", he, H, U]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [he, H, U]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", he, H, U]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [he, H, U]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [he, H, U]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", he, H, U]
      }],
      // --------------
      // --- Tables ---
      // --------------
      /**
       * Border Collapse
       * @see https://tailwindcss.com/docs/border-collapse
       */
      "border-collapse": [{
        border: ["collapse", "separate"]
      }],
      /**
       * Border Spacing
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing": [{
        "border-spacing": _()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": _()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": _()
      }],
      /**
       * Table Layout
       * @see https://tailwindcss.com/docs/table-layout
       */
      "table-layout": [{
        table: ["auto", "fixed"]
      }],
      /**
       * Caption Side
       * @see https://tailwindcss.com/docs/caption-side
       */
      caption: [{
        caption: ["top", "bottom"]
      }],
      // ---------------------------------
      // --- Transitions and Animation ---
      // ---------------------------------
      /**
       * Transition Property
       * @see https://tailwindcss.com/docs/transition-property
       */
      transition: [{
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", H, U]
      }],
      /**
       * Transition Behavior
       * @see https://tailwindcss.com/docs/transition-behavior
       */
      "transition-behavior": [{
        transition: ["normal", "discrete"]
      }],
      /**
       * Transition Duration
       * @see https://tailwindcss.com/docs/transition-duration
       */
      duration: [{
        duration: [he, "initial", H, U]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", N, H, U]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [he, H, U]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", g, H, U]
      }],
      // ------------------
      // --- Transforms ---
      // ------------------
      /**
       * Backface Visibility
       * @see https://tailwindcss.com/docs/backface-visibility
       */
      backface: [{
        backface: ["hidden", "visible"]
      }],
      /**
       * Perspective
       * @see https://tailwindcss.com/docs/perspective
       */
      perspective: [{
        perspective: [w, H, U]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": J()
      }],
      /**
       * Rotate
       * @see https://tailwindcss.com/docs/rotate
       */
      rotate: [{
        rotate: f()
      }],
      /**
       * Rotate X
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-x": [{
        "rotate-x": f()
      }],
      /**
       * Rotate Y
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-y": [{
        "rotate-y": f()
      }],
      /**
       * Rotate Z
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-z": [{
        "rotate-z": f()
      }],
      /**
       * Scale
       * @see https://tailwindcss.com/docs/scale
       */
      scale: [{
        scale: p()
      }],
      /**
       * Scale X
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-x": [{
        "scale-x": p()
      }],
      /**
       * Scale Y
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-y": [{
        "scale-y": p()
      }],
      /**
       * Scale Z
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-z": [{
        "scale-z": p()
      }],
      /**
       * Scale 3D
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-3d": ["scale-3d"],
      /**
       * Skew
       * @see https://tailwindcss.com/docs/skew
       */
      skew: [{
        skew: v()
      }],
      /**
       * Skew X
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-x": [{
        "skew-x": v()
      }],
      /**
       * Skew Y
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-y": [{
        "skew-y": v()
      }],
      /**
       * Transform
       * @see https://tailwindcss.com/docs/transform
       */
      transform: [{
        transform: [H, U, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: J()
      }],
      /**
       * Transform Style
       * @see https://tailwindcss.com/docs/transform-style
       */
      "transform-style": [{
        transform: ["3d", "flat"]
      }],
      /**
       * Translate
       * @see https://tailwindcss.com/docs/translate
       */
      translate: [{
        translate: b()
      }],
      /**
       * Translate X
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-x": [{
        "translate-x": b()
      }],
      /**
       * Translate Y
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-y": [{
        "translate-y": b()
      }],
      /**
       * Translate Z
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-z": [{
        "translate-z": b()
      }],
      /**
       * Translate None
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-none": ["translate-none"],
      /**
       * Zoom
       * @see https://tailwindcss.com/docs/zoom
       */
      zoom: [{
        zoom: [Nt, H, U]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: $()
      }],
      /**
       * Appearance
       * @see https://tailwindcss.com/docs/appearance
       */
      appearance: [{
        appearance: ["none", "auto"]
      }],
      /**
       * Caret Color
       * @see https://tailwindcss.com/docs/just-in-time-mode#caret-color-utilities
       */
      "caret-color": [{
        caret: $()
      }],
      /**
       * Color Scheme
       * @see https://tailwindcss.com/docs/color-scheme
       */
      "color-scheme": [{
        scheme: ["normal", "dark", "light", "light-dark", "only-dark", "only-light"]
      }],
      /**
       * Cursor
       * @see https://tailwindcss.com/docs/cursor
       */
      cursor: [{
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", H, U]
      }],
      /**
       * Field Sizing
       * @see https://tailwindcss.com/docs/field-sizing
       */
      "field-sizing": [{
        "field-sizing": ["fixed", "content"]
      }],
      /**
       * Pointer Events
       * @see https://tailwindcss.com/docs/pointer-events
       */
      "pointer-events": [{
        "pointer-events": ["auto", "none"]
      }],
      /**
       * Resize
       * @see https://tailwindcss.com/docs/resize
       */
      resize: [{
        resize: ["none", "", "y", "x"]
      }],
      /**
       * Scroll Behavior
       * @see https://tailwindcss.com/docs/scroll-behavior
       */
      "scroll-behavior": [{
        scroll: ["auto", "smooth"]
      }],
      /**
       * Scrollbar Thumb Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-thumb-color": [{
        "scrollbar-thumb": $()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": $()
      }],
      /**
       * Scrollbar Gutter
       * @see https://tailwindcss.com/docs/scrollbar-gutter
       */
      "scrollbar-gutter": [{
        "scrollbar-gutter": ["auto", "stable", "both"]
      }],
      /**
       * Scrollbar Width
       * @see https://tailwindcss.com/docs/scrollbar-width
       */
      "scrollbar-w": [{
        scrollbar: ["auto", "thin", "none"]
      }],
      /**
       * Scroll Margin
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-m": [{
        "scroll-m": _()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": _()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": _()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": _()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": _()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": _()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": _()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": _()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": _()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": _()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": _()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": _()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": _()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": _()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": _()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": _()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": _()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": _()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": _()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": _()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": _()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": _()
      }],
      /**
       * Scroll Snap Align
       * @see https://tailwindcss.com/docs/scroll-snap-align
       */
      "snap-align": [{
        snap: ["start", "end", "center", "align-none"]
      }],
      /**
       * Scroll Snap Stop
       * @see https://tailwindcss.com/docs/scroll-snap-stop
       */
      "snap-stop": [{
        snap: ["normal", "always"]
      }],
      /**
       * Scroll Snap Type
       * @see https://tailwindcss.com/docs/scroll-snap-type
       */
      "snap-type": [{
        snap: ["none", "x", "y", "both"]
      }],
      /**
       * Scroll Snap Type Strictness
       * @see https://tailwindcss.com/docs/scroll-snap-type
       */
      "snap-strictness": [{
        snap: ["mandatory", "proximity"]
      }],
      /**
       * Touch Action
       * @see https://tailwindcss.com/docs/touch-action
       */
      touch: [{
        touch: ["auto", "none", "manipulation"]
      }],
      /**
       * Touch Action X
       * @see https://tailwindcss.com/docs/touch-action
       */
      "touch-x": [{
        "touch-pan": ["x", "left", "right"]
      }],
      /**
       * Touch Action Y
       * @see https://tailwindcss.com/docs/touch-action
       */
      "touch-y": [{
        "touch-pan": ["y", "up", "down"]
      }],
      /**
       * Touch Action Pinch Zoom
       * @see https://tailwindcss.com/docs/touch-action
       */
      "touch-pz": ["touch-pinch-zoom"],
      /**
       * User Select
       * @see https://tailwindcss.com/docs/user-select
       */
      select: [{
        select: ["none", "text", "all", "auto"]
      }],
      /**
       * Will Change
       * @see https://tailwindcss.com/docs/will-change
       */
      "will-change": [{
        "will-change": ["auto", "scroll", "contents", "transform", H, U]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...$()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [he, on, Cs, Va]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...$()]
      }],
      // ---------------------
      // --- Accessibility ---
      // ---------------------
      /**
       * Forced Color Adjust
       * @see https://tailwindcss.com/docs/forced-color-adjust
       */
      "forced-color-adjust": [{
        "forced-color-adjust": ["auto", "none"]
      }]
    },
    conflictingClassGroups: {
      "container-named": ["container-type"],
      overflow: ["overflow-x", "overflow-y"],
      overscroll: ["overscroll-x", "overscroll-y"],
      inset: ["inset-x", "inset-y", "inset-bs", "inset-be", "start", "end", "top", "right", "bottom", "left"],
      "inset-x": ["start", "end", "right", "left"],
      "inset-y": ["inset-bs", "inset-be", "top", "bottom"],
      flex: ["basis", "grow", "shrink"],
      gap: ["gap-x", "gap-y"],
      p: ["px", "py", "ps", "pe", "pbs", "pbe", "pt", "pr", "pb", "pl"],
      px: ["ps", "pe", "pr", "pl"],
      py: ["pbs", "pbe", "pt", "pb"],
      m: ["mx", "my", "ms", "me", "mbs", "mbe", "mt", "mr", "mb", "ml"],
      mx: ["ms", "me", "mr", "ml"],
      my: ["mbs", "mbe", "mt", "mb"],
      size: ["w", "h"],
      "font-size": ["leading"],
      "fvn-normal": ["fvn-ordinal", "fvn-slashed-zero", "fvn-figure", "fvn-spacing", "fvn-fraction"],
      "fvn-ordinal": ["fvn-normal"],
      "fvn-slashed-zero": ["fvn-normal"],
      "fvn-figure": ["fvn-normal"],
      "fvn-spacing": ["fvn-normal"],
      "fvn-fraction": ["fvn-normal"],
      "line-clamp": ["display", "overflow"],
      rounded: ["rounded-s", "rounded-e", "rounded-t", "rounded-r", "rounded-b", "rounded-l", "rounded-ss", "rounded-se", "rounded-ee", "rounded-es", "rounded-tl", "rounded-tr", "rounded-br", "rounded-bl"],
      "rounded-s": ["rounded-ss", "rounded-es"],
      "rounded-e": ["rounded-se", "rounded-ee"],
      "rounded-t": ["rounded-tl", "rounded-tr"],
      "rounded-r": ["rounded-tr", "rounded-br"],
      "rounded-b": ["rounded-br", "rounded-bl"],
      "rounded-l": ["rounded-tl", "rounded-bl"],
      "border-spacing": ["border-spacing-x", "border-spacing-y"],
      "border-w": ["border-w-x", "border-w-y", "border-w-s", "border-w-e", "border-w-bs", "border-w-be", "border-w-t", "border-w-r", "border-w-b", "border-w-l"],
      "border-w-x": ["border-w-s", "border-w-e", "border-w-r", "border-w-l"],
      "border-w-y": ["border-w-bs", "border-w-be", "border-w-t", "border-w-b"],
      "border-color": ["border-color-x", "border-color-y", "border-color-s", "border-color-e", "border-color-bs", "border-color-be", "border-color-t", "border-color-r", "border-color-b", "border-color-l"],
      "border-color-x": ["border-color-s", "border-color-e", "border-color-r", "border-color-l"],
      "border-color-y": ["border-color-bs", "border-color-be", "border-color-t", "border-color-b"],
      translate: ["translate-x", "translate-y", "translate-none"],
      "translate-none": ["translate", "translate-x", "translate-y", "translate-z"],
      "scroll-m": ["scroll-mx", "scroll-my", "scroll-ms", "scroll-me", "scroll-mbs", "scroll-mbe", "scroll-mt", "scroll-mr", "scroll-mb", "scroll-ml"],
      "scroll-mx": ["scroll-ms", "scroll-me", "scroll-mr", "scroll-ml"],
      "scroll-my": ["scroll-mbs", "scroll-mbe", "scroll-mt", "scroll-mb"],
      "scroll-p": ["scroll-px", "scroll-py", "scroll-ps", "scroll-pe", "scroll-pbs", "scroll-pbe", "scroll-pt", "scroll-pr", "scroll-pb", "scroll-pl"],
      "scroll-px": ["scroll-ps", "scroll-pe", "scroll-pr", "scroll-pl"],
      "scroll-py": ["scroll-pbs", "scroll-pbe", "scroll-pt", "scroll-pb"],
      touch: ["touch-x", "touch-y", "touch-pz"],
      "touch-x": ["touch"],
      "touch-y": ["touch"],
      "touch-pz": ["touch"]
    },
    conflictingClassGroupModifiers: {
      "font-size": ["leading"]
    },
    postfixLookupClassGroups: ["container-type"],
    orderSensitiveModifiers: ["*", "**", "after", "backdrop", "before", "details-content", "file", "first-letter", "first-line", "marker", "placeholder", "selection"]
  };
}, gg = /* @__PURE__ */ Zh(hg);
function mi(...e) {
  return gg(Dc(e));
}
const vg = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, yg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, bg = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, _g = { class: "cmst:flex-1" }, wg = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, xg = { "data-testid": "vue-status-route" }, kg = { "data-testid": "vue-status-ops" }, Sg = { "data-testid": "vue-status-density" }, Cg = { class: "cmst:flex cmst:items-center cmst:gap-1" }, Ag = /* @__PURE__ */ vt({
  __name: "StudioApp",
  setup(e) {
    const t = wc(), s = ai(), n = jc(), r = ui();
    Qs(() => {
      n.initialize(), r.initialize();
    });
    const o = bp("(min-width: 768px)"), i = {
      playground: xc,
      history: kc,
      workflows: Oo,
      backend: Sc,
      settings: Cc
    }, a = Oe(() => String(t.name ?? "playground"));
    function l(c) {
      const u = a.value === c;
      return mi(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        u ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (c, u) => (X(), ge("div", vg, [
      y("header", yg, [
        u[0] || (u[0] = y("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          te(" Modal Studio "),
          y("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        y("nav", bg, [
          (X(!0), ge(ze, null, Ys(C(ii), (d) => (X(), at(C(bc), {
            key: d,
            to: { name: d },
            class: ft(l(d)),
            "data-testid": `vue-nav-${d}`
          }, {
            default: ae(() => [
              (X(), at(ad(i[d]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              te(" " + re(C(_p)[d]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      y("main", _g, [
        W(C(_c))
      ]),
      y("footer", wg, [
        y("span", null, [
          u[1] || (u[1] = te("route: ", -1)),
          y("strong", xg, re(a.value), 1)
        ]),
        y("span", null, [
          u[2] || (u[2] = te(" operations: ", -1)),
          y("strong", kg, re(C(s).active.length) + " active", 1),
          te(" / " + re(C(s).all.length) + " total ", 1)
        ]),
        y("span", null, [
          u[3] || (u[3] = te(" density: ", -1)),
          y("strong", Sg, re(C(n).density), 1)
        ]),
        y("span", Cg, [
          W(C(Jm), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          u[4] || (u[4] = te(" viewport: ", -1)),
          y("strong", null, re(C(o) ? "wide" : "narrow"), 1),
          u[5] || (u[5] = te(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), Rg = "/", Xc = { page: "playground", focus: null };
function Hn(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function ao(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = ys(n) ? n : Xc.page;
  let o = null;
  if (s)
    for (const i of s.split("&")) {
      const a = i.indexOf("=");
      if (a !== -1 && decodeURIComponent(i.slice(0, a)) === "focus") {
        try {
          const l = decodeURIComponent(i.slice(a + 1));
          o = l === "" ? null : l;
        } catch {
          o = null;
        }
        break;
      }
    }
  return { page: r, focus: o };
}
function lo(e) {
  const t = Ec(e.location.hash);
  return !t.matched || !ys(t.page) ? null : { page: t.page, focus: t.focus };
}
function co(e, t, s) {
  const n = Oc(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function Eg(e, t) {
  let s = wp(t, e.location.hash), n = Hn(s), r = {};
  const o = n, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = n;
    s = lo(e) ?? { ...Xc }, n = Hn(s), i.forEach((m) => m(n, u));
  }, c = (u, d) => u === null && d === o;
  return {
    get base() {
      return Rg;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const d = Oc(ao(u));
      return d === "" ? "#" + u : d;
    },
    replace: (u, d) => {
      const m = lo(e), h = ao(u), k = Hn(h);
      s = h, d !== void 0 && (r = d), n = k, !c(m, k) && ga(m, h) !== "none" && co(e, h, "replace");
    },
    push: (u, d) => {
      const m = lo(e), h = ao(u), k = Hn(h);
      if (s = h, d !== void 0 && (r = d), n = k, c(m, k)) return;
      const w = ga(m, h);
      w === "push" ? co(e, h, "push") : w === "replace" && co(e, h, "replace");
    },
    go: (u) => {
      e.history.go(u);
    },
    listen: (u) => {
      const d = (m, h) => {
        u(m, h, { type: "pop", direction: "unknown", delta: 0 });
      };
      return i.add(d), a || (e.addEventListener("popstate", l), a = !0), () => {
        i.delete(d), i.size === 0 && a && (e.removeEventListener("popstate", l), a = !1);
      };
    },
    destroy: () => {
      i.clear(), a && (e.removeEventListener("popstate", l), a = !1);
    }
  };
}
const Ua = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, Wa = Dc, Og = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return Wa(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = s?.[c], d = o?.[c];
    if (u === null) return null;
    const m = Ua(u) || Ua(d);
    return r[c][m];
  }), a = s && Object.entries(s).reduce((c, u) => {
    let [d, m] = u;
    return m === void 0 || (c[d] = m), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, u) => {
    let { class: d, className: m, ...h } = u;
    return Object.entries(h).every((k) => {
      let [w, z] = k;
      return Array.isArray(z) ? z.includes({
        ...o,
        ...a
      }[w]) : {
        ...o,
        ...a
      }[w] === z;
    }) ? [
      ...c,
      d,
      m
    ] : c;
  }, []);
  return Wa(e, i, l, s?.class, s?.className);
}, Tg = Og(
  "cmst:inline-flex cmst:items-center cmst:justify-center cmst:gap-2 cmst:whitespace-nowrap cmst:rounded-md cmst:text-sm cmst:font-medium cmst:transition-colors cmst:cursor-pointer cmst:disabled:pointer-events-none cmst:disabled:opacity-50 cmst:[&_svg]:size-4 cmst:[&_svg]:shrink-0 cmst:outline-none cmst:border cmst:border-solid",
  {
    variants: {
      variant: {
        default: "cmst:bg-cmst-primary cmst:text-cmst-primary-fg cmst:border-transparent cmst:hover:bg-cmst-primary-hover",
        secondary: "cmst:bg-cmst-secondary cmst:text-cmst-secondary-fg cmst:border-cmst-border cmst:hover:bg-cmst-secondary-hover",
        outline: "cmst:bg-transparent cmst:text-cmst-fg cmst:border-cmst-border cmst:hover:bg-cmst-secondary",
        ghost: "cmst:bg-transparent cmst:text-cmst-fg cmst:border-transparent cmst:hover:bg-cmst-secondary"
      },
      size: {
        default: "cmst:h-9 cmst:px-4 cmst:py-2",
        sm: "cmst:h-8 cmst:px-3 cmst:text-xs",
        lg: "cmst:h-10 cmst:px-6",
        icon: "cmst:h-9 cmst:w-9"
      }
    },
    defaultVariants: { variant: "default", size: "default" }
  }
), Ig = ["type", "disabled"], $e = /* @__PURE__ */ vt({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (X(), ge("button", {
      type: e.type,
      disabled: e.disabled,
      class: ft(C(Tg)({ variant: e.variant, size: e.size }))
    }, [
      Nl(t.$slots, "default")
    ], 10, Ig));
  }
}), qe = /* @__PURE__ */ vt({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (X(), ge("div", {
      class: ft(
        C(mi)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      Nl(t.$slots, "default")
    ], 2));
  }
});
function Mn(e) {
  return mi(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const Ng = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Pg = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, Mg = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, jg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, $g = { value: "" }, zg = ["value"], Dg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, Vg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Lg = { class: "cmst:mt-1 cmst:text-sm" }, Fg = { "data-testid": "vue-deploy-state" }, Ug = {
  key: 0,
  class: "cmst:text-sm cmst:opacity-80"
}, Wg = { class: "cmst:flex cmst:gap-2" }, Bg = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, Hg = { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, Gg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Zg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, qg = /* @__PURE__ */ vt({
  __name: "BackendView",
  setup(e) {
    const t = ui(), s = /* @__PURE__ */ G(""), n = /* @__PURE__ */ G(!1), r = Oe(() => t.models.length), o = Oe(() => t.customNodes.length);
    Qs(() => {
      t.workspaces.length || t.initialize();
    });
    async function i() {
      s.value && await t.selectWorkspace(s.value);
    }
    async function a() {
      await t.deploy();
    }
    return (l, c) => (X(), ge("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-backend"
    }, [
      C(t).error ? (X(), ge("div", Ng, re(C(t).error), 1)) : Ye("", !0),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          y("div", Pg, [
            y("div", null, [
              y("h2", Mg, [
                W(C(Sc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[2] || (c[2] = te(" Manage Modal ", -1))
              ]),
              c[3] || (c[3] = y("p", { class: "cmst:text-sm cmst:opacity-80" }, [
                te("Route key remains "),
                y("code", null, "backend"),
                te(". Workspace and readiness state come from the server.")
              ], -1))
            ]),
            W($e, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload infrastructure",
              disabled: C(t).loading,
              onClick: C(t).load
            }, {
              default: ae(() => [
                W(C(Pr), {
                  class: ft(["cmst:size-4", C(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ])
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          c[5] || (c[5] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Workspaces", -1)),
          y("div", jg, [
            Xt(y("select", {
              "onUpdate:modelValue": c[0] || (c[0] = (u) => s.value = u),
              class: "cmst:h-9 cmst:min-w-52 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              "data-testid": "vue-workspace-select"
            }, [
              y("option", $g, re(C(t).activeWorkspace?.label ?? "Select workspace"), 1),
              (X(!0), ge(ze, null, Ys(C(t).workspaces, (u) => (X(), ge("option", {
                key: u.id,
                value: u.id
              }, re(u.label) + re(u.isActive ? " (active)" : ""), 9, zg))), 128))
            ], 512), [
              [ni, s.value]
            ]),
            W($e, {
              size: "sm",
              variant: "secondary",
              disabled: !s.value,
              "data-testid": "vue-workspace-activate",
              onClick: i
            }, {
              default: ae(() => [...c[4] || (c[4] = [
                te(" Activate workspace ", -1)
              ])]),
              _: 1
            }, 8, ["disabled"])
          ]),
          y("p", Dg, "Active ID: " + re(C(t).activeWorkspaceId ?? "none"), 1)
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          y("div", Vg, [
            y("div", null, [
              c[7] || (c[7] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Deployment readiness", -1)),
              y("p", Lg, [
                c[6] || (c[6] = te("State: ", -1)),
                y("strong", Fg, re(C(t).deployStatus.state), 1)
              ]),
              C(t).deployMessage ? (X(), ge("p", Ug, re(C(t).deployMessage), 1)) : Ye("", !0)
            ]),
            y("div", Wg, [
              W($e, {
                size: "sm",
                disabled: C(t).loading,
                "data-testid": "vue-deploy",
                onClick: a
              }, {
                default: ae(() => [...c[8] || (c[8] = [
                  te("Deploy / redeploy", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              W($e, {
                size: "sm",
                variant: "outline",
                onClick: c[1] || (c[1] = (u) => n.value = !n.value)
              }, {
                default: ae(() => [
                  te(re(n.value ? "Hide" : "Show") + " log", 1)
                ]),
                _: 1
              })
            ])
          ]),
          n.value ? (X(), ge("pre", Bg, re(C(t).deployLog ?? "Loading…"), 1)) : Ye("", !0),
          n.value && !C(t).deployLog ? (X(), at($e, {
            key: 1,
            class: "cmst:mt-2",
            size: "sm",
            variant: "ghost",
            onClick: C(t).loadLog
          }, {
            default: ae(() => [...c[9] || (c[9] = [
              te("Load deployment log", -1)
            ])]),
            _: 1
          }, 8, ["onClick"])) : Ye("", !0)
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          c[13] || (c[13] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared inventory", -1)),
          y("p", Hg, "Models: " + re(r.value) + " · Custom nodes: " + re(o.value), 1),
          y("div", Gg, [
            W($e, {
              size: "sm",
              variant: "outline",
              onClick: C(t).refreshRemoteInventoryNow
            }, {
              default: ae(() => [...c[10] || (c[10] = [
                te("Refresh remote inventory", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            W($e, {
              size: "sm",
              variant: "outline",
              onClick: C(t).rescanModelsNow
            }, {
              default: ae(() => [...c[11] || (c[11] = [
                te("Rescan models", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            W($e, {
              size: "sm",
              variant: "outline",
              onClick: C(t).refreshCustomNodesNow
            }, {
              default: ae(() => [...c[12] || (c[12] = [
                te("Refresh custom nodes", -1)
              ])]),
              _: 1
            }, 8, ["onClick"])
          ]),
          y("p", Zg, re(C(t).syncSummary ?? "Not loaded"), 1)
        ]),
        _: 1
      })
    ], 2));
  }
});
function eu(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return t.item ?? t.generation ?? t.experiment ?? e;
}
function et(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function Kg(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = et(s, "asset_id", "assetId"), r = () => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: et(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: et(s, "logical_key", "logicalKey"),
    thumbUrl: et(s, "thumb_url", "thumbnail_url") || r(),
    previewUrl: et(s, "preview_url", "data_saver_url") || r(),
    originalUrl: et(s, "original_url") || r(),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: et(s, "filename", "name")
  };
}
function Ba(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((r, o) => Kg(r, o));
  return {
    id: et(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: et(t, "status", "outcome") || "unknown",
    workflow: et(t, "workflow", "workflow_name"),
    workflowVersion: et(t, "workflow_version", "workflowVersion", "version_id"),
    preset: et(t, "preset", "preset_name"),
    prompt: et(t, "prompt", "positive_prompt"),
    startedAt: et(t, "started_at", "created_at") || null,
    completedAt: et(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: et(t, "note"),
    outputs: n,
    featuredOutput: n[0] ?? null,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    raw: t
  };
}
async function Jg(e = {}) {
  const t = new URLSearchParams(), s = { limit: 24, ...e };
  s.sort !== void 0 && (s.order = s.sort, delete s.sort), s.favorite_only !== void 0 && (s.favorite = s.favorite_only, delete s.favorite_only);
  for (const [n, r] of Object.entries(s))
    r !== void 0 && String(r) !== "" && t.set(n, String(r));
  return Ce(`/history-v2/feed?${t}`);
}
async function Qg(e) {
  return Ce(`/history-v2/generations/${encodeURIComponent(e)}`).then(eu);
}
async function Yg(e) {
  return Ce(`/history-v2/experiments/${encodeURIComponent(e)}`).then(eu);
}
async function Xg(e, t) {
  return Ce(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function ev(e, t) {
  return Ce(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function tv(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return Ce(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const js = Pc("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1 }), sv = /* @__PURE__ */ Xs("studio-history", () => {
  const e = /* @__PURE__ */ G([]), t = /* @__PURE__ */ G(null), s = /* @__PURE__ */ G(null), n = /* @__PURE__ */ G(js.read().query), r = /* @__PURE__ */ G(js.read().sort), o = /* @__PURE__ */ G(js.read().favoriteOnly), i = /* @__PURE__ */ G(null), a = /* @__PURE__ */ G(!1), l = /* @__PURE__ */ G(!1), c = /* @__PURE__ */ G(null), u = fr(), d = fr();
  let m = null;
  function h(_) {
    s.value = _, t.value = e.value.find((V) => V.id === _) ?? t.value;
  }
  function k(_) {
    n.value = _, js.write({ query: _, sort: r.value, favoriteOnly: o.value });
  }
  function w(_) {
    r.value = _, js.write({ query: n.value, sort: _, favoriteOnly: o.value });
  }
  function z(_) {
    o.value = _, js.write({ query: n.value, sort: r.value, favoriteOnly: _ });
  }
  async function N(_ = !1) {
    l.value = !0, c.value = null;
    try {
      const V = await u.run(async (ke) => {
        const Te = await Jg({ search: n.value, sort: r.value, favorite_only: o.value, cursor: _ ? i.value ?? void 0 : void 0 });
        return ke.aborted ? null : Te;
      });
      if (V.stale || !V.value) return;
      const ce = V.value, xe = (ce.items ?? ce.records ?? []).map(Ba);
      e.value = _ ? e.value.concat(xe) : xe, i.value = ce.next_cursor ?? null, a.value = ce.has_more === !0 || !!i.value, t.value && (t.value = e.value.find((ke) => ke.id === t.value?.id) ?? t.value);
    } catch (V) {
      c.value = V instanceof Error ? V.message : "Could not load History V2";
    } finally {
      l.value = !1;
    }
  }
  async function g(_, V = "generation") {
    try {
      const ce = await d.run(async (Te) => {
        const D = V === "experiment" ? await Yg(_) : await Qg(_);
        return Te.aborted ? null : D;
      });
      if (ce.stale || !ce.value) return;
      const xe = Ba(ce.value);
      t.value = xe;
      const ke = e.value.findIndex((Te) => Te.id === xe.id);
      ke >= 0 && (e.value[ke] = xe);
    } catch (ce) {
      c.value = ce instanceof Error ? ce.message : "Could not load History detail";
    }
  }
  async function E(_, V) {
    await Xg(_.id, V), _.favorite = V, gs("history");
  }
  async function P(_, V) {
    await ev(_.id, V), _.note = V, gs("history");
  }
  async function J(_) {
    await tv(_), e.value = e.value.filter((V) => V.id !== _.id), t.value?.id === _.id && (t.value = null), gs("history");
  }
  async function ve() {
    m || (m = Mr((_) => {
      _ === "history" && N();
    })), e.value.length || await N();
  }
  function oe() {
    e.value = [], t.value = null, s.value = null, i.value = null;
  }
  return { records: e, selected: t, focusId: s, query: n, sort: r, favoriteOnly: o, cursor: i, hasMore: a, loading: l, error: c, setFocus: h, setQuery: k, setSort: w, setFavoriteOnly: z, loadFeed: N, loadDetail: g, setFavorite: E, setNote: P, remove: J, initialize: ve, clear: oe };
}), nv = ["src", "alt"], rv = { class: "cmst:p-3 cmst:text-sm" }, ov = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, iv = { class: "cmst:truncate" }, av = { class: "cmst:text-xs cmst:opacity-70" }, lv = { class: "cmst:mt-1 cmst:truncate cmst:text-xs cmst:opacity-70" }, cv = /* @__PURE__ */ vt({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (X(), at(qe, {
      class: "cmst:overflow-hidden cmst:cursor-pointer",
      onClick: r[0] || (r[0] = (o) => s("select", e.record))
    }, {
      default: ae(() => [
        e.record.featuredOutput ? (X(), ge("img", {
          key: 0,
          src: e.record.featuredOutput.thumbUrl,
          alt: e.record.workflow || e.record.id,
          class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
          loading: "lazy"
        }, null, 8, nv)) : Ye("", !0),
        y("div", rv, [
          y("div", ov, [
            y("strong", iv, re(e.record.workflow || e.record.id), 1),
            y("span", av, re(e.record.status), 1)
          ]),
          y("p", lv, re(e.record.id), 1)
        ])
      ]),
      _: 1
    }));
  }
}), uv = {
  class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2 cmst:lg:grid-cols-3",
  "data-testid": "vue-history-grid"
}, dv = /* @__PURE__ */ vt({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (X(), ge("div", uv, [
      (X(!0), ge(ze, null, Ys(e.records, (o) => (X(), at(cv, {
        key: `${o.kind}:${o.id}`,
        record: o,
        onSelect: r[0] || (r[0] = (i) => s("select", i))
      }, null, 8, ["record"]))), 128))
    ]));
  }
}), fv = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, mv = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, pv = { class: "cmst:text-lg cmst:font-semibold" }, hv = { class: "cmst:text-xs cmst:opacity-70" }, gv = ["src", "alt"], vv = {
  key: 1,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, yv = /* @__PURE__ */ vt({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => e.record ? (X(), ge("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-testid": "vue-history-viewer",
      onClick: r[1] || (r[1] = xf((o) => s("close"), ["self"]))
    }, [
      y("div", fv, [
        y("div", mv, [
          y("div", null, [
            y("h2", pv, re(e.record.workflow || e.record.id), 1),
            y("p", hv, re(e.record.status) + " · " + re(e.record.kind), 1)
          ]),
          W($e, {
            variant: "outline",
            size: "sm",
            onClick: r[0] || (r[0] = (o) => s("close"))
          }, {
            default: ae(() => [...r[2] || (r[2] = [
              te("Close", -1)
            ])]),
            _: 1
          })
        ]),
        e.record.featuredOutput ? (X(), ge("img", {
          key: 0,
          src: e.record.featuredOutput.previewUrl,
          alt: e.record.workflow || e.record.id,
          class: "cmst:mt-4 cmst:mx-auto cmst:max-h-[70vh] cmst:max-w-full cmst:object-contain"
        }, null, 8, gv)) : (X(), ge("p", vv, "No projected image asset."))
      ])
    ])) : Ye("", !0);
  }
}), bv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, _v = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, wv = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, xv = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, kv = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, Sv = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Cv = /* @__PURE__ */ vt({
  __name: "HistoryView",
  setup(e) {
    const t = sv(), s = wc(), n = Dm(), r = /* @__PURE__ */ G(t.query), o = /* @__PURE__ */ G(!1);
    Qs(async () => {
      await t.initialize();
      const l = typeof s.query.focus == "string" ? s.query.focus : null;
      l && (t.setFocus(l), await t.loadDetail(l));
    });
    let i;
    es(r, (l) => {
      window.clearTimeout(i), i = window.setTimeout(() => {
        t.setQuery(l), t.loadFeed();
      }, 250);
    });
    async function a(l) {
      t.setFocus(l.id), await n.replace({ name: "history", query: { focus: l.id } }), await t.loadDetail(l.id, l.kind), o.value = !0;
    }
    return (l, c) => (X(), ge("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-history"
    }, [
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          y("div", bv, [
            y("div", null, [
              y("h2", _v, [
                W(C(kc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[8] || (c[8] = te("History V2", -1))
              ]),
              c[9] || (c[9] = y("p", { class: "cmst:text-sm cmst:opacity-80" }, "History V2 is the Vue production data source; the server cursor remains authoritative.", -1))
            ]),
            W($e, {
              variant: "outline",
              size: "icon",
              "aria-label": "Refresh history",
              disabled: C(t).loading,
              onClick: c[0] || (c[0] = (u) => C(t).loadFeed())
            }, {
              default: ae(() => [
                W(C(Pr), {
                  class: ft(["cmst:size-4", C(t).loading ? "cmst:animate-spin" : ""])
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          y("div", wv, [
            y("label", xv, [
              W(C(sp), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              }),
              Xt(y("input", {
                "onUpdate:modelValue": c[1] || (c[1] = (u) => r.value = u),
                class: "cmst:h-9 cmst:w-64 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search history",
                "data-testid": "vue-history-search"
              }, null, 512), [
                [Cn, r.value]
              ])
            ]),
            Xt(y("select", {
              "onUpdate:modelValue": c[2] || (c[2] = (u) => C(t).sort = u),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              onChange: c[3] || (c[3] = (u) => {
                C(t).setSort(C(t).sort), C(t).loadFeed();
              })
            }, [...c[10] || (c[10] = [
              y("option", { value: "newest" }, "Newest", -1),
              y("option", { value: "oldest" }, "Oldest", -1),
              y("option", { value: "fastest" }, "Fastest", -1),
              y("option", { value: "slowest" }, "Slowest", -1)
            ])], 544), [
              [ni, C(t).sort]
            ]),
            y("label", kv, [
              Xt(y("input", {
                "onUpdate:modelValue": c[4] || (c[4] = (u) => C(t).favoriteOnly = u),
                type: "checkbox",
                onChange: c[5] || (c[5] = (u) => {
                  C(t).setFavoriteOnly(C(t).favoriteOnly), C(t).loadFeed();
                })
              }, null, 544), [
                [yf, C(t).favoriteOnly]
              ]),
              c[11] || (c[11] = te(" Favorites", -1))
            ])
          ])
        ]),
        _: 1
      }),
      C(t).error ? (X(), ge("div", Sv, re(C(t).error), 1)) : Ye("", !0),
      C(t).loading && !C(t).records.length ? (X(), at(qe, {
        key: 1,
        class: "cmst:p-6 cmst:text-sm"
      }, {
        default: ae(() => [...c[12] || (c[12] = [
          te("Loading History V2…", -1)
        ])]),
        _: 1
      })) : C(t).records.length ? (X(), at(dv, {
        key: 3,
        records: C(t).records,
        onSelect: a
      }, null, 8, ["records"])) : (X(), at(qe, {
        key: 2,
        class: "cmst:p-6 cmst:text-sm cmst:opacity-75"
      }, {
        default: ae(() => [...c[13] || (c[13] = [
          te("No History V2 records match this query.", -1)
        ])]),
        _: 1
      })),
      C(t).hasMore ? (X(), at($e, {
        key: 4,
        variant: "outline",
        class: "cmst:self-center",
        onClick: c[6] || (c[6] = (u) => C(t).loadFeed(!0))
      }, {
        default: ae(() => [...c[14] || (c[14] = [
          te("Load more", -1)
        ])]),
        _: 1
      })) : Ye("", !0),
      o.value ? (X(), at(yv, {
        key: 5,
        record: C(t).selected,
        onClose: c[7] || (c[7] = (u) => o.value = !1)
      }, null, 8, ["record"])) : Ye("", !0)
    ], 2));
  }
}), Av = /* @__PURE__ */ Xs("studio-playground", () => {
  const e = /* @__PURE__ */ G("txt2img"), t = /* @__PURE__ */ G(!1);
  function s(r) {
    e.value = r;
  }
  function n(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: s, setExperimentMode: n };
}), Rv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Ev = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, Ov = ["checked"], Tv = { class: "cmst:text-sm cmst:opacity-80" }, Iv = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, Nv = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, Pv = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Mv = { key: 0 }, jv = /* @__PURE__ */ vt({
  __name: "PlaygroundView",
  setup(e) {
    const t = Av(), s = ai(), n = /* @__PURE__ */ G(null), r = Oe(() => n.value ? s.get(n.value)?.progress ?? null : null);
    function o() {
      if (n.value) return;
      const i = s.start({
        kind: "other",
        label: "Synthetic local proof operation",
        status: "running",
        progress: 0,
        message: "Counting to ten locally — no backend involved."
      });
      n.value = i;
      let a = 0;
      const l = setInterval(() => {
        if (a += 1, a >= 10) {
          clearInterval(l), s.finish(i, "Synthetic proof completed."), n.value = null;
          return;
        }
        s.patch(i, { progress: a / 10, message: `Local tick ${a}/10` });
      }, 150);
    }
    return (i, a) => (X(), ge("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-playground"
    }, [
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          y("h2", Rv, [
            W(C(xc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = te(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = y("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          y("label", Ev, [
            y("input", {
              type: "checkbox",
              checked: C(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => C(t).setExperimentMode(l.target.checked))
            }, null, 40, Ov),
            a[2] || (a[2] = te(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          a[5] || (a[5] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          y("p", Tv, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + re(C(s).active.length) + ". ", 1),
          y("div", Iv, [
            W($e, {
              variant: "default",
              size: "sm",
              disabled: n.value !== null,
              onClick: o
            }, {
              default: ae(() => [
                W(C(Ym), { "aria-hidden": "true" }),
                a[4] || (a[4] = te(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? (X(), ge("span", Nv, re(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : Ye("", !0)
          ]),
          y("ul", Pv, [
            (X(!0), ge(ze, null, Ys(C(s).all.slice(-5), (l) => (X(), ge("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              y("strong", null, re(l.label), 1),
              te(" — " + re(l.status), 1),
              l.message ? (X(), ge("span", Mv, " — " + re(l.message), 1)) : Ye("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), $v = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, zv = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, Dv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Vv = { class: "cmst:mt-3 cmst:text-sm" }, Lv = { key: 0 }, Fv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Uv = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Wv = ["value"], Bv = ["value"], Hv = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Gv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Zv = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, qv = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Kv = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-3" }, Jv = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, Qv = ["checked"], Yv = /* @__PURE__ */ vt({
  __name: "SettingsView",
  setup(e) {
    const t = jc(), s = /* @__PURE__ */ G(75), n = /* @__PURE__ */ G(""), r = /* @__PURE__ */ G("off"), o = Oe(() => t.config), i = Oe(() => o.value?.available_gpus ?? []);
    es(o, (d) => {
      d && (s.value = d.quality, n.value = d.save_folder);
    }, { immediate: !0 }), es(() => t.profileLevel, (d) => {
      r.value = d;
    }, { immediate: !0 });
    async function a() {
      await t.save({
        quality: Number(s.value),
        save_folder: n.value
      });
    }
    async function l(d) {
      const m = d.target.value;
      await t.save({ gpu: m });
    }
    async function c(d) {
      await t.save({ skip_plan_validation: d.target.checked });
    }
    async function u() {
      await t.setProfile(r.value);
    }
    return (d, m) => (X(), ge("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-settings"
    }, [
      C(t).error ? (X(), ge("div", $v, re(C(t).error), 1)) : Ye("", !0),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          y("div", zv, [
            y("div", null, [
              y("h2", Dv, [
                W(C(Cc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                m[3] || (m[3] = te(" Settings ", -1))
              ]),
              m[4] || (m[4] = y("p", { class: "cmst:text-sm cmst:opacity-80" }, " Server-backed Settings authority. Vue reads `/config` and projects proven output values one-way to legacy canvas consumers. ", -1))
            ]),
            W($e, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload settings",
              disabled: C(t).loading,
              onClick: C(t).load
            }, {
              default: ae(() => [
                W(C(Pr), {
                  class: ft(["cmst:size-4", C(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ]),
          y("p", Vv, [
            m[5] || (m[5] = te(" Active section: ", -1)),
            y("strong", null, re(C(t).activeSection), 1),
            C(t).config ? (X(), ge("span", Lv, " · server config loaded")) : Ye("", !0)
          ])
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          m[9] || (m[9] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Generation", -1)),
          y("div", Fv, [
            y("label", Uv, [
              m[6] || (m[6] = te(" GPU ", -1)),
              y("select", {
                value: o.value?.gpu ?? "",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-settings-gpu",
                onChange: l
              }, [
                (X(!0), ge(ze, null, Ys(i.value, (h) => (X(), ge("option", {
                  key: h.value,
                  value: h.value
                }, re(h.label), 9, Bv))), 128))
              ], 40, Wv)
            ]),
            y("label", Hv, [
              m[8] || (m[8] = te(" Profile/tracing level ", -1)),
              Xt(y("select", {
                "onUpdate:modelValue": m[0] || (m[0] = (h) => r.value = h),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: u
              }, [...m[7] || (m[7] = [
                y("option", { value: "off" }, "Off", -1),
                y("option", { value: "summary" }, "Summary", -1),
                y("option", { value: "detailed" }, "Detailed", -1),
                y("option", { value: "trace" }, "Trace", -1),
                y("option", { value: "trace_verbose" }, "Trace verbose", -1)
              ])], 544), [
                [ni, r.value]
              ])
            ])
          ])
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          m[13] || (m[13] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Outputs / Data Saver", -1)),
          y("div", Gv, [
            y("label", Zv, [
              m[10] || (m[10] = te(" Quality ", -1)),
              Xt(y("input", {
                "onUpdate:modelValue": m[1] || (m[1] = (h) => s.value = h),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [
                  Cn,
                  s.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            y("label", qv, [
              m[11] || (m[11] = te(" Save folder ", -1)),
              Xt(y("input", {
                "onUpdate:modelValue": m[2] || (m[2] = (h) => n.value = h),
                type: "text",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [Cn, n.value]
              ])
            ])
          ]),
          y("div", Kv, [
            W($e, {
              size: "sm",
              disabled: C(t).saving,
              "data-testid": "vue-settings-save-output",
              onClick: a
            }, {
              default: ae(() => [
                te(re(C(t).saving ? "Saving…" : "Save output settings"), 1)
              ]),
              _: 1
            }, 8, ["disabled"]),
            m[12] || (m[12] = y("span", { class: "cmst:text-xs cmst:opacity-70" }, "Server truth is reread after every save.", -1))
          ])
        ]),
        _: 1
      }),
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          m[15] || (m[15] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Advanced", -1)),
          y("label", Jv, [
            y("input", {
              type: "checkbox",
              checked: o.value?.skip_plan_validation ?? !1,
              onChange: c
            }, null, 40, Qv),
            m[14] || (m[14] = te(" Skip plan validation (preserves current backend semantics) ", -1))
          ]),
          m[16] || (m[16] = y("p", { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, "Execution mode remains server-owned and V2-only.", -1))
        ]),
        _: 1
      })
    ], 2));
  }
});
function pi(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return Object.prototype.hasOwnProperty.call(t, "workflow") ? t.workflow : Object.prototype.hasOwnProperty.call(t, "version") ? t.version : Object.prototype.hasOwnProperty.call(t, "mapping") ? t.mapping : e;
}
async function Xv(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.tag && t.set("tag", e.tag), e.folder && t.set("folder", e.folder), e.favorite && t.set("favorite", "1");
  const s = t.toString() ? `?${t}` : "";
  return Ce(`/studio/workflows${s}`);
}
async function ey(e) {
  return Ce(`/studio/workflows/${encodeURIComponent(e)}`).then((t) => ({ ...t, workflow: pi(t) }));
}
async function ty(e) {
  return Ce(`/studio/workflows/${encodeURIComponent(e)}/versions`);
}
async function sy(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}`).then((t) => pi(t));
}
async function ny(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`).then((t) => pi(t));
}
async function ry(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/candidates`);
}
async function oy(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/dependencies`);
}
async function iy(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`);
}
async function ay(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/portability`);
}
async function ly(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`);
}
async function cy(e, t) {
  return Ce(`/studio/workflows/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
function uy(e) {
  const t = String(e || "t2i").toLowerCase();
  return t === "txt2img" ? "t2i" : t;
}
const cs = ["feature-type", "required-bindings", "exposed-controls", "details"];
function Kn(e) {
  return {
    v: 1,
    workflowId: e.workflowId || "",
    versionId: e.versionId || "",
    step: e.step && cs.includes(e.step) ? e.step : "feature-type",
    featureType: e.featureType || "t2i",
    bindings: e.bindings || {},
    outputBinding: e.outputBinding || null,
    controls: Array.isArray(e.controls) ? e.controls.slice(0, 64) : [],
    details: e.details || {}
  };
}
function dy(e, t, s) {
  if (!e || e.length > 12e3) return null;
  try {
    const n = JSON.parse(e);
    return n.v !== 1 || n.workflowId !== t || n.versionId !== s ? null : Kn(n);
  } catch {
    return null;
  }
}
const uo = "comfymodal.studio.wizard.draft.v1", fy = /* @__PURE__ */ Xs("studio-workflows", () => {
  const e = /* @__PURE__ */ G([]), t = /* @__PURE__ */ G(null), s = /* @__PURE__ */ G(null), n = /* @__PURE__ */ G([]), r = /* @__PURE__ */ G(null), o = /* @__PURE__ */ G(null), i = /* @__PURE__ */ G(null), a = /* @__PURE__ */ G(null), l = /* @__PURE__ */ G(null), c = /* @__PURE__ */ G(null), u = /* @__PURE__ */ G([]), d = /* @__PURE__ */ G(""), m = /* @__PURE__ */ G(!1), h = /* @__PURE__ */ G(null), k = /* @__PURE__ */ G(!1), w = /* @__PURE__ */ G(null), z = fr();
  let N = null;
  function g(D) {
    t.value = D;
  }
  function E() {
    t.value = null, s.value = null, n.value = [], r.value = null;
  }
  async function P() {
    m.value = !0, h.value = null;
    try {
      const D = await Xv({ search: d.value });
      e.value = D.workflows ?? [];
    } catch (D) {
      throw h.value = D instanceof Error ? D.message : "Could not load workflows", D;
    } finally {
      m.value = !1;
    }
  }
  async function J() {
    N || (N = Mr((D) => {
      D === "workflows" && !m.value && P();
    })), e.value.length || await P();
  }
  async function ve(D) {
    t.value = D;
    const me = await z.run(async (fe) => {
      const [Pe, $] = await Promise.all([ey(D), ty(D)]);
      return fe.aborted ? null : { workflowResponse: Pe, versionsResponse: $ };
    });
    if (me.stale || !me.value) return;
    s.value = me.value.workflowResponse.workflow ?? null, n.value = me.value.versionsResponse.versions ?? [];
    const ne = s.value?.latest_version_id, q = n.value.find((fe) => fe.workflow_version_id === ne) ?? n.value.at(-1) ?? null;
    q && await oe(q.workflow_version_id);
  }
  async function oe(D) {
    const me = await z.run(async (q) => {
      const [fe, Pe, $, nt, Ue, wt] = await Promise.all([
        sy(D),
        ny(D),
        oy(D),
        iy(D),
        ay(D),
        ly(D)
      ]);
      return q.aborted ? null : { versionResponse: fe, mappingResponse: Pe, dependencyResponse: $, compatibilityResponse: nt, portabilityResponse: Ue, presetsResponse: wt };
    });
    if (me.stale || !me.value) return;
    r.value = me.value.versionResponse, o.value = me.value.mappingResponse, i.value = null, a.value = me.value.dependencyResponse, l.value = me.value.compatibilityResponse, c.value = me.value.portabilityResponse;
    const ne = me.value.presetsResponse;
    u.value = ne.presets ?? [];
  }
  async function _() {
    r.value && (i.value = await ry(r.value.workflow_version_id));
  }
  function V() {
    const D = s.value?.workflow_id ?? "", me = r.value?.workflow_version_id ?? "";
    try {
      w.value = dy(sessionStorage.getItem(uo), D, me) ?? Kn({ workflowId: D, versionId: me, featureType: uy(s.value?.workflow_type) });
    } catch {
      w.value = Kn({ workflowId: D, versionId: me });
    }
    k.value = !0;
  }
  function ce(D) {
    if (w.value) {
      w.value = Kn({ ...w.value, ...D });
      try {
        sessionStorage.setItem(uo, JSON.stringify(w.value));
      } catch {
      }
    }
  }
  function xe(D) {
    ce({ step: D });
  }
  function ke() {
    k.value = !1, w.value = null;
    try {
      sessionStorage.removeItem(uo);
    } catch {
    }
  }
  async function Te(D) {
    t.value && (await cy(t.value, D), await P(), await ve(t.value), gs("workflows"));
  }
  return {
    workflows: e,
    selectedId: t,
    selectedWorkflow: s,
    versions: n,
    selectedVersion: r,
    mapping: o,
    mappingCandidates: i,
    dependencies: a,
    compatibility: l,
    portability: c,
    presets: u,
    query: d,
    loading: m,
    error: h,
    wizardOpen: k,
    wizardDraft: w,
    select: g,
    clear: E,
    loadList: P,
    initialize: J,
    selectWorkflow: ve,
    selectVersion: oe,
    loadMappingCandidates: _,
    openWizard: V,
    updateWizard: ce,
    setWizardStep: xe,
    closeWizard: ke,
    updateMetadata: Te
  };
}), my = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, py = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, hy = { class: "cmst:flex cmst:gap-2" }, gy = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, vy = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, yy = ["data-testid", "onClick"], by = { class: "cmst:block cmst:text-xs cmst:opacity-70" }, _y = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70"
}, wy = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, xy = { class: "cmst:text-base cmst:font-semibold" }, ky = { class: "cmst:text-xs cmst:opacity-70" }, Sy = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, Cy = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Ay = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Ry = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Ey = { class: "cmst:mt-3 cmst:text-sm" }, Oy = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, Ty = {
  key: 2,
  class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
  "data-testid": "vue-workflow-wizard"
}, Iy = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Ny = { class: "cmst:text-xs cmst:opacity-70" }, Py = { class: "cmst:mt-5 cmst:rounded-md cmst:bg-cmst-bg cmst:p-4" }, My = ["value"], jy = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, $y = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs"
}, zy = { class: "cmst:mt-4 cmst:flex cmst:justify-between" }, Dy = /* @__PURE__ */ vt({
  __name: "WorkflowsView",
  setup(e) {
    const t = fy(), s = ui(), n = /* @__PURE__ */ G(""), r = /* @__PURE__ */ G("workflows"), o = /* @__PURE__ */ G(""), i = /* @__PURE__ */ G(""), a = /* @__PURE__ */ G(""), l = Oe(() => Math.max(0, cs.indexOf(t.wizardDraft?.step ?? "feature-type"))), c = Oe(() => cs[l.value]);
    Qs(async () => {
      await Promise.all([t.initialize(), s.initialize()]);
    });
    async function u() {
      t.query = n.value, await t.loadList();
    }
    async function d(N) {
      o.value = N, await t.selectWorkflow(N);
    }
    function m() {
      t.openWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!0);
    }
    function h() {
      window.__comfymodalCancelStudioGraphBinding?.(), t.closeWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
    }
    async function k() {
      if (!i.value.trim()) return;
      const N = i.value.trim();
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = "Click a node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "prompt",
          label: "prompt",
          allowOutput: !1,
          onCapture: (g) => {
            t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { ...g, confirmed: !0 } } }), a.value = `Confirmed ${String(g.nodeTitle ?? g.nodeId ?? "graph target")}`;
          },
          onCancel: (g) => {
            a.value = g;
          }
        });
        return;
      }
      t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { target: N, confirmed: !0 } } }), a.value = `Confirmed graph target ${N}`;
    }
    function w() {
      const N = cs[Math.min(cs.length - 1, l.value + 1)];
      t.setWizardStep(N);
    }
    function z() {
      const N = cs[Math.max(0, l.value - 1)];
      t.setWizardStep(N);
    }
    return (N, g) => (X(), ge("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-workflows"
    }, [
      W(qe, { class: "cmst:p-4" }, {
        default: ae(() => [
          y("div", my, [
            y("div", null, [
              y("h2", py, [
                W(C(Oo), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                g[5] || (g[5] = te("Workflows & Models", -1))
              ]),
              g[6] || (g[6] = y("p", { class: "cmst:text-sm cmst:opacity-80" }, "Workflow/version state and shared infrastructure inventory remain separate authorities.", -1))
            ]),
            y("div", hy, [
              W($e, {
                variant: r.value === "workflows" ? "default" : "outline",
                size: "sm",
                onClick: g[0] || (g[0] = (E) => r.value = "workflows")
              }, {
                default: ae(() => [
                  W(C(Oo), { class: "cmst:size-4" }),
                  g[7] || (g[7] = te("Workflows", -1))
                ]),
                _: 1
              }, 8, ["variant"]),
              W($e, {
                variant: r.value === "models" ? "default" : "outline",
                size: "sm",
                onClick: g[1] || (g[1] = (E) => r.value = "models")
              }, {
                default: ae(() => [
                  W(C(Gm), { class: "cmst:size-4" }),
                  g[8] || (g[8] = te("Models / Nodes", -1))
                ]),
                _: 1
              }, 8, ["variant"])
            ])
          ])
        ]),
        _: 1
      }),
      r.value === "workflows" ? (X(), ge(ze, { key: 0 }, [
        W(qe, { class: "cmst:p-4" }, {
          default: ae(() => [
            y("div", gy, [
              Xt(y("input", {
                "onUpdate:modelValue": g[2] || (g[2] = (E) => n.value = E),
                class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search workflows",
                onKeyup: Sf(u, ["enter"])
              }, null, 544), [
                [Cn, n.value]
              ]),
              W($e, {
                size: "sm",
                variant: "secondary",
                onClick: u
              }, {
                default: ae(() => [...g[9] || (g[9] = [
                  te("Search", -1)
                ])]),
                _: 1
              }),
              W($e, {
                size: "sm",
                variant: "outline",
                onClick: C(t).loadList
              }, {
                default: ae(() => [
                  W(C(Pr), { class: "cmst:size-4" })
                ]),
                _: 1
              }, 8, ["onClick"])
            ]),
            y("div", vy, [
              (X(!0), ge(ze, null, Ys(C(t).workflows, (E) => (X(), ge("button", {
                key: E.workflow_id,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-workflow-${E.workflow_id}`,
                onClick: (P) => d(E.workflow_id)
              }, [
                y("strong", null, re(E.name || E.workflow_id), 1),
                y("span", by, re(E.folder || "No folder") + " · " + re(E.latest_version_id || "No version"), 1)
              ], 8, yy))), 128))
            ]),
            C(t).workflows.length ? Ye("", !0) : (X(), ge("p", _y, "No workflows returned by the server."))
          ]),
          _: 1
        }),
        C(t).selectedWorkflow ? (X(), at(qe, {
          key: 0,
          class: "cmst:p-4"
        }, {
          default: ae(() => [
            y("div", wy, [
              y("div", null, [
                y("h3", xy, re(C(t).selectedWorkflow.name), 1),
                y("p", ky, "Version " + re(C(t).selectedVersion?.version ?? C(t).selectedVersion?.workflow_version_id), 1)
              ]),
              W($e, {
                size: "sm",
                onClick: m
              }, {
                default: ae(() => [
                  W(C(ip), { class: "cmst:size-4" }),
                  g[10] || (g[10] = te("Setup wizard", -1))
                ]),
                _: 1
              })
            ]),
            y("div", Sy, [
              y("div", Cy, [
                g[11] || (g[11] = te("Mapping", -1)),
                g[12] || (g[12] = y("br", null, null, -1)),
                y("strong", null, re(C(t).mapping ? "configured" : "not configured"), 1)
              ]),
              y("div", Ay, [
                g[13] || (g[13] = te("Dependencies", -1)),
                g[14] || (g[14] = y("br", null, null, -1)),
                y("strong", null, re(C(t).dependencies ? "loaded" : "not loaded"), 1)
              ]),
              y("div", Ry, [
                g[15] || (g[15] = te("Portability", -1)),
                g[16] || (g[16] = y("br", null, null, -1)),
                y("strong", null, re(C(t).portability ? "analyzed" : "not analyzed"), 1)
              ])
            ])
          ]),
          _: 1
        })) : Ye("", !0)
      ], 64)) : (X(), at(qe, {
        key: 1,
        class: "cmst:p-4"
      }, {
        default: ae(() => [
          g[19] || (g[19] = y("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared model inventory", -1)),
          g[20] || (g[20] = y("p", { class: "cmst:mt-1 cmst:text-sm cmst:opacity-70" }, "Owned by infrastructureStore; workflow dependencies reference this state.", -1)),
          y("div", Ey, "Models: " + re(C(s).models.length) + " · Custom nodes: " + re(C(s).customNodes.length), 1),
          y("div", Oy, [
            W($e, {
              size: "sm",
              variant: "outline",
              onClick: C(s).rescanModelsNow
            }, {
              default: ae(() => [...g[17] || (g[17] = [
                te("Rescan models", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            W($e, {
              size: "sm",
              variant: "outline",
              onClick: C(s).refreshCustomNodesNow
            }, {
              default: ae(() => [...g[18] || (g[18] = [
                te("Refresh nodes", -1)
              ])]),
              _: 1
            }, 8, ["onClick"])
          ])
        ]),
        _: 1
      })),
      C(t).wizardOpen ? (X(), ge("div", Ty, [
        W(qe, { class: "cmst:w-[min(42rem,94vw)] cmst:p-5" }, {
          default: ae(() => [
            y("div", Iy, [
              y("div", null, [
                g[21] || (g[21] = y("h2", { class: "cmst:text-lg cmst:font-semibold" }, "Setup workflow", -1)),
                y("p", Ny, "Step " + re(l.value + 1) + " of " + re(C(cs).length) + " · " + re(c.value), 1)
              ]),
              W($e, {
                variant: "ghost",
                size: "sm",
                onClick: h
              }, {
                default: ae(() => [...g[22] || (g[22] = [
                  te("Close", -1)
                ])]),
                _: 1
              })
            ]),
            y("div", Py, [
              c.value === "feature-type" ? (X(), ge(ze, { key: 0 }, [
                g[24] || (g[24] = y("h3", { class: "cmst:font-semibold" }, "Feature Type", -1)),
                g[25] || (g[25] = y("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Feature type is explicit and provider-neutral.", -1)),
                y("select", {
                  class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  value: C(t).wizardDraft?.featureType,
                  onChange: g[3] || (g[3] = (E) => C(t).updateWizard({ featureType: E.target.value }))
                }, [...g[23] || (g[23] = [
                  y("option", { value: "t2i" }, "Text to Image", -1),
                  y("option", { value: "i2i" }, "Image to Image", -1),
                  y("option", { value: "inpaint" }, "Inpaint", -1),
                  y("option", { value: "sketch" }, "Sketch", -1),
                  y("option", { value: "outpaint" }, "Outpaint", -1)
                ])], 40, My)
              ], 64)) : c.value === "required-bindings" ? (X(), ge(ze, { key: 1 }, [
                g[27] || (g[27] = y("h3", { class: "cmst:font-semibold" }, "Required Bindings", -1)),
                g[28] || (g[28] = y("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Graph binding is explicit: underlying ComfyUI graph interaction is enabled while this step is active.", -1)),
                y("div", jy, [
                  Xt(y("input", {
                    "onUpdate:modelValue": g[4] || (g[4] = (E) => i.value = E),
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                    placeholder: "Node/widget target"
                  }, null, 512), [
                    [Cn, i.value]
                  ]),
                  W($e, {
                    size: "sm",
                    onClick: k
                  }, {
                    default: ae(() => [...g[26] || (g[26] = [
                      te("Confirm binding", -1)
                    ])]),
                    _: 1
                  })
                ]),
                a.value ? (X(), ge("p", $y, re(a.value), 1)) : Ye("", !0)
              ], 64)) : c.value === "exposed-controls" ? (X(), ge(ze, { key: 2 }, [
                g[29] || (g[29] = y("h3", { class: "cmst:font-semibold" }, "Exposed Controls", -1)),
                g[30] || (g[30] = y("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Control selection is stored in the bounded session draft.", -1))
              ], 64)) : (X(), ge(ze, { key: 3 }, [
                g[31] || (g[31] = y("h3", { class: "cmst:font-semibold" }, "Details", -1)),
                g[32] || (g[32] = y("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Review the explicit bindings before saving the version mapping.", -1))
              ], 64))
            ]),
            y("div", zy, [
              W($e, {
                variant: "outline",
                size: "sm",
                disabled: l.value === 0,
                onClick: z
              }, {
                default: ae(() => [...g[33] || (g[33] = [
                  te("Back", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              W($e, {
                size: "sm",
                disabled: l.value === C(cs).length - 1,
                onClick: w
              }, {
                default: ae(() => [...g[34] || (g[34] = [
                  te("Next", -1)
                ])]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          _: 1
        })
      ])) : Ye("", !0)
    ], 2));
  }
}), Vy = {
  playground: jv,
  history: Cv,
  workflows: Dy,
  backend: qg,
  settings: Yv
};
function Ly(e = {}) {
  let t;
  return e.memory || !e.win ? t = vm() : t = Eg(e.win, e.initial), zm({
    history: t,
    routes: ii.map((n) => ({
      path: `/${n}`,
      name: n,
      component: Vy[n]
    }))
  });
}
function Fy(e, t = {}) {
  const s = Tf(), n = Ly({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = Rf(Ag);
  return r.use(s), r.use(n), r.mount(e), {
    app: r,
    router: n,
    pinia: s,
    unmount: () => {
      r.unmount();
    }
  };
}
export {
  Fy as mountStudioPreview
};

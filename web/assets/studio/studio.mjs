/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function zo(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const Ne = {}, As = [], zt = () => {
}, Ba = () => !1, pr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), hr = (e) => e.startsWith("onUpdate:"), Qe = Object.assign, Do = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, Xc = Object.prototype.hasOwnProperty, Se = (e, t) => Xc.call(e, t), K = Array.isArray, ms = (e) => Tn(e) === "[object Map]", ts = (e) => Tn(e) === "[object Set]", yi = (e) => Tn(e) === "[object Date]", ue = (e) => typeof e == "function", De = (e) => typeof e == "string", gt = (e) => typeof e == "symbol", Ae = (e) => e !== null && typeof e == "object", Ha = (e) => (Ae(e) || ue(e)) && ue(e.then) && ue(e.catch), Za = Object.prototype.toString, Tn = (e) => Za.call(e), eu = (e) => Tn(e).slice(8, -1), Ga = (e) => Tn(e) === "[object Object]", gr = (e) => De(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, un = /* @__PURE__ */ zo(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), yr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, tu = /-\w/g, lt = yr(
  (e) => e.replace(tu, (t) => t.slice(1).toUpperCase())
), su = /\B([A-Z])/g, bs = yr(
  (e) => e.replace(su, "-$1").toLowerCase()
), vr = yr((e) => e.charAt(0).toUpperCase() + e.slice(1)), Mr = yr(
  (e) => e ? `on${vr(e)}` : ""
), $t = (e, t) => !Object.is(e, t), Zn = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, qa = (e, t, s, n = !1) => {
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
let vi;
const _r = () => vi || (vi = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Vo(e) {
  if (K(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = De(n) ? iu(n) : Vo(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (De(e) || Ae(e))
    return e;
}
const nu = /;(?![^(]*\))/g, ru = /:([^]+)/, ou = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function iu(e) {
  const t = {};
  return e.replace(ou, (s) => s.startsWith("/*") ? "" : s).split(nu).forEach((s) => {
    if (s) {
      const n = s.split(ru);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function ft(e) {
  let t = "";
  if (De(e))
    t = e;
  else if (K(e))
    for (let s = 0; s < e.length; s++) {
      const n = ft(e[s]);
      n && (t += n + " ");
    }
  else if (Ae(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const au = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", lu = /* @__PURE__ */ zo(au);
function Ka(e) {
  return !!e || e === "";
}
function cu(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = ss(e[r], t[r], s);
  return n;
}
function bi(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < n.length; a++)
      if (!r[a] && ss(o, n[a], s)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function uu(e, t, s) {
  let n = ms(e), r = ms(t);
  if (n || r || (n = ts(e), r = ts(t), n || r))
    return n && r ? bi(e, t, s) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !ss(e[a], t[a], s))
      return !1;
  }
  return String(e) === String(t);
}
function _i(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = n(e, t, s);
  return r.delete(e), o.delete(t), i;
}
function ss(e, t, s) {
  if (e === t) return !0;
  let n = yi(e), r = yi(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = gt(e), r = gt(t), n || r ? e === t : (n = K(e), r = K(t), n || r ? n && r ? _i(e, t, s, cu) : !1 : (n = Ae(e), r = Ae(t), n || r ? !n || !r ? !1 : _i(e, t, s, uu) : String(e) === String(t))));
}
function Lo(e, t) {
  return e.findIndex((s) => ss(s, t));
}
const Ja = (e) => !!(e && e.__v_isRef === !0), re = (e) => De(e) ? e : e == null ? "" : K(e) || Ae(e) && (e.toString === Za || !ue(e.toString)) ? Ja(e) ? re(e.value) : JSON.stringify(e, Ya, 2) : String(e), Ya = (e, t) => Ja(t) ? Ya(e, t.value) : ms(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[$r(n, o) + " =>"] = r, s),
    {}
  )
} : ts(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => $r(s))
} : gt(t) ? $r(t) : Ae(t) && !K(t) && !Ga(t) ? String(t) : t, $r = (e, t = "") => {
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
let He;
class Qa {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && He && (He.active ? (this.parent = He, this.index = (He.scopes || (He.scopes = [])).push(
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
      const s = He;
      try {
        return He = this, t();
      } finally {
        He = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = He, He = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (He === this)
        He = this.prevScope;
      else {
        let t = He;
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
function Xa(e) {
  return new Qa(e);
}
function Fo() {
  return He;
}
function el(e, t = !1) {
  He && He.cleanups.push(e);
}
let Pe;
const jr = /* @__PURE__ */ new WeakSet();
class tl {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, He && (He.active ? He.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, jr.has(this) && (jr.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || nl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, xi(this), rl(this);
    const t = Pe, s = kt;
    Pe = this, kt = !0;
    try {
      return this.fn();
    } finally {
      ol(this), Pe = t, kt = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        Bo(t);
      this.deps = this.depsTail = void 0, xi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? jr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    uo(this) && this.run();
  }
  get dirty() {
    return uo(this);
  }
}
let sl = 0, dn, fn;
function nl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = fn, fn = e;
    return;
  }
  e.next = dn, dn = e;
}
function Uo() {
  sl++;
}
function Wo() {
  if (--sl > 0)
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
function rl(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function ol(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), Bo(n), du(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function uo(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (il(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function il(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === vn) || (e.globalVersion = vn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !uo(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = Pe, n = kt;
  Pe = e, kt = !0;
  try {
    rl(e);
    const r = e.fn(e._value);
    (t.version === 0 || $t(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Pe = s, kt = n, ol(e), e.flags &= -3;
  }
}
function Bo(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      Bo(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function du(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let kt = !0;
const al = [];
function Lt() {
  al.push(kt), kt = !1;
}
function Ft() {
  const e = al.pop();
  kt = e === void 0 ? !0 : e;
}
function xi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = Pe;
    Pe = void 0;
    try {
      t();
    } finally {
      Pe = s;
    }
  }
}
let vn = 0;
class fu {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Ho {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!Pe || !kt || Pe === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== Pe)
      s = this.activeLink = new fu(Pe, this), Pe.deps ? (s.prevDep = Pe.depsTail, Pe.depsTail.nextDep = s, Pe.depsTail = s) : Pe.deps = Pe.depsTail = s, ll(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = Pe.depsTail, s.nextDep = void 0, Pe.depsTail.nextDep = s, Pe.depsTail = s, Pe.deps === s && (Pe.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, vn++, this.notify(t);
  }
  notify(t) {
    Uo();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      Wo();
    }
  }
}
function ll(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        ll(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const Jn = /* @__PURE__ */ new WeakMap(), Es = /* @__PURE__ */ Symbol(
  ""
), fo = /* @__PURE__ */ Symbol(
  ""
), bn = /* @__PURE__ */ Symbol(
  ""
);
function et(e, t, s) {
  if (kt && Pe) {
    let n = Jn.get(e);
    n || Jn.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new Ho()), r.map = n, r.key = s), r.track();
  }
}
function Jt(e, t, s, n, r, o) {
  const i = Jn.get(e);
  if (!i) {
    vn++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (Uo(), t === "clear")
    i.forEach(a);
  else {
    const l = K(e), c = l && gr(s);
    if (l && s === "length") {
      const u = Number(n);
      i.forEach((d, m) => {
        (m === "length" || m === bn || !gt(m) && m >= u) && a(d);
      });
    } else
      switch ((s !== void 0 || i.has(void 0)) && a(i.get(s)), c && a(i.get(bn)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(Es)), ms(e) && a(i.get(fo)));
          break;
        case "delete":
          l || (a(i.get(Es)), ms(e) && a(i.get(fo)));
          break;
        case "set":
          ms(e) && a(i.get(Es));
          break;
      }
  }
  Wo();
}
function mu(e, t) {
  const s = Jn.get(e);
  return s && s.get(t);
}
function Ps(e) {
  const t = /* @__PURE__ */ xe(e);
  return t === e || (et(t, "iterate", bn), /* @__PURE__ */ ht(e)) ? t : /* @__PURE__ */ Ut(e) ? /* @__PURE__ */ Dt(e) ? t.map((s) => gs(vt(s))) : t.map(gs) : t.map(vt);
}
function xr(e) {
  return et(e = /* @__PURE__ */ xe(e), "iterate", bn), e;
}
function Nt(e, t) {
  return /* @__PURE__ */ Ut(e) ? gs(/* @__PURE__ */ Dt(e) ? vt(t) : t) : vt(t);
}
const pu = {
  __proto__: null,
  [Symbol.iterator]() {
    return zr(this, Symbol.iterator, (e) => Nt(this, e));
  },
  concat(...e) {
    return Ps(this).concat(
      ...e.map((t) => K(t) ? Ps(t) : t)
    );
  },
  entries() {
    return zr(this, "entries", (e) => (e[1] = Nt(this, e[1]), e));
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
      (s) => s.map((n) => Nt(this, n)),
      arguments
    );
  },
  find(e, t) {
    return Ht(
      this,
      "find",
      e,
      t,
      (s) => Nt(this, s),
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
      (s) => Nt(this, s),
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
    return Dr(this, "includes", e);
  },
  indexOf(...e) {
    return Dr(this, "indexOf", e);
  },
  join(e) {
    return Ps(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return Dr(this, "lastIndexOf", e);
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
    return ki(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return ki(this, "reduceRight", e, t);
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
    return zr(this, "values", (e) => Nt(this, e));
  }
};
function zr(e, t, s) {
  const n = xr(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ ht(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => wi(o.next(), s), r !== cl[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => wi(o._next(), s);
  }
  return o;
}
function wi(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const cl = Array.prototype;
function Ht(e, t, s, n, r, o) {
  const i = xr(e), a = i !== e && !/* @__PURE__ */ ht(e), l = i[t];
  if (l !== cl[t]) {
    const d = l.apply(e, o);
    return a ? vt(d) : d;
  }
  let c = s;
  i !== e && (a ? c = function(d, m) {
    return s.call(this, Nt(e, d), m, e);
  } : s.length > 2 && (c = function(d, m) {
    return s.call(this, d, m, e);
  }));
  const u = l.call(i, c, n);
  return a && r ? r(u) : u;
}
function ki(e, t, s, n) {
  const r = xr(e), o = r !== e && !/* @__PURE__ */ ht(e);
  let i = s, a = !1;
  r !== e && (o ? (a = n.length === 0, i = function(c, u, d) {
    return a && (a = !1, c = Nt(e, c)), s.call(this, c, Nt(e, u), d, e);
  }) : s.length > 3 && (i = function(c, u, d) {
    return s.call(this, c, u, d, e);
  }));
  const l = r[t](i, ...n);
  return a ? Nt(e, l) : l;
}
function Dr(e, t, s) {
  const n = /* @__PURE__ */ xe(e);
  et(n, "iterate", bn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ wr(s[0]) ? (s[0] = /* @__PURE__ */ xe(s[0]), n[t](...s)) : r;
}
function tn(e, t, s = []) {
  Lt(), Uo();
  const n = (/* @__PURE__ */ xe(e))[t].apply(e, s);
  return Wo(), Ft(), n;
}
const hu = /* @__PURE__ */ zo("__proto__,__v_isRef,__isVue"), ul = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(gt)
);
function gu(e) {
  gt(e) || (e = String(e));
  const t = /* @__PURE__ */ xe(this);
  return et(t, "has", e), t.hasOwnProperty(e);
}
class dl {
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
      return n === (r ? o ? Au : hl : o ? pl : ml).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const i = K(t);
    if (!r) {
      let l;
      if (i && (l = pu[s]))
        return l;
      if (s === "hasOwnProperty")
        return gu;
    }
    const a = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ Le(t) ? t : n
    );
    if ((gt(s) ? ul.has(s) : hu(s)) || (r || et(t, "get", s), o))
      return a;
    if (/* @__PURE__ */ Le(a)) {
      const l = i && gr(s) ? a : a.value;
      return r && Ae(l) ? /* @__PURE__ */ po(l) : l;
    }
    return Ae(a) ? r ? /* @__PURE__ */ po(a) : /* @__PURE__ */ In(a) : a;
  }
}
class fl extends dl {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const i = K(t) && gr(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ Ut(o);
      if (!/* @__PURE__ */ ht(n) && !/* @__PURE__ */ Ut(n) && (o = /* @__PURE__ */ xe(o), n = /* @__PURE__ */ xe(n)), !i && /* @__PURE__ */ Le(o) && !/* @__PURE__ */ Le(n))
        return c || (o.value = n), !0;
    }
    const a = i ? Number(s) < t.length : Se(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ Le(t) ? t : r
    );
    return t === /* @__PURE__ */ xe(r) && l && (a ? $t(n, o) && Jt(t, "set", s, n) : Jt(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = Se(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && Jt(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!gt(s) || !ul.has(s)) && et(t, "has", s), n;
  }
  ownKeys(t) {
    return et(
      t,
      "iterate",
      K(t) ? "length" : Es
    ), Reflect.ownKeys(t);
  }
}
class yu extends dl {
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
const vu = /* @__PURE__ */ new fl(), bu = /* @__PURE__ */ new yu(), _u = /* @__PURE__ */ new fl(!0);
const mo = (e) => e, $n = (e) => Reflect.getPrototypeOf(e);
function xu(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ xe(r), i = ms(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...n), u = s ? mo : t ? gs : vt;
    return !t && et(
      o,
      "iterate",
      l ? fo : Es
    ), Qe(
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
function jn(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function wu(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ xe(o), a = /* @__PURE__ */ xe(r);
      e || ($t(r, a) && et(i, "get", r), et(i, "get", a));
      const { has: l } = $n(i), c = t ? mo : e ? gs : vt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && et(/* @__PURE__ */ xe(r), "iterate", Es), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ xe(o), a = /* @__PURE__ */ xe(r);
      return e || ($t(r, a) && et(i, "has", r), et(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ xe(a), c = t ? mo : e ? gs : vt;
      return !e && et(l, "iterate", Es), a.forEach((u, d) => r.call(o, c(u), c(d), i));
    }
  };
  return Qe(
    s,
    e ? {
      add: jn("add"),
      set: jn("set"),
      delete: jn("delete"),
      clear: jn("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ xe(this), i = $n(o), a = /* @__PURE__ */ xe(r), l = !t && !/* @__PURE__ */ ht(r) && !/* @__PURE__ */ Ut(r) ? a : r;
        return i.has.call(o, l) || $t(r, l) && i.has.call(o, r) || $t(a, l) && i.has.call(o, a) || (o.add(l), Jt(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ ht(o) && !/* @__PURE__ */ Ut(o) && (o = /* @__PURE__ */ xe(o));
        const i = /* @__PURE__ */ xe(this), { has: a, get: l } = $n(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ xe(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? $t(o, u) && Jt(i, "set", r, o) : Jt(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ xe(this), { has: i, get: a } = $n(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ xe(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && Jt(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ xe(this), o = r.size !== 0, i = r.clear();
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
    s[r] = xu(r, e, t);
  }), s;
}
function Zo(e, t) {
  const s = wu(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    Se(s, r) && r in n ? s : n,
    r,
    o
  );
}
const ku = {
  get: /* @__PURE__ */ Zo(!1, !1)
}, Su = {
  get: /* @__PURE__ */ Zo(!1, !0)
}, Cu = {
  get: /* @__PURE__ */ Zo(!0, !1)
};
const ml = /* @__PURE__ */ new WeakMap(), pl = /* @__PURE__ */ new WeakMap(), hl = /* @__PURE__ */ new WeakMap(), Au = /* @__PURE__ */ new WeakMap();
function Ru(e) {
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
  return /* @__PURE__ */ Ut(e) ? e : Go(
    e,
    !1,
    vu,
    ku,
    ml
  );
}
// @__NO_SIDE_EFFECTS__
function gl(e) {
  return Go(
    e,
    !1,
    _u,
    Su,
    pl
  );
}
// @__NO_SIDE_EFFECTS__
function po(e) {
  return Go(
    e,
    !0,
    bu,
    Cu,
    hl
  );
}
function Go(e, t, s, n, r) {
  if (!Ae(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = Ru(eu(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? n : s
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Dt(e) {
  return /* @__PURE__ */ Ut(e) ? /* @__PURE__ */ Dt(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function Ut(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function ht(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function wr(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function xe(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ xe(t) : e;
}
function qo(e) {
  return !Se(e, "__v_skip") && Object.isExtensible(e) && qa(e, "__v_skip", !0), e;
}
const vt = (e) => Ae(e) ? /* @__PURE__ */ In(e) : e, gs = (e) => Ae(e) ? /* @__PURE__ */ po(e) : e;
// @__NO_SIDE_EFFECTS__
function Le(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function Z(e) {
  return yl(e, !1);
}
// @__NO_SIDE_EFFECTS__
function mn(e) {
  return yl(e, !0);
}
function yl(e, t) {
  return /* @__PURE__ */ Le(e) ? e : new Eu(e, t);
}
class Eu {
  constructor(t, s) {
    this.dep = new Ho(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ xe(t), this._value = s ? t : vt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ ht(t) || /* @__PURE__ */ Ut(t);
    t = n ? t : /* @__PURE__ */ xe(t), $t(t, s) && (this._rawValue = t, this._value = n ? t : vt(t), this.dep.trigger());
  }
}
function C(e) {
  return /* @__PURE__ */ Le(e) ? e.value : e;
}
function Vs(e) {
  return ue(e) ? e() : C(e);
}
const Ou = {
  get: (e, t, s) => t === "__v_raw" ? e : C(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ Le(r) && !/* @__PURE__ */ Le(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function vl(e) {
  return /* @__PURE__ */ Dt(e) ? e : new Proxy(e, Ou);
}
// @__NO_SIDE_EFFECTS__
function Tu(e) {
  const t = K(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = Nu(e, s);
  return t;
}
class Iu {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = gt(s) ? s : String(s), this._raw = /* @__PURE__ */ xe(t);
    let r = !0, o = t;
    if (!K(t) || gt(this._key) || !gr(this._key))
      do
        r = !/* @__PURE__ */ wr(o) || /* @__PURE__ */ ht(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = C(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ Le(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ Le(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return mu(this._raw, this._key);
  }
}
function Nu(e, t, s) {
  return new Iu(e, t, s);
}
class Pu {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new Ho(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = vn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Pe !== this)
      return nl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return il(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function Mu(e, t, s = !1) {
  let n, r;
  return ue(e) ? n = e : (n = e.get, r = e.set), new Pu(n, r, s);
}
const zn = {}, Yn = /* @__PURE__ */ new WeakMap();
let Cs;
function $u(e, t = !1, s = Cs) {
  if (s) {
    let n = Yn.get(s);
    n || Yn.set(s, n = []), n.push(e);
  }
}
function ju(e, t, s = Ne) {
  const { immediate: n, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = s, c = (P) => r ? P : /* @__PURE__ */ ht(P) || r === !1 || r === 0 ? Yt(P, 1) : Yt(P);
  let u, d, m, h, S = !1, x = !1;
  if (/* @__PURE__ */ Le(e) ? (d = () => e.value, S = /* @__PURE__ */ ht(e)) : /* @__PURE__ */ Dt(e) ? (d = () => c(e), S = !0) : K(e) ? (x = !0, S = e.some((P) => /* @__PURE__ */ Dt(P) || /* @__PURE__ */ ht(P)), d = () => e.map((P) => {
    if (/* @__PURE__ */ Le(P))
      return P.value;
    if (/* @__PURE__ */ Dt(P))
      return c(P);
    if (ue(P))
      return l ? l(P, 2) : P();
  })) : ue(e) ? t ? d = l ? () => l(e, 2) : e : d = () => {
    if (m) {
      Lt();
      try {
        m();
      } finally {
        Ft();
      }
    }
    const P = Cs;
    Cs = u;
    try {
      return l ? l(e, 3, [h]) : e(h);
    } finally {
      Cs = P;
    }
  } : d = zt, t && r) {
    const P = d, J = r === !0 ? 1 / 0 : r;
    d = () => Yt(P(), J);
  }
  const z = Fo(), $ = () => {
    u.stop(), z && z.active && Do(z.effects, u);
  };
  if (o && t) {
    const P = t;
    t = (...J) => {
      try {
        return P(...J);
      } finally {
        $();
      }
    };
  }
  let g = x ? new Array(e.length).fill(zn) : zn;
  const E = (P) => {
    if (!(!(u.flags & 1) || !u.dirty && !P))
      if (t) {
        const J = u.run();
        if (P || r || S || (x ? J.some((be, oe) => $t(be, g[oe])) : $t(J, g))) {
          const be = Cs;
          Lt();
          try {
            m && m(), Cs = u;
            const oe = [
              J,
              // pass undefined as the old value when it's changed for the first time
              g === zn ? void 0 : x && g[0] === zn ? [] : g,
              h
            ];
            g = J, l ? l(t, 3, oe) : (
              // @ts-expect-error
              t(...oe)
            );
          } finally {
            Cs = be, Ft();
          }
        }
      } else
        u.run();
  };
  return a && a(E), u = new tl(d), u.scheduler = i ? () => i(E, !1) : E, h = (P) => $u(P, !1, u), m = u.onStop = () => {
    const P = Yn.get(u);
    if (P) {
      if (l)
        l(P, 4);
      else
        for (const J of P) J();
      Yn.delete(u);
    }
  }, t ? n ? E(!0) : g = u.run() : i ? i(E.bind(null, !0), !0) : u.run(), $.pause = u.pause.bind(u), $.resume = u.resume.bind(u), $.stop = $, $;
}
function Yt(e, t = 1 / 0, s) {
  if (t <= 0 || !Ae(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ Le(e))
    Yt(e.value, t, s);
  else if (K(e))
    for (let n = 0; n < e.length; n++)
      Yt(e[n], t, s);
  else if (ts(e) || ms(e))
    e.forEach((n) => {
      Yt(n, t, s);
    });
  else if (Ga(e)) {
    for (const n in e)
      Yt(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && Yt(e[n], t, s);
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
function St(e, t, s, n) {
  if (ue(e)) {
    const r = Nn(e, t, s, n);
    return r && Ha(r) && r.catch((o) => {
      kr(o, t, s);
    }), r;
  }
  if (K(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(St(e[o], t, s, n));
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
      Lt(), Nn(o, null, 10, [
        e,
        l,
        c
      ]), Ft();
      return;
    }
  }
  zu(e, s, r, n, i);
}
function zu(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const it = [];
let wt = -1;
const Pt = [];
let cs = null, js = 0;
const bl = /* @__PURE__ */ Promise.resolve();
let Qn = null;
function Sr(e) {
  const t = Qn || bl;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function Du(e) {
  let t = wt + 1, s = it.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = it[n], o = _n(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function Ko(e) {
  if (!(e.flags & 1)) {
    const t = _n(e), s = it[it.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= _n(s) ? it.push(e) : it.splice(Du(t), 0, e), e.flags |= 1, _l();
  }
}
function _l() {
  Qn || (Qn = bl.then(kl));
}
function Vu(e) {
  if (!K(e))
    cs && e.id === -1 ? cs.splice(js + 1, 0, e) : e.flags & 1 || (Pt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Pt.push(e[t]);
  _l();
}
function xl(e, t, s, n = wt + 1) {
  for (; n < it.length; n++) {
    const r = it[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      it.splice(n, 1), n = e ? n - 1 : wt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function wl(e, t, s = 0) {
  if (Pt.length) {
    let n = Pt, r = 0;
    if (t) {
      n = [];
      for (let i = 0; i < Pt.length; i++) {
        const a = Pt[i];
        (a.i !== void 0 ? !a.i || a.i.uid < s : t.has(a)) ? Pt[r++] = a : n.push(a);
      }
    }
    const o = [...new Set(n)].sort((i, a) => _n(i) - _n(a));
    if (Pt.length = r, cs) {
      for (let i = 0; i < o.length; i++)
        cs.push(o[i]);
      return;
    }
    for (cs = o, js = 0; js < cs.length; js++) {
      const i = cs[js];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    cs = null, js = 0;
  }
}
let Vr = !1;
function Lu(e, t) {
  if (Vr) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Pt);
  e(), Vr = !0;
  try {
    xl(void 0, t), wl(void 0, s, t);
  } finally {
    Vr = !1;
  }
}
const _n = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function kl(e) {
  try {
    for (wt = 0; wt < it.length; wt++) {
      const t = it[wt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), Nn(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; wt < it.length; wt++) {
      const t = it[wt];
      t && (t.flags &= -2);
    }
    wt = -1, it.length = 0, wl(), Qn = null, (it.length || Pt.length) && kl();
  }
}
let Je = null, Sl = null;
function Xn(e) {
  const t = Je;
  return Je = e, Sl = e && e.type.__scopeId || null, t;
}
function ae(e, t = Je, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && nr(-1);
    const o = Xn(t), i = es.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = es.length; l > i; l--) ti();
      Xn(o), n._d && nr(1);
    }
    return a;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Xt(e, t) {
  if (Je === null)
    return e;
  const s = Tr(Je), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = Ne] = t[r];
    o && (ue(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && Yt(i), n.push({
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
    l && (Lt(), St(l, s, 8, [
      e.el,
      a,
      e,
      t
    ]), Ft());
  }
}
function Gn(e, t) {
  if (tt) {
    let s = tt.provides;
    const n = tt.parent && tt.parent.provides;
    n === s && (s = tt.provides = Object.create(n)), s[e] = t;
  }
}
function dt(e, t, s = !1) {
  const n = Or();
  if (n || Ts) {
    let r = Ts ? Ts._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && ue(t) ? t.call(n && n.proxy) : t;
  }
}
function Jo() {
  return !!(Or() || Ts);
}
const Fu = /* @__PURE__ */ Symbol.for("v-scx"), Uu = () => dt(Fu);
function Wu(e, t) {
  return Yo(e, null, t);
}
function Os(e, t, s) {
  return Yo(e, t, s);
}
function Yo(e, t, s = Ne) {
  const { immediate: n, deep: r, flush: o, once: i } = s, a = Qe({}, s), l = t && n || !t && o !== "post";
  let c;
  if (kn) {
    if (o === "sync") {
      const h = Uu();
      c = h.__watcherHandles || (h.__watcherHandles = []);
    } else if (!l) {
      const h = () => {
      };
      return h.stop = zt, h.resume = zt, h.pause = zt, h;
    }
  }
  const u = tt;
  a.call = (h, S, x) => St(h, u, S, x);
  let d = !1;
  o === "post" ? a.scheduler = (h) => {
    h.i = u, ut(h, u && u.suspense);
  } : o !== "sync" && (d = !0, a.scheduler = (h, S) => {
    S ? h() : Ko(h);
  }), a.augmentJob = (h) => {
    t && (h.flags |= 4), d && (h.flags |= 2, u && (h.id = u.uid, h.i = u));
  };
  const m = ju(e, t, a);
  return kn && (c ? c.push(m) : l && m()), m;
}
function Bu(e, t, s) {
  const n = this.proxy, r = De(e) ? e.includes(".") ? Cl(n, e) : () => n[e] : e.bind(n, n);
  let o;
  ue(t) ? o = t : (o = t.handler, s = t);
  const i = Pn(this), a = Yo(r, o.bind(n), s);
  return i(), a;
}
function Cl(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const Hu = /* @__PURE__ */ Symbol("_vte"), Cr = (e) => e.__isTeleport, Lr = /* @__PURE__ */ Symbol("_leaveCb");
function Zu(e) {
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
function Al(e) {
  if (!Qo(e))
    return Cr(e.type) && e.children ? Zu(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && ue(s.default))
      return s.default();
  }
}
function er(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    er(
      Cr(s.type) && Al(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === je && K(e.children)) {
    const s = zl(e.children, !1);
    s && er(s, t);
  }
}
function ho(e) {
  if (e.component)
    return ho(e.component.subTree);
  if (e.type === je) {
    const t = K(e.children) && zl(e.children, !1);
    return t ? ho(t) : void 0;
  }
  if (e.type !== bt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function yt(e, t) {
  return ue(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    Qe({ name: e.name }, t, { setup: e })
  ) : e;
}
function Rl(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function Si(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const tr = /* @__PURE__ */ new WeakMap();
function pn(e, t, s, n, r = !1) {
  if (K(e)) {
    e.forEach(
      (x, z) => pn(
        x,
        t && (K(t) ? t[z] : t),
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
  const o = n.shapeFlag & 4 ? Tr(n.component) : n.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === Ne ? a.refs = {} : a.refs, d = a.setupState, m = /* @__PURE__ */ xe(d), h = d === Ne ? Ba : (x) => Si(u, x) ? !1 : Se(m, x), S = (x, z) => !(z && Si(u, z));
  if (c != null && c !== l) {
    if (Ci(t), De(c))
      u[c] = null, h(c) && (d[c] = null);
    else if (/* @__PURE__ */ Le(c)) {
      const x = t;
      S(c, x.k) && (c.value = null), x.k && (u[x.k] = null);
    }
  }
  if (ue(l))
    Nn(l, a, 12, [i, u]);
  else {
    const x = De(l), z = /* @__PURE__ */ Le(l);
    if (x || z) {
      const $ = () => {
        if (e.f) {
          const g = x ? h(l) ? d[l] : u[l] : S() || !e.k ? l.value : u[e.k];
          if (r)
            K(g) && Do(g, o);
          else if (K(g))
            g.includes(o) || g.push(o);
          else if (x)
            u[l] = [o], h(l) && (d[l] = u[l]);
          else {
            const E = [o];
            S(l, e.k) && (l.value = E), e.k && (u[e.k] = E);
          }
        } else x ? (u[l] = i, h(l) && (d[l] = i)) : z && (S(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const g = () => {
          $(), tr.delete(e);
        };
        g.id = -1, tr.set(e, g), ut(g, s);
      } else
        Ci(e), $();
    }
  }
}
function Ci(e) {
  const t = tr.get(e);
  t && (t.flags |= 8, tr.delete(e));
}
_r().requestIdleCallback;
_r().cancelIdleCallback;
const Ls = (e) => !!e.type.__asyncLoader, Qo = (e) => e.type.__isKeepAlive;
function Gu(e, t) {
  El(e, "a", t);
}
function qu(e, t) {
  El(e, "da", t);
}
function El(e, t, s = tt) {
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
      Qo(r.parent.vnode) && Ku(n, t, s, r), r = r.parent;
  }
}
function Ku(e, t, s, n) {
  const r = Ar(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  Ol(() => {
    Do(n[t], r);
  }, s);
}
function Ar(e, t, s = tt, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Lt();
      const a = Pn(s), l = St(t, s, e, i);
      return a(), Ft(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const rs = (e) => (t, s = tt) => {
  (!kn || e === "sp") && Ar(e, (...n) => t(...n), s);
}, Ju = rs("bm"), Ys = rs("m"), Yu = rs(
  "bu"
), Qu = rs("u"), Xu = rs(
  "bum"
), Ol = rs("um"), ed = rs(
  "sp"
), td = rs("rtg"), sd = rs("rtc");
function nd(e, t = tt) {
  Ar("ec", e, t);
}
const rd = "components", Tl = /* @__PURE__ */ Symbol.for("v-ndc");
function od(e) {
  return De(e) ? id(rd, e, !1) || e : e || Tl;
}
function id(e, t, s = !0, n = !1) {
  const r = Je || tt;
  if (r) {
    const o = r.type;
    {
      const a = Wd(
        o,
        !1
      );
      if (a && (a === t || a === lt(t) || a === vr(lt(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      Ai(r[e] || o[e], t) || // global registration
      Ai(r.appContext[e], t)
    );
    return !i && n ? o : i;
  }
}
function Ai(e, t) {
  return e && (e[t] || e[lt(t)] || e[vr(lt(t))]);
}
function Qs(e, t, s, n) {
  let r;
  const o = s, i = K(e);
  if (i || De(e)) {
    const a = i && /* @__PURE__ */ Dt(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ ht(e), c = /* @__PURE__ */ Ut(e), e = xr(e)), r = new Array(e.length);
    for (let u = 0, d = e.length; u < d; u++)
      r[u] = t(
        l ? c ? gs(vt(e[u])) : vt(e[u]) : e[u],
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
function Il(e, t, s, n, r, o) {
  if (s == null && (s = {}), Je.ce || Je.parent && Ls(Je.parent) && Je.parent.ce) {
    const c = s, u = Object.keys(c).length > 0;
    return Q(), at(
      je,
      null,
      [U("slot", c, n)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = es.length;
  Q();
  let l;
  try {
    const c = i && Nl(i(s)), u = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = at(
      je,
      {
        key: (u && !gt(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = es.length; u > a; u--) ti();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function Nl(e) {
  return e.some((t) => Fs(t) ? !(t.type === bt || t.type === je && !Nl(t.children)) : !0) ? e : null;
}
const go = (e) => e ? Xl(e) ? Tr(e) : go(e.parent) : null, hn = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ Qe(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => go(e.parent),
    $root: (e) => go(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => Ml(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      Ko(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = Sr.bind(e.proxy)),
    $watch: (e) => Bu.bind(e)
  })
), Fr = (e, t) => e !== Ne && !e.__isScriptSetup && Se(e, t), ad = {
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
        if (Fr(n, t))
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
      return t === "$attrs" && et(e.attrs, "get", ""), c(e);
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
    return Fr(r, t) ? (r[t] = s, !0) : n !== Ne && Se(n, t) ? (n[t] = s, !0) : Se(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(s[a] || e !== Ne && a[0] !== "$" && Se(e, a) || Fr(t, a) || Se(o, a) || Se(n, a) || Se(hn, a) || Se(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : Se(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function Ri(e) {
  return K(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let yo = !0;
function ld(e) {
  const t = Ml(e), s = e.proxy, n = e.ctx;
  yo = !1, t.beforeCreate && Ei(t.beforeCreate, e, "bc");
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
    updated: S,
    activated: x,
    deactivated: z,
    beforeDestroy: $,
    beforeUnmount: g,
    destroyed: E,
    unmounted: P,
    render: J,
    renderTracked: be,
    renderTriggered: oe,
    errorCaptured: _,
    serverPrefetch: V,
    // public API
    expose: fe,
    inheritAttrs: ke,
    // assets
    components: N,
    directives: se,
    filters: Re
  } = t;
  if (c && cd(c, n, null), i)
    for (const X in i) {
      const ge = i[X];
      ue(ge) && (n[X] = ge.bind(s));
    }
  if (r) {
    const X = r.call(s, s);
    Ae(X) && (e.data = /* @__PURE__ */ In(X));
  }
  if (yo = !0, o)
    for (const X in o) {
      const ge = o[X], st = ue(ge) ? ge.bind(s, s) : ue(ge.get) ? ge.get.bind(s, s) : zt, G = !ue(ge) && ue(ge.set) ? ge.set.bind(s) : zt, nt = Te({
        get: st,
        set: G
      });
      Object.defineProperty(n, X, {
        enumerable: !0,
        configurable: !0,
        get: () => nt.value,
        set: (Ge) => nt.value = Ge
      });
    }
  if (a)
    for (const X in a)
      Pl(a[X], n, s, X);
  if (l) {
    const X = ue(l) ? l.call(s) : l;
    Reflect.ownKeys(X).forEach((ge) => {
      Gn(ge, X[ge]);
    });
  }
  u && Ei(u, e, "c");
  function de(X, ge) {
    K(ge) ? ge.forEach((st) => X(st.bind(s))) : ge && X(ge.bind(s));
  }
  if (de(Ju, d), de(Ys, m), de(Yu, h), de(Qu, S), de(Gu, x), de(qu, z), de(nd, _), de(sd, be), de(td, oe), de(Xu, g), de(Ol, P), de(ed, V), K(fe))
    if (fe.length) {
      const X = e.exposed || (e.exposed = {});
      fe.forEach((ge) => {
        Object.defineProperty(X, ge, {
          get: () => s[ge],
          set: (st) => s[ge] = st,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  J && e.render === zt && (e.render = J), ke != null && (e.inheritAttrs = ke), N && (e.components = N), se && (e.directives = se), V && Rl(e);
}
function cd(e, t, s = zt) {
  K(e) && (e = vo(e));
  for (const n in e) {
    const r = e[n];
    let o;
    Ae(r) ? "default" in r ? o = dt(
      r.from || n,
      r.default,
      !0
    ) : o = dt(r.from || n) : o = dt(r), /* @__PURE__ */ Le(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[n] = o;
  }
}
function Ei(e, t, s) {
  St(
    K(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function Pl(e, t, s, n) {
  let r = n.includes(".") ? Cl(s, n) : () => s[n];
  if (De(e)) {
    const o = t[e];
    ue(o) && Os(r, o);
  } else if (ue(e))
    Os(r, e.bind(s));
  else if (Ae(e))
    if (K(e))
      e.forEach((o) => Pl(o, t, s, n));
    else {
      const o = ue(e.handler) ? e.handler.bind(s) : t[e.handler];
      ue(o) && Os(r, o, e);
    }
}
function Ml(e) {
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
      const a = ud[i] || s && s[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const ud = {
  data: Oi,
  props: Ti,
  emits: Ti,
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
  watch: fd,
  // provide / inject
  provide: Oi,
  inject: dd
};
function Oi(e, t) {
  return t ? e ? function() {
    return Qe(
      ue(e) ? e.call(this, this) : e,
      ue(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function dd(e, t) {
  return an(vo(e), vo(t));
}
function vo(e) {
  if (K(e)) {
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
  return e ? Qe(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function Ti(e, t) {
  return e ? K(e) && K(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : Qe(
    /* @__PURE__ */ Object.create(null),
    Ri(e),
    Ri(t ?? {})
  ) : t;
}
function fd(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = Qe(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = rt(e[n], t[n]);
  return s;
}
function $l() {
  return {
    app: null,
    config: {
      isNativeTag: Ba,
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
let md = 0;
function pd(e, t) {
  return function(n, r = null) {
    ue(n) || (n = Qe({}, n)), r != null && !Ae(r) && (r = null);
    const o = $l(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: md++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: Hd,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...d) {
        return i.has(u) || (u && ue(u.install) ? (i.add(u), u.install(c, ...d)) : ue(u) && (i.add(u), u(c, ...d))), c;
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
          const h = c._ceVNode || U(n, r);
          return h.appContext = o, m === !0 ? m = "svg" : m === !1 && (m = void 0), e(h, u, m), l = !0, c._container = u, u.__vue_app__ = c, Tr(h.component);
        }
      },
      onUnmount(u) {
        a.push(u);
      },
      unmount() {
        l && (St(
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
const hd = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${lt(t)}Modifiers`] || e[`${bs(t)}Modifiers`];
function gd(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || Ne;
  let r = s;
  const o = t.startsWith("update:"), i = o && hd(n, t.slice(7));
  i && (i.trim && (r = s.map((u) => De(u) ? u.trim() : u)), i.number && (r = r.map(br)));
  let a, l = n[a = Mr(t)] || // also try camelCase event handler (#2249)
  n[a = Mr(lt(t))];
  !l && o && (l = n[a = Mr(bs(t))]), l && St(
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
    e.emitted[a] = !0, St(
      c,
      e,
      6,
      r
    );
  }
}
const yd = /* @__PURE__ */ new WeakMap();
function jl(e, t, s = !1) {
  const n = s ? yd : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!ue(e)) {
    const l = (c) => {
      const u = jl(c, t, !0);
      u && (a = !0, Qe(i, u));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (Ae(e) && n.set(e, null), null) : (K(o) ? o.forEach((l) => i[l] = null) : Qe(i, o), Ae(e) && n.set(e, i), i);
}
function Rr(e, t) {
  return !e || !pr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), Se(e, t[0].toLowerCase() + t.slice(1)) || Se(e, bs(t)) || Se(e, t));
}
function Ii(e) {
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
    ctx: S,
    inheritAttrs: x
  } = e, z = Xn(e);
  let $, g;
  try {
    if (s.shapeFlag & 4) {
      const P = r || n, J = P;
      $ = Mt(
        c.call(
          J,
          P,
          u,
          d,
          h,
          m,
          S
        )
      ), g = a;
    } else {
      const P = t;
      $ = Mt(
        P.length > 1 ? P(
          d,
          { attrs: a, slots: i, emit: l }
        ) : P(
          d,
          null
        )
      ), g = t.props ? a : vd(a);
    }
  } catch (P) {
    es.length = 0, kr(P, e, 1), $ = U(bt);
  }
  let E = $;
  if (g && x !== !1) {
    const P = Object.keys(g), { shapeFlag: J } = E;
    P.length && J & 7 && (o && P.some(hr) && (g = bd(
      g,
      o
    )), E = Us(E, g, !1, !0));
  }
  if (s.dirs && (E = Us(E, null, !1, !0), E.dirs = E.dirs ? E.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const P = Cr(E.type) && Al(E) || E;
    er(P, s.transition);
  }
  return $ = E, Xn(z), $;
}
function zl(e, t = !0) {
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
const vd = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || pr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, bd = (e, t) => {
  const s = {};
  for (const n in e)
    (!hr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function _d(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? Ni(n, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let d = 0; d < u.length; d++) {
        const m = u[d];
        if (Dl(i, n, m) && !Rr(c, m))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : n === i ? !1 : n ? i ? Ni(n, i, c) : !0 : !!i;
  return !1;
}
function Ni(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!Se(e, o) || Dl(t, e, o) && !Rr(s, o))
      return !0;
  }
  return !1;
}
function Dl(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && Ae(n) && Ae(r) ? !ss(n, r) : n !== r;
}
function xd({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const Vl = {}, Ll = () => Object.create(Vl), Fl = (e) => Object.getPrototypeOf(e) === Vl;
function wd(e, t, s, n = !1) {
  const r = {}, o = Ll();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), Ul(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ gl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function kd(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ xe(r), [l] = e.propsOptions;
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
            const S = lt(m);
            r[S] = bo(
              l,
              a,
              S,
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
    Ul(e, t, r, o) && (c = !0);
    let u;
    for (const d in a)
      (!t || // for camelCase
      !Se(t, d) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = bs(d)) === d || !Se(t, u))) && (l ? s && // for camelCase
      (s[d] !== void 0 || // for kebab-case
      s[u] !== void 0) && (r[d] = bo(
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
function Ul(e, t, s, n) {
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
    const l = /* @__PURE__ */ xe(s), c = a || Ne;
    for (let u = 0; u < o.length; u++) {
      const d = o[u];
      s[d] = bo(
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
function bo(e, t, s, n, r, o) {
  const i = e[s];
  if (i != null) {
    const a = Se(i, "default");
    if (a && n === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && ue(l)) {
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
    ] && (n === "" || n === bs(s)) && (n = !0));
  }
  return n;
}
const Sd = /* @__PURE__ */ new WeakMap();
function Wl(e, t, s = !1) {
  const n = s ? Sd : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!ue(e)) {
    const u = (d) => {
      l = !0;
      const [m, h] = Wl(d, t, !0);
      Qe(i, m), h && a.push(...h);
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return Ae(e) && n.set(e, As), As;
  if (K(o))
    for (let u = 0; u < o.length; u++) {
      const d = lt(o[u]);
      Pi(d) && (i[d] = Ne);
    }
  else if (o)
    for (const u in o) {
      const d = lt(u);
      if (Pi(d)) {
        const m = o[u], h = i[d] = K(m) || ue(m) ? { type: m } : Qe({}, m), S = h.type;
        let x = !1, z = !0;
        if (K(S))
          for (let $ = 0; $ < S.length; ++$) {
            const g = S[$], E = ue(g) && g.name;
            if (E === "Boolean") {
              x = !0;
              break;
            } else E === "String" && (z = !1);
          }
        else
          x = ue(S) && S.name === "Boolean";
        h[
          0
          /* shouldCast */
        ] = x, h[
          1
          /* shouldCastTrue */
        ] = z, (x || Se(h, "default")) && a.push(d);
      }
    }
  const c = [i, a];
  return Ae(e) && n.set(e, c), c;
}
function Pi(e) {
  return e[0] !== "$" && !un(e);
}
const Xo = (e) => e === "_" || e === "_ctx" || e === "$stable", ei = (e) => K(e) ? e.map(Mt) : [Mt(e)], Cd = (e, t, s) => {
  if (t._n)
    return t;
  const n = ae((...r) => ei(t(...r)), s);
  return n._c = !1, n;
}, Bl = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (Xo(r)) continue;
    const o = e[r];
    if (ue(o))
      t[r] = Cd(r, o, n);
    else if (o != null) {
      const i = ei(o);
      t[r] = () => i;
    }
  }
}, Hl = (e, t) => {
  const s = ei(t);
  e.slots.default = () => s;
}, Zl = (e, t, s) => {
  for (const n in t)
    (s || !Xo(n)) && (e[n] = t[n]);
}, Ad = (e, t, s) => {
  const n = e.slots = Ll();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (Zl(n, t, s), s && qa(n, "_", r, !0)) : Bl(t, n);
  } else t && Hl(e, t);
}, Rd = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, i = Ne;
  if (n.shapeFlag & 32) {
    const a = t._;
    a ? s && a === 1 ? o = !1 : Zl(r, t, s) : (o = !t.$stable, Bl(t, r)), i = t;
  } else t && (Hl(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !Xo(a) && i[a] == null && delete r[a];
}, ut = Nd;
function Ed(e) {
  return Od(e);
}
function Od(e, t) {
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
    setScopeId: h = zt,
    insertStaticContent: S
  } = e, x = (f, p, y, b = null, w = null, A = null, O = void 0, j = null, M = !!p.dynamicChildren) => {
    if (f === p)
      return;
    f && !sn(f, p) && (b = k(f), Ge(f, w, A, !0), f = null), p.patchFlag === -2 && (M = !1, p.dynamicChildren = null), p.dynamicChildren && f && f.dynamicChildren && f.dynamicChildren.hasOnce && (p.dynamicChildren === As && (p.dynamicChildren = []), p.dynamicChildren.hasOnce = !0);
    const { type: R, ref: Y, shapeFlag: D } = p;
    switch (R) {
      case Er:
        z(f, p, y, b);
        break;
      case bt:
        $(f, p, y, b);
        break;
      case Wr:
        f == null && g(p, y, b, O);
        break;
      case je:
        N(
          f,
          p,
          y,
          b,
          w,
          A,
          O,
          j,
          M
        );
        break;
      default:
        D & 1 ? J(
          f,
          p,
          y,
          b,
          w,
          A,
          O,
          j,
          M
        ) : D & 6 ? se(
          f,
          p,
          y,
          b,
          w,
          A,
          O,
          j,
          M
        ) : (D & 64 || D & 128) && R.process(
          f,
          p,
          y,
          b,
          w,
          A,
          O,
          j,
          M,
          T
        );
    }
    Y != null && w ? pn(Y, f && f.ref, A, p || f, !p) : Y == null && f && f.ref != null && pn(f.ref, null, A, f, !0);
  }, z = (f, p, y, b) => {
    if (f == null)
      n(
        p.el = a(p.children),
        y,
        b
      );
    else {
      const w = p.el = f.el;
      p.children !== f.children && c(w, p.children);
    }
  }, $ = (f, p, y, b) => {
    f == null ? n(
      p.el = l(p.children || ""),
      y,
      b
    ) : p.el = f.el;
  }, g = (f, p, y, b) => {
    [f.el, f.anchor] = S(
      f.children,
      p,
      y,
      b,
      f.el,
      f.anchor
    );
  }, E = ({ el: f, anchor: p }, y, b) => {
    let w;
    for (; f && f !== p; )
      w = m(f), n(f, y, b), f = w;
    n(p, y, b);
  }, P = ({ el: f, anchor: p }) => {
    let y;
    for (; f && f !== p; )
      y = m(f), r(f), f = y;
    r(p);
  }, J = (f, p, y, b, w, A, O, j, M) => {
    if (p.type === "svg" ? O = "svg" : p.type === "math" && (O = "mathml"), f == null)
      be(
        p,
        y,
        b,
        w,
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
          w,
          A,
          O,
          j,
          M
        );
      } finally {
        R && R._endPatch();
      }
    }
  }, be = (f, p, y, b, w, A, O, j) => {
    let M, R;
    const { props: Y, shapeFlag: D, transition: ee, dirs: ie } = f;
    if (M = f.el = i(
      f.type,
      A,
      Y && Y.is,
      Y
    ), D & 8 ? u(M, f.children) : D & 16 && _(
      f.children,
      M,
      null,
      b,
      w,
      Ur(f, A),
      O,
      j
    ), ie && xs(f, null, b, "created"), oe(M, f, f.scopeId, O, b), Y) {
      for (const Ie in Y)
        Ie !== "value" && !un(Ie) && o(M, Ie, null, Y[Ie], A, b);
      "value" in Y && o(M, "value", null, Y.value, A), (R = Y.onVnodeBeforeMount) && Tt(R, b, f);
    }
    ie && xs(f, null, b, "beforeMount");
    const _e = Td(w, ee);
    _e && ee.beforeEnter(M), n(M, p, y), ((R = Y && Y.onVnodeMounted) || _e || ie) && ut(() => {
      try {
        R && Tt(R, b, f), _e && ee.enter(M), ie && xs(f, null, b, "mounted");
      } finally {
      }
    }, w);
  }, oe = (f, p, y, b, w) => {
    if (y && h(f, y), b)
      for (let A = 0; A < b.length; A++)
        h(f, b[A]);
    if (w) {
      let A = w.subTree;
      if (p === A || Kl(A.type) && (A.ssContent === p || A.ssFallback === p)) {
        const O = w.vnode;
        oe(
          f,
          O,
          O.scopeId,
          O.slotScopeIds,
          w.parent
        );
      }
    }
  }, _ = (f, p, y, b, w, A, O, j, M = 0) => {
    for (let R = M; R < f.length; R++) {
      const Y = f[R] = j ? Kt(f[R]) : Mt(f[R]);
      x(
        null,
        Y,
        p,
        y,
        b,
        w,
        A,
        O,
        j
      );
    }
  }, V = (f, p, y, b, w, A, O) => {
    const j = p.el = f.el;
    let { patchFlag: M, dynamicChildren: R, dirs: Y } = p;
    M |= f.patchFlag & 16;
    const D = f.props || Ne, ee = p.props || Ne;
    let ie;
    if (y && ws(y, !1), (ie = ee.onVnodeBeforeUpdate) && Tt(ie, y, p, f), Y && xs(p, f, y, "beforeUpdate"), y && ws(y, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    R && (!f.dynamicChildren || f.dynamicChildren.length !== R.length) && (M = 0, O = !1, R = null), (D.innerHTML && ee.innerHTML == null || D.textContent && ee.textContent == null) && u(j, ""), R ? fe(
      f.dynamicChildren,
      R,
      j,
      y,
      b,
      Ur(p, w),
      A
    ) : O || ge(
      f,
      p,
      j,
      null,
      y,
      b,
      Ur(p, w),
      A,
      !1
    ), M > 0) {
      if (M & 16)
        ke(j, D, ee, y, w);
      else if (M & 2 && D.class !== ee.class && o(j, "class", null, ee.class, w), M & 4 && o(j, "style", D.style, ee.style, w), M & 8) {
        const _e = p.dynamicProps;
        for (let Ie = 0; Ie < _e.length; Ie++) {
          const Oe = _e[Ie], Fe = D[Oe], qe = ee[Oe];
          (qe !== Fe || Oe === "value") && o(j, Oe, Fe, qe, w, y);
        }
      }
      M & 1 && f.children !== p.children && u(j, p.children);
    } else !O && R == null && ke(j, D, ee, y, w);
    ((ie = ee.onVnodeUpdated) || Y) && ut(() => {
      ie && Tt(ie, y, p, f), Y && xs(p, f, y, "updated");
    }, b);
  }, fe = (f, p, y, b, w, A, O) => {
    for (let j = 0; j < p.length; j++) {
      const M = f[j], R = p[j], Y = M.el || _o(M), D = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        Y && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (M.type === je || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !sn(M, R) || // - In the case of a component, it could contain anything.
        M.shapeFlag & 198) ? d(Y) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          y
        )
      );
      x(
        M,
        R,
        D,
        null,
        b,
        w,
        A,
        O,
        !0
      );
    }
  }, ke = (f, p, y, b, w) => {
    if (p !== y) {
      if (p !== Ne)
        for (const A in p)
          !un(A) && !(A in y) && o(
            f,
            A,
            p[A],
            null,
            w,
            b
          );
      for (const A in y) {
        if (un(A)) continue;
        const O = y[A], j = p[A];
        O !== j && A !== "value" && o(f, A, j, O, w, b);
      }
      "value" in y && o(f, "value", p.value, y.value, w);
    }
  }, N = (f, p, y, b, w, A, O, j, M) => {
    const R = p.el = f ? f.el : a(""), Y = p.anchor = f ? f.anchor : a("");
    let { patchFlag: D, dynamicChildren: ee, slotScopeIds: ie } = p;
    ie && (j = j ? j.concat(ie) : ie), f == null ? (n(R, y, b), n(Y, y, b), _(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      p.children || [],
      y,
      Y,
      w,
      A,
      O,
      j,
      M
    )) : D > 0 && D & 64 && ee && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    f.dynamicChildren && f.dynamicChildren.length === ee.length ? (fe(
      f.dynamicChildren,
      ee,
      y,
      w,
      A,
      O,
      j
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (p.key != null || w && p === w.subTree) && Gl(
      f,
      p,
      !0
      /* shallow */
    )) : ge(
      f,
      p,
      y,
      Y,
      w,
      A,
      O,
      j,
      M
    );
  }, se = (f, p, y, b, w, A, O, j, M) => {
    p.slotScopeIds = j, f == null ? p.shapeFlag & 512 ? w.ctx.activate(
      p,
      y,
      b,
      O,
      M
    ) : Re(
      p,
      y,
      b,
      w,
      A,
      O,
      M
    ) : ye(f, p, M);
  }, Re = (f, p, y, b, w, A, O) => {
    const j = f.component = Dd(
      f,
      b,
      w
    );
    if (Qo(f) && (j.ctx.renderer = T), Vd(j, !1, O), j.asyncDep) {
      if (w && w.registerDep(
        j,
        de,
        O,
        A
      ), !f.el) {
        const M = j.subTree = U(bt);
        $(null, M, p, y), f.placeholder = M.el;
      }
    } else
      de(
        j,
        f,
        p,
        y,
        w,
        A,
        O
      );
  }, ye = (f, p, y) => {
    const b = p.component = f.component;
    if (_d(f, p, y))
      if (b.asyncDep && !b.asyncResolved) {
        p.el = f.el, p.placeholder = f.placeholder, X(b, p, y);
        return;
      } else
        b.next = p, b.update();
    else
      p.el = f.el, p.placeholder = f.placeholder, b.vnode = p;
  }, de = (f, p, y, b, w, A, O) => {
    const j = () => {
      if (f.isMounted) {
        let { next: D, bu: ee, u: ie, parent: _e, vnode: Ie } = f;
        {
          const Et = ql(f);
          if (Et) {
            D && (D.el = Ie.el, X(f, D, O)), Et.asyncDep.then(() => {
              ut(() => {
                f.isUnmounted || R();
              }, w);
            });
            return;
          }
        }
        let Oe = D, Fe;
        ws(f, !1), D ? (D.el = Ie.el, X(f, D, O)) : D = Ie, ee && Zn(ee), (Fe = D.props && D.props.onVnodeBeforeUpdate) && Tt(Fe, _e, D, Ie), ws(f, !0);
        const qe = Ii(f), Rt = f.subTree;
        f.subTree = qe, x(
          Rt,
          qe,
          // parent may have changed if it's in a teleport
          d(Rt.el),
          // anchor may have changed if it's in a fragment
          k(Rt),
          f,
          w,
          A
        ), D.el = qe.el, Oe === null && xd(f, qe.el), ie && ut(ie, w), (Fe = D.props && D.props.onVnodeUpdated) && ut(
          () => Tt(Fe, _e, D, Ie),
          w
        );
      } else {
        let D;
        const { el: ee, props: ie } = p, { bm: _e, m: Ie, parent: Oe, root: Fe, type: qe } = f, Rt = Ls(p);
        ws(f, !1), _e && Zn(_e), !Rt && (D = ie && ie.onVnodeBeforeMount) && Tt(D, Oe, p), ws(f, !0);
        {
          Fe.ce && Fe.ce._hasShadowRoot() && Fe.ce._injectChildStyle(
            qe,
            f.parent ? f.parent.type : void 0
          );
          const Et = f.subTree = Ii(f);
          x(
            null,
            Et,
            y,
            b,
            f,
            w,
            A
          ), p.el = Et.el;
        }
        if (Ie && ut(Ie, w), !Rt && (D = ie && ie.onVnodeMounted)) {
          const Et = p;
          ut(
            () => Tt(D, Oe, Et),
            w
          );
        }
        (p.shapeFlag & 256 || Oe && Ls(Oe.vnode) && Oe.vnode.shapeFlag & 256) && f.a && ut(f.a, w), f.isMounted = !0, p = y = b = null;
      }
    };
    f.scope.on();
    const M = f.effect = new tl(j);
    f.scope.off();
    const R = f.update = M.run.bind(M), Y = f.job = M.runIfDirty.bind(M);
    Y.i = f, Y.id = f.uid, M.scheduler = () => Ko(Y), ws(f, !0), R();
  }, X = (f, p, y) => {
    p.component = f;
    const b = f.vnode.props;
    f.vnode = p, f.next = null, kd(f, p.props, b, y), Rd(f, p.children, y), Lt(), xl(f), Ft();
  }, ge = (f, p, y, b, w, A, O, j, M = !1) => {
    const R = f && f.children, Y = f ? f.shapeFlag : 0, D = p.children, { patchFlag: ee, shapeFlag: ie } = p;
    if (ee > 0) {
      if (ee & 128) {
        G(
          R,
          D,
          y,
          b,
          w,
          A,
          O,
          j,
          M
        );
        return;
      } else if (ee & 256) {
        st(
          R,
          D,
          y,
          b,
          w,
          A,
          O,
          j,
          M
        );
        return;
      }
    }
    ie & 8 ? (Y & 16 && Ee(R, w, A), D !== R && u(y, D)) : Y & 16 ? ie & 16 ? G(
      R,
      D,
      y,
      b,
      w,
      A,
      O,
      j,
      M
    ) : Ee(R, w, A, !0) : (Y & 8 && u(y, ""), ie & 16 && _(
      D,
      y,
      b,
      w,
      A,
      O,
      j,
      M
    ));
  }, st = (f, p, y, b, w, A, O, j, M) => {
    f = f || As, p = p || As;
    const R = f.length, Y = p.length, D = Math.min(R, Y);
    let ee;
    for (ee = 0; ee < D; ee++) {
      const ie = p[ee] = M ? Kt(p[ee]) : Mt(p[ee]);
      x(
        f[ee],
        ie,
        y,
        null,
        w,
        A,
        O,
        j,
        M
      );
    }
    R > Y ? Ee(
      f,
      w,
      A,
      !0,
      !1,
      D
    ) : _(
      p,
      y,
      b,
      w,
      A,
      O,
      j,
      M,
      D
    );
  }, G = (f, p, y, b, w, A, O, j, M) => {
    let R = 0;
    const Y = p.length;
    let D = f.length - 1, ee = Y - 1;
    for (; R <= D && R <= ee; ) {
      const ie = f[R], _e = p[R] = M ? Kt(p[R]) : Mt(p[R]);
      if (sn(ie, _e))
        x(
          ie,
          _e,
          y,
          null,
          w,
          A,
          O,
          j,
          M
        );
      else
        break;
      R++;
    }
    for (; R <= D && R <= ee; ) {
      const ie = f[D], _e = p[ee] = M ? Kt(p[ee]) : Mt(p[ee]);
      if (sn(ie, _e))
        x(
          ie,
          _e,
          y,
          null,
          w,
          A,
          O,
          j,
          M
        );
      else
        break;
      D--, ee--;
    }
    if (R > D) {
      if (R <= ee) {
        const ie = ee + 1, _e = ie < Y ? p[ie].el : b;
        for (; R <= ee; )
          x(
            null,
            p[R] = M ? Kt(p[R]) : Mt(p[R]),
            y,
            _e,
            w,
            A,
            O,
            j,
            M
          ), R++;
      }
    } else if (R > ee)
      for (; R <= D; )
        Ge(f[R], w, A, !0), R++;
    else {
      const ie = R, _e = R, Ie = /* @__PURE__ */ new Map();
      for (R = _e; R <= ee; R++) {
        const mt = p[R] = M ? Kt(p[R]) : Mt(p[R]);
        mt.key != null && Ie.set(mt.key, R);
      }
      let Oe, Fe = 0;
      const qe = ee - _e + 1;
      let Rt = !1, Et = 0;
      const en = new Array(qe);
      for (R = 0; R < qe; R++) en[R] = 0;
      for (R = ie; R <= D; R++) {
        const mt = f[R];
        if (Fe >= qe) {
          Ge(mt, w, A, !0);
          continue;
        }
        let Ot;
        if (mt.key != null)
          Ot = Ie.get(mt.key);
        else
          for (Oe = _e; Oe <= ee; Oe++)
            if (en[Oe - _e] === 0 && sn(mt, p[Oe])) {
              Ot = Oe;
              break;
            }
        Ot === void 0 ? Ge(mt, w, A, !0) : (en[Ot - _e] = R + 1, Ot >= Et ? Et = Ot : Rt = !0, x(
          mt,
          p[Ot],
          y,
          null,
          w,
          A,
          O,
          j,
          M
        ), Fe++);
      }
      const pi = Rt ? Id(en) : As;
      for (Oe = pi.length - 1, R = qe - 1; R >= 0; R--) {
        const mt = _e + R, Ot = p[mt], hi = p[mt + 1], gi = mt + 1 < Y ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          hi.el || _o(hi)
        ) : b;
        en[R] === 0 ? x(
          null,
          Ot,
          y,
          gi,
          w,
          A,
          O,
          j,
          M
        ) : Rt && (Oe < 0 || R !== pi[Oe] ? nt(Ot, y, gi, 2) : Oe--);
      }
    }
  }, nt = (f, p, y, b, w = null) => {
    const { el: A, type: O, transition: j, children: M, shapeFlag: R } = f;
    if (R & 6) {
      nt(f.component.subTree, p, y, b);
      return;
    }
    if (R & 128) {
      f.suspense.move(p, y, b);
      return;
    }
    if (R & 64) {
      O.move(f, p, y, T);
      return;
    }
    if (O === je) {
      n(A, p, y);
      for (let D = 0; D < M.length; D++)
        nt(M[D], p, y, b);
      n(f.anchor, p, y);
      return;
    }
    if (O === Wr) {
      E(f, p, y);
      return;
    }
    if (b !== 2 && R & 1 && j)
      if (b === 0)
        j.persisted && !A[Lr] ? n(A, p, y) : (j.beforeEnter(A), n(A, p, y), ut(() => j.enter(A), w));
      else {
        const { leave: D, delayLeave: ee, afterLeave: ie } = j, _e = () => {
          f.ctx.isUnmounted ? r(A) : n(A, p, y);
        }, Ie = () => {
          const Oe = A._isLeaving || !!A[Lr];
          A._isLeaving && A[Lr](
            !0
            /* cancelled */
          ), j.persisted && !Oe ? _e() : D(A, () => {
            _e(), ie && ie();
          });
        };
        ee ? ee(A, _e, Ie) : Ie();
      }
    else
      n(A, p, y);
  }, Ge = (f, p, y, b = !1, w = !1) => {
    const {
      type: A,
      props: O,
      ref: j,
      children: M,
      dynamicChildren: R,
      shapeFlag: Y,
      patchFlag: D,
      dirs: ee,
      cacheIndex: ie,
      memo: _e
    } = f;
    if ((D === -2 || R && R.hasOnce) && (w = !1), j != null && (Lt(), pn(j, null, y, f, !0), Ft()), ie != null && (!f.ctx || f.ctx === p) && (p.renderCache[ie] = void 0), Y & 256) {
      p.ctx.deactivate(f);
      return;
    }
    const Ie = Y & 1 && ee, Oe = !Ls(f);
    let Fe;
    if (Oe && (Fe = O && O.onVnodeBeforeUnmount) && Tt(Fe, p, f), Y & 6)
      ze(f.component, y, b);
    else {
      if (Y & 128) {
        f.suspense.unmount(y, b);
        return;
      }
      Ie && xs(f, null, p, "beforeUnmount"), Y & 64 ? f.type.remove(
        f,
        p,
        y,
        T,
        b
      ) : R && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !R.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (A !== je || D > 0 && D & 64) ? Ee(
        R,
        p,
        y,
        !1,
        !0
      ) : (A === je && D & 384 || !w && Y & 16) && Ee(M, p, y), b && Bt(f);
    }
    const qe = _e != null && ie == null;
    (Oe && (Fe = O && O.onVnodeUnmounted) || Ie || qe) && ut(() => {
      Fe && Tt(Fe, p, f), Ie && xs(f, null, p, "unmounted"), qe && (f.el = null);
    }, y);
  }, Bt = (f) => {
    const { type: p, el: y, anchor: b, transition: w } = f, A = p === je;
    if (A && !w) {
      xt(y, b);
      return;
    }
    if (p === Wr) {
      P(f), w && !w.persisted && w.afterLeave && w.afterLeave();
      return;
    }
    const O = A ? ho(f) : f, j = () => {
      A ? d(y) && xt(y, b) : r(y), w && !w.persisted && w.afterLeave && w.afterLeave();
    };
    if (O && O.shapeFlag & 1 && w && !w.persisted) {
      const { leave: M, delayLeave: R } = w, Y = O.el, D = () => M(Y, j);
      R ? R(Y, j, D) : D();
    } else
      j();
  }, xt = (f, p) => {
    let y;
    for (; f !== p; )
      y = m(f), r(f), f = y;
    r(p);
  }, ze = (f, p, y) => {
    const { bum: b, scope: w, job: A, subTree: O, um: j, m: M, a: R } = f;
    Mi(M), Mi(R), b && Zn(b), w.stop(), A ? (A.flags |= 8, Ge(O, f, p, y)) : f.vnode.el && O && (O.transition = f.vnode.transition, Ge(O, f, p, y)), j && ut(j, p), ut(() => {
      f.isUnmounted = !0;
    }, p);
  }, Ee = (f, p, y, b = !1, w = !1, A = 0) => {
    for (let O = A; O < f.length; O++)
      Ge(f[O], p, y, b, w);
  }, k = (f) => {
    if (f.shapeFlag & 6)
      return k(f.component.subTree);
    if (f.shapeFlag & 128)
      return f.suspense.next();
    const p = m(f.anchor || f.el), y = p && p[Hu];
    return y ? m(y) : p;
  }, W = (f, p, y) => {
    const b = f && p._vnode ? void 0 : f && f.component ? f.component.uid : zd();
    Lu(() => {
      f == null ? p._vnode && Ge(p._vnode, null, null, !0) : x(
        p._vnode || null,
        f,
        p,
        null,
        null,
        null,
        y
      ), p._vnode = f;
    }, b);
  }, T = {
    p: x,
    um: Ge,
    m: nt,
    r: Bt,
    mt: Re,
    mc: _,
    pc: ge,
    pbc: fe,
    n: k,
    o: e
  };
  return {
    render: W,
    hydrate: void 0,
    createApp: pd(W)
  };
}
function Ur({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function ws({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function Td(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function Gl(e, t, s = !1) {
  const n = e.children, r = t.children;
  if (K(n) && K(r))
    for (let o = 0; o < n.length; o++) {
      const i = n[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = Kt(r[o]), a.el = i.el), !s && a.patchFlag !== -2 && Gl(i, a)), a.type === Er && (a.patchFlag === -1 && (a = r[o] = Kt(a)), a.el = i.el), a.type === bt && !a.el && (a.el = i.el);
    }
}
function Id(e) {
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
function ql(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : ql(t);
}
function Mi(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function _o(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? _o(t.subTree) : null;
}
const Kl = (e) => e.__isSuspense;
function Nd(e, t) {
  t && t.pendingBranch ? K(e) ? t.effects.push(...e) : t.effects.push(e) : Vu(e);
}
const je = /* @__PURE__ */ Symbol.for("v-fgt"), Er = /* @__PURE__ */ Symbol.for("v-txt"), bt = /* @__PURE__ */ Symbol.for("v-cmt"), Wr = /* @__PURE__ */ Symbol.for("v-stc"), es = [];
let pt = null;
function Q(e = !1) {
  es.push(pt = e ? null : []);
}
function ti() {
  es.pop(), pt = es[es.length - 1] || null;
}
let xn = 1;
function nr(e, t = !1) {
  xn += e, e < 0 && pt && t && (pt.hasOnce = !0);
}
function Jl(e) {
  return e.dynamicChildren = xn > 0 ? pt || As : null, ti(), xn > 0 && pt && pt.push(e), e;
}
function he(e, t, s, n, r, o) {
  return Jl(
    v(
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
  return Jl(
    U(
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
}) => (typeof e == "number" && (e = "" + e), e != null ? De(e) || /* @__PURE__ */ Le(e) || ue(e) ? { i: Je, r: e, k: t, f: !!s } : e : null);
function v(e, t = null, s = null, n = 0, r = null, o = e === je ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Yl(t),
    ref: t && qn(t),
    scopeId: Sl,
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
    ctx: Je
  };
  return a ? (rr(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= De(s) ? 8 : 16), xn > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  pt && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && pt.push(l), l;
}
const U = Pd;
function Pd(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === Tl) && (e = bt), Fs(e)) {
    const a = Us(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && rr(a, s), xn > 0 && !o && pt && (a.shapeFlag & 6 ? pt[pt.indexOf(e)] = a : pt.push(a)), a.patchFlag = -2, a;
  }
  if (Bd(e) && (e = e.__vccOpts), t) {
    t = Md(t);
    let { class: a, style: l } = t;
    a && !De(a) && (t.class = ft(a)), Ae(l) && (/* @__PURE__ */ wr(l) && !K(l) && (l = Qe({}, l)), t.style = Vo(l));
  }
  const i = De(e) ? 1 : Kl(e) ? 128 : Cr(e) ? 64 : Ae(e) ? 4 : ue(e) ? 2 : 0;
  return v(
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
function Md(e) {
  return e ? /* @__PURE__ */ wr(e) || Fl(e) ? Qe({}, e) : e : null;
}
function Us(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? $d(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Yl(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? K(o) ? o.concat(qn(t)) : [o, qn(t)] : qn(t)
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
    patchFlag: t && e.type !== je ? i === -1 ? 16 : i | 16 : i,
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
  return U(Er, null, e, t);
}
function Ye(e = "", t = !1) {
  return t ? (Q(), at(bt, null, e)) : U(bt, null, e);
}
function Mt(e) {
  return e == null || typeof e == "boolean" ? U(bt) : K(e) ? U(
    je,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : Fs(e) ? Kt(e) : U(Er, null, String(e));
}
function Kt(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : Us(e);
}
function rr(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (K(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), rr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !Fl(t) ? t._ctx = Je : r === 3 && Je && (Je.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (ue(t)) {
    if (n & 65) {
      rr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: Je }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [te(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function $d(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = ft([t.class, n.class]));
      else if (r === "style")
        t.style = Vo([t.style, n.style]);
      else if (pr(r)) {
        const o = t[r], i = n[r];
        i && o !== i && !(K(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !hr(r) && (t[r] = i);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function Tt(e, t, s, n = null) {
  St(e, t, 7, [
    s,
    n
  ]);
}
const jd = $l();
let Ql = 0;
function zd() {
  return Ql;
}
function Dd(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || jd, o = {
    uid: Ql++,
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
    scope: new Qa(
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
    propsOptions: Wl(n, r),
    emitsOptions: jl(n, r),
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = gd.bind(null, o), e.ce && e.ce(o), o;
}
let tt = null;
const Or = () => tt || Je;
let or, wn;
{
  const e = _r(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  or = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => tt = s
  ), wn = t(
    "__VUE_SSR_SETTERS__",
    (s) => kn = s
  );
}
const Pn = (e) => {
  const t = tt;
  return or(e), e.scope.on(), () => {
    e.scope.off(), or(t);
  };
}, $i = () => {
  tt && tt.scope.off(), or(null);
};
function Xl(e) {
  return e.vnode.shapeFlag & 4;
}
let kn = !1;
function Vd(e, t = !1, s = !1) {
  t && wn(t);
  const { props: n, children: r } = e.vnode, o = Xl(e);
  wd(e, n, o, t), Ad(e, r, s || t);
  const i = o ? Ld(e, t) : void 0;
  return t && wn(!1), i;
}
function Ld(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, ad);
  const { setup: n } = s;
  if (n) {
    Lt();
    const r = e.setupContext = n.length > 1 ? Ud(e) : null, o = Pn(e), i = Nn(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = Ha(i);
    if (Ft(), o(), (a || e.sp) && !Ls(e) && Rl(e), a) {
      if (i.then($i, $i), t)
        return i.then((l) => {
          wn(!0);
          try {
            ji(e, l, t);
          } finally {
            wn(!1);
          }
        }).catch((l) => {
          kr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      ji(e, i);
  } else
    ec(e);
}
function ji(e, t, s) {
  ue(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : Ae(t) && (e.setupState = vl(t)), ec(e);
}
function ec(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || zt);
  {
    const r = Pn(e);
    Lt();
    try {
      ld(e);
    } finally {
      Ft(), r();
    }
  }
}
const Fd = {
  get(e, t) {
    return et(e, "get", ""), e[t];
  }
};
function Ud(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Fd),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Tr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(vl(qo(e.exposed)), {
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
function Wd(e, t = !0) {
  return ue(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function Bd(e) {
  return ue(e) && "__vccOpts" in e;
}
const Te = (e, t) => /* @__PURE__ */ Mu(e, t, kn);
function Sn(e, t, s) {
  try {
    nr(-1);
    const n = arguments.length;
    return n === 2 ? Ae(t) && !K(t) ? Fs(t) ? U(e, null, [t]) : U(e, t) : U(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && Fs(s) && (s = [s]), U(e, t, s));
  } finally {
    nr(1);
  }
}
const Hd = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let xo;
const zi = typeof window < "u" && window.trustedTypes;
if (zi)
  try {
    xo = /* @__PURE__ */ zi.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const tc = xo ? (e) => xo.createHTML(e) : (e) => e, Zd = "http://www.w3.org/2000/svg", Gd = "http://www.w3.org/1998/Math/MathML", qt = typeof document < "u" ? document : null, Di = qt && /* @__PURE__ */ qt.createElement("template"), qd = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? qt.createElementNS(Zd, e) : t === "mathml" ? qt.createElementNS(Gd, e) : s ? qt.createElement(e, { is: s }) : qt.createElement(e);
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
      Di.innerHTML = tc(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const a = Di.content;
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
}, Kd = /* @__PURE__ */ Symbol("_vtc");
function Jd(e, t, s) {
  const n = e[Kd];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const Vi = /* @__PURE__ */ Symbol("_vod"), Yd = /* @__PURE__ */ Symbol("_vsh"), Qd = /* @__PURE__ */ Symbol(""), Xd = /(?:^|;)\s*display\s*:/;
function ef(e, t, s) {
  const n = e.style, r = De(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (De(t))
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
      a != null ? sf(
        e,
        i,
        !De(t) && t ? t[i] : void 0,
        a
      ) || ln(n, i, a) : ln(n, i, "");
    }
  } else if (r) {
    if (t !== s) {
      const i = n[Qd];
      i && (s += ";" + i), n.cssText = s, o = Xd.test(s);
    }
  } else t && e.removeAttribute("style");
  Vi in e && ((!r || t !== s) && (e[Vi] = o ? n.display : ""), e[Yd] && (n.display = "none"));
}
const Dn = /\s*!important$/;
function ln(e, t, s) {
  if (K(s))
    s.forEach((n) => ln(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    Dn.test(s) ? e.setProperty(t, s.replace(Dn, ""), "important") : e.setProperty(t, s);
  else {
    const n = tf(e, t);
    Dn.test(s) ? e.setProperty(
      bs(n),
      s.replace(Dn, ""),
      "important"
    ) : e[n] = s;
  }
}
const Li = ["Webkit", "Moz", "ms"], Br = {};
function tf(e, t) {
  const s = Br[t];
  if (s)
    return s;
  let n = lt(t);
  if (n !== "filter" && n in e)
    return Br[t] = n;
  n = vr(n);
  for (let r = 0; r < Li.length; r++) {
    const o = Li[r] + n;
    if (o in e)
      return Br[t] = o;
  }
  return t;
}
function sf(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && De(n) && s === n;
}
const Fi = "http://www.w3.org/1999/xlink";
function Ui(e, t, s, n, r, o = lu(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(Fi, t.slice(6, t.length)) : e.setAttributeNS(Fi, t, s) : s == null || o && !Ka(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : gt(s) ? String(s) : s
  );
}
function Wi(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? tc(s) : s);
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
    a === "boolean" ? s = Ka(s) : s == null && a === "string" ? (s = "", i = !0) : a === "number" && (s = 0, i = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function fs(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function nf(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const Bi = /* @__PURE__ */ Symbol("_vei");
function rf(e, t, s, n, r = null) {
  const o = e[Bi] || (e[Bi] = {}), i = o[t];
  if (n && i)
    i.value = n;
  else {
    const [a, l] = lf(t);
    if (n) {
      const c = o[t] = df(
        n,
        r
      );
      fs(e, a, c, l);
    } else i && (nf(e, a, i, l), o[t] = void 0);
  }
}
const of = /(Once|Passive|Capture)$/, af = /^on:?(?:Once|Passive|Capture)$/;
function lf(e) {
  let t, s;
  for (; (s = e.match(of)) && !af.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : bs(e.slice(2)), t];
}
let Hr = 0;
const cf = /* @__PURE__ */ Promise.resolve(), uf = () => Hr || (cf.then(() => Hr = 0), Hr = Date.now());
function df(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if (K(r)) {
      const o = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        o.call(n), n._stopped = !0;
      };
      const i = r.slice(), a = [n];
      for (let l = 0; l < i.length && !n._stopped; l++) {
        const c = i[l];
        c && St(
          c,
          t,
          5,
          a
        );
      }
    } else
      St(
        r,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = uf(), s;
}
const Hi = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, ff = (e, t, s, n, r, o) => {
  const i = r === "svg";
  t === "class" ? Jd(e, n, i) : t === "style" ? ef(e, s, n) : pr(t) ? hr(t) || rf(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : mf(e, t, n, i)) ? (Wi(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && Ui(e, t, n, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (pf(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !De(n))) ? Wi(e, lt(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), Ui(e, t, n, i));
};
function mf(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && Hi(t) && ue(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return Hi(t) && De(s) ? !1 : t in e;
}
function pf(e, t) {
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
  return K(t) ? (s) => Zn(t, s) : t;
};
function hf(e) {
  e.target.composing = !0;
}
function Zi(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const jt = /* @__PURE__ */ Symbol("_assign"), Vn = /* @__PURE__ */ Symbol("_initialValue");
function Zr(e, t, s) {
  return t && (e = e.trim()), s && (e = br(e)), e;
}
const Cn = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[Vn] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[Vn] = e.defaultValue.replace(/\r\n?/g, `
`))), e[jt] = Ws(r);
    const o = n || r.props && r.props.type === "number";
    fs(e, t ? "change" : "input", (i) => {
      i.target.composing || e[jt](Zr(e.value, s, o));
    }), (s || o) && fs(e, "change", () => {
      e.value = Zr(e.value, s, o);
    }), t || (fs(e, "compositionstart", hf), fs(e, "compositionend", Zi), fs(e, "change", Zi));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[Vn];
    delete e[Vn], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[jt](Zr(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, i) {
    if (e[jt] = Ws(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? br(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, gf = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[jt] = Ws(s), fs(e, "change", () => {
      const n = e._modelValue, r = An(e), o = e.checked, i = e[jt];
      if (K(n)) {
        const a = Lo(n, r), l = a !== -1;
        if (o && !l)
          i(n.concat(r));
        else if (!o && l) {
          const c = [...n];
          c.splice(a, 1), i(c);
        }
      } else if (ts(n)) {
        const a = new Set(n);
        o ? a.add(r) : a.delete(r), i(a);
      } else
        i(sc(e, o));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: Gi,
  beforeUpdate(e, t, s) {
    e[jt] = Ws(s), Gi(e, t, s);
  }
};
function Gi(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let r;
  if (K(t))
    r = Lo(t, n.props.value) > -1;
  else if (ts(t))
    r = t.has(n.props.value);
  else {
    if (t === s) return;
    r = ss(t, sc(e, !0));
  }
  e.checked !== r && (e.checked = r);
}
const si = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, fs(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? br(An(l)) : An(l)
      ), o = e.multiple, i = o ? ts(e._modelValue) ? new Set(r) : r : r[0], a = e._pendingValue = [
        o,
        o ? K(i) ? r.slice() : r : i
      ];
      try {
        e[jt](i);
      } finally {
        Sr(() => {
          e._pendingValue === a && (e._pendingValue = void 0);
        });
      }
    }), e[jt] = Ws(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    qi(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[jt] = Ws(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !yf(t, s[1], s[0])) && qi(e, t);
  }
};
function yf(e, t, s) {
  if (!s || K(e)) return ss(e, t);
  if (ts(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function qi(e, t) {
  const s = e.multiple, n = K(t);
  if (!(s && !n && !ts(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const i = e.options[r], a = An(i);
      if (s)
        if (n) {
          const l = typeof a;
          l === "string" || l === "number" ? i.selected = t.some((c) => String(c) === String(a)) : i.selected = Lo(t, a) > -1;
        } else
          i.selected = t.has(a);
      else if (ss(An(i), t)) {
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
function sc(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const vf = ["ctrl", "shift", "alt", "meta"], bf = {
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
  exact: (e, t) => vf.some((s) => e[`${s}Key`] && !t.includes(s))
}, _f = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = bf[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, xf = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
}, wf = (e, t) => {
  const s = e._withKeys || (e._withKeys = {}), n = t.join(".");
  return s[n] || (s[n] = ((r) => {
    if (!("key" in r))
      return;
    const o = bs(r.key);
    if (t.some(
      (i) => i === o || xf[i] === o
    ))
      return e(r);
  }));
}, kf = /* @__PURE__ */ Qe({ patchProp: ff }, qd);
let Ki;
function Sf() {
  return Ki || (Ki = Ed(kf));
}
const Cf = ((...e) => {
  const t = Sf().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = Rf(n);
    if (!r) return;
    const o = t._component;
    !ue(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = s(r, !1, Af(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function Af(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function Rf(e) {
  return De(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let nc;
const Ir = (e) => nc = e, rc = (
  /* istanbul ignore next */
  Symbol()
);
function wo(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var gn;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(gn || (gn = {}));
function Ef() {
  const e = Xa(!0), t = e.run(() => /* @__PURE__ */ Z({}));
  let s = [], n = [];
  const r = qo({
    install(o) {
      Ir(r), r._a = o, o.provide(rc, r), o.config.globalProperties.$pinia = r, n.forEach((i) => s.push(i)), n = [];
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
const oc = () => {
};
function Ji(e, t, s, n = oc) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && Fo() && el(r), r;
}
function Ms(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const Of = (e) => e(), Yi = Symbol(), Gr = Symbol();
function ko(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    wo(r) && wo(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ Le(n) && !/* @__PURE__ */ Dt(n) ? e[s] = ko(r, n) : e[s] = n;
  }
  return e;
}
const Tf = (
  /* istanbul ignore next */
  Symbol()
);
function If(e) {
  return !wo(e) || !Object.prototype.hasOwnProperty.call(e, Tf);
}
const { assign: as } = Object;
function Nf(e) {
  return !!(/* @__PURE__ */ Le(e) && e.effect);
}
function Pf(e, t, s, n) {
  const { state: r, actions: o, getters: i } = t, a = s.state.value[e];
  let l;
  function c() {
    a || (s.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ Tu(s.state.value[e]);
    return as(u, o, Object.keys(i || {}).reduce((d, m) => (d[m] = qo(Te(() => {
      Ir(s);
      const h = s._s.get(e);
      return i[m].call(h, h);
    })), d), {}));
  }
  return l = ic(e, c, t, s, n, !0), l;
}
function ic(e, t, s = {}, n, r, o) {
  let i;
  const a = as({ actions: {} }, s), l = { deep: !0 };
  let c, u, d = /* @__PURE__ */ new Set(), m = /* @__PURE__ */ new Set(), h;
  const S = n.state.value[e];
  !o && !S && (n.state.value[e] = {});
  let x;
  function z(_) {
    let V;
    c = u = !1, typeof _ == "function" ? (_(n.state.value[e]), V = {
      type: gn.patchFunction,
      storeId: e,
      events: h
    }) : (ko(n.state.value[e], _), V = {
      type: gn.patchObject,
      payload: _,
      storeId: e,
      events: h
    });
    const fe = x = Symbol();
    Sr().then(() => {
      x === fe && (c = !0);
    }), u = !0, Ms(d, V, n.state.value[e]);
  }
  const $ = o ? function() {
    const { state: V } = s, fe = V ? V() : {};
    this.$patch((ke) => {
      as(ke, fe);
    });
  } : (
    /* istanbul ignore next */
    oc
  );
  function g() {
    i.stop(), d.clear(), m.clear(), n._s.delete(e);
  }
  const E = (_, V = "") => {
    if (Yi in _)
      return _[Gr] = V, _;
    const fe = function() {
      Ir(n);
      const ke = Array.from(arguments), N = /* @__PURE__ */ new Set(), se = /* @__PURE__ */ new Set();
      function Re(X) {
        N.add(X);
      }
      function ye(X) {
        se.add(X);
      }
      Ms(m, {
        args: ke,
        name: fe[Gr],
        store: J,
        after: Re,
        onError: ye
      });
      let de;
      try {
        de = _.apply(this && this.$id === e ? this : J, ke);
      } catch (X) {
        throw Ms(se, X), X;
      }
      return de instanceof Promise ? de.then((X) => (Ms(N, X), X)).catch((X) => (Ms(se, X), Promise.reject(X))) : (Ms(N, de), de);
    };
    return fe[Yi] = !0, fe[Gr] = V, fe;
  }, P = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: Ji.bind(null, m),
    $patch: z,
    $reset: $,
    $subscribe(_, V = {}) {
      const fe = Ji(d, _, V.detached, () => ke()), ke = i.run(() => Os(() => n.state.value[e], (N) => {
        (V.flush === "sync" ? u : c) && _({
          storeId: e,
          type: gn.direct,
          events: h
        }, N);
      }, as({}, l, V)));
      return fe;
    },
    $dispose: g
  }, J = /* @__PURE__ */ In(P);
  n._s.set(e, J);
  const oe = (n._a && n._a.runWithContext || Of)(() => n._e.run(() => (i = Xa()).run(() => t({ action: E }))));
  for (const _ in oe) {
    const V = oe[_];
    if (/* @__PURE__ */ Le(V) && !Nf(V) || /* @__PURE__ */ Dt(V))
      o || (S && If(V) && (/* @__PURE__ */ Le(V) ? V.value = S[_] : ko(V, S[_])), n.state.value[e][_] = V);
    else if (typeof V == "function") {
      const fe = E(V, _);
      oe[_] = fe, a.actions[_] = V;
    }
  }
  return as(J, oe), as(/* @__PURE__ */ xe(J), oe), Object.defineProperty(J, "$state", {
    get: () => n.state.value[e],
    set: (_) => {
      z((V) => {
        as(V, _);
      });
    }
  }), n._p.forEach((_) => {
    as(J, i.run(() => _({
      store: J,
      app: n._a,
      pinia: n,
      options: a
    })));
  }), S && o && s.hydrate && s.hydrate(J.$state, S), c = !0, u = !0, J;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function Xs(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(i, a) {
    const l = Jo();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? dt(rc, null) : null), i && Ir(i), i = nc, i._s.has(e) || (r ? ic(e, t, n, i) : Pf(e, n, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const zs = typeof document < "u";
function ac(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function Mf(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && ac(e.default);
}
const Me = Object.assign;
function qr(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = Ct(r) ? r.map(e) : e(r);
  }
  return s;
}
const yn = () => {
}, Ct = Array.isArray;
function Qi(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const lc = /#/g, $f = /&/g, jf = /\//g, zf = /=/g, Df = /\?/g, cc = /\+/g, Vf = /%5B/g, Lf = /%5D/g, uc = /%5E/g, Ff = /%60/g, dc = /%7B/g, Uf = /%7C/g, fc = /%7D/g, Wf = /%20/g;
function ni(e) {
  return e == null ? "" : encodeURI("" + e).replace(Uf, "|").replace(Vf, "[").replace(Lf, "]");
}
function Bf(e) {
  return ni(e).replace(dc, "{").replace(fc, "}").replace(uc, "^");
}
function So(e) {
  return ni(e).replace(cc, "%2B").replace(Wf, "+").replace(lc, "%23").replace($f, "%26").replace(Ff, "`").replace(dc, "{").replace(fc, "}").replace(uc, "^");
}
function Hf(e) {
  return So(e).replace(zf, "%3D");
}
function Zf(e) {
  return ni(e).replace(lc, "%23").replace(Df, "%3F");
}
function Gf(e) {
  return Zf(e).replace(jf, "%2F");
}
function Rn(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const qf = /\/$/, Kf = (e) => e.replace(qf, "");
function Kr(e, t, s = "/") {
  let n, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (n = n || t.slice(0, a), i = t.slice(a, t.length)), n = Xf(n ?? t, s), {
    fullPath: n + o + i,
    path: n,
    query: r,
    hash: Rn(i)
  };
}
function Jf(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Yf(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && Bs(t.matched[n], s.matched[r]) && mc(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function Bs(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function mc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!Qf(e[s], t[s])) return !1;
  return !0;
}
function Qf(e, t) {
  return Ct(e) ? Xi(e, t) : Ct(t) ? Xi(t, e) : e?.valueOf() === t?.valueOf();
}
function Xi(e, t) {
  return Ct(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function Xf(e, t) {
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
const os = {
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
let Co = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), ea = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const Jr = "";
function em(e) {
  if (!e) if (zs) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), Kf(e);
}
const tm = /^[^#]+#/;
function sm(e, t) {
  return e.replace(tm, "#") + t;
}
function nm(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const rm = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function om(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = nm(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function ta(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Ao = /* @__PURE__ */ new Map();
function im(e, t) {
  Ao.set(e, t);
}
function am(e) {
  const t = Ao.get(e);
  return Ao.delete(e), t;
}
function lm(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function pc(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let Ve = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const hc = Symbol("");
Ve.MATCHER_NOT_FOUND + "", Ve.NAVIGATION_GUARD_REDIRECT + "", Ve.NAVIGATION_ABORTED + "", Ve.NAVIGATION_CANCELLED + "", Ve.NAVIGATION_DUPLICATED + "";
function Hs(e, t) {
  return Me(/* @__PURE__ */ new Error(), {
    type: e,
    [hc]: !0
  }, t);
}
function Zt(e, t) {
  return e instanceof Error && hc in e && (t == null || !!(e.type & t));
}
const cm = [
  "params",
  "query",
  "hash"
];
function um(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of cm) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function dm(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(cc, " "), o = r.indexOf("="), i = Rn(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : Rn(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      Ct(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function sa(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Hf(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (Ct(n) ? n.map((r) => r && So(r)) : [n && So(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function fm(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = Ct(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const mm = Symbol(""), na = Symbol(""), Nr = Symbol(""), ri = Symbol(""), Ro = Symbol("");
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
function us(e, t, s, n, r, o = (i) => i()) {
  const i = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (m) => {
      m === !1 ? l(Hs(Ve.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : m instanceof Error ? l(m) : lm(m) ? l(Hs(Ve.NAVIGATION_GUARD_REDIRECT, {
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
        if (ac(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(us(c, s, n, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const d = Mf(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = d;
            const m = (d.__vccOpts || d)[t];
            return m && us(m, s, n, i, a, r)();
          }));
        }
    }
  return o;
}
function pm(e, t) {
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
function hm(e = "") {
  let t = [], s = [[Jr, {}]], n = 0;
  e = em(e);
  function r(a, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const d = {
      direction: c,
      delta: u,
      type: Co.pop
    };
    for (const m of t) m(a, l, d);
  }
  const i = {
    location: Jr,
    state: {},
    base: e,
    createHref: sm.bind(null, e),
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
      t = [], s = [[Jr, {}]], n = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? ea.back : ea.forward;
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
let Rs = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var Be = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(Be || {});
const gm = {
  type: Rs.Static,
  value: ""
}, ym = /[a-zA-Z0-9_]/;
function vm(e) {
  if (!e) return [[]];
  if (e === "/") return [[gm]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(h) {
    throw new Error(`ERR (${s})/"${c}": ${h}`);
  }
  let s = Be.Static, n = s;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function d() {
    c && (s === Be.Static ? o.push({
      type: Rs.Static,
      value: c
    }) : s === Be.Param || s === Be.ParamRegExp || s === Be.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: Rs.Param,
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
    if (l = e[a++], l === "\\" && s !== Be.ParamRegExp) {
      n = s, s = Be.EscapeNext;
      continue;
    }
    switch (s) {
      case Be.Static:
        l === "/" ? (c && d(), i()) : l === ":" ? (d(), s = Be.Param) : m();
        break;
      case Be.EscapeNext:
        m(), s = n;
        break;
      case Be.Param:
        l === "(" ? s = Be.ParamRegExp : ym.test(l) ? m() : (d(), s = Be.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case Be.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : s = Be.ParamRegExpEnd : u += l;
        break;
      case Be.ParamRegExpEnd:
        d(), s = Be.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === Be.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), d(), i(), r;
}
const ra = "[^/]+?", bm = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var ot = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(ot || {});
const _m = /[.+*?^${}()[\]/\\]/g;
function xm(e, t) {
  const s = Me({}, bm, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [ot.Root];
    s.strict && !c.length && (r += "/");
    for (let d = 0; d < c.length; d++) {
      const m = c[d];
      let h = ot.Segment + (s.sensitive ? ot.BonusCaseSensitive : 0);
      if (m.type === Rs.Static)
        d || (r += "/"), r += m.value.replace(_m, "\\$&"), h += ot.Static;
      else if (m.type === Rs.Param) {
        const { value: S, repeatable: x, optional: z, regexp: $ } = m;
        o.push({
          name: S,
          repeatable: x,
          optional: z
        });
        const g = $ || ra;
        if (g !== ra) {
          h += ot.BonusCustomRegExp;
          try {
            `${g}`;
          } catch (P) {
            throw new Error(`Invalid custom RegExp for param "${S}" (${g}): ` + P.message);
          }
        }
        let E = x ? `((?:${g})(?:/(?:${g}))*)` : `(${g})`;
        d || (E = z && c.length < 2 ? `(?:/${E})` : "/" + E), z && (E += "?"), r += E, h += ot.Dynamic, z && (h += ot.BonusOptional), x && (h += ot.BonusRepeatable), g === ".*" && (h += ot.BonusWildcard);
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
      const h = u[m] || "", S = o[m - 1];
      d[S.name] = h && S.repeatable ? h.split("/") : h;
    }
    return d;
  }
  function l(c) {
    let u = "", d = !1;
    for (const m of e) {
      (!d || !u.endsWith("/")) && (u += "/"), d = !1;
      for (const h of m) if (h.type === Rs.Static) u += h.value;
      else if (h.type === Rs.Param) {
        const { value: S, repeatable: x, optional: z } = h, $ = S in c ? c[S] : "";
        if (Ct($) && !x) throw new Error(`Provided param "${S}" is an array but it is not repeatable (* or + modifiers)`);
        const g = Ct($) ? $.join("/") : $;
        if (!g) if (z)
          m.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : d = !0);
        else throw new Error(`Missing required param "${S}"`);
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
function wm(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === ot.Static + ot.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === ot.Static + ot.Segment ? 1 : -1 : 0;
}
function gc(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = wm(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (oa(n)) return 1;
    if (oa(r)) return -1;
  }
  return r.length - n.length;
}
function oa(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const km = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function Sm(e, t, s) {
  const n = xm(vm(e.path), s), r = Me(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function Cm(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = Qi(km, t);
  function r(d) {
    return n.get(d);
  }
  function o(d, m, h) {
    const S = !h, x = aa(d);
    x.aliasOf = h && h.record;
    const z = Qi(t, d), $ = [x];
    if ("alias" in d) {
      const P = typeof d.alias == "string" ? [d.alias] : d.alias;
      for (const J of P) $.push(aa(Me({}, x, {
        components: h ? h.record.components : x.components,
        path: J,
        aliasOf: h ? h.record : x
      })));
    }
    let g, E;
    for (const P of $) {
      const { path: J } = P;
      if (m && J[0] !== "/") {
        const be = m.record.path, oe = be[be.length - 1] === "/" ? "" : "/";
        P.path = m.record.path + (J && oe + J);
      }
      if (g = Sm(P, m, z), h ? h.alias.push(g) : (E = E || g, E !== g && E.alias.push(g), S && d.name && !la(g) && i(d.name)), yc(g) && l(g), x.children) {
        const be = x.children;
        for (let oe = 0; oe < be.length; oe++) o(be[oe], g, h && h.children[oe]);
      }
      h = h || g;
    }
    return E ? () => {
      i(E);
    } : yn;
  }
  function i(d) {
    if (pc(d)) {
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
    const m = Em(d, s);
    s.splice(m, 0, d), d.record.name && !la(d) && n.set(d.record.name, d);
  }
  function c(d, m) {
    let h, S = {}, x, z;
    if ("name" in d && d.name) {
      if (h = n.get(d.name), !h) throw Hs(Ve.MATCHER_NOT_FOUND, { location: d });
      z = h.record.name, S = Me(ia(m.params, h.keys.filter((E) => !E.optional).concat(h.parent ? h.parent.keys.filter((E) => E.optional) : []).map((E) => E.name)), d.params && ia(d.params, h.keys.map((E) => E.name))), x = h.stringify(S);
    } else if (d.path != null)
      x = d.path, h = s.find((E) => E.re.test(x)), h && (S = h.parse(x), z = h.record.name);
    else {
      if (h = m.name ? n.get(m.name) : s.find((E) => E.re.test(m.path)), !h) throw Hs(Ve.MATCHER_NOT_FOUND, {
        location: d,
        currentLocation: m
      });
      z = h.record.name, S = Me({}, m.params, d.params), x = h.stringify(S);
    }
    const $ = [];
    let g = h;
    for (; g; )
      $.unshift(g.record), g = g.parent;
    return {
      name: z,
      path: x,
      params: S,
      matched: $,
      meta: Rm($)
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
function ia(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function aa(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: Am(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function Am(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function la(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function Rm(e) {
  return e.reduce((t, s) => Me(t, s.meta), {});
}
function Em(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    gc(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = Om(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function Om(e) {
  let t = e;
  for (; t = t.parent; ) if (yc(t) && gc(e, t) === 0) return t;
}
function yc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function ca(e) {
  const t = dt(Nr), s = dt(ri), n = Te(() => {
    const l = C(e.to);
    return t.resolve(l);
  }), r = Te(() => {
    const { matched: l } = n.value, { length: c } = l, u = l[c - 1], d = s.matched;
    if (!u || !d.length) return -1;
    const m = d.findIndex(Bs.bind(null, u));
    if (m > -1) return m;
    const h = ua(l[c - 2]);
    return c > 1 && ua(u) === h && d[d.length - 1].path !== h ? d.findIndex(Bs.bind(null, l[c - 2])) : m;
  }), o = Te(() => r.value > -1 && Pm(s.params, n.value.params)), i = Te(() => r.value > -1 && r.value === s.matched.length - 1 && mc(s.params, n.value.params));
  function a(l = {}) {
    if (Nm(l)) {
      const c = t[C(e.replace) ? "replace" : "push"](C(e.to)).catch(yn);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: Te(() => n.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function Tm(e) {
  return e.length === 1 ? e[0] : e;
}
const Im = /* @__PURE__ */ yt({
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
  useLink: ca,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ In(ca(e)), { options: n } = dt(Nr), r = Te(() => ({
      [da(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [da(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && Tm(t.default(s));
      return e.custom ? o : Sn("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), vc = Im;
function Nm(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function Pm(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!Ct(r) || r.length !== n.length || n.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function ua(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const da = (e, t, s) => e ?? t ?? s, Mm = /* @__PURE__ */ yt({
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
    const n = dt(Ro), r = Te(() => e.route || n.value), o = dt(na, 0), i = Te(() => {
      let c = C(o);
      const { matched: u } = r.value;
      let d;
      for (; (d = u[c]) && !d.components; ) c++;
      return c;
    }), a = Te(() => r.value.matched[i.value]);
    Gn(na, Te(() => i.value + 1)), Gn(mm, a), Gn(Ro, r);
    const l = /* @__PURE__ */ Z();
    return Os(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, d], [m, h, S]) => {
      u && (u.instances[d] = c, h && h !== u && c && c === m && (u.leaveGuards.size || (u.leaveGuards = h.leaveGuards), u.updateGuards.size || (u.updateGuards = h.updateGuards))), c && u && (!h || !Bs(u, h) || !m) && (u.enterCallbacks[d] || []).forEach((x) => x(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, d = a.value, m = d && d.components[u];
      if (!m) return fa(s.default, {
        Component: m,
        route: c
      });
      const h = d.props[u], S = h ? h === !0 ? c.params : typeof h == "function" ? h(c) : h : null, z = Sn(m, Me({}, S, t, {
        onVnodeUnmounted: ($) => {
          $.component.isUnmounted && (d.instances[u] = null);
        },
        ref: l
      }));
      return fa(s.default, {
        Component: z,
        route: c
      }) || z;
    };
  }
});
function fa(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const bc = Mm;
function $m(e) {
  const t = Cm(e.routes, e), s = e.parseQuery || dm, n = e.stringifyQuery || sa, r = e.history, o = nn(), i = nn(), a = nn(), l = /* @__PURE__ */ mn(os);
  let c = os;
  zs && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = qr.bind(null, (k) => "" + k), d = qr.bind(null, Gf), m = qr.bind(null, Rn);
  function h(k, W) {
    let T, ne;
    return pc(k) ? (T = t.getRecordMatcher(k), ne = W) : ne = k, t.addRoute(ne, T);
  }
  function S(k) {
    const W = t.getRecordMatcher(k);
    W && t.removeRoute(W);
  }
  function x() {
    return t.getRoutes().map((k) => k.record);
  }
  function z(k) {
    return !!t.getRecordMatcher(k);
  }
  function $(k, W) {
    if (W = Me({}, W || l.value), typeof k == "string") {
      const b = Kr(s, k, W.path), w = t.resolve({ path: b.path }, W), A = r.createHref(b.fullPath);
      return Me(b, w, {
        params: m(w.params),
        hash: Rn(b.hash),
        redirectedFrom: void 0,
        href: A
      });
    }
    let T;
    if (k.path != null)
      T = Me({}, k, { path: Kr(s, k.path, W.path).path });
    else {
      const b = Me({}, k.params);
      for (const w in b) b[w] == null && delete b[w];
      T = Me({}, k, { params: d(b) }), W.params = d(W.params);
    }
    const ne = t.resolve(T, W), f = k.hash || "";
    ne.params = u(m(ne.params));
    const p = Jf(n, Me({}, k, {
      hash: Bf(f),
      path: ne.path
    })), y = r.createHref(p);
    return Me({
      fullPath: p,
      hash: f,
      query: n === sa ? fm(k.query) : k.query || {}
    }, ne, {
      redirectedFrom: void 0,
      href: y
    });
  }
  function g(k) {
    return typeof k == "string" ? Kr(s, k, l.value.path) : Me({}, k);
  }
  function E(k, W) {
    if (c !== k) return Hs(Ve.NAVIGATION_CANCELLED, {
      from: W,
      to: k
    });
  }
  function P(k) {
    return oe(k);
  }
  function J(k) {
    return P(Me(g(k), { replace: !0 }));
  }
  function be(k, W) {
    const T = k.matched[k.matched.length - 1];
    if (T && T.redirect) {
      const { redirect: ne } = T;
      let f = typeof ne == "function" ? ne(k, W) : ne;
      return typeof f == "string" && (f = f.includes("?") || f.includes("#") ? f = g(f) : { path: f }, f.params = {}), Me({
        query: k.query,
        hash: k.hash,
        params: f.path != null ? {} : k.params
      }, f);
    }
  }
  function oe(k, W) {
    const T = c = $(k), ne = l.value, f = k.state, p = k.force, y = k.replace === !0, b = be(T, ne);
    if (b) return oe(Me(g(b), {
      state: typeof b == "object" ? Me({}, f, b.state) : f,
      force: p,
      replace: y
    }), W || T);
    const w = T;
    w.redirectedFrom = W;
    let A;
    return !p && Yf(n, ne, T) && (A = Hs(Ve.NAVIGATION_DUPLICATED, {
      to: w,
      from: ne
    }), nt(ne, ne, !0, !1)), (A ? Promise.resolve(A) : fe(w, ne)).catch((O) => Zt(O) ? Zt(O, Ve.NAVIGATION_GUARD_REDIRECT) ? O : G(O) : ge(O, w, ne)).then((O) => {
      if (O) {
        if (Zt(O, Ve.NAVIGATION_GUARD_REDIRECT))
          return oe(Me({ replace: y }, g(O.to), {
            state: typeof O.to == "object" ? Me({}, f, O.to.state) : f,
            force: p
          }), W || w);
      } else O = N(w, ne, !0, y, f);
      return ke(w, ne, O), O;
    });
  }
  function _(k, W) {
    const T = E(k, W);
    return T ? Promise.reject(T) : Promise.resolve();
  }
  function V(k) {
    const W = xt.values().next().value;
    return W && typeof W.runWithContext == "function" ? W.runWithContext(k) : k();
  }
  function fe(k, W) {
    let T;
    const [ne, f, p] = pm(k, W);
    T = Yr(ne.reverse(), "beforeRouteLeave", k, W);
    for (const b of ne) b.leaveGuards.forEach((w) => {
      T.push(us(w, k, W));
    });
    const y = _.bind(null, k, W);
    return T.push(y), Ee(T).then(() => {
      T = [];
      for (const b of o.list()) T.push(us(b, k, W));
      return T.push(y), Ee(T);
    }).then(() => {
      T = Yr(f, "beforeRouteUpdate", k, W);
      for (const b of f) b.updateGuards.forEach((w) => {
        T.push(us(w, k, W));
      });
      return T.push(y), Ee(T);
    }).then(() => {
      T = [];
      for (const b of p) if (b.beforeEnter) if (Ct(b.beforeEnter)) for (const w of b.beforeEnter) T.push(us(w, k, W));
      else T.push(us(b.beforeEnter, k, W));
      return T.push(y), Ee(T);
    }).then(() => (k.matched.forEach((b) => b.enterCallbacks = {}), T = Yr(p, "beforeRouteEnter", k, W, V), T.push(y), Ee(T))).then(() => {
      T = [];
      for (const b of i.list()) T.push(us(b, k, W));
      return T.push(y), Ee(T);
    }).catch((b) => Zt(b, Ve.NAVIGATION_CANCELLED) ? b : Promise.reject(b));
  }
  function ke(k, W, T) {
    a.list().forEach((ne) => V(() => ne(k, W, T)));
  }
  function N(k, W, T, ne, f) {
    const p = E(k, W);
    if (p) return p;
    const y = W === os, b = zs ? history.state : {};
    T && (ne || y ? r.replace(k.fullPath, Me({ scroll: y && b && b.scroll }, f)) : r.push(k.fullPath, f)), l.value = k, nt(k, W, T, y), G();
  }
  let se;
  function Re() {
    se || (se = r.listen((k, W, T) => {
      if (!ze.listening) return;
      const ne = $(k), f = be(ne, ze.currentRoute.value);
      if (f) {
        oe(Me(f, {
          replace: !0,
          force: !0
        }), ne).catch(yn);
        return;
      }
      c = ne;
      const p = l.value;
      zs && im(ta(p.fullPath, T.delta), rm()), fe(ne, p).catch((y) => Zt(y, Ve.NAVIGATION_ABORTED | Ve.NAVIGATION_CANCELLED) ? y : Zt(y, Ve.NAVIGATION_GUARD_REDIRECT) ? (oe(Me(g(y.to), { force: !0 }), ne).then((b) => {
        Zt(b, Ve.NAVIGATION_ABORTED | Ve.NAVIGATION_DUPLICATED) && !T.delta && T.type === Co.pop && r.go(-1, !1);
      }).catch(yn), Promise.reject()) : (T.delta && r.go(-T.delta, !1), ge(y, ne, p))).then((y) => {
        y = y || N(ne, p, !1), y && (T.delta && !Zt(y, Ve.NAVIGATION_CANCELLED) ? r.go(-T.delta, !1) : T.type === Co.pop && Zt(y, Ve.NAVIGATION_ABORTED | Ve.NAVIGATION_DUPLICATED) && r.go(-1, !1)), ke(ne, p, y);
      }).catch(yn);
    }));
  }
  let ye = nn(), de = nn(), X;
  function ge(k, W, T) {
    G(k);
    const ne = de.list();
    return ne.length ? ne.forEach((f) => f(k, W, T)) : console.error(k), Promise.reject(k);
  }
  function st() {
    return X && l.value !== os ? Promise.resolve() : new Promise((k, W) => {
      ye.add([k, W]);
    });
  }
  function G(k) {
    return X || (X = !k, Re(), ye.list().forEach(([W, T]) => k ? T(k) : W()), ye.reset()), k;
  }
  function nt(k, W, T, ne) {
    const { scrollBehavior: f } = e;
    if (!zs || !f) return Promise.resolve();
    const p = !T && am(ta(k.fullPath, 0)) || (ne || !T) && history.state && history.state.scroll || null;
    return Sr().then(() => f(k, W, p)).then((y) => y && om(y)).catch((y) => ge(y, k, W));
  }
  const Ge = (k) => r.go(k);
  let Bt;
  const xt = /* @__PURE__ */ new Set(), ze = {
    currentRoute: l,
    listening: !0,
    addRoute: h,
    removeRoute: S,
    clearRoutes: t.clearRoutes,
    hasRoute: z,
    getRoutes: x,
    resolve: $,
    options: e,
    push: P,
    replace: J,
    go: Ge,
    back: () => Ge(-1),
    forward: () => Ge(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: de.add,
    isReady: st,
    install(k) {
      k.component("RouterLink", vc), k.component("RouterView", bc), k.config.globalProperties.$router = ze, Object.defineProperty(k.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => C(l)
      }), zs && !Bt && l.value === os && (Bt = !0, P(r.location).catch((ne) => {
      }));
      const W = {};
      for (const ne in os) Object.defineProperty(W, ne, {
        get: () => l.value[ne],
        enumerable: !0
      });
      k.provide(Nr, ze), k.provide(ri, /* @__PURE__ */ gl(W)), k.provide(Ro, l);
      const T = k.unmount;
      xt.add(k), k.unmount = function() {
        xt.delete(k), xt.size < 1 && (c = os, se && se(), se = null, l.value = os, Bt = !1, X = !1), T();
      };
    }
  };
  function Ee(k) {
    return k.reduce((W, T) => W.then(() => V(T)), Promise.resolve());
  }
  return ze;
}
function jm() {
  return dt(Nr);
}
function _c(e) {
  return dt(ri);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ks = {
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
const ma = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Qr(e) {
  return e != null;
}
function zm(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (m) => s[m] ?? m, r = e.size ?? e.width ?? ks.width, o = e.size ?? e.height ?? ks.height, i = e.aliases?.filter((m) => typeof m == "string" && m.trim() !== "").map((m) => `lucide-${m}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? ma(...l) : ma("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? ks["stroke-width"]) * Number(e.size ?? e.width ?? ks.width) / Number(t.size ?? t.width ?? ks.width) : t.strokeWidth ?? ks["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(ks).reduce((m, [h, S]) => (m[n(h)] = S, m), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && Qr(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && Qr(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && Qr(t.height) && {
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
      const [h, S, x] = m, z = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...S } : S;
      return x ? [h, z, x] : [h, z];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Dm = (e) => {
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
const Vm = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Lm = /* @__PURE__ */ Symbol("lucide-icons");
function Fm() {
  return dt(Lm, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Um = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && Vm(e),
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
  ...S
}, { slots: x }) => {
  const {
    size: z,
    color: $,
    strokeWidth: g = 2,
    absoluteStrokeWidth: E = !1,
    nonScalingStroke: P = !1,
    class: J = ""
  } = Fm(), be = Ln(r) || Ln(o) || r === !0 || o === !0 || E === !0, oe = Ln(i) || Ln(a) || i === !0 || a === !0 || P === !0;
  delete S.class;
  const _ = x.default?.(), [, V, fe = []] = zm(n, {
    color: h ?? $,
    width: d ?? u ?? z,
    height: m ?? u ?? z,
    strokeWidth: l ?? c ?? g,
    absoluteStrokeWidth: be,
    nonScalingStroke: oe,
    className: J,
    hasA11yProp: _ != null && _.length > 0 || Dm(S),
    attributes: S
  });
  return Sn("svg", V, [
    ...fe.map(([ke, N]) => Sn(ke, N)),
    ..._ ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function At(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => Sn(
    Um,
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
const Wm = {
  name: "database",
  size: 24,
  node: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]
}, Bm = At(Wm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Hm = {
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
}, xc = At(Hm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Zm = {
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
}, Eo = At(Zm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Gm = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, qm = At(Gm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Km = {
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
}, Jm = At(Km);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ym = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, Pr = At(Ym);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Qm = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, wc = At(Qm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Xm = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, ep = At(Xm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const tp = {
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
}, kc = At(tp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const sp = {
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
}, Sc = At(sp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const np = {
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
}, rp = At(np);
function op(e) {
  return Fo() ? (el(e), !0) : !1;
}
const Xr = /* @__PURE__ */ new WeakMap(), ip = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const s = e[0], n = (t = Or()) == null ? void 0 : t.proxy;
  if (n == null && !Jo())
    throw new Error("injectLocal must be called in setup");
  return n && Xr.has(n) && s in Xr.get(n) ? Xr.get(n)[s] : dt(...e);
}, ap = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const lp = Object.prototype.toString, cp = (e) => lp.call(e) === "[object Object]";
function pa(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function eo(e) {
  return Array.isArray(e) ? e : [e];
}
function up(e, t, s) {
  return Os(
    e,
    t,
    {
      ...s,
      immediate: !0
    }
  );
}
const Cc = ap ? window : void 0;
function dp(e) {
  var t;
  const s = Vs(e);
  return (t = s?.$el) != null ? t : s;
}
function fp(...e) {
  const t = [], s = () => {
    t.forEach((a) => a()), t.length = 0;
  }, n = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = Te(() => {
    const a = eo(Vs(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = up(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => dp(c))) != null ? l : [Cc].filter((c) => c != null),
        eo(Vs(r.value ? e[1] : e[0])),
        eo(C(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Vs(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (s(), !a?.length || !l?.length || !c?.length)
        return;
      const d = cp(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (m) => l.flatMap(
            (h) => c.map((S) => n(m, h, S, d))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), s();
  };
  return op(s), i;
}
// @__NO_SIDE_EFFECTS__
function mp() {
  const e = /* @__PURE__ */ mn(!1), t = Or();
  return t && Ys(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function pp(e) {
  const t = /* @__PURE__ */ mp();
  return Te(() => (t.value, !!e()));
}
const hp = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function gp() {
  const e = Jo() ? /* @__PURE__ */ ip(hp, null) : null;
  return typeof e == "number" ? e : void 0;
}
function yp(e, t = {}) {
  const { window: s = Cc, ssrWidth: n = /* @__PURE__ */ gp() } = t, r = /* @__PURE__ */ pp(() => s && "matchMedia" in s && typeof s.matchMedia == "function"), o = /* @__PURE__ */ mn(typeof n == "number"), i = /* @__PURE__ */ mn(), a = /* @__PURE__ */ mn(!1), l = (c) => {
    a.value = c.matches;
  };
  return Wu(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Vs(e).split(",");
      a.value = c.some((u) => {
        const d = u.includes("not all"), m = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), h = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let S = !!(m || h);
        return m && S && (S = n >= pa(m[1])), h && S && (S = n <= pa(h[1])), d ? !S : S;
      });
      return;
    }
    r.value && (i.value = s.matchMedia(Vs(e)), a.value = i.value.matches);
  }), fp(i, "change", l, { passive: !0 }), Te(() => a.value);
}
const Ac = "comfymodal", oi = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], vp = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function ys(e) {
  return typeof e == "string" && oi.indexOf(e) !== -1;
}
function Fn(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function Rc(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || Fn(r.slice(0, o)) !== Ac) return t;
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
function Ec(e) {
  if (!ys(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + Ac + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function ha(e, t) {
  if (!t || !ys(t.page)) return "none";
  if (!e || !ys(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function bp(e, t) {
  if (e && ys(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = Rc(t);
  return s.matched && ys(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
const _p = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function to(e) {
  return _p.has(e);
}
let ga = 0;
function xp() {
  return ga += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${ga}`;
}
const ii = /* @__PURE__ */ Xs("studio-operations", () => {
  const e = /* @__PURE__ */ Z(/* @__PURE__ */ new Map()), t = Te(() => [...e.value.values()]), s = Te(
    () => t.value.filter((m) => m.status === "pending" || m.status === "running")
  );
  function n(m) {
    return e.value.get(m);
  }
  function r(m) {
    const h = Date.now(), S = xp(), x = m.status === "pending" ? "pending" : "running";
    return e.value.set(S, {
      id: S,
      kind: m.kind,
      label: m.label,
      status: x,
      progress: m.progress,
      message: m.message,
      startedAt: h,
      finishedAt: void 0,
      workspaceId: m.workspaceId
    }), S;
  }
  function o(m, h) {
    const S = e.value.get(m);
    if (!S) return;
    const { status: x, ...z } = h, $ = { ...S, ...z };
    !to(S.status) && x !== void 0 && !to(x) && ($.status = x), e.value.set(m, $);
  }
  function i(m, h, S) {
    const x = e.value.get(m);
    !x || to(x.status) || e.value.set(m, {
      ...x,
      status: h,
      message: S === void 0 ? x.message : S,
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
const H = we.arrayToEnum([
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
]), ds = (e) => {
  switch (typeof e) {
    case "undefined":
      return H.undefined;
    case "string":
      return H.string;
    case "number":
      return Number.isNaN(e) ? H.nan : H.number;
    case "boolean":
      return H.boolean;
    case "function":
      return H.function;
    case "bigint":
      return H.bigint;
    case "symbol":
      return H.symbol;
    case "object":
      return Array.isArray(e) ? H.array : e === null ? H.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? H.promise : typeof Map < "u" && e instanceof Map ? H.map : typeof Set < "u" && e instanceof Set ? H.set : typeof Date < "u" && e instanceof Date ? H.date : H.object;
    default:
      return H.unknown;
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
class ns extends Error {
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
    if (!(t instanceof ns))
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
ns.create = (e) => new ns(e);
const Oo = (e, t) => {
  let s;
  switch (e.code) {
    case I.invalid_type:
      e.received === H.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
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
let wp = Oo;
function kp() {
  return wp;
}
const Sp = (e) => {
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
function L(e, t) {
  const s = kp(), n = Sp({
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
      s === Oo ? void 0 : Oo
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
        return ce;
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
        return ce;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (n[o.value] = i.value);
    }
    return { status: t.value, value: n };
  }
}
const ce = Object.freeze({
  status: "aborted"
}), cn = (e) => ({ status: "dirty", value: e }), _t = (e) => ({ status: "valid", value: e }), va = (e) => e.status === "aborted", ba = (e) => e.status === "dirty", Zs = (e) => e.status === "valid", ir = (e) => typeof Promise < "u" && e instanceof Promise;
var q;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(q || (q = {}));
class Wt {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const _a = (e, t) => {
  if (Zs(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new ns(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function me(e) {
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
class ve {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return ds(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: ds(t.data),
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
        parsedType: ds(t.data),
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
      parsedType: ds(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return _a(n, r);
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
      parsedType: ds(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return Zs(n) ? {
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
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => Zs(n) ? {
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
      parsedType: ds(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (ir(r) ? r : Promise.resolve(r));
    return _a(n, o);
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
    return ps.create(this, this._def);
  }
  nullable() {
    return Js.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return Vt.create(this);
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
      ...me(this._def),
      schema: this,
      typeName: le.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new No({
      ...me(this._def),
      innerType: this,
      defaultValue: s,
      typeName: le.ZodDefault
    });
  }
  brand() {
    return new Gp({
      typeName: le.ZodBranded,
      type: this,
      ...me(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Po({
      ...me(this._def),
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
    return ai.create(this, t);
  }
  readonly() {
    return Mo.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const Cp = /^c[^\s-]{8,}$/i, Ap = /^[0-9a-z]+$/, Rp = /^[0-9A-HJKMNP-TV-Z]{26}$/i, Ep = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, Op = /^[a-z0-9_-]{21}$/i, Tp = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, Ip = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Np = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, Pp = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let so;
const Mp = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, $p = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, jp = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, zp = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, Dp = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, Vp = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, Oc = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", Lp = new RegExp(`^${Oc}$`);
function Tc(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function Fp(e) {
  return new RegExp(`^${Tc(e)}$`);
}
function Up(e) {
  let t = `${Oc}T${Tc(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function Wp(e, t) {
  return !!((t === "v4" || !t) && Mp.test(e) || (t === "v6" || !t) && jp.test(e));
}
function Bp(e, t) {
  if (!Tp.test(e))
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
function Hp(e, t) {
  return !!((t === "v4" || !t) && $p.test(e) || (t === "v6" || !t) && zp.test(e));
}
class Qt extends ve {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== H.string) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: I.invalid_type,
        expected: H.string,
        received: o.parsedType
      }), ce;
    }
    const n = new ct();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), L(r, {
          code: I.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), L(r, {
          code: I.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? L(r, {
          code: I.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && L(r, {
          code: I.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        Np.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "email",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        so || (so = new RegExp(Pp, "u")), so.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "emoji",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        Ep.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "uuid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        Op.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "nanoid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        Cp.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "cuid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        Ap.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "cuid2",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        Rp.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "ulid",
          code: I.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), L(r, {
            validation: "url",
            code: I.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "regex",
        code: I.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? Up(o).test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? Lp.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? Fp(o).test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? Ip.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "duration",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? Wp(t.data, o.version) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "ip",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? Bp(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "jwt",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Hp(t.data, o.version) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "cidr",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? Dp.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "base64",
        code: I.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? Vp.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
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
      ...q.errToObj(n)
    });
  }
  _addCheck(t) {
    return new Qt({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...q.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...q.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...q.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...q.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...q.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...q.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...q.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...q.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...q.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...q.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...q.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...q.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...q.errToObj(t) });
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
      ...q.errToObj(t?.message)
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
      ...q.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...q.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...q.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...q.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...q.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...q.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...q.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...q.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...q.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, q.errToObj(t));
  }
  trim() {
    return new Qt({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new Qt({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new Qt({
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
Qt.create = (e) => new Qt({
  checks: [],
  typeName: le.ZodString,
  coerce: e?.coerce ?? !1,
  ...me(e)
});
function Zp(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class Gs extends ve {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== H.number) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: I.invalid_type,
        expected: H.number,
        received: o.parsedType
      }), ce;
    }
    let n;
    const r = new ct();
    for (const o of this._def.checks)
      o.kind === "int" ? we.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? Zp(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.not_finite,
        message: o.message
      }), r.dirty()) : we.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, q.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, q.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, q.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, q.toString(s));
  }
  setLimit(t, s, n, r) {
    return new Gs({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: q.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Gs({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: q.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: q.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: q.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: q.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: q.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: q.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: q.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: q.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: q.toString(t)
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
Gs.create = (e) => new Gs({
  checks: [],
  typeName: le.ZodNumber,
  coerce: e?.coerce || !1,
  ...me(e)
});
class En extends ve {
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
    if (this._getType(t) !== H.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new ct();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: I.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : we.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return L(s, {
      code: I.invalid_type,
      expected: H.bigint,
      received: s.parsedType
    }), ce;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, q.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, q.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, q.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, q.toString(s));
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
          message: q.toString(r)
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
      message: q.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: q.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: q.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: q.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: q.toString(s)
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
  ...me(e)
});
class To extends ve {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== H.boolean) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: I.invalid_type,
        expected: H.boolean,
        received: n.parsedType
      }), ce;
    }
    return _t(t.data);
  }
}
To.create = (e) => new To({
  typeName: le.ZodBoolean,
  coerce: e?.coerce || !1,
  ...me(e)
});
class ar extends ve {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== H.date) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: I.invalid_type,
        expected: H.date,
        received: o.parsedType
      }), ce;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: I.invalid_date
      }), ce;
    }
    const n = new ct();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), L(r, {
        code: I.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), L(r, {
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
      message: q.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: q.toString(s)
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
  ...me(e)
});
class xa extends ve {
  _parse(t) {
    if (this._getType(t) !== H.symbol) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: I.invalid_type,
        expected: H.symbol,
        received: n.parsedType
      }), ce;
    }
    return _t(t.data);
  }
}
xa.create = (e) => new xa({
  typeName: le.ZodSymbol,
  ...me(e)
});
class wa extends ve {
  _parse(t) {
    if (this._getType(t) !== H.undefined) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: I.invalid_type,
        expected: H.undefined,
        received: n.parsedType
      }), ce;
    }
    return _t(t.data);
  }
}
wa.create = (e) => new wa({
  typeName: le.ZodUndefined,
  ...me(e)
});
class ka extends ve {
  _parse(t) {
    if (this._getType(t) !== H.null) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: I.invalid_type,
        expected: H.null,
        received: n.parsedType
      }), ce;
    }
    return _t(t.data);
  }
}
ka.create = (e) => new ka({
  typeName: le.ZodNull,
  ...me(e)
});
class Sa extends ve {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return _t(t.data);
  }
}
Sa.create = (e) => new Sa({
  typeName: le.ZodAny,
  ...me(e)
});
class Ca extends ve {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return _t(t.data);
  }
}
Ca.create = (e) => new Ca({
  typeName: le.ZodUnknown,
  ...me(e)
});
class vs extends ve {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return L(s, {
      code: I.invalid_type,
      expected: H.never,
      received: s.parsedType
    }), ce;
  }
}
vs.create = (e) => new vs({
  typeName: le.ZodNever,
  ...me(e)
});
class Aa extends ve {
  _parse(t) {
    if (this._getType(t) !== H.undefined) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: I.invalid_type,
        expected: H.void,
        received: n.parsedType
      }), ce;
    }
    return _t(t.data);
  }
}
Aa.create = (e) => new Aa({
  typeName: le.ZodVoid,
  ...me(e)
});
class Vt extends ve {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== H.array)
      return L(s, {
        code: I.invalid_type,
        expected: H.array,
        received: s.parsedType
      }), ce;
    if (r.exactLength !== null) {
      const i = s.data.length > r.exactLength.value, a = s.data.length < r.exactLength.value;
      (i || a) && (L(s, {
        code: i ? I.too_big : I.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (L(s, {
      code: I.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (L(s, {
      code: I.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((i, a) => r.type._parseAsync(new Wt(s, i, s.path, a)))).then((i) => ct.mergeArray(n, i));
    const o = [...s.data].map((i, a) => r.type._parseSync(new Wt(s, i, s.path, a)));
    return ct.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new Vt({
      ...this._def,
      minLength: { value: t, message: q.toString(s) }
    });
  }
  max(t, s) {
    return new Vt({
      ...this._def,
      maxLength: { value: t, message: q.toString(s) }
    });
  }
  length(t, s) {
    return new Vt({
      ...this._def,
      exactLength: { value: t, message: q.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Vt.create = (e, t) => new Vt({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: le.ZodArray,
  ...me(t)
});
function Ds(e) {
  if (e instanceof Ue) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = ps.create(Ds(n));
    }
    return new Ue({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof Vt ? new Vt({
    ...e._def,
    type: Ds(e.element)
  }) : e instanceof ps ? ps.create(Ds(e.unwrap())) : e instanceof Js ? Js.create(Ds(e.unwrap())) : e instanceof Is ? Is.create(e.items.map((t) => Ds(t))) : e;
}
class Ue extends ve {
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
    if (this._getType(t) !== H.object) {
      const c = this._getOrReturnCtx(t);
      return L(c, {
        code: I.invalid_type,
        expected: H.object,
        received: c.parsedType
      }), ce;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof vs && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], d = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new Wt(r, d, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof vs) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && (L(r, {
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
            new Wt(r, d, r.path, u)
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
    return q.errToObj, new Ue({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: q.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new Ue({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new Ue({
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
    return new Ue({
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
    return new Ue({
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
    return new Ue({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of we.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new Ue({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of we.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new Ue({
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
    return new Ue({
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
        for (; o instanceof ps; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new Ue({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return Ic(we.objectKeys(this.shape));
  }
}
Ue.create = (e, t) => new Ue({
  shape: () => e,
  unknownKeys: "strip",
  catchall: vs.create(),
  typeName: le.ZodObject,
  ...me(t)
});
Ue.strictCreate = (e, t) => new Ue({
  shape: () => e,
  unknownKeys: "strict",
  catchall: vs.create(),
  typeName: le.ZodObject,
  ...me(t)
});
Ue.lazycreate = (e, t) => new Ue({
  shape: e,
  unknownKeys: "strip",
  catchall: vs.create(),
  typeName: le.ZodObject,
  ...me(t)
});
class lr extends ve {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return s.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new ns(a.ctx.common.issues));
      return L(s, {
        code: I.invalid_union,
        unionErrors: i
      }), ce;
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
      const a = i.map((l) => new ns(l));
      return L(s, {
        code: I.invalid_union,
        unionErrors: a
      }), ce;
    }
  }
  get options() {
    return this._def.options;
  }
}
lr.create = (e, t) => new lr({
  options: e,
  typeName: le.ZodUnion,
  ...me(t)
});
function Io(e, t) {
  const s = ds(e), n = ds(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === H.object && n === H.object) {
    const r = we.objectKeys(t), o = we.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = Io(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (s === H.array && n === H.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = Io(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === H.date && n === H.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class cr extends ve {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, i) => {
      if (va(o) || va(i))
        return ce;
      const a = Io(o.value, i.value);
      return a.valid ? ((ba(o) || ba(i)) && s.dirty(), { status: s.value, value: a.data }) : (L(n, {
        code: I.invalid_intersection_types
      }), ce);
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
  ...me(s)
});
class Is extends ve {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== H.array)
      return L(n, {
        code: I.invalid_type,
        expected: H.array,
        received: n.parsedType
      }), ce;
    if (n.data.length < this._def.items.length)
      return L(n, {
        code: I.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), ce;
    !this._def.rest && n.data.length > this._def.items.length && (L(n, {
      code: I.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new Wt(n, i, n.path, a)) : null;
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
    ...me(t)
  });
};
class ur extends ve {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== H.object)
      return L(n, {
        code: I.invalid_type,
        expected: H.object,
        received: n.parsedType
      }), ce;
    const r = [], o = this._def.keyType, i = this._def.valueType;
    for (const a in n.data)
      r.push({
        key: o._parse(new Wt(n, a, n.path, a)),
        value: i._parse(new Wt(n, n.data[a], n.path, a)),
        alwaysSet: a in n.data
      });
    return n.common.async ? ct.mergeObjectAsync(s, r) : ct.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof ve ? new ur({
      keyType: t,
      valueType: s,
      typeName: le.ZodRecord,
      ...me(n)
    }) : new ur({
      keyType: Qt.create(),
      valueType: t,
      typeName: le.ZodRecord,
      ...me(s)
    });
  }
}
class Ra extends ve {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== H.map)
      return L(n, {
        code: I.invalid_type,
        expected: H.map,
        received: n.parsedType
      }), ce;
    const r = this._def.keyType, o = this._def.valueType, i = [...n.data.entries()].map(([a, l], c) => ({
      key: r._parse(new Wt(n, a, n.path, [c, "key"])),
      value: o._parse(new Wt(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return ce;
          (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
        }
        return { status: s.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return ce;
        (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
      }
      return { status: s.value, value: a };
    }
  }
}
Ra.create = (e, t, s) => new Ra({
  valueType: t,
  keyType: e,
  typeName: le.ZodMap,
  ...me(s)
});
class On extends ve {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== H.set)
      return L(n, {
        code: I.invalid_type,
        expected: H.set,
        received: n.parsedType
      }), ce;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (L(n, {
      code: I.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (L(n, {
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
          return ce;
        u.status === "dirty" && s.dirty(), c.add(u.value);
      }
      return { status: s.value, value: c };
    }
    const a = [...n.data.values()].map((l, c) => o._parse(new Wt(n, l, n.path, c)));
    return n.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, s) {
    return new On({
      ...this._def,
      minSize: { value: t, message: q.toString(s) }
    });
  }
  max(t, s) {
    return new On({
      ...this._def,
      maxSize: { value: t, message: q.toString(s) }
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
  ...me(t)
});
class Ea extends ve {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
Ea.create = (e, t) => new Ea({
  getter: e,
  typeName: le.ZodLazy,
  ...me(t)
});
class Oa extends ve {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return L(s, {
        received: s.data,
        code: I.invalid_literal,
        expected: this._def.value
      }), ce;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Oa.create = (e, t) => new Oa({
  value: e,
  typeName: le.ZodLiteral,
  ...me(t)
});
function Ic(e, t) {
  return new qs({
    values: e,
    typeName: le.ZodEnum,
    ...me(t)
  });
}
class qs extends ve {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return L(s, {
        expected: we.joinValues(n),
        received: s.parsedType,
        code: I.invalid_type
      }), ce;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return L(s, {
        received: s.data,
        code: I.invalid_enum_value,
        options: n
      }), ce;
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
qs.create = Ic;
class Ta extends ve {
  _parse(t) {
    const s = we.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== H.string && n.parsedType !== H.number) {
      const r = we.objectValues(s);
      return L(n, {
        expected: we.joinValues(r),
        received: n.parsedType,
        code: I.invalid_type
      }), ce;
    }
    if (this._cache || (this._cache = new Set(we.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = we.objectValues(s);
      return L(n, {
        received: n.data,
        code: I.invalid_enum_value,
        options: r
      }), ce;
    }
    return _t(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
Ta.create = (e, t) => new Ta({
  values: e,
  typeName: le.ZodNativeEnum,
  ...me(t)
});
class dr extends ve {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== H.promise && s.common.async === !1)
      return L(s, {
        code: I.invalid_type,
        expected: H.promise,
        received: s.parsedType
      }), ce;
    const n = s.parsedType === H.promise ? s.data : Promise.resolve(s.data);
    return _t(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
dr.create = (e, t) => new dr({
  type: e,
  typeName: le.ZodPromise,
  ...me(t)
});
class Ks extends ve {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === le.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (i) => {
        L(n, i), i.fatal ? s.abort() : s.dirty();
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
            return ce;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? ce : l.status === "dirty" || s.value === "dirty" ? cn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return ce;
        const a = this._def.schema._parseSync({
          data: i,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? ce : a.status === "dirty" || s.value === "dirty" ? cn(a.value) : a;
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
        return a.status === "aborted" ? ce : (a.status === "dirty" && s.dirty(), i(a.value), { status: s.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => a.status === "aborted" ? ce : (a.status === "dirty" && s.dirty(), i(a.value).then(() => ({ status: s.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!Zs(i))
          return ce;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => Zs(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: s.value,
          value: a
        })) : ce);
    we.assertNever(r);
  }
}
Ks.create = (e, t, s) => new Ks({
  schema: e,
  typeName: le.ZodEffects,
  effect: t,
  ...me(s)
});
Ks.createWithPreprocess = (e, t, s) => new Ks({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: le.ZodEffects,
  ...me(s)
});
class ps extends ve {
  _parse(t) {
    return this._getType(t) === H.undefined ? _t(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
ps.create = (e, t) => new ps({
  innerType: e,
  typeName: le.ZodOptional,
  ...me(t)
});
class Js extends ve {
  _parse(t) {
    return this._getType(t) === H.null ? _t(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Js.create = (e, t) => new Js({
  innerType: e,
  typeName: le.ZodNullable,
  ...me(t)
});
class No extends ve {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === H.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
No.create = (e, t) => new No({
  innerType: e,
  typeName: le.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...me(t)
});
class Po extends ve {
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
          return new ns(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new ns(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
Po.create = (e, t) => new Po({
  innerType: e,
  typeName: le.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...me(t)
});
class Ia extends ve {
  _parse(t) {
    if (this._getType(t) !== H.nan) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: I.invalid_type,
        expected: H.nan,
        received: n.parsedType
      }), ce;
    }
    return { status: "valid", value: t.data };
  }
}
Ia.create = (e) => new Ia({
  typeName: le.ZodNaN,
  ...me(e)
});
class Gp extends ve {
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
class ai extends ve {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? ce : o.status === "dirty" ? (s.dirty(), cn(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? ce : r.status === "dirty" ? (s.dirty(), {
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
    return new ai({
      in: t,
      out: s,
      typeName: le.ZodPipeline
    });
  }
}
class Mo extends ve {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (Zs(r) && (r.value = Object.freeze(r.value)), r);
    return ir(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Mo.create = (e, t) => new Mo({
  innerType: e,
  typeName: le.ZodReadonly,
  ...me(t)
});
var le;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(le || (le = {}));
const Ke = Qt.create, no = Gs.create, Un = To.create;
vs.create;
const qp = Vt.create, li = Ue.create;
lr.create;
cr.create;
Is.create;
const Kp = ur.create, $o = qs.create;
dr.create;
ps.create;
Js.create;
const Jp = "comfymodal.studio.vue.";
function Yp() {
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
function Qp() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return Yp();
}
function Nc(e, t, s, n) {
  const r = Jp + e, o = Qp();
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
const Xp = "/comfymodal";
class eh extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function th(e, t) {
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
function sh(e, t) {
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
  } = t, { signal: l, cleanup: c } = sh(o, i);
  try {
    if (l && l.aborted) throw l.reason;
    const u = await s(Xp + e, {
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
      throw new eh(
        u.status,
        th(m, `Request failed with status ${u.status}`),
        m
      );
    return m;
  } finally {
    c();
  }
}
const nh = li({ value: Ke(), label: Ke() }).passthrough(), rh = li({
  gpu: Ke().default(""),
  default_gpu: Ke().default(""),
  available_gpus: qp(nh).default([]),
  persisted_gpu: Ke().default(""),
  output_format: Ke().default("original"),
  quality: no().default(75),
  webp_lossless_compression: Ke().default("balanced"),
  auto_save_local: Un().default(!1),
  save_folder: Ke().default(""),
  save_metadata_sidecar: Un().default(!0),
  preview_default: $o(["off", "on"]).default("off"),
  preview_codec: Ke().default("webp"),
  preview_quality: no().default(70),
  data_saver_default: $o(["off", "on"]).default("off"),
  data_saver_codec: Ke().default("webp"),
  data_saver_quality: no().default(70),
  execution_mode: Ke().default("v2"),
  execution_mode_source: Ke().default(""),
  execution_mode_locked: Un().default(!1),
  engine_migration_notice: Ke().nullable().default(null),
  skip_plan_validation: Un().default(!1),
  golden_gpu_order: Kp(Ke()).default({})
}).passthrough(), oh = li({ status: Ke().optional(), level: Ke().default("off"), effective: Ke().default("off") }).passthrough();
async function Na() {
  return rh.parse(await Ce("/config"));
}
async function ih(e) {
  return Ce("/config", { method: "POST", body: e });
}
async function ah() {
  return oh.parse(await Ce("/profile/level"));
}
async function lh(e) {
  return Ce("/profile/level", { method: "POST", body: { level: e } });
}
const rn = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function Pa(e) {
  const t = {
    outputFormat: String(e.output_format ?? "original"),
    quality: typeof e.quality == "number" ? e.quality : null,
    autoSaveLocal: e.auto_save_local === !0
  };
  if (typeof window > "u") return t;
  const s = {
    output_format: t.outputFormat,
    quality: t.quality ?? 75,
    auto_save_local: t.autoSaveLocal,
    save_folder: String(e.save_folder ?? ""),
    save_metadata_sidecar: e.save_metadata_sidecar !== !1
  };
  window._comfyModalOutputOptions = s;
  try {
    localStorage.setItem(rn.outputFormat, s.output_format), localStorage.setItem(rn.quality, String(s.quality)), localStorage.setItem(rn.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(rn.saveFolder, s.save_folder), localStorage.setItem(rn.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const Pc = "comfymodal-studio";
function ci(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(Pc), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function hs(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(Pc);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
const ch = $o(["comfortable", "compact"]), ro = Nc(
  "shell.density",
  "comfortable",
  ch
), Mc = /* @__PURE__ */ Xs("studio-settings", () => {
  const e = /* @__PURE__ */ Z("studio"), t = /* @__PURE__ */ Z(ro.read()), s = /* @__PURE__ */ Z(null), n = /* @__PURE__ */ Z("off"), r = /* @__PURE__ */ Z(!1), o = /* @__PURE__ */ Z(!1), i = /* @__PURE__ */ Z(null), a = /* @__PURE__ */ Z(!1);
  let l = null;
  const c = Te(() => s.value?.gpu ?? ""), u = Te(() => s.value ? {
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
      const [g, E] = await Promise.all([Na(), ah()]);
      s.value = g, n.value = E.effective || E.level, Pa(g), a.value = !0;
    } catch (g) {
      throw i.value = g instanceof Error ? g.message : "Could not load Settings", g;
    } finally {
      r.value = !1;
    }
  }
  async function m(g) {
    o.value = !0, i.value = null;
    try {
      await ih(g);
      const E = await Na();
      s.value = E, Pa(E), hs("settings");
    } catch (E) {
      throw i.value = E instanceof Error ? E.message : "Could not save Settings", E;
    } finally {
      o.value = !1;
    }
  }
  async function h(g) {
    await lh(g), n.value = g, hs("settings");
  }
  async function S() {
    l || (l = ci((g) => {
      g === "settings" && !r.value && d();
    })), a.value || await d();
  }
  function x(g) {
    e.value = g;
  }
  function z(g) {
    t.value = g, ro.write(g);
  }
  function $() {
    e.value = "studio", t.value = "comfortable", ro.write("comfortable");
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
    initialize: S,
    save: m,
    setProfile: h,
    setSection: x,
    setDensity: z,
    reset: $
  };
});
function uh(e) {
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
function dh(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function fh() {
  return Ce("/workspaces");
}
async function mh(e) {
  return Ce("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function Ma() {
  return $c(await Ce("/deploy/status"));
}
async function ph() {
  return Ce("/deploy", { method: "POST" });
}
async function hh() {
  return Ce("/deploy/log");
}
async function gh(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return Ce(`/studio/inventory/refresh${t}`);
}
async function yh(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return Ce(`/studio/models${s}`);
}
async function vh(e = !1) {
  return Ce("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function bh() {
  return Ce("/studio/custom-nodes");
}
async function _h() {
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
function xh(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function wh(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function kh(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    xh(s), i += 1, o && o(i);
    const a = await n(s, i);
    if (r(a)) return a;
    await wh(t, s);
  }
}
const ui = /* @__PURE__ */ Xs("studio-infrastructure", () => {
  const e = /* @__PURE__ */ Z("unknown"), t = /* @__PURE__ */ Z(null), s = /* @__PURE__ */ Z(null), n = /* @__PURE__ */ Z([]), r = /* @__PURE__ */ Z(null), o = /* @__PURE__ */ Z($c(null)), i = /* @__PURE__ */ Z(null), a = /* @__PURE__ */ Z([]), l = /* @__PURE__ */ Z([]), c = /* @__PURE__ */ Z(!1), u = /* @__PURE__ */ Z(null), d = fr();
  let m = null;
  const h = Te(() => n.value.find((N) => N.isActive) ?? null);
  function S(N, se) {
    e.value = N, t.value = se ?? null;
  }
  function x(N) {
    s.value = N;
  }
  function z() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  async function $() {
    const N = uh(await fh());
    n.value = N.rows, r.value = N.activeId;
  }
  async function g() {
    o.value = await Ma(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function E() {
    const N = await d.run(async (se) => {
      const [Re, ye] = await Promise.all([yh(), bh()]);
      return se.aborted ? null : { modelResult: Re, nodeResult: ye };
    });
    N.stale || !N.value || (a.value = N.value.modelResult.models ?? [], l.value = N.value.nodeResult.custom_nodes ?? []);
  }
  async function P() {
    c.value = !0, u.value = null;
    try {
      await Promise.all([$(), g(), E()]), s.value = "server inventory loaded";
    } catch (N) {
      throw u.value = N instanceof Error ? N.message : "Could not load infrastructure", N;
    } finally {
      c.value = !1;
    }
  }
  async function J() {
    m || (m = ci((N) => {
      N === "workspace" && !c.value && P();
    })), n.value.length || await P();
  }
  async function be(N) {
    await mh(N), await $(), hs("workspace");
  }
  async function oe() {
    const N = ii(), se = N.start({ kind: "deploy", label: "Deploy workspace" });
    try {
      await ph(), N.patch(se, { status: "running", message: "Deployment started" });
      const Re = await kh({
        intervalMs: 3e3,
        run: async () => {
          const ye = await Ma();
          return o.value = ye, e.value = ye.state, t.value = ye.message || null, N.patch(se, { message: ye.message || `Deployment: ${ye.state}` }), ye;
        },
        done: (ye) => ye.state === "ready" || ye.state === "deployed_unwarmed" || ye.state !== "deploying" && ye.state !== "starting" && ye.state !== "unknown"
      });
      if (!dh(Re.state)) throw new Error(Re.message || `Deployment ended in ${Re.state}`);
      N.finish(se, Re.message || "Deployment completed");
    } catch (Re) {
      const ye = Re instanceof Error ? Re.message : "Deployment failed";
      throw N.fail(se, ye), Re;
    }
    return se;
  }
  async function _() {
    await gh(0), await E(), s.value = "inventory refreshed", hs("workspace");
  }
  async function V() {
    const N = await vh(!0);
    a.value = N.models ?? a.value, await E();
  }
  async function fe() {
    const N = await _h();
    l.value = N.custom_nodes ?? l.value, await E();
  }
  async function ke() {
    i.value = await hh();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: r,
    activeWorkspace: h,
    deployStatus: o,
    deployLog: i,
    models: a,
    customNodes: l,
    loading: c,
    error: u,
    setDeploy: S,
    setSyncSummary: x,
    reset: z,
    load: P,
    initialize: J,
    loadWorkspaces: $,
    loadDeployment: g,
    loadInventory: E,
    selectWorkspace: be,
    deploy: oe,
    refreshRemoteInventoryNow: _,
    rescanModelsNow: V,
    refreshCustomNodesNow: fe,
    loadLog: ke
  };
});
function jc(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = jc(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function zc() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = jc(e)) && (n && (n += " "), n += t);
  return n;
}
const Sh = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, Ch = (e, t) => ({
  classGroupId: e,
  validator: t
}), Dc = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), mr = "-", $a = [], Ah = "arbitrary..", Rh = (e) => {
  const t = Oh(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return Eh(i);
      const a = i.split(mr), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return Vc(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = n[i], c = s[i];
        return l ? c ? Sh(c, l) : l : c || $a;
      }
      return s[i] || $a;
    }
  };
}, Vc = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const r = e[t], o = s.nextPart.get(r);
  if (o) {
    const c = Vc(e, t + 1, o);
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
}, Eh = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? Ah + n : void 0;
})(), Oh = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return Th(s, t);
}, Th = (e, t) => {
  const s = Dc();
  for (const n in e) {
    const r = e[n];
    di(r, s, n, t);
  }
  return s;
}, di = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    Ih(i, t, s, n);
  }
}, Ih = (e, t, s, n) => {
  if (typeof e == "string") {
    Nh(e, t, s);
    return;
  }
  if (typeof e == "function") {
    Ph(e, t, s, n);
    return;
  }
  Mh(e, t, s, n);
}, Nh = (e, t, s) => {
  const n = e === "" ? t : Lc(t, e);
  n.classGroupId = s;
}, Ph = (e, t, s, n) => {
  if ($h(e)) {
    di(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(Ch(s, e));
}, Mh = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    di(l, Lc(t, a), s, n);
  }
}, Lc = (e, t) => {
  let s = e;
  const n = t.split(mr), r = n.length;
  for (let o = 0; o < r; o++) {
    const i = n[o];
    let a = s.nextPart.get(i);
    a || (a = Dc(), s.nextPart.set(i, a)), s = a;
  }
  return s;
}, $h = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, jh = (e) => {
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
}, jo = "!", ja = ":", zh = [], za = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), Dh = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let x = 0; x < u; x++) {
      const z = r[x];
      if (i === 0 && a === 0) {
        if (z === ja) {
          o.push(r.slice(l, x)), l = x + 1;
          continue;
        }
        if (z === "/") {
          c = x;
          continue;
        }
      }
      z === "[" ? i++ : z === "]" ? i-- : z === "(" ? a++ : z === ")" && a--;
    }
    const d = o.length === 0 ? r : r.slice(l);
    let m = d, h = !1;
    d.endsWith(jo) ? (m = d.slice(0, -1), h = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      d.startsWith(jo) && (m = d.slice(1), h = !0)
    );
    const S = c && c > l ? c - l : void 0;
    return za(o, h, m, S);
  };
  if (t) {
    const r = t + ja, o = n;
    n = (i) => i.startsWith(r) ? o(i.slice(r.length)) : za(zh, !1, i, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, Vh = (e) => {
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
}, Lh = (e) => ({
  cache: jh(e.cacheSize),
  parseClassName: Dh(e),
  sortModifiers: Vh(e),
  postfixLookupClassGroupIds: Fh(e),
  ...Rh(e)
}), Fh = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, Uh = /\s+/, Wh = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Uh);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const d = l[u], {
      isExternal: m,
      modifiers: h,
      hasImportantModifier: S,
      baseClassName: x,
      maybePostfixModifierPosition: z
    } = s(d);
    if (m) {
      c = d + (c.length > 0 ? " " + c : c);
      continue;
    }
    let $ = !!z, g;
    if ($) {
      const oe = x.substring(0, z);
      g = n(oe);
      const _ = g && i[g] ? n(x) : void 0;
      _ && _ !== g && (g = _, $ = !1);
    } else
      g = n(x);
    if (!g) {
      if (!$) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (g = n(x), !g) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      $ = !1;
    }
    const E = h.length === 0 ? "" : h.length === 1 ? h[0] : o(h).join(":"), P = S ? E + jo : E, J = P + g;
    if (a.indexOf(J) > -1)
      continue;
    a.push(J);
    const be = r(g, $);
    for (let oe = 0; oe < be.length; ++oe) {
      const _ = be[oe];
      a.push(P + _);
    }
    c = d + (c.length > 0 ? " " + c : c);
  }
  return c;
}, Bh = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = Fc(s)) && (r && (r += " "), r += n);
  return r;
}, Fc = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = Fc(e[n])) && (s && (s += " "), s += t);
  return s;
}, Hh = (e, ...t) => {
  let s, n, r, o;
  const i = (l) => {
    const c = t.reduce((u, d) => d(u), e());
    return s = Lh(c), n = s.cache.get, r = s.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = n(l);
    if (c)
      return c;
    const u = Wh(l, s);
    return r(l, u), u;
  };
  return o = i, (...l) => o(Bh(...l));
}, Zh = [], We = (e) => {
  const t = (s) => s[e] || Zh;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, Uc = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, Wc = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Gh = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, qh = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, Kh = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Jh = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Yh = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, Qh = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, is = (e) => Gh.test(e), pe = (e) => !!e && !Number.isNaN(Number(e)), It = (e) => !!e && Number.isInteger(Number(e)), oo = (e) => e.endsWith("%") && pe(e.slice(0, -1)), Gt = (e) => qh.test(e), Bc = () => !0, Xh = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  Kh.test(e) && !Jh.test(e)
), fi = () => !1, eg = (e) => Yh.test(e), tg = (e) => Qh.test(e), sg = (e) => !F(e) && !B(e), ng = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), rg = (e) => _s(e, Gc, fi), F = (e) => Uc.test(e), Ss = (e) => _s(e, qc, Xh), Da = (e) => _s(e, fg, pe), og = (e) => _s(e, Jc, Bc), ig = (e) => _s(e, Kc, fi), Va = (e) => _s(e, Hc, fi), ag = (e) => _s(e, Zc, tg), Wn = (e) => _s(e, Yc, eg), B = (e) => Wc.test(e), on = (e) => Ns(e, qc), lg = (e) => Ns(e, Kc), La = (e) => Ns(e, Hc), cg = (e) => Ns(e, Gc), ug = (e) => Ns(e, Zc), Bn = (e) => Ns(e, Yc, !0), dg = (e) => Ns(e, Jc, !0), _s = (e, t, s) => {
  const n = Uc.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, Ns = (e, t, s = !1) => {
  const n = Wc.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, Hc = (e) => e === "position" || e === "percentage", Zc = (e) => e === "image" || e === "url", Gc = (e) => e === "length" || e === "size" || e === "bg-size", qc = (e) => e === "length", fg = (e) => e === "number", Kc = (e) => e === "family-name", Jc = (e) => e === "number" || e === "weight", Yc = (e) => e === "shadow", mg = () => {
  const e = We("color"), t = We("font"), s = We("text"), n = We("font-weight"), r = We("tracking"), o = We("leading"), i = We("breakpoint"), a = We("container"), l = We("spacing"), c = We("radius"), u = We("shadow"), d = We("inset-shadow"), m = We("text-shadow"), h = We("drop-shadow"), S = We("blur"), x = We("perspective"), z = We("aspect"), $ = We("ease"), g = We("animate"), E = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], P = () => [
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
  ], J = () => [...P(), B, F], be = () => ["auto", "hidden", "clip", "visible", "scroll"], oe = () => ["auto", "contain", "none"], _ = () => [B, F, l], V = () => [is, "full", "auto", ..._()], fe = () => [It, "none", "subgrid", B, F], ke = () => ["auto", {
    span: ["full", It, B, F]
  }, It, B, F], N = () => [It, "auto", B, F], se = () => ["auto", "min", "max", "fr", B, F], Re = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], ye = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], de = () => ["auto", ..._()], X = () => [is, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ..._()], ge = () => [a, is, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ..._()], st = () => [is, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ..._()], G = () => [e, B, F], nt = () => [...P(), La, Va, {
    position: [B, F]
  }], Ge = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], Bt = () => ["auto", "cover", "contain", cg, rg, {
    size: [B, F]
  }], xt = () => [oo, on, Ss], ze = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    B,
    F
  ], Ee = () => ["", pe, on, Ss], k = () => ["solid", "dashed", "dotted", "double"], W = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], T = () => [pe, oo, La, Va], ne = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    S,
    B,
    F
  ], f = () => ["none", pe, B, F], p = () => ["none", pe, B, F], y = () => [pe, B, F], b = () => [is, "full", ..._()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [Gt],
      breakpoint: [Gt],
      color: [Bc],
      container: [Gt],
      "drop-shadow": [Gt],
      ease: ["in", "out", "in-out"],
      font: [sg],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [Gt],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [Gt],
      shadow: [Gt],
      spacing: ["px", pe],
      text: [Gt],
      "text-shadow": [Gt],
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
        aspect: ["auto", "square", is, F, B, z]
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
        "@container": ["", "normal", "size", B, F]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [ng],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [pe, "auto", F, B, a]
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
        overflow: be()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": be()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": be()
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
        z: [It, "auto", B, F]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [is, "full", "auto", a, ..._()]
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
        flex: [pe, is, "auto", "initial", "none", F]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", pe, B, F]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", pe, B, F]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [It, "first", "last", "none", B, F]
      }],
      /**
       * Grid Template Columns
       * @see https://tailwindcss.com/docs/grid-template-columns
       */
      "grid-cols": [{
        "grid-cols": fe()
      }],
      /**
       * Grid Column Start / End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start-end": [{
        col: ke()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": N()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": N()
      }],
      /**
       * Grid Template Rows
       * @see https://tailwindcss.com/docs/grid-template-rows
       */
      "grid-rows": [{
        "grid-rows": fe()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: ke()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": N()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": N()
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
        "auto-cols": se()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": se()
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
        justify: [...Re(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...ye(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...ye()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...Re()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...ye(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...ye(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": Re()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...ye(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...ye()]
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
        m: de()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: de()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: de()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: de()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: de()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: de()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: de()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: de()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: de()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: de()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: de()
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
        size: X()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ...ge()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...ge()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...ge()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...st()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...st()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...st()]
      }],
      /**
       * Width
       * @see https://tailwindcss.com/docs/width
       */
      w: [{
        w: [a, "screen", ...X()]
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
          ...X()
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
          ...X()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...X()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...X()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...X()]
      }],
      // ------------------
      // --- Typography ---
      // ------------------
      /**
       * Font Size
       * @see https://tailwindcss.com/docs/font-size
       */
      "font-size": [{
        text: ["base", s, on, Ss]
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
        font: [n, dg, og]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", oo, F]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [lg, ig, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [F]
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
        tracking: [r, B, F]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [pe, "none", B, Da]
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
        "list-image": ["none", B, F]
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
        list: ["disc", "decimal", "none", B, F]
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
        placeholder: G()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: G()
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
        decoration: [...k(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [pe, "from-font", "auto", B, Ss]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: G()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [pe, "auto", B, F]
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
        tab: [It, B, F]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", B, F]
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
        content: ["none", B, F]
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
        bg: Ge()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: Bt()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, It, B, F],
          radial: ["", B, F],
          conic: ["", It, B, F]
        }, ug, ag]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: G()
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
        from: G()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: G()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: G()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: ze()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": ze()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": ze()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": ze()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": ze()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": ze()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": ze()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": ze()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": ze()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": ze()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": ze()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": ze()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": ze()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": ze()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": ze()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: Ee()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": Ee()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": Ee()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": Ee()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": Ee()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": Ee()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": Ee()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": Ee()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": Ee()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": Ee()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": Ee()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": Ee()
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
        "divide-y": Ee()
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
        border: [...k(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...k(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: G()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": G()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": G()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": G()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": G()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": G()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": G()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": G()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": G()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": G()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": G()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: G()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [...k(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [pe, B, F]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", pe, on, Ss]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: G()
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
        shadow: G()
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
        "inset-shadow": G()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: Ee()
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
        ring: G()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [pe, Ss]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": G()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": Ee()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": G()
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
        "text-shadow": G()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [pe, B, F]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...W(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": W()
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
        "mask-linear": [pe]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": T()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": T()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": G()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": G()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": T()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": T()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": G()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": G()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": T()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": T()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": G()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": G()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": T()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": T()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": G()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": G()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": T()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": T()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": G()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": G()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": T()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": T()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": G()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": G()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": T()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": T()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": G()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": G()
      }],
      "mask-image-radial": [{
        "mask-radial": [B, F]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": T()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": T()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": G()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": G()
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
        "mask-conic": [pe]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": T()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": T()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": G()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": G()
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
        mask: Ge()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: Bt()
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
        mask: ["none", B, F]
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
          B,
          F
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: ne()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [pe, B, F]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [pe, B, F]
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
        "drop-shadow": G()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", pe, B, F]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [pe, B, F]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", pe, B, F]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [pe, B, F]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", pe, B, F]
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
          B,
          F
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": ne()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [pe, B, F]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [pe, B, F]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", pe, B, F]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [pe, B, F]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", pe, B, F]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [pe, B, F]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [pe, B, F]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", pe, B, F]
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", B, F]
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
        duration: [pe, "initial", B, F]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", $, B, F]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [pe, B, F]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", g, B, F]
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
        perspective: [x, B, F]
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
        skew: y()
      }],
      /**
       * Skew X
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-x": [{
        "skew-x": y()
      }],
      /**
       * Skew Y
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-y": [{
        "skew-y": y()
      }],
      /**
       * Transform
       * @see https://tailwindcss.com/docs/transform
       */
      transform: [{
        transform: [B, F, "", "none", "gpu", "cpu"]
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
        zoom: [It, B, F]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: G()
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
        caret: G()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", B, F]
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
        "scrollbar-thumb": G()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": G()
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
        "will-change": ["auto", "scroll", "contents", "transform", B, F]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...G()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [pe, on, Ss, Da]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...G()]
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
}, pg = /* @__PURE__ */ Hh(mg);
function mi(...e) {
  return pg(zc(e));
}
const hg = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, gg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, yg = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, vg = { class: "cmst:flex-1" }, bg = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, _g = { "data-testid": "vue-status-route" }, xg = { "data-testid": "vue-status-ops" }, wg = { "data-testid": "vue-status-density" }, kg = { class: "cmst:flex cmst:items-center cmst:gap-1" }, Sg = /* @__PURE__ */ yt({
  __name: "StudioApp",
  setup(e) {
    const t = _c(), s = ii(), n = Mc(), r = ui();
    Ys(() => {
      n.initialize(), r.initialize();
    });
    const o = yp("(min-width: 768px)"), i = {
      playground: xc,
      history: wc,
      workflows: Eo,
      backend: kc,
      settings: Sc
    }, a = Te(() => String(t.name ?? "playground"));
    function l(c) {
      const u = a.value === c;
      return mi(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        u ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (c, u) => (Q(), he("div", hg, [
      v("header", gg, [
        u[0] || (u[0] = v("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          te(" Modal Studio "),
          v("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        v("nav", yg, [
          (Q(!0), he(je, null, Qs(C(oi), (d) => (Q(), at(C(vc), {
            key: d,
            to: { name: d },
            class: ft(l(d)),
            "data-testid": `vue-nav-${d}`
          }, {
            default: ae(() => [
              (Q(), at(od(i[d]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              te(" " + re(C(vp)[d]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      v("main", vg, [
        U(C(bc))
      ]),
      v("footer", bg, [
        v("span", null, [
          u[1] || (u[1] = te("route: ", -1)),
          v("strong", _g, re(a.value), 1)
        ]),
        v("span", null, [
          u[2] || (u[2] = te(" operations: ", -1)),
          v("strong", xg, re(C(s).active.length) + " active", 1),
          te(" / " + re(C(s).all.length) + " total ", 1)
        ]),
        v("span", null, [
          u[3] || (u[3] = te(" density: ", -1)),
          v("strong", wg, re(C(n).density), 1)
        ]),
        v("span", kg, [
          U(C(qm), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          u[4] || (u[4] = te(" viewport: ", -1)),
          v("strong", null, re(C(o) ? "wide" : "narrow"), 1),
          u[5] || (u[5] = te(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), Cg = "/", Qc = { page: "playground", focus: null };
function Hn(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function io(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = ys(n) ? n : Qc.page;
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
function ao(e) {
  const t = Rc(e.location.hash);
  return !t.matched || !ys(t.page) ? null : { page: t.page, focus: t.focus };
}
function lo(e, t, s) {
  const n = Ec(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function Ag(e, t) {
  let s = bp(t, e.location.hash), n = Hn(s), r = {};
  const o = n, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = n;
    s = ao(e) ?? { ...Qc }, n = Hn(s), i.forEach((m) => m(n, u));
  }, c = (u, d) => u === null && d === o;
  return {
    get base() {
      return Cg;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const d = Ec(io(u));
      return d === "" ? "#" + u : d;
    },
    replace: (u, d) => {
      const m = ao(e), h = io(u), S = Hn(h);
      s = h, d !== void 0 && (r = d), n = S, !c(m, S) && ha(m, h) !== "none" && lo(e, h, "replace");
    },
    push: (u, d) => {
      const m = ao(e), h = io(u), S = Hn(h);
      if (s = h, d !== void 0 && (r = d), n = S, c(m, S)) return;
      const x = ha(m, h);
      x === "push" ? lo(e, h, "push") : x === "replace" && lo(e, h, "replace");
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
const Fa = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, Ua = zc, Rg = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return Ua(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = s?.[c], d = o?.[c];
    if (u === null) return null;
    const m = Fa(u) || Fa(d);
    return r[c][m];
  }), a = s && Object.entries(s).reduce((c, u) => {
    let [d, m] = u;
    return m === void 0 || (c[d] = m), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, u) => {
    let { class: d, className: m, ...h } = u;
    return Object.entries(h).every((S) => {
      let [x, z] = S;
      return Array.isArray(z) ? z.includes({
        ...o,
        ...a
      }[x]) : {
        ...o,
        ...a
      }[x] === z;
    }) ? [
      ...c,
      d,
      m
    ] : c;
  }, []);
  return Ua(e, i, l, s?.class, s?.className);
}, Eg = Rg(
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
), Og = ["type", "disabled"], $e = /* @__PURE__ */ yt({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (Q(), he("button", {
      type: e.type,
      disabled: e.disabled,
      class: ft(C(Eg)({ variant: e.variant, size: e.size }))
    }, [
      Il(t.$slots, "default")
    ], 10, Og));
  }
}), Ze = /* @__PURE__ */ yt({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (Q(), he("div", {
      class: ft(
        C(mi)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      Il(t.$slots, "default")
    ], 2));
  }
});
function Mn(e) {
  return mi(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const Tg = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Ig = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, Ng = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Pg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, Mg = { value: "" }, $g = ["value"], jg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, zg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Dg = { class: "cmst:mt-1 cmst:text-sm" }, Vg = { "data-testid": "vue-deploy-state" }, Lg = {
  key: 0,
  class: "cmst:text-sm cmst:opacity-80"
}, Fg = { class: "cmst:flex cmst:gap-2" }, Ug = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, Wg = { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, Bg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Hg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, Zg = /* @__PURE__ */ yt({
  __name: "BackendView",
  setup(e) {
    const t = ui(), s = /* @__PURE__ */ Z(""), n = /* @__PURE__ */ Z(!1), r = Te(() => t.models.length), o = Te(() => t.customNodes.length);
    Ys(() => {
      t.workspaces.length || t.initialize();
    });
    async function i() {
      s.value && await t.selectWorkspace(s.value);
    }
    async function a() {
      await t.deploy();
    }
    return (l, c) => (Q(), he("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-backend"
    }, [
      C(t).error ? (Q(), he("div", Tg, re(C(t).error), 1)) : Ye("", !0),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          v("div", Ig, [
            v("div", null, [
              v("h2", Ng, [
                U(C(kc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[2] || (c[2] = te(" Manage Modal ", -1))
              ]),
              c[3] || (c[3] = v("p", { class: "cmst:text-sm cmst:opacity-80" }, [
                te("Route key remains "),
                v("code", null, "backend"),
                te(". Workspace and readiness state come from the server.")
              ], -1))
            ]),
            U($e, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload infrastructure",
              disabled: C(t).loading,
              onClick: C(t).load
            }, {
              default: ae(() => [
                U(C(Pr), {
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
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          c[5] || (c[5] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Workspaces", -1)),
          v("div", Pg, [
            Xt(v("select", {
              "onUpdate:modelValue": c[0] || (c[0] = (u) => s.value = u),
              class: "cmst:h-9 cmst:min-w-52 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              "data-testid": "vue-workspace-select"
            }, [
              v("option", Mg, re(C(t).activeWorkspace?.label ?? "Select workspace"), 1),
              (Q(!0), he(je, null, Qs(C(t).workspaces, (u) => (Q(), he("option", {
                key: u.id,
                value: u.id
              }, re(u.label) + re(u.isActive ? " (active)" : ""), 9, $g))), 128))
            ], 512), [
              [si, s.value]
            ]),
            U($e, {
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
          v("p", jg, "Active ID: " + re(C(t).activeWorkspaceId ?? "none"), 1)
        ]),
        _: 1
      }),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          v("div", zg, [
            v("div", null, [
              c[7] || (c[7] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Deployment readiness", -1)),
              v("p", Dg, [
                c[6] || (c[6] = te("State: ", -1)),
                v("strong", Vg, re(C(t).deployStatus.state), 1)
              ]),
              C(t).deployMessage ? (Q(), he("p", Lg, re(C(t).deployMessage), 1)) : Ye("", !0)
            ]),
            v("div", Fg, [
              U($e, {
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
              U($e, {
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
          n.value ? (Q(), he("pre", Ug, re(C(t).deployLog ?? "Loading…"), 1)) : Ye("", !0),
          n.value && !C(t).deployLog ? (Q(), at($e, {
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
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          c[13] || (c[13] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared inventory", -1)),
          v("p", Wg, "Models: " + re(r.value) + " · Custom nodes: " + re(o.value), 1),
          v("div", Bg, [
            U($e, {
              size: "sm",
              variant: "outline",
              onClick: C(t).refreshRemoteInventoryNow
            }, {
              default: ae(() => [...c[10] || (c[10] = [
                te("Refresh remote inventory", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            U($e, {
              size: "sm",
              variant: "outline",
              onClick: C(t).rescanModelsNow
            }, {
              default: ae(() => [...c[11] || (c[11] = [
                te("Rescan models", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            U($e, {
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
          v("p", Hg, re(C(t).syncSummary ?? "Not loaded"), 1)
        ]),
        _: 1
      })
    ], 2));
  }
});
function Xe(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function Gg(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = Xe(s, "asset_id", "assetId"), r = (o) => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}?variant=${o}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: Xe(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: Xe(s, "logical_key", "logicalKey"),
    thumbUrl: Xe(s, "thumb_url", "thumbnail_url") || r("thumbnail"),
    previewUrl: Xe(s, "preview_url", "data_saver_url") || r("data_saver"),
    originalUrl: Xe(s, "original_url") || r("original"),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: Xe(s, "filename", "name")
  };
}
function Wa(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((r, o) => Gg(r, o));
  return {
    id: Xe(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: Xe(t, "status", "outcome") || "unknown",
    workflow: Xe(t, "workflow", "workflow_name"),
    workflowVersion: Xe(t, "workflow_version", "workflowVersion", "version_id"),
    preset: Xe(t, "preset", "preset_name"),
    prompt: Xe(t, "prompt", "positive_prompt"),
    startedAt: Xe(t, "started_at", "created_at") || null,
    completedAt: Xe(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: Xe(t, "note"),
    outputs: n,
    featuredOutput: n[0] ?? null,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    raw: t
  };
}
async function qg(e = {}) {
  const t = new URLSearchParams();
  for (const [s, n] of Object.entries({ limit: 24, ...e }))
    n !== void 0 && String(n) !== "" && t.set(s, String(n));
  return Ce(`/history-v2/feed?${t}`);
}
async function Kg(e) {
  return Ce(`/history-v2/generations/${encodeURIComponent(e)}`);
}
async function Jg(e) {
  return Ce(`/history-v2/experiments/${encodeURIComponent(e)}`);
}
async function Yg(e, t) {
  return Ce(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function Qg(e, t) {
  return Ce(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function Xg(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return Ce(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const $s = Nc("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1 }), ey = /* @__PURE__ */ Xs("studio-history", () => {
  const e = /* @__PURE__ */ Z([]), t = /* @__PURE__ */ Z(null), s = /* @__PURE__ */ Z(null), n = /* @__PURE__ */ Z($s.read().query), r = /* @__PURE__ */ Z($s.read().sort), o = /* @__PURE__ */ Z($s.read().favoriteOnly), i = /* @__PURE__ */ Z(null), a = /* @__PURE__ */ Z(!1), l = /* @__PURE__ */ Z(!1), c = /* @__PURE__ */ Z(null), u = fr(), d = fr();
  let m = null;
  function h(_) {
    s.value = _, t.value = e.value.find((V) => V.id === _) ?? t.value;
  }
  function S(_) {
    n.value = _, $s.write({ query: _, sort: r.value, favoriteOnly: o.value });
  }
  function x(_) {
    r.value = _, $s.write({ query: n.value, sort: _, favoriteOnly: o.value });
  }
  function z(_) {
    o.value = _, $s.write({ query: n.value, sort: r.value, favoriteOnly: _ });
  }
  async function $(_ = !1) {
    l.value = !0, c.value = null;
    const V = await u.run(async (N) => {
      const se = await qg({ search: n.value, sort: r.value, favorite_only: o.value, cursor: _ ? i.value ?? void 0 : void 0 });
      return N.aborted ? null : se;
    });
    if (V.stale || !V.value) return;
    const fe = V.value, ke = (fe.items ?? fe.records ?? []).map(Wa);
    e.value = _ ? e.value.concat(ke) : ke, i.value = fe.next_cursor ?? null, a.value = fe.has_more === !0 || !!i.value, l.value = !1;
  }
  async function g(_, V = "generation") {
    const fe = await d.run(async (se) => {
      const Re = V === "experiment" ? await Jg(_) : await Kg(_);
      return se.aborted ? null : Re;
    });
    if (fe.stale || !fe.value) return;
    const ke = Wa(fe.value);
    t.value = ke;
    const N = e.value.findIndex((se) => se.id === ke.id);
    N >= 0 && (e.value[N] = ke);
  }
  async function E(_, V) {
    await Yg(_.id, V), _.favorite = V, hs("history");
  }
  async function P(_, V) {
    await Qg(_.id, V), _.note = V, hs("history");
  }
  async function J(_) {
    await Xg(_), e.value = e.value.filter((V) => V.id !== _.id), t.value?.id === _.id && (t.value = null), hs("history");
  }
  async function be() {
    m || (m = ci((_) => {
      _ === "history" && $();
    })), e.value.length || await $();
  }
  function oe() {
    e.value = [], t.value = null, s.value = null, i.value = null;
  }
  return { records: e, selected: t, focusId: s, query: n, sort: r, favoriteOnly: o, cursor: i, hasMore: a, loading: l, error: c, setFocus: h, setQuery: S, setSort: x, setFavoriteOnly: z, loadFeed: $, loadDetail: g, setFavorite: E, setNote: P, remove: J, initialize: be, clear: oe };
}), ty = ["src", "alt"], sy = { class: "cmst:p-3 cmst:text-sm" }, ny = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, ry = { class: "cmst:truncate" }, oy = { class: "cmst:text-xs cmst:opacity-70" }, iy = { class: "cmst:mt-1 cmst:truncate cmst:text-xs cmst:opacity-70" }, ay = /* @__PURE__ */ yt({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (Q(), at(Ze, {
      class: "cmst:overflow-hidden cmst:cursor-pointer",
      onClick: r[0] || (r[0] = (o) => s("select", e.record))
    }, {
      default: ae(() => [
        e.record.featuredOutput ? (Q(), he("img", {
          key: 0,
          src: e.record.featuredOutput.thumbUrl,
          alt: e.record.workflow || e.record.id,
          class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
          loading: "lazy"
        }, null, 8, ty)) : Ye("", !0),
        v("div", sy, [
          v("div", ny, [
            v("strong", ry, re(e.record.workflow || e.record.id), 1),
            v("span", oy, re(e.record.status), 1)
          ]),
          v("p", iy, re(e.record.id), 1)
        ])
      ]),
      _: 1
    }));
  }
}), ly = {
  class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2 cmst:lg:grid-cols-3",
  "data-testid": "vue-history-grid"
}, cy = /* @__PURE__ */ yt({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (Q(), he("div", ly, [
      (Q(!0), he(je, null, Qs(e.records, (o) => (Q(), at(ay, {
        key: `${o.kind}:${o.id}`,
        record: o,
        onSelect: r[0] || (r[0] = (i) => s("select", i))
      }, null, 8, ["record"]))), 128))
    ]));
  }
}), uy = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, dy = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, fy = { class: "cmst:text-lg cmst:font-semibold" }, my = { class: "cmst:text-xs cmst:opacity-70" }, py = ["src", "alt"], hy = {
  key: 1,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, gy = /* @__PURE__ */ yt({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => e.record ? (Q(), he("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-testid": "vue-history-viewer",
      onClick: r[1] || (r[1] = _f((o) => s("close"), ["self"]))
    }, [
      v("div", uy, [
        v("div", dy, [
          v("div", null, [
            v("h2", fy, re(e.record.workflow || e.record.id), 1),
            v("p", my, re(e.record.status) + " · " + re(e.record.kind), 1)
          ]),
          U($e, {
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
        e.record.featuredOutput ? (Q(), he("img", {
          key: 0,
          src: e.record.featuredOutput.previewUrl,
          alt: e.record.workflow || e.record.id,
          class: "cmst:mt-4 cmst:mx-auto cmst:max-h-[70vh] cmst:max-w-full cmst:object-contain"
        }, null, 8, py)) : (Q(), he("p", hy, "No projected image asset."))
      ])
    ])) : Ye("", !0);
  }
}), yy = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, vy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, by = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, _y = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, xy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, wy = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, ky = /* @__PURE__ */ yt({
  __name: "HistoryView",
  setup(e) {
    const t = ey(), s = _c(), n = jm(), r = /* @__PURE__ */ Z(t.query), o = /* @__PURE__ */ Z(!1);
    Ys(async () => {
      await t.initialize();
      const l = typeof s.query.focus == "string" ? s.query.focus : null;
      l && (t.setFocus(l), await t.loadDetail(l));
    });
    let i;
    Os(r, (l) => {
      window.clearTimeout(i), i = window.setTimeout(() => {
        t.setQuery(l), t.loadFeed();
      }, 250);
    });
    async function a(l) {
      t.setFocus(l.id), await n.replace({ name: "history", query: { focus: l.id } }), await t.loadDetail(l.id, l.kind), o.value = !0;
    }
    return (l, c) => (Q(), he("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-history"
    }, [
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          v("div", yy, [
            v("div", null, [
              v("h2", vy, [
                U(C(wc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[8] || (c[8] = te("History V2", -1))
              ]),
              c[9] || (c[9] = v("p", { class: "cmst:text-sm cmst:opacity-80" }, "History V2 is the Vue production data source; the server cursor remains authoritative.", -1))
            ]),
            U($e, {
              variant: "outline",
              size: "icon",
              "aria-label": "Refresh history",
              disabled: C(t).loading,
              onClick: c[0] || (c[0] = (u) => C(t).loadFeed())
            }, {
              default: ae(() => [
                U(C(Pr), {
                  class: ft(["cmst:size-4", C(t).loading ? "cmst:animate-spin" : ""])
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          v("div", by, [
            v("label", _y, [
              U(C(ep), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              }),
              Xt(v("input", {
                "onUpdate:modelValue": c[1] || (c[1] = (u) => r.value = u),
                class: "cmst:h-9 cmst:w-64 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search history",
                "data-testid": "vue-history-search"
              }, null, 512), [
                [Cn, r.value]
              ])
            ]),
            Xt(v("select", {
              "onUpdate:modelValue": c[2] || (c[2] = (u) => C(t).sort = u),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              onChange: c[3] || (c[3] = (u) => {
                C(t).setSort(C(t).sort), C(t).loadFeed();
              })
            }, [...c[10] || (c[10] = [
              v("option", { value: "newest" }, "Newest", -1),
              v("option", { value: "oldest" }, "Oldest", -1),
              v("option", { value: "fastest" }, "Fastest", -1),
              v("option", { value: "slowest" }, "Slowest", -1)
            ])], 544), [
              [si, C(t).sort]
            ]),
            v("label", xy, [
              Xt(v("input", {
                "onUpdate:modelValue": c[4] || (c[4] = (u) => C(t).favoriteOnly = u),
                type: "checkbox",
                onChange: c[5] || (c[5] = (u) => {
                  C(t).setFavoriteOnly(C(t).favoriteOnly), C(t).loadFeed();
                })
              }, null, 544), [
                [gf, C(t).favoriteOnly]
              ]),
              c[11] || (c[11] = te(" Favorites", -1))
            ])
          ])
        ]),
        _: 1
      }),
      C(t).error ? (Q(), he("div", wy, re(C(t).error), 1)) : Ye("", !0),
      C(t).loading && !C(t).records.length ? (Q(), at(Ze, {
        key: 1,
        class: "cmst:p-6 cmst:text-sm"
      }, {
        default: ae(() => [...c[12] || (c[12] = [
          te("Loading History V2…", -1)
        ])]),
        _: 1
      })) : C(t).records.length ? (Q(), at(cy, {
        key: 3,
        records: C(t).records,
        onSelect: a
      }, null, 8, ["records"])) : (Q(), at(Ze, {
        key: 2,
        class: "cmst:p-6 cmst:text-sm cmst:opacity-75"
      }, {
        default: ae(() => [...c[13] || (c[13] = [
          te("No History V2 records match this query.", -1)
        ])]),
        _: 1
      })),
      C(t).hasMore ? (Q(), at($e, {
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
      o.value ? (Q(), at(gy, {
        key: 5,
        record: C(t).selected,
        onClose: c[7] || (c[7] = (u) => o.value = !1)
      }, null, 8, ["record"])) : Ye("", !0)
    ], 2));
  }
}), Sy = /* @__PURE__ */ Xs("studio-playground", () => {
  const e = /* @__PURE__ */ Z("txt2img"), t = /* @__PURE__ */ Z(!1);
  function s(r) {
    e.value = r;
  }
  function n(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: s, setExperimentMode: n };
}), Cy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Ay = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, Ry = ["checked"], Ey = { class: "cmst:text-sm cmst:opacity-80" }, Oy = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, Ty = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, Iy = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Ny = { key: 0 }, Py = /* @__PURE__ */ yt({
  __name: "PlaygroundView",
  setup(e) {
    const t = Sy(), s = ii(), n = /* @__PURE__ */ Z(null), r = Te(() => n.value ? s.get(n.value)?.progress ?? null : null);
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
    return (i, a) => (Q(), he("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-playground"
    }, [
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          v("h2", Cy, [
            U(C(xc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = te(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = v("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          v("label", Ay, [
            v("input", {
              type: "checkbox",
              checked: C(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => C(t).setExperimentMode(l.target.checked))
            }, null, 40, Ry),
            a[2] || (a[2] = te(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          a[5] || (a[5] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          v("p", Ey, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + re(C(s).active.length) + ". ", 1),
          v("div", Oy, [
            U($e, {
              variant: "default",
              size: "sm",
              disabled: n.value !== null,
              onClick: o
            }, {
              default: ae(() => [
                U(C(Jm), { "aria-hidden": "true" }),
                a[4] || (a[4] = te(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? (Q(), he("span", Ty, re(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : Ye("", !0)
          ]),
          v("ul", Iy, [
            (Q(!0), he(je, null, Qs(C(s).all.slice(-5), (l) => (Q(), he("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              v("strong", null, re(l.label), 1),
              te(" — " + re(l.status), 1),
              l.message ? (Q(), he("span", Ny, " — " + re(l.message), 1)) : Ye("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), My = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, $y = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, jy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, zy = { class: "cmst:mt-3 cmst:text-sm" }, Dy = { key: 0 }, Vy = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Ly = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Fy = ["value"], Uy = ["value"], Wy = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, By = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Hy = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Zy = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Gy = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-3" }, qy = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, Ky = ["checked"], Jy = /* @__PURE__ */ yt({
  __name: "SettingsView",
  setup(e) {
    const t = Mc(), s = /* @__PURE__ */ Z(75), n = /* @__PURE__ */ Z(""), r = /* @__PURE__ */ Z("off"), o = Te(() => t.config), i = Te(() => o.value?.available_gpus ?? []);
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
    return (d, m) => (Q(), he("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-settings"
    }, [
      C(t).error ? (Q(), he("div", My, re(C(t).error), 1)) : Ye("", !0),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          v("div", $y, [
            v("div", null, [
              v("h2", jy, [
                U(C(Sc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                m[3] || (m[3] = te(" Settings ", -1))
              ]),
              m[4] || (m[4] = v("p", { class: "cmst:text-sm cmst:opacity-80" }, " Server-backed Settings authority. Vue reads `/config` and projects proven output values one-way to legacy canvas consumers. ", -1))
            ]),
            U($e, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload settings",
              disabled: C(t).loading,
              onClick: C(t).load
            }, {
              default: ae(() => [
                U(C(Pr), {
                  class: ft(["cmst:size-4", C(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ]),
          v("p", zy, [
            m[5] || (m[5] = te(" Active section: ", -1)),
            v("strong", null, re(C(t).activeSection), 1),
            C(t).config ? (Q(), he("span", Dy, " · server config loaded")) : Ye("", !0)
          ])
        ]),
        _: 1
      }),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          m[9] || (m[9] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Generation", -1)),
          v("div", Vy, [
            v("label", Ly, [
              m[6] || (m[6] = te(" GPU ", -1)),
              v("select", {
                value: o.value?.gpu ?? "",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-settings-gpu",
                onChange: l
              }, [
                (Q(!0), he(je, null, Qs(i.value, (h) => (Q(), he("option", {
                  key: h.value,
                  value: h.value
                }, re(h.label), 9, Uy))), 128))
              ], 40, Fy)
            ]),
            v("label", Wy, [
              m[8] || (m[8] = te(" Profile/tracing level ", -1)),
              Xt(v("select", {
                "onUpdate:modelValue": m[0] || (m[0] = (h) => r.value = h),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: u
              }, [...m[7] || (m[7] = [
                v("option", { value: "off" }, "Off", -1),
                v("option", { value: "summary" }, "Summary", -1),
                v("option", { value: "detailed" }, "Detailed", -1),
                v("option", { value: "trace" }, "Trace", -1),
                v("option", { value: "trace_verbose" }, "Trace verbose", -1)
              ])], 544), [
                [si, r.value]
              ])
            ])
          ])
        ]),
        _: 1
      }),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          m[13] || (m[13] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Outputs / Data Saver", -1)),
          v("div", By, [
            v("label", Hy, [
              m[10] || (m[10] = te(" Quality ", -1)),
              Xt(v("input", {
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
            v("label", Zy, [
              m[11] || (m[11] = te(" Save folder ", -1)),
              Xt(v("input", {
                "onUpdate:modelValue": m[2] || (m[2] = (h) => n.value = h),
                type: "text",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [Cn, n.value]
              ])
            ])
          ]),
          v("div", Gy, [
            U($e, {
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
            m[12] || (m[12] = v("span", { class: "cmst:text-xs cmst:opacity-70" }, "Server truth is reread after every save.", -1))
          ])
        ]),
        _: 1
      }),
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          m[15] || (m[15] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Advanced", -1)),
          v("label", qy, [
            v("input", {
              type: "checkbox",
              checked: o.value?.skip_plan_validation ?? !1,
              onChange: c
            }, null, 40, Ky),
            m[14] || (m[14] = te(" Skip plan validation (preserves current backend semantics) ", -1))
          ]),
          m[16] || (m[16] = v("p", { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, "Execution mode remains server-owned and V2-only.", -1))
        ]),
        _: 1
      })
    ], 2));
  }
});
async function Yy(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.tag && t.set("tag", e.tag), e.folder && t.set("folder", e.folder), e.favorite && t.set("favorite", "1");
  const s = t.toString() ? `?${t}` : "";
  return Ce(`/studio/workflows${s}`);
}
async function Qy(e) {
  return Ce(`/studio/workflows/${encodeURIComponent(e)}`);
}
async function Xy(e) {
  return Ce(`/studio/workflows/${encodeURIComponent(e)}/versions`);
}
async function ev(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}`);
}
async function tv(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`);
}
async function sv(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/candidates`);
}
async function nv(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/dependencies`);
}
async function rv(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`);
}
async function ov(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/portability`);
}
async function iv(e) {
  return Ce(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`);
}
async function av(e, t) {
  return Ce(`/studio/workflows/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
function lv(e) {
  const t = String(e || "t2i").toLowerCase();
  return t === "txt2img" ? "t2i" : t;
}
const ls = ["feature-type", "required-bindings", "exposed-controls", "details"];
function Kn(e) {
  return {
    v: 1,
    workflowId: e.workflowId || "",
    versionId: e.versionId || "",
    step: e.step && ls.includes(e.step) ? e.step : "feature-type",
    featureType: e.featureType || "t2i",
    bindings: e.bindings || {},
    outputBinding: e.outputBinding || null,
    controls: Array.isArray(e.controls) ? e.controls.slice(0, 64) : [],
    details: e.details || {}
  };
}
function cv(e, t, s) {
  if (!e || e.length > 12e3) return null;
  try {
    const n = JSON.parse(e);
    return n.v !== 1 || n.workflowId !== t || n.versionId !== s ? null : Kn(n);
  } catch {
    return null;
  }
}
const co = "comfymodal.studio.wizard.draft.v1", uv = /* @__PURE__ */ Xs("studio-workflows", () => {
  const e = /* @__PURE__ */ Z([]), t = /* @__PURE__ */ Z(null), s = /* @__PURE__ */ Z(null), n = /* @__PURE__ */ Z([]), r = /* @__PURE__ */ Z(null), o = /* @__PURE__ */ Z(null), i = /* @__PURE__ */ Z(null), a = /* @__PURE__ */ Z(null), l = /* @__PURE__ */ Z(null), c = /* @__PURE__ */ Z(null), u = /* @__PURE__ */ Z([]), d = /* @__PURE__ */ Z(""), m = /* @__PURE__ */ Z(!1), h = /* @__PURE__ */ Z(null), S = /* @__PURE__ */ Z(!1), x = /* @__PURE__ */ Z(null), z = fr();
  function $(N) {
    t.value = N;
  }
  function g() {
    t.value = null, s.value = null, n.value = [], r.value = null;
  }
  async function E() {
    m.value = !0, h.value = null;
    try {
      const N = await Yy({ search: d.value });
      e.value = N.workflows ?? [];
    } catch (N) {
      throw h.value = N instanceof Error ? N.message : "Could not load workflows", N;
    } finally {
      m.value = !1;
    }
  }
  async function P(N) {
    t.value = N;
    const se = await z.run(async (de) => {
      const [X, ge] = await Promise.all([Qy(N), Xy(N)]);
      return de.aborted ? null : { workflowResponse: X, versionsResponse: ge };
    });
    if (se.stale || !se.value) return;
    s.value = se.value.workflowResponse.workflow ?? null, n.value = se.value.versionsResponse.versions ?? [];
    const Re = s.value?.latest_version_id, ye = n.value.find((de) => de.workflow_version_id === Re) ?? n.value.at(-1) ?? null;
    ye && await J(ye.workflow_version_id);
  }
  async function J(N) {
    const se = await z.run(async (ye) => {
      const [de, X, ge, st, G, nt] = await Promise.all([
        ev(N),
        tv(N),
        nv(N),
        rv(N),
        ov(N),
        iv(N)
      ]);
      return ye.aborted ? null : { versionResponse: de, mappingResponse: X, dependencyResponse: ge, compatibilityResponse: st, portabilityResponse: G, presetsResponse: nt };
    });
    if (se.stale || !se.value) return;
    r.value = se.value.versionResponse, o.value = se.value.mappingResponse, i.value = null, a.value = se.value.dependencyResponse, l.value = se.value.compatibilityResponse, c.value = se.value.portabilityResponse;
    const Re = se.value.presetsResponse;
    u.value = Re.presets ?? [];
  }
  async function be() {
    r.value && (i.value = await sv(r.value.workflow_version_id));
  }
  function oe() {
    const N = s.value?.workflow_id ?? "", se = r.value?.workflow_version_id ?? "";
    try {
      x.value = cv(sessionStorage.getItem(co), N, se) ?? Kn({ workflowId: N, versionId: se, featureType: lv(s.value?.workflow_type) });
    } catch {
      x.value = Kn({ workflowId: N, versionId: se });
    }
    S.value = !0;
  }
  function _(N) {
    if (x.value) {
      x.value = Kn({ ...x.value, ...N });
      try {
        sessionStorage.setItem(co, JSON.stringify(x.value));
      } catch {
      }
    }
  }
  function V(N) {
    _({ step: N });
  }
  function fe() {
    S.value = !1, x.value = null;
    try {
      sessionStorage.removeItem(co);
    } catch {
    }
  }
  async function ke(N) {
    t.value && (await av(t.value, N), await E(), await P(t.value), hs("workflows"));
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
    wizardOpen: S,
    wizardDraft: x,
    select: $,
    clear: g,
    loadList: E,
    selectWorkflow: P,
    selectVersion: J,
    loadMappingCandidates: be,
    openWizard: oe,
    updateWizard: _,
    setWizardStep: V,
    closeWizard: fe,
    updateMetadata: ke
  };
}), dv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, fv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, mv = { class: "cmst:flex cmst:gap-2" }, pv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, hv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, gv = ["data-testid", "onClick"], yv = { class: "cmst:block cmst:text-xs cmst:opacity-70" }, vv = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70"
}, bv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, _v = { class: "cmst:text-base cmst:font-semibold" }, xv = { class: "cmst:text-xs cmst:opacity-70" }, wv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, kv = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Sv = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Cv = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Av = { class: "cmst:mt-3 cmst:text-sm" }, Rv = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, Ev = {
  key: 2,
  class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
  "data-testid": "vue-workflow-wizard"
}, Ov = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Tv = { class: "cmst:text-xs cmst:opacity-70" }, Iv = { class: "cmst:mt-5 cmst:rounded-md cmst:bg-cmst-bg cmst:p-4" }, Nv = ["value"], Pv = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, Mv = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs"
}, $v = { class: "cmst:mt-4 cmst:flex cmst:justify-between" }, jv = /* @__PURE__ */ yt({
  __name: "WorkflowsView",
  setup(e) {
    const t = uv(), s = ui(), n = /* @__PURE__ */ Z(""), r = /* @__PURE__ */ Z("workflows"), o = /* @__PURE__ */ Z(""), i = /* @__PURE__ */ Z(""), a = /* @__PURE__ */ Z(""), l = Te(() => Math.max(0, ls.indexOf(t.wizardDraft?.step ?? "feature-type"))), c = Te(() => ls[l.value]);
    Ys(async () => {
      await Promise.all([t.loadList(), s.initialize()]);
    });
    async function u() {
      t.query = n.value, await t.loadList();
    }
    async function d($) {
      o.value = $, await t.selectWorkflow($);
    }
    function m() {
      t.openWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!0);
    }
    function h() {
      t.closeWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
    }
    function S() {
      i.value.trim() && (t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { target: i.value.trim(), confirmed: !0 } } }), a.value = `Confirmed graph target ${i.value.trim()}`);
    }
    function x() {
      const $ = ls[Math.min(ls.length - 1, l.value + 1)];
      t.setWizardStep($);
    }
    function z() {
      const $ = ls[Math.max(0, l.value - 1)];
      t.setWizardStep($);
    }
    return ($, g) => (Q(), he("section", {
      class: ft(C(Mn)()),
      "data-testid": "vue-page-workflows"
    }, [
      U(Ze, { class: "cmst:p-4" }, {
        default: ae(() => [
          v("div", dv, [
            v("div", null, [
              v("h2", fv, [
                U(C(Eo), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                g[5] || (g[5] = te("Workflows & Models", -1))
              ]),
              g[6] || (g[6] = v("p", { class: "cmst:text-sm cmst:opacity-80" }, "Workflow/version state and shared infrastructure inventory remain separate authorities.", -1))
            ]),
            v("div", mv, [
              U($e, {
                variant: r.value === "workflows" ? "default" : "outline",
                size: "sm",
                onClick: g[0] || (g[0] = (E) => r.value = "workflows")
              }, {
                default: ae(() => [
                  U(C(Eo), { class: "cmst:size-4" }),
                  g[7] || (g[7] = te("Workflows", -1))
                ]),
                _: 1
              }, 8, ["variant"]),
              U($e, {
                variant: r.value === "models" ? "default" : "outline",
                size: "sm",
                onClick: g[1] || (g[1] = (E) => r.value = "models")
              }, {
                default: ae(() => [
                  U(C(Bm), { class: "cmst:size-4" }),
                  g[8] || (g[8] = te("Models / Nodes", -1))
                ]),
                _: 1
              }, 8, ["variant"])
            ])
          ])
        ]),
        _: 1
      }),
      r.value === "workflows" ? (Q(), he(je, { key: 0 }, [
        U(Ze, { class: "cmst:p-4" }, {
          default: ae(() => [
            v("div", pv, [
              Xt(v("input", {
                "onUpdate:modelValue": g[2] || (g[2] = (E) => n.value = E),
                class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search workflows",
                onKeyup: wf(u, ["enter"])
              }, null, 544), [
                [Cn, n.value]
              ]),
              U($e, {
                size: "sm",
                variant: "secondary",
                onClick: u
              }, {
                default: ae(() => [...g[9] || (g[9] = [
                  te("Search", -1)
                ])]),
                _: 1
              }),
              U($e, {
                size: "sm",
                variant: "outline",
                onClick: C(t).loadList
              }, {
                default: ae(() => [
                  U(C(Pr), { class: "cmst:size-4" })
                ]),
                _: 1
              }, 8, ["onClick"])
            ]),
            v("div", hv, [
              (Q(!0), he(je, null, Qs(C(t).workflows, (E) => (Q(), he("button", {
                key: E.workflow_id,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-workflow-${E.workflow_id}`,
                onClick: (P) => d(E.workflow_id)
              }, [
                v("strong", null, re(E.name || E.workflow_id), 1),
                v("span", yv, re(E.folder || "No folder") + " · " + re(E.latest_version_id || "No version"), 1)
              ], 8, gv))), 128))
            ]),
            C(t).workflows.length ? Ye("", !0) : (Q(), he("p", vv, "No workflows returned by the server."))
          ]),
          _: 1
        }),
        C(t).selectedWorkflow ? (Q(), at(Ze, {
          key: 0,
          class: "cmst:p-4"
        }, {
          default: ae(() => [
            v("div", bv, [
              v("div", null, [
                v("h3", _v, re(C(t).selectedWorkflow.name), 1),
                v("p", xv, "Version " + re(C(t).selectedVersion?.version ?? C(t).selectedVersion?.workflow_version_id), 1)
              ]),
              U($e, {
                size: "sm",
                onClick: m
              }, {
                default: ae(() => [
                  U(C(rp), { class: "cmst:size-4" }),
                  g[10] || (g[10] = te("Setup wizard", -1))
                ]),
                _: 1
              })
            ]),
            v("div", wv, [
              v("div", kv, [
                g[11] || (g[11] = te("Mapping", -1)),
                g[12] || (g[12] = v("br", null, null, -1)),
                v("strong", null, re(C(t).mapping ? "configured" : "not configured"), 1)
              ]),
              v("div", Sv, [
                g[13] || (g[13] = te("Dependencies", -1)),
                g[14] || (g[14] = v("br", null, null, -1)),
                v("strong", null, re(C(t).dependencies ? "loaded" : "not loaded"), 1)
              ]),
              v("div", Cv, [
                g[15] || (g[15] = te("Portability", -1)),
                g[16] || (g[16] = v("br", null, null, -1)),
                v("strong", null, re(C(t).portability ? "analyzed" : "not analyzed"), 1)
              ])
            ])
          ]),
          _: 1
        })) : Ye("", !0)
      ], 64)) : (Q(), at(Ze, {
        key: 1,
        class: "cmst:p-4"
      }, {
        default: ae(() => [
          g[19] || (g[19] = v("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared model inventory", -1)),
          g[20] || (g[20] = v("p", { class: "cmst:mt-1 cmst:text-sm cmst:opacity-70" }, "Owned by infrastructureStore; workflow dependencies reference this state.", -1)),
          v("div", Av, "Models: " + re(C(s).models.length) + " · Custom nodes: " + re(C(s).customNodes.length), 1),
          v("div", Rv, [
            U($e, {
              size: "sm",
              variant: "outline",
              onClick: C(s).rescanModelsNow
            }, {
              default: ae(() => [...g[17] || (g[17] = [
                te("Rescan models", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            U($e, {
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
      C(t).wizardOpen ? (Q(), he("div", Ev, [
        U(Ze, { class: "cmst:w-[min(42rem,94vw)] cmst:p-5" }, {
          default: ae(() => [
            v("div", Ov, [
              v("div", null, [
                g[21] || (g[21] = v("h2", { class: "cmst:text-lg cmst:font-semibold" }, "Setup workflow", -1)),
                v("p", Tv, "Step " + re(l.value + 1) + " of " + re(C(ls).length) + " · " + re(c.value), 1)
              ]),
              U($e, {
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
            v("div", Iv, [
              c.value === "feature-type" ? (Q(), he(je, { key: 0 }, [
                g[24] || (g[24] = v("h3", { class: "cmst:font-semibold" }, "Feature Type", -1)),
                g[25] || (g[25] = v("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Feature type is explicit and provider-neutral.", -1)),
                v("select", {
                  class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  value: C(t).wizardDraft?.featureType,
                  onChange: g[3] || (g[3] = (E) => C(t).updateWizard({ featureType: E.target.value }))
                }, [...g[23] || (g[23] = [
                  v("option", { value: "t2i" }, "Text to Image", -1),
                  v("option", { value: "i2i" }, "Image to Image", -1),
                  v("option", { value: "inpaint" }, "Inpaint", -1),
                  v("option", { value: "sketch" }, "Sketch", -1),
                  v("option", { value: "outpaint" }, "Outpaint", -1)
                ])], 40, Nv)
              ], 64)) : c.value === "required-bindings" ? (Q(), he(je, { key: 1 }, [
                g[27] || (g[27] = v("h3", { class: "cmst:font-semibold" }, "Required Bindings", -1)),
                g[28] || (g[28] = v("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Graph binding is explicit: underlying ComfyUI graph interaction is enabled while this step is active.", -1)),
                v("div", Pv, [
                  Xt(v("input", {
                    "onUpdate:modelValue": g[4] || (g[4] = (E) => i.value = E),
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                    placeholder: "Node/widget target"
                  }, null, 512), [
                    [Cn, i.value]
                  ]),
                  U($e, {
                    size: "sm",
                    onClick: S
                  }, {
                    default: ae(() => [...g[26] || (g[26] = [
                      te("Confirm binding", -1)
                    ])]),
                    _: 1
                  })
                ]),
                a.value ? (Q(), he("p", Mv, re(a.value), 1)) : Ye("", !0)
              ], 64)) : c.value === "exposed-controls" ? (Q(), he(je, { key: 2 }, [
                g[29] || (g[29] = v("h3", { class: "cmst:font-semibold" }, "Exposed Controls", -1)),
                g[30] || (g[30] = v("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Control selection is stored in the bounded session draft.", -1))
              ], 64)) : (Q(), he(je, { key: 3 }, [
                g[31] || (g[31] = v("h3", { class: "cmst:font-semibold" }, "Details", -1)),
                g[32] || (g[32] = v("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Review the explicit bindings before saving the version mapping.", -1))
              ], 64))
            ]),
            v("div", $v, [
              U($e, {
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
              U($e, {
                size: "sm",
                disabled: l.value === C(ls).length - 1,
                onClick: x
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
}), zv = {
  playground: Py,
  history: ky,
  workflows: jv,
  backend: Zg,
  settings: Jy
};
function Dv(e = {}) {
  let t;
  return e.memory || !e.win ? t = hm() : t = Ag(e.win, e.initial), $m({
    history: t,
    routes: oi.map((n) => ({
      path: `/${n}`,
      name: n,
      component: zv[n]
    }))
  });
}
function Vv(e, t = {}) {
  const s = Ef(), n = Dv({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = Cf(Sg);
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
  Vv as mountStudioPreview
};

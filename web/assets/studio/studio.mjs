/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function No(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const Oe = {}, ks = [], Dt = () => {
}, Va = () => !1, dr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), fr = (e) => e.startsWith("onUpdate:"), Ke = Object.assign, Po = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, Yc = Object.prototype.hasOwnProperty, we = (e, t) => Yc.call(e, t), G = Array.isArray, ds = (e) => An(e) === "[object Map]", Xt = (e) => An(e) === "[object Set]", fi = (e) => An(e) === "[object Date]", oe = (e) => typeof e == "function", je = (e) => typeof e == "string", gt = (e) => typeof e == "symbol", Ce = (e) => e !== null && typeof e == "object", za = (e) => (Ce(e) || oe(e)) && oe(e.then) && oe(e.catch), Fa = Object.prototype.toString, An = (e) => Fa.call(e), Qc = (e) => An(e).slice(8, -1), Ua = (e) => An(e) === "[object Object]", mr = (e) => je(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, an = /* @__PURE__ */ No(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), hr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, Xc = /-\w/g, rt = hr(
  (e) => e.replace(Xc, (t) => t.slice(1).toUpperCase())
), eu = /\B([A-Z])/g, Ts = hr(
  (e) => e.replace(eu, "-$1").toLowerCase()
), pr = hr((e) => e.charAt(0).toUpperCase() + e.slice(1)), Tr = hr(
  (e) => e ? `on${pr(e)}` : ""
), Mt = (e, t) => !Object.is(e, t), Wn = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Ba = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, gr = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let mi;
const yr = () => mi || (mi = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Mo(e) {
  if (G(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = je(n) ? ru(n) : Mo(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (je(e) || Ce(e))
    return e;
}
const tu = /;(?![^(]*\))/g, su = /:([^]+)/, nu = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function ru(e) {
  const t = {};
  return e.replace(nu, (s) => s.startsWith("/*") ? "" : s).split(tu).forEach((s) => {
    if (s) {
      const n = s.split(su);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function lt(e) {
  let t = "";
  if (je(e))
    t = e;
  else if (G(e))
    for (let s = 0; s < e.length; s++) {
      const n = lt(e[s]);
      n && (t += n + " ");
    }
  else if (Ce(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const ou = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", iu = /* @__PURE__ */ No(ou);
function Wa(e) {
  return !!e || e === "";
}
function au(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = es(e[r], t[r], s);
  return n;
}
function hi(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < n.length; a++)
      if (!r[a] && es(o, n[a], s)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function lu(e, t, s) {
  let n = ds(e), r = ds(t);
  if (n || r || (n = Xt(e), r = Xt(t), n || r))
    return n && r ? hi(e, t, s) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !es(e[a], t[a], s))
      return !1;
  }
  return String(e) === String(t);
}
function pi(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = n(e, t, s);
  return r.delete(e), o.delete(t), i;
}
function es(e, t, s) {
  if (e === t) return !0;
  let n = fi(e), r = fi(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = gt(e), r = gt(t), n || r ? e === t : (n = G(e), r = G(t), n || r ? n && r ? pi(e, t, s, au) : !1 : (n = Ce(e), r = Ce(t), n || r ? !n || !r ? !1 : pi(e, t, s, lu) : String(e) === String(t))));
}
function jo(e, t) {
  return e.findIndex((s) => es(s, t));
}
const Ha = (e) => !!(e && e.__v_isRef === !0), de = (e) => je(e) ? e : e == null ? "" : G(e) || Ce(e) && (e.toString === Fa || !oe(e.toString)) ? Ha(e) ? de(e.value) : JSON.stringify(e, Za, 2) : String(e), Za = (e, t) => Ha(t) ? Za(e, t.value) : ds(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[Ir(n, o) + " =>"] = r, s),
    {}
  )
} : Xt(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => Ir(s))
} : gt(t) ? Ir(t) : Ce(t) && !G(t) && !Ua(t) ? String(t) : t, Ir = (e, t = "") => {
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
let Be;
class Ga {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && Be && (Be.active ? (this.parent = Be, this.index = (Be.scopes || (Be.scopes = [])).push(
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
      const s = Be;
      try {
        return Be = this, t();
      } finally {
        Be = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = Be, Be = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (Be === this)
        Be = this.prevScope;
      else {
        let t = Be;
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
function qa(e) {
  return new Ga(e);
}
function Do() {
  return Be;
}
function Ka(e, t = !1) {
  Be && Be.cleanups.push(e);
}
let Te;
const Nr = /* @__PURE__ */ new WeakSet();
class Ja {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, Be && (Be.active ? Be.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, Nr.has(this) && (Nr.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || Qa(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, gi(this), Xa(this);
    const t = Te, s = kt;
    Te = this, kt = !0;
    try {
      return this.fn();
    } finally {
      el(this), Te = t, kt = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        Vo(t);
      this.deps = this.depsTail = void 0, gi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? Nr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    oo(this) && this.run();
  }
  get dirty() {
    return oo(this);
  }
}
let Ya = 0, ln, cn;
function Qa(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = cn, cn = e;
    return;
  }
  e.next = ln, ln = e;
}
function Lo() {
  Ya++;
}
function $o() {
  if (--Ya > 0)
    return;
  if (cn) {
    let t = cn;
    for (cn = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; ln; ) {
    let t = ln;
    for (ln = void 0; t; ) {
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
function Xa(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function el(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), Vo(n), cu(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function oo(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (tl(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function tl(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === pn) || (e.globalVersion = pn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !oo(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = Te, n = kt;
  Te = e, kt = !0;
  try {
    Xa(e);
    const r = e.fn(e._value);
    (t.version === 0 || Mt(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Te = s, kt = n, el(e), e.flags &= -3;
  }
}
function Vo(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      Vo(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function cu(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let kt = !0;
const sl = [];
function Vt() {
  sl.push(kt), kt = !1;
}
function zt() {
  const e = sl.pop();
  kt = e === void 0 ? !0 : e;
}
function gi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = Te;
    Te = void 0;
    try {
      t();
    } finally {
      Te = s;
    }
  }
}
let pn = 0;
class uu {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class zo {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!Te || !kt || Te === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== Te)
      s = this.activeLink = new uu(Te, this), Te.deps ? (s.prevDep = Te.depsTail, Te.depsTail.nextDep = s, Te.depsTail = s) : Te.deps = Te.depsTail = s, nl(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = Te.depsTail, s.nextDep = void 0, Te.depsTail.nextDep = s, Te.depsTail = s, Te.deps === s && (Te.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, pn++, this.notify(t);
  }
  notify(t) {
    Lo();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      $o();
    }
  }
}
function nl(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        nl(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const Gn = /* @__PURE__ */ new WeakMap(), Cs = /* @__PURE__ */ Symbol(
  ""
), io = /* @__PURE__ */ Symbol(
  ""
), gn = /* @__PURE__ */ Symbol(
  ""
);
function Qe(e, t, s) {
  if (kt && Te) {
    let n = Gn.get(e);
    n || Gn.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new zo()), r.map = n, r.key = s), r.track();
  }
}
function Kt(e, t, s, n, r, o) {
  const i = Gn.get(e);
  if (!i) {
    pn++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (Lo(), t === "clear")
    i.forEach(a);
  else {
    const l = G(e), c = l && mr(s);
    if (l && s === "length") {
      const u = Number(n);
      i.forEach((d, m) => {
        (m === "length" || m === gn || !gt(m) && m >= u) && a(d);
      });
    } else
      switch ((s !== void 0 || i.has(void 0)) && a(i.get(s)), c && a(i.get(gn)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(Cs)), ds(e) && a(i.get(io)));
          break;
        case "delete":
          l || (a(i.get(Cs)), ds(e) && a(i.get(io)));
          break;
        case "set":
          ds(e) && a(i.get(Cs));
          break;
      }
  }
  $o();
}
function du(e, t) {
  const s = Gn.get(e);
  return s && s.get(t);
}
function Ns(e) {
  const t = /* @__PURE__ */ be(e);
  return t === e || (Qe(t, "iterate", gn), /* @__PURE__ */ pt(e)) ? t : /* @__PURE__ */ Ft(e) ? /* @__PURE__ */ Lt(e) ? t.map((s) => hs(vt(s))) : t.map(hs) : t.map(vt);
}
function vr(e) {
  return Qe(e = /* @__PURE__ */ be(e), "iterate", gn), e;
}
function It(e, t) {
  return /* @__PURE__ */ Ft(e) ? hs(/* @__PURE__ */ Lt(e) ? vt(t) : t) : vt(t);
}
const fu = {
  __proto__: null,
  [Symbol.iterator]() {
    return Pr(this, Symbol.iterator, (e) => It(this, e));
  },
  concat(...e) {
    return Ns(this).concat(
      ...e.map((t) => G(t) ? Ns(t) : t)
    );
  },
  entries() {
    return Pr(this, "entries", (e) => (e[1] = It(this, e[1]), e));
  },
  every(e, t) {
    return Wt(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return Wt(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => It(this, n)),
      arguments
    );
  },
  find(e, t) {
    return Wt(
      this,
      "find",
      e,
      t,
      (s) => It(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return Wt(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return Wt(
      this,
      "findLast",
      e,
      t,
      (s) => It(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return Wt(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return Wt(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return Mr(this, "includes", e);
  },
  indexOf(...e) {
    return Mr(this, "indexOf", e);
  },
  join(e) {
    return Ns(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return Mr(this, "lastIndexOf", e);
  },
  map(e, t) {
    return Wt(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return Qs(this, "pop");
  },
  push(...e) {
    return Qs(this, "push", e);
  },
  reduce(e, ...t) {
    return vi(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return vi(this, "reduceRight", e, t);
  },
  shift() {
    return Qs(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return Wt(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return Qs(this, "splice", e);
  },
  toReversed() {
    return Ns(this).toReversed();
  },
  toSorted(e) {
    return Ns(this).toSorted(e);
  },
  toSpliced(...e) {
    return Ns(this).toSpliced(...e);
  },
  unshift(...e) {
    return Qs(this, "unshift", e);
  },
  values() {
    return Pr(this, "values", (e) => It(this, e));
  }
};
function Pr(e, t, s) {
  const n = vr(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ pt(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => yi(o.next(), s), r !== rl[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => yi(o._next(), s);
  }
  return o;
}
function yi(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const rl = Array.prototype;
function Wt(e, t, s, n, r, o) {
  const i = vr(e), a = i !== e && !/* @__PURE__ */ pt(e), l = i[t];
  if (l !== rl[t]) {
    const d = l.apply(e, o);
    return a ? vt(d) : d;
  }
  let c = s;
  i !== e && (a ? c = function(d, m) {
    return s.call(this, It(e, d), m, e);
  } : s.length > 2 && (c = function(d, m) {
    return s.call(this, d, m, e);
  }));
  const u = l.call(i, c, n);
  return a && r ? r(u) : u;
}
function vi(e, t, s, n) {
  const r = vr(e), o = r !== e && !/* @__PURE__ */ pt(e);
  let i = s, a = !1;
  r !== e && (o ? (a = n.length === 0, i = function(c, u, d) {
    return a && (a = !1, c = It(e, c)), s.call(this, c, It(e, u), d, e);
  }) : s.length > 3 && (i = function(c, u, d) {
    return s.call(this, c, u, d, e);
  }));
  const l = r[t](i, ...n);
  return a ? It(e, l) : l;
}
function Mr(e, t, s) {
  const n = /* @__PURE__ */ be(e);
  Qe(n, "iterate", gn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ br(s[0]) ? (s[0] = /* @__PURE__ */ be(s[0]), n[t](...s)) : r;
}
function Qs(e, t, s = []) {
  Vt(), Lo();
  const n = (/* @__PURE__ */ be(e))[t].apply(e, s);
  return $o(), zt(), n;
}
const mu = /* @__PURE__ */ No("__proto__,__v_isRef,__isVue"), ol = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(gt)
);
function hu(e) {
  gt(e) || (e = String(e));
  const t = /* @__PURE__ */ be(this);
  return Qe(t, "has", e), t.hasOwnProperty(e);
}
class il {
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
      return n === (r ? o ? Su : ul : o ? cl : ll).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const i = G(t);
    if (!r) {
      let l;
      if (i && (l = fu[s]))
        return l;
      if (s === "hasOwnProperty")
        return hu;
    }
    const a = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ Le(t) ? t : n
    );
    if ((gt(s) ? ol.has(s) : mu(s)) || (r || Qe(t, "get", s), o))
      return a;
    if (/* @__PURE__ */ Le(a)) {
      const l = i && mr(s) ? a : a.value;
      return r && Ce(l) ? /* @__PURE__ */ lo(l) : l;
    }
    return Ce(a) ? r ? /* @__PURE__ */ lo(a) : /* @__PURE__ */ En(a) : a;
  }
}
class al extends il {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const i = G(t) && mr(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ Ft(o);
      if (!/* @__PURE__ */ pt(n) && !/* @__PURE__ */ Ft(n) && (o = /* @__PURE__ */ be(o), n = /* @__PURE__ */ be(n)), !i && /* @__PURE__ */ Le(o) && !/* @__PURE__ */ Le(n))
        return c || (o.value = n), !0;
    }
    const a = i ? Number(s) < t.length : we(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ Le(t) ? t : r
    );
    return t === /* @__PURE__ */ be(r) && l && (a ? Mt(n, o) && Kt(t, "set", s, n) : Kt(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = we(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && Kt(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!gt(s) || !ol.has(s)) && Qe(t, "has", s), n;
  }
  ownKeys(t) {
    return Qe(
      t,
      "iterate",
      G(t) ? "length" : Cs
    ), Reflect.ownKeys(t);
  }
}
class pu extends il {
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
const gu = /* @__PURE__ */ new al(), yu = /* @__PURE__ */ new pu(), vu = /* @__PURE__ */ new al(!0);
const ao = (e) => e, Pn = (e) => Reflect.getPrototypeOf(e);
function bu(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ be(r), i = ds(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...n), u = s ? ao : t ? hs : vt;
    return !t && Qe(
      o,
      "iterate",
      l ? io : Cs
    ), Ke(
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
function Mn(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function _u(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ be(o), a = /* @__PURE__ */ be(r);
      e || (Mt(r, a) && Qe(i, "get", r), Qe(i, "get", a));
      const { has: l } = Pn(i), c = t ? ao : e ? hs : vt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && Qe(/* @__PURE__ */ be(r), "iterate", Cs), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ be(o), a = /* @__PURE__ */ be(r);
      return e || (Mt(r, a) && Qe(i, "has", r), Qe(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ be(a), c = t ? ao : e ? hs : vt;
      return !e && Qe(l, "iterate", Cs), a.forEach((u, d) => r.call(o, c(u), c(d), i));
    }
  };
  return Ke(
    s,
    e ? {
      add: Mn("add"),
      set: Mn("set"),
      delete: Mn("delete"),
      clear: Mn("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ be(this), i = Pn(o), a = /* @__PURE__ */ be(r), l = !t && !/* @__PURE__ */ pt(r) && !/* @__PURE__ */ Ft(r) ? a : r;
        return i.has.call(o, l) || Mt(r, l) && i.has.call(o, r) || Mt(a, l) && i.has.call(o, a) || (o.add(l), Kt(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ pt(o) && !/* @__PURE__ */ Ft(o) && (o = /* @__PURE__ */ be(o));
        const i = /* @__PURE__ */ be(this), { has: a, get: l } = Pn(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ be(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? Mt(o, u) && Kt(i, "set", r, o) : Kt(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ be(this), { has: i, get: a } = Pn(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ be(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && Kt(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ be(this), o = r.size !== 0, i = r.clear();
        return o && Kt(
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
    s[r] = bu(r, e, t);
  }), s;
}
function Fo(e, t) {
  const s = _u(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    we(s, r) && r in n ? s : n,
    r,
    o
  );
}
const xu = {
  get: /* @__PURE__ */ Fo(!1, !1)
}, wu = {
  get: /* @__PURE__ */ Fo(!1, !0)
}, ku = {
  get: /* @__PURE__ */ Fo(!0, !1)
};
const ll = /* @__PURE__ */ new WeakMap(), cl = /* @__PURE__ */ new WeakMap(), ul = /* @__PURE__ */ new WeakMap(), Su = /* @__PURE__ */ new WeakMap();
function Cu(e) {
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
function En(e) {
  return /* @__PURE__ */ Ft(e) ? e : Uo(
    e,
    !1,
    gu,
    xu,
    ll
  );
}
// @__NO_SIDE_EFFECTS__
function dl(e) {
  return Uo(
    e,
    !1,
    vu,
    wu,
    cl
  );
}
// @__NO_SIDE_EFFECTS__
function lo(e) {
  return Uo(
    e,
    !0,
    yu,
    ku,
    ul
  );
}
function Uo(e, t, s, n, r) {
  if (!Ce(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = Cu(Qc(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? n : s
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Lt(e) {
  return /* @__PURE__ */ Ft(e) ? /* @__PURE__ */ Lt(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function Ft(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function pt(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function br(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function be(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ be(t) : e;
}
function Bo(e) {
  return !we(e, "__v_skip") && Object.isExtensible(e) && Ba(e, "__v_skip", !0), e;
}
const vt = (e) => Ce(e) ? /* @__PURE__ */ En(e) : e, hs = (e) => Ce(e) ? /* @__PURE__ */ lo(e) : e;
// @__NO_SIDE_EFFECTS__
function Le(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function te(e) {
  return fl(e, !1);
}
// @__NO_SIDE_EFFECTS__
function un(e) {
  return fl(e, !0);
}
function fl(e, t) {
  return /* @__PURE__ */ Le(e) ? e : new Au(e, t);
}
class Au {
  constructor(t, s) {
    this.dep = new zo(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ be(t), this._value = s ? t : vt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ pt(t) || /* @__PURE__ */ Ft(t);
    t = n ? t : /* @__PURE__ */ be(t), Mt(t, s) && (this._rawValue = t, this._value = n ? t : vt(t), this.dep.trigger());
  }
}
function O(e) {
  return /* @__PURE__ */ Le(e) ? e.value : e;
}
function $s(e) {
  return oe(e) ? e() : O(e);
}
const Eu = {
  get: (e, t, s) => t === "__v_raw" ? e : O(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ Le(r) && !/* @__PURE__ */ Le(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function ml(e) {
  return /* @__PURE__ */ Lt(e) ? e : new Proxy(e, Eu);
}
// @__NO_SIDE_EFFECTS__
function Ru(e) {
  const t = G(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = Tu(e, s);
  return t;
}
class Ou {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = gt(s) ? s : String(s), this._raw = /* @__PURE__ */ be(t);
    let r = !0, o = t;
    if (!G(t) || gt(this._key) || !mr(this._key))
      do
        r = !/* @__PURE__ */ br(o) || /* @__PURE__ */ pt(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = O(t)), this._value = t === void 0 ? this._defaultValue : t;
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
    return du(this._raw, this._key);
  }
}
function Tu(e, t, s) {
  return new Ou(e, t, s);
}
class Iu {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new zo(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = pn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Te !== this)
      return Qa(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return tl(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function Nu(e, t, s = !1) {
  let n, r;
  return oe(e) ? n = e : (n = e.get, r = e.set), new Iu(n, r, s);
}
const jn = {}, qn = /* @__PURE__ */ new WeakMap();
let ws;
function Pu(e, t = !1, s = ws) {
  if (s) {
    let n = qn.get(s);
    n || qn.set(s, n = []), n.push(e);
  }
}
function Mu(e, t, s = Oe) {
  const { immediate: n, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = s, c = (M) => r ? M : /* @__PURE__ */ pt(M) || r === !1 || r === 0 ? Jt(M, 1) : Jt(M);
  let u, d, m, p, w = !1, x = !1;
  if (/* @__PURE__ */ Le(e) ? (d = () => e.value, w = /* @__PURE__ */ pt(e)) : /* @__PURE__ */ Lt(e) ? (d = () => c(e), w = !0) : G(e) ? (x = !0, w = e.some((M) => /* @__PURE__ */ Lt(M) || /* @__PURE__ */ pt(M)), d = () => e.map((M) => {
    if (/* @__PURE__ */ Le(M))
      return M.value;
    if (/* @__PURE__ */ Lt(M))
      return c(M);
    if (oe(M))
      return l ? l(M, 2) : M();
  })) : oe(e) ? t ? d = l ? () => l(e, 2) : e : d = () => {
    if (m) {
      Vt();
      try {
        m();
      } finally {
        zt();
      }
    }
    const M = ws;
    ws = u;
    try {
      return l ? l(e, 3, [p]) : e(p);
    } finally {
      ws = M;
    }
  } : d = Dt, t && r) {
    const M = d, Y = r === !0 ? 1 / 0 : r;
    d = () => Jt(M(), Y);
  }
  const D = Do(), $ = () => {
    u.stop(), D && D.active && Po(D.effects, u);
  };
  if (o && t) {
    const M = t;
    t = (...Y) => {
      try {
        return M(...Y);
      } finally {
        $();
      }
    };
  }
  let C = x ? new Array(e.length).fill(jn) : jn;
  const I = (M) => {
    if (!(!(u.flags & 1) || !u.dirty && !M))
      if (t) {
        const Y = u.run();
        if (M || r || w || (x ? Y.some((xe, ne) => Mt(xe, C[ne])) : Mt(Y, C))) {
          const xe = ws;
          Vt();
          try {
            m && m(), ws = u;
            const ne = [
              Y,
              // pass undefined as the old value when it's changed for the first time
              C === jn ? void 0 : x && C[0] === jn ? [] : C,
              p
            ];
            C = Y, l ? l(t, 3, ne) : (
              // @ts-expect-error
              t(...ne)
            );
          } finally {
            ws = xe, zt();
          }
        }
      } else
        u.run();
  };
  return a && a(I), u = new Ja(d), u.scheduler = i ? () => i(I, !1) : I, p = (M) => Pu(M, !1, u), m = u.onStop = () => {
    const M = qn.get(u);
    if (M) {
      if (l)
        l(M, 4);
      else
        for (const Y of M) Y();
      qn.delete(u);
    }
  }, t ? n ? I(!0) : C = u.run() : i ? i(I.bind(null, !0), !0) : u.run(), $.pause = u.pause.bind(u), $.resume = u.resume.bind(u), $.stop = $, $;
}
function Jt(e, t = 1 / 0, s) {
  if (t <= 0 || !Ce(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ Le(e))
    Jt(e.value, t, s);
  else if (G(e))
    for (let n = 0; n < e.length; n++)
      Jt(e[n], t, s);
  else if (Xt(e) || ds(e))
    e.forEach((n) => {
      Jt(n, t, s);
    });
  else if (Ua(e)) {
    for (const n in e)
      Jt(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && Jt(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function Rn(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (r) {
    _r(r, t, s);
  }
}
function St(e, t, s, n) {
  if (oe(e)) {
    const r = Rn(e, t, s, n);
    return r && za(r) && r.catch((o) => {
      _r(o, t, s);
    }), r;
  }
  if (G(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(St(e[o], t, s, n));
    return r;
  }
}
function _r(e, t, s, n = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || Oe;
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
      Vt(), Rn(o, null, 10, [
        e,
        l,
        c
      ]), zt();
      return;
    }
  }
  ju(e, s, r, n, i);
}
function ju(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const nt = [];
let wt = -1;
const Nt = [];
let as = null, js = 0;
const hl = /* @__PURE__ */ Promise.resolve();
let Kn = null;
function xr(e) {
  const t = Kn || hl;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function Du(e) {
  let t = wt + 1, s = nt.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = nt[n], o = yn(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function Wo(e) {
  if (!(e.flags & 1)) {
    const t = yn(e), s = nt[nt.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= yn(s) ? nt.push(e) : nt.splice(Du(t), 0, e), e.flags |= 1, pl();
  }
}
function pl() {
  Kn || (Kn = hl.then(vl));
}
function Lu(e) {
  if (!G(e))
    as && e.id === -1 ? as.splice(js + 1, 0, e) : e.flags & 1 || (Nt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Nt.push(e[t]);
  pl();
}
function gl(e, t, s, n = wt + 1) {
  for (; n < nt.length; n++) {
    const r = nt[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      nt.splice(n, 1), n = e ? n - 1 : wt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function yl(e, t, s = 0) {
  if (Nt.length) {
    let n = Nt, r = 0;
    if (t) {
      n = [];
      for (let i = 0; i < Nt.length; i++) {
        const a = Nt[i];
        (a.i !== void 0 ? !a.i || a.i.uid < s : t.has(a)) ? Nt[r++] = a : n.push(a);
      }
    }
    const o = [...new Set(n)].sort((i, a) => yn(i) - yn(a));
    if (Nt.length = r, as) {
      for (let i = 0; i < o.length; i++)
        as.push(o[i]);
      return;
    }
    for (as = o, js = 0; js < as.length; js++) {
      const i = as[js];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    as = null, js = 0;
  }
}
let jr = !1;
function $u(e, t) {
  if (jr) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Nt);
  e(), jr = !0;
  try {
    gl(void 0, t), yl(void 0, s, t);
  } finally {
    jr = !1;
  }
}
const yn = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function vl(e) {
  try {
    for (wt = 0; wt < nt.length; wt++) {
      const t = nt[wt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), Rn(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; wt < nt.length; wt++) {
      const t = nt[wt];
      t && (t.flags &= -2);
    }
    wt = -1, nt.length = 0, yl(), Kn = null, (nt.length || Nt.length) && vl();
  }
}
let qe = null, bl = null;
function Jn(e) {
  const t = qe;
  return qe = e, bl = e && e.type.__scopeId || null, t;
}
function pe(e, t = qe, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && er(-1);
    const o = Jn(t), i = Qt.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = Qt.length; l > i; l--) Jo();
      Jn(o), n._d && er(1);
    }
    return a;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function fs(e, t) {
  if (qe === null)
    return e;
  const s = Er(qe), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = Oe] = t[r];
    o && (oe(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && Jt(i), n.push({
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
function vs(e, t, s, n) {
  const r = e.dirs, o = t && t.dirs;
  for (let i = 0; i < r.length; i++) {
    const a = r[i];
    o && (a.oldValue = o[i].value);
    let l = a.dir[n];
    l && (Vt(), St(l, s, 8, [
      e.el,
      a,
      e,
      t
    ]), zt());
  }
}
function Hn(e, t) {
  if (Xe) {
    let s = Xe.provides;
    const n = Xe.parent && Xe.parent.provides;
    n === s && (s = Xe.provides = Object.create(n)), s[e] = t;
  }
}
function at(e, t, s = !1) {
  const n = Ar();
  if (n || Es) {
    let r = Es ? Es._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && oe(t) ? t.call(n && n.proxy) : t;
  }
}
function Ho() {
  return !!(Ar() || Es);
}
const Vu = /* @__PURE__ */ Symbol.for("v-scx"), zu = () => at(Vu);
function Fu(e, t) {
  return Zo(e, null, t);
}
function As(e, t, s) {
  return Zo(e, t, s);
}
function Zo(e, t, s = Oe) {
  const { immediate: n, deep: r, flush: o, once: i } = s, a = Ke({}, s), l = t && n || !t && o !== "post";
  let c;
  if (_n) {
    if (o === "sync") {
      const p = zu();
      c = p.__watcherHandles || (p.__watcherHandles = []);
    } else if (!l) {
      const p = () => {
      };
      return p.stop = Dt, p.resume = Dt, p.pause = Dt, p;
    }
  }
  const u = Xe;
  a.call = (p, w, x) => St(p, u, w, x);
  let d = !1;
  o === "post" ? a.scheduler = (p) => {
    p.i = u, it(p, u && u.suspense);
  } : o !== "sync" && (d = !0, a.scheduler = (p, w) => {
    w ? p() : Wo(p);
  }), a.augmentJob = (p) => {
    t && (p.flags |= 4), d && (p.flags |= 2, u && (p.id = u.uid, p.i = u));
  };
  const m = Mu(e, t, a);
  return _n && (c ? c.push(m) : l && m()), m;
}
function Uu(e, t, s) {
  const n = this.proxy, r = je(e) ? e.includes(".") ? _l(n, e) : () => n[e] : e.bind(n, n);
  let o;
  oe(t) ? o = t : (o = t.handler, s = t);
  const i = In(this), a = Zo(r, o.bind(n), s);
  return i(), a;
}
function _l(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const Bu = /* @__PURE__ */ Symbol("_vte"), wr = (e) => e.__isTeleport, Dr = /* @__PURE__ */ Symbol("_leaveCb");
function Wu(e) {
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
function xl(e) {
  if (!Go(e))
    return wr(e.type) && e.children ? Wu(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && oe(s.default))
      return s.default();
  }
}
function Yn(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    Yn(
      wr(s.type) && xl(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === We && G(e.children)) {
    const s = Nl(e.children, !1);
    s && Yn(s, t);
  }
}
function co(e) {
  if (e.component)
    return co(e.component.subTree);
  if (e.type === We) {
    const t = G(e.children) && Nl(e.children, !1);
    return t ? co(t) : void 0;
  }
  if (e.type !== bt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function yt(e, t) {
  return oe(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    Ke({ name: e.name }, t, { setup: e })
  ) : e;
}
function wl(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function bi(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const Qn = /* @__PURE__ */ new WeakMap();
function dn(e, t, s, n, r = !1) {
  if (G(e)) {
    e.forEach(
      (x, D) => dn(
        x,
        t && (G(t) ? t[D] : t),
        s,
        n,
        r
      )
    );
    return;
  }
  if (Vs(n) && !r) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && dn(e, t, s, n.component.subTree);
    return;
  }
  const o = n.shapeFlag & 4 ? Er(n.component) : n.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === Oe ? a.refs = {} : a.refs, d = a.setupState, m = /* @__PURE__ */ be(d), p = d === Oe ? Va : (x) => bi(u, x) ? !1 : we(m, x), w = (x, D) => !(D && bi(u, D));
  if (c != null && c !== l) {
    if (_i(t), je(c))
      u[c] = null, p(c) && (d[c] = null);
    else if (/* @__PURE__ */ Le(c)) {
      const x = t;
      w(c, x.k) && (c.value = null), x.k && (u[x.k] = null);
    }
  }
  if (oe(l))
    Rn(l, a, 12, [i, u]);
  else {
    const x = je(l), D = /* @__PURE__ */ Le(l);
    if (x || D) {
      const $ = () => {
        if (e.f) {
          const C = x ? p(l) ? d[l] : u[l] : w() || !e.k ? l.value : u[e.k];
          if (r)
            G(C) && Po(C, o);
          else if (G(C))
            C.includes(o) || C.push(o);
          else if (x)
            u[l] = [o], p(l) && (d[l] = u[l]);
          else {
            const I = [o];
            w(l, e.k) && (l.value = I), e.k && (u[e.k] = I);
          }
        } else x ? (u[l] = i, p(l) && (d[l] = i)) : D && (w(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const C = () => {
          $(), Qn.delete(e);
        };
        C.id = -1, Qn.set(e, C), it(C, s);
      } else
        _i(e), $();
    }
  }
}
function _i(e) {
  const t = Qn.get(e);
  t && (t.flags |= 8, Qn.delete(e));
}
yr().requestIdleCallback;
yr().cancelIdleCallback;
const Vs = (e) => !!e.type.__asyncLoader, Go = (e) => e.type.__isKeepAlive;
function Hu(e, t) {
  kl(e, "a", t);
}
function Zu(e, t) {
  kl(e, "da", t);
}
function kl(e, t, s = Xe) {
  const n = e.__wdc || (e.__wdc = () => {
    let r = s;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (kr(t, n, s), s) {
    let r = s.parent;
    for (; r && r.parent; )
      Go(r.parent.vnode) && Gu(n, t, s, r), r = r.parent;
  }
}
function Gu(e, t, s, n) {
  const r = kr(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  Sl(() => {
    Po(n[t], r);
  }, s);
}
function kr(e, t, s = Xe, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Vt();
      const a = In(s), l = St(t, s, e, i);
      return a(), zt(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const ss = (e) => (t, s = Xe) => {
  (!_n || e === "sp") && kr(e, (...n) => t(...n), s);
}, qu = ss("bm"), On = ss("m"), Ku = ss(
  "bu"
), Ju = ss("u"), Yu = ss(
  "bum"
), Sl = ss("um"), Qu = ss(
  "sp"
), Xu = ss("rtg"), ed = ss("rtc");
function td(e, t = Xe) {
  kr("ec", e, t);
}
const sd = "components", Cl = /* @__PURE__ */ Symbol.for("v-ndc");
function nd(e) {
  return je(e) ? rd(sd, e, !1) || e : e || Cl;
}
function rd(e, t, s = !0, n = !1) {
  const r = qe || Xe;
  if (r) {
    const o = r.type;
    {
      const a = Fd(
        o,
        !1
      );
      if (a && (a === t || a === rt(t) || a === pr(rt(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      xi(r[e] || o[e], t) || // global registration
      xi(r.appContext[e], t)
    );
    return !i && n ? o : i;
  }
}
function xi(e, t) {
  return e && (e[t] || e[rt(t)] || e[pr(rt(t))]);
}
function Tn(e, t, s, n) {
  let r;
  const o = s, i = G(e);
  if (i || je(e)) {
    const a = i && /* @__PURE__ */ Lt(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ pt(e), c = /* @__PURE__ */ Ft(e), e = vr(e)), r = new Array(e.length);
    for (let u = 0, d = e.length; u < d; u++)
      r[u] = t(
        l ? c ? hs(vt(e[u])) : vt(e[u]) : e[u],
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
  else if (Ce(e))
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
function Al(e, t, s, n, r, o) {
  if (s == null && (s = {}), qe.ce || qe.parent && Vs(qe.parent) && qe.parent.ce) {
    const c = s, u = Object.keys(c).length > 0;
    return ae(), ft(
      We,
      null,
      [J("slot", c, n)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = Qt.length;
  ae();
  let l;
  try {
    const c = i && El(i(s)), u = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = ft(
      We,
      {
        key: (u && !gt(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = Qt.length; u > a; u--) Jo();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function El(e) {
  return e.some((t) => zs(t) ? !(t.type === bt || t.type === We && !El(t.children)) : !0) ? e : null;
}
const uo = (e) => e ? ql(e) ? Er(e) : uo(e.parent) : null, fn = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ Ke(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => uo(e.parent),
    $root: (e) => uo(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => Ol(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      Wo(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = xr.bind(e.proxy)),
    $watch: (e) => Uu.bind(e)
  })
), Lr = (e, t) => e !== Oe && !e.__isScriptSetup && we(e, t), od = {
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
        if (Lr(n, t))
          return i[t] = 1, n[t];
        if (r !== Oe && we(r, t))
          return i[t] = 2, r[t];
        if (we(o, t))
          return i[t] = 3, o[t];
        if (s !== Oe && we(s, t))
          return i[t] = 4, s[t];
        fo && (i[t] = 0);
      }
    }
    const c = fn[t];
    let u, d;
    if (c)
      return t === "$attrs" && Qe(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (u = a.__cssModules) && (u = u[t])
    )
      return u;
    if (s !== Oe && we(s, t))
      return i[t] = 4, s[t];
    if (
      // global properties
      d = l.config.globalProperties, we(d, t)
    )
      return d[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: r, ctx: o } = e;
    return Lr(r, t) ? (r[t] = s, !0) : n !== Oe && we(n, t) ? (n[t] = s, !0) : we(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(s[a] || e !== Oe && a[0] !== "$" && we(e, a) || Lr(t, a) || we(o, a) || we(n, a) || we(fn, a) || we(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : we(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function wi(e) {
  return G(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let fo = !0;
function id(e) {
  const t = Ol(e), s = e.proxy, n = e.ctx;
  fo = !1, t.beforeCreate && ki(t.beforeCreate, e, "bc");
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
    beforeUpdate: p,
    updated: w,
    activated: x,
    deactivated: D,
    beforeDestroy: $,
    beforeUnmount: C,
    destroyed: I,
    unmounted: M,
    render: Y,
    renderTracked: xe,
    renderTriggered: ne,
    errorCaptured: v,
    serverPrefetch: V,
    // public API
    expose: ce,
    inheritAttrs: ke,
    // assets
    components: Z,
    directives: ge,
    filters: Pe
  } = t;
  if (c && ad(c, n, null), i)
    for (const X in i) {
      const he = i[X];
      oe(he) && (n[X] = he.bind(s));
    }
  if (r) {
    const X = r.call(s, s);
    Ce(X) && (e.data = /* @__PURE__ */ En(X));
  }
  if (fo = !0, o)
    for (const X in o) {
      const he = o[X], ct = oe(he) ? he.bind(s, s) : oe(he.get) ? he.get.bind(s, s) : Dt, W = !oe(he) && oe(he.set) ? he.set.bind(s) : Dt, ut = Ie({
        get: ct,
        set: W
      });
      Object.defineProperty(n, X, {
        enumerable: !0,
        configurable: !0,
        get: () => ut.value,
        set: (He) => ut.value = He
      });
    }
  if (a)
    for (const X in a)
      Rl(a[X], n, s, X);
  if (l) {
    const X = oe(l) ? l.call(s) : l;
    Reflect.ownKeys(X).forEach((he) => {
      Hn(he, X[he]);
    });
  }
  u && ki(u, e, "c");
  function fe(X, he) {
    G(he) ? he.forEach((ct) => X(ct.bind(s))) : he && X(he.bind(s));
  }
  if (fe(qu, d), fe(On, m), fe(Ku, p), fe(Ju, w), fe(Hu, x), fe(Zu, D), fe(td, v), fe(ed, xe), fe(Xu, ne), fe(Yu, C), fe(Sl, M), fe(Qu, V), G(ce))
    if (ce.length) {
      const X = e.exposed || (e.exposed = {});
      ce.forEach((he) => {
        Object.defineProperty(X, he, {
          get: () => s[he],
          set: (ct) => s[he] = ct,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  Y && e.render === Dt && (e.render = Y), ke != null && (e.inheritAttrs = ke), Z && (e.components = Z), ge && (e.directives = ge), V && wl(e);
}
function ad(e, t, s = Dt) {
  G(e) && (e = mo(e));
  for (const n in e) {
    const r = e[n];
    let o;
    Ce(r) ? "default" in r ? o = at(
      r.from || n,
      r.default,
      !0
    ) : o = at(r.from || n) : o = at(r), /* @__PURE__ */ Le(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[n] = o;
  }
}
function ki(e, t, s) {
  St(
    G(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function Rl(e, t, s, n) {
  let r = n.includes(".") ? _l(s, n) : () => s[n];
  if (je(e)) {
    const o = t[e];
    oe(o) && As(r, o);
  } else if (oe(e))
    As(r, e.bind(s));
  else if (Ce(e))
    if (G(e))
      e.forEach((o) => Rl(o, t, s, n));
    else {
      const o = oe(e.handler) ? e.handler.bind(s) : t[e.handler];
      oe(o) && As(r, o, e);
    }
}
function Ol(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !s && !n ? l = t : (l = {}, r.length && r.forEach(
    (c) => Xn(l, c, i, !0)
  ), Xn(l, t, i)), Ce(t) && o.set(t, l), l;
}
function Xn(e, t, s, n = !1) {
  const { mixins: r, extends: o } = t;
  o && Xn(e, o, s, !0), r && r.forEach(
    (i) => Xn(e, i, s, !0)
  );
  for (const i in t)
    if (!(n && i === "expose")) {
      const a = ld[i] || s && s[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const ld = {
  data: Si,
  props: Ci,
  emits: Ci,
  // objects
  methods: nn,
  computed: nn,
  // lifecycle
  beforeCreate: tt,
  created: tt,
  beforeMount: tt,
  mounted: tt,
  beforeUpdate: tt,
  updated: tt,
  beforeDestroy: tt,
  beforeUnmount: tt,
  destroyed: tt,
  unmounted: tt,
  activated: tt,
  deactivated: tt,
  errorCaptured: tt,
  serverPrefetch: tt,
  // assets
  components: nn,
  directives: nn,
  // watch
  watch: ud,
  // provide / inject
  provide: Si,
  inject: cd
};
function Si(e, t) {
  return t ? e ? function() {
    return Ke(
      oe(e) ? e.call(this, this) : e,
      oe(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function cd(e, t) {
  return nn(mo(e), mo(t));
}
function mo(e) {
  if (G(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function tt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function nn(e, t) {
  return e ? Ke(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function Ci(e, t) {
  return e ? G(e) && G(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : Ke(
    /* @__PURE__ */ Object.create(null),
    wi(e),
    wi(t ?? {})
  ) : t;
}
function ud(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = Ke(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = tt(e[n], t[n]);
  return s;
}
function Tl() {
  return {
    app: null,
    config: {
      isNativeTag: Va,
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
let dd = 0;
function fd(e, t) {
  return function(n, r = null) {
    oe(n) || (n = Ke({}, n)), r != null && !Ce(r) && (r = null);
    const o = Tl(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: dd++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: Bd,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...d) {
        return i.has(u) || (u && oe(u.install) ? (i.add(u), u.install(c, ...d)) : oe(u) && (i.add(u), u(c, ...d))), c;
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
          const p = c._ceVNode || J(n, r);
          return p.appContext = o, m === !0 ? m = "svg" : m === !1 && (m = void 0), e(p, u, m), l = !0, c._container = u, u.__vue_app__ = c, Er(p.component);
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
        const d = Es;
        Es = c;
        try {
          return u();
        } finally {
          Es = d;
        }
      }
    };
    return c;
  };
}
let Es = null;
const md = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${rt(t)}Modifiers`] || e[`${Ts(t)}Modifiers`];
function hd(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || Oe;
  let r = s;
  const o = t.startsWith("update:"), i = o && md(n, t.slice(7));
  i && (i.trim && (r = s.map((u) => je(u) ? u.trim() : u)), i.number && (r = r.map(gr)));
  let a, l = n[a = Tr(t)] || // also try camelCase event handler (#2249)
  n[a = Tr(rt(t))];
  !l && o && (l = n[a = Tr(Ts(t))]), l && St(
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
const pd = /* @__PURE__ */ new WeakMap();
function Il(e, t, s = !1) {
  const n = s ? pd : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!oe(e)) {
    const l = (c) => {
      const u = Il(c, t, !0);
      u && (a = !0, Ke(i, u));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (Ce(e) && n.set(e, null), null) : (G(o) ? o.forEach((l) => i[l] = null) : Ke(i, o), Ce(e) && n.set(e, i), i);
}
function Sr(e, t) {
  return !e || !dr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), we(e, t[0].toLowerCase() + t.slice(1)) || we(e, Ts(t)) || we(e, t));
}
function Ai(e) {
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
    setupState: p,
    ctx: w,
    inheritAttrs: x
  } = e, D = Jn(e);
  let $, C;
  try {
    if (s.shapeFlag & 4) {
      const M = r || n, Y = M;
      $ = Pt(
        c.call(
          Y,
          M,
          u,
          d,
          p,
          m,
          w
        )
      ), C = a;
    } else {
      const M = t;
      $ = Pt(
        M.length > 1 ? M(
          d,
          { attrs: a, slots: i, emit: l }
        ) : M(
          d,
          null
        )
      ), C = t.props ? a : gd(a);
    }
  } catch (M) {
    Qt.length = 0, _r(M, e, 1), $ = J(bt);
  }
  let I = $;
  if (C && x !== !1) {
    const M = Object.keys(C), { shapeFlag: Y } = I;
    M.length && Y & 7 && (o && M.some(fr) && (C = yd(
      C,
      o
    )), I = Fs(I, C, !1, !0));
  }
  if (s.dirs && (I = Fs(I, null, !1, !0), I.dirs = I.dirs ? I.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const M = wr(I.type) && xl(I) || I;
    Yn(M, s.transition);
  }
  return $ = I, Jn(D), $;
}
function Nl(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const r = e[n];
    if (zs(r)) {
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
const gd = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || dr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, yd = (e, t) => {
  const s = {};
  for (const n in e)
    (!fr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function vd(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? Ei(n, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let d = 0; d < u.length; d++) {
        const m = u[d];
        if (Pl(i, n, m) && !Sr(c, m))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : n === i ? !1 : n ? i ? Ei(n, i, c) : !0 : !!i;
  return !1;
}
function Ei(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!we(e, o) || Pl(t, e, o) && !Sr(s, o))
      return !0;
  }
  return !1;
}
function Pl(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && Ce(n) && Ce(r) ? !es(n, r) : n !== r;
}
function bd({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const Ml = {}, jl = () => Object.create(Ml), Dl = (e) => Object.getPrototypeOf(e) === Ml;
function _d(e, t, s, n = !1) {
  const r = {}, o = jl();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), Ll(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ dl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function xd(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ be(r), [l] = e.propsOptions;
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
        if (Sr(e.emitsOptions, m))
          continue;
        const p = t[m];
        if (l)
          if (we(o, m))
            p !== o[m] && (o[m] = p, c = !0);
          else {
            const w = rt(m);
            r[w] = ho(
              l,
              a,
              w,
              p,
              e,
              !1
            );
          }
        else
          p !== o[m] && (o[m] = p, c = !0);
      }
    }
  } else {
    Ll(e, t, r, o) && (c = !0);
    let u;
    for (const d in a)
      (!t || // for camelCase
      !we(t, d) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = Ts(d)) === d || !we(t, u))) && (l ? s && // for camelCase
      (s[d] !== void 0 || // for kebab-case
      s[u] !== void 0) && (r[d] = ho(
        l,
        a,
        d,
        void 0,
        e,
        !0
      )) : delete r[d]);
    if (o !== a)
      for (const d in o)
        (!t || !we(t, d)) && (delete o[d], c = !0);
  }
  c && Kt(e.attrs, "set", "");
}
function Ll(e, t, s, n) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (an(l))
        continue;
      const c = t[l];
      let u;
      r && we(r, u = rt(l)) ? !o || !o.includes(u) ? s[u] = c : (a || (a = {}))[u] = c : Sr(e.emitsOptions, l) || (!(l in n) || c !== n[l]) && (n[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ be(s), c = a || Oe;
    for (let u = 0; u < o.length; u++) {
      const d = o[u];
      s[d] = ho(
        r,
        l,
        d,
        c[d],
        e,
        !we(c, d)
      );
    }
  }
  return i;
}
function ho(e, t, s, n, r, o) {
  const i = e[s];
  if (i != null) {
    const a = we(i, "default");
    if (a && n === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && oe(l)) {
        const { propsDefaults: c } = r;
        if (s in c)
          n = c[s];
        else {
          const u = In(r);
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
    ] && (n === "" || n === Ts(s)) && (n = !0));
  }
  return n;
}
const wd = /* @__PURE__ */ new WeakMap();
function $l(e, t, s = !1) {
  const n = s ? wd : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!oe(e)) {
    const u = (d) => {
      l = !0;
      const [m, p] = $l(d, t, !0);
      Ke(i, m), p && a.push(...p);
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return Ce(e) && n.set(e, ks), ks;
  if (G(o))
    for (let u = 0; u < o.length; u++) {
      const d = rt(o[u]);
      Ri(d) && (i[d] = Oe);
    }
  else if (o)
    for (const u in o) {
      const d = rt(u);
      if (Ri(d)) {
        const m = o[u], p = i[d] = G(m) || oe(m) ? { type: m } : Ke({}, m), w = p.type;
        let x = !1, D = !0;
        if (G(w))
          for (let $ = 0; $ < w.length; ++$) {
            const C = w[$], I = oe(C) && C.name;
            if (I === "Boolean") {
              x = !0;
              break;
            } else I === "String" && (D = !1);
          }
        else
          x = oe(w) && w.name === "Boolean";
        p[
          0
          /* shouldCast */
        ] = x, p[
          1
          /* shouldCastTrue */
        ] = D, (x || we(p, "default")) && a.push(d);
      }
    }
  const c = [i, a];
  return Ce(e) && n.set(e, c), c;
}
function Ri(e) {
  return e[0] !== "$" && !an(e);
}
const qo = (e) => e === "_" || e === "_ctx" || e === "$stable", Ko = (e) => G(e) ? e.map(Pt) : [Pt(e)], kd = (e, t, s) => {
  if (t._n)
    return t;
  const n = pe((...r) => Ko(t(...r)), s);
  return n._c = !1, n;
}, Vl = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (qo(r)) continue;
    const o = e[r];
    if (oe(o))
      t[r] = kd(r, o, n);
    else if (o != null) {
      const i = Ko(o);
      t[r] = () => i;
    }
  }
}, zl = (e, t) => {
  const s = Ko(t);
  e.slots.default = () => s;
}, Fl = (e, t, s) => {
  for (const n in t)
    (s || !qo(n)) && (e[n] = t[n]);
}, Sd = (e, t, s) => {
  const n = e.slots = jl();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (Fl(n, t, s), s && Ba(n, "_", r, !0)) : Vl(t, n);
  } else t && zl(e, t);
}, Cd = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, i = Oe;
  if (n.shapeFlag & 32) {
    const a = t._;
    a ? s && a === 1 ? o = !1 : Fl(r, t, s) : (o = !t.$stable, Vl(t, r)), i = t;
  } else t && (zl(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !qo(a) && i[a] == null && delete r[a];
}, it = Td;
function Ad(e) {
  return Ed(e);
}
function Ed(e, t) {
  const s = yr();
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
    setScopeId: p = Dt,
    insertStaticContent: w
  } = e, x = (f, h, g, y = null, b = null, k = null, E = void 0, P = null, N = !!h.dynamicChildren) => {
    if (f === h)
      return;
    f && !Xs(f, h) && (y = _(f), He(f, b, k, !0), f = null), h.patchFlag === -2 && (N = !1, h.dynamicChildren = null), h.dynamicChildren && f && f.dynamicChildren && f.dynamicChildren.hasOnce && (h.dynamicChildren === ks && (h.dynamicChildren = []), h.dynamicChildren.hasOnce = !0);
    const { type: A, ref: q, shapeFlag: j } = h;
    switch (A) {
      case Cr:
        D(f, h, g, y);
        break;
      case bt:
        $(f, h, g, y);
        break;
      case Vr:
        f == null && C(h, g, y, E);
        break;
      case We:
        Z(
          f,
          h,
          g,
          y,
          b,
          k,
          E,
          P,
          N
        );
        break;
      default:
        j & 1 ? Y(
          f,
          h,
          g,
          y,
          b,
          k,
          E,
          P,
          N
        ) : j & 6 ? ge(
          f,
          h,
          g,
          y,
          b,
          k,
          E,
          P,
          N
        ) : (j & 64 || j & 128) && A.process(
          f,
          h,
          g,
          y,
          b,
          k,
          E,
          P,
          N,
          R
        );
    }
    q != null && b ? dn(q, f && f.ref, k, h || f, !h) : q == null && f && f.ref != null && dn(f.ref, null, k, f, !0);
  }, D = (f, h, g, y) => {
    if (f == null)
      n(
        h.el = a(h.children),
        g,
        y
      );
    else {
      const b = h.el = f.el;
      h.children !== f.children && c(b, h.children);
    }
  }, $ = (f, h, g, y) => {
    f == null ? n(
      h.el = l(h.children || ""),
      g,
      y
    ) : h.el = f.el;
  }, C = (f, h, g, y) => {
    [f.el, f.anchor] = w(
      f.children,
      h,
      g,
      y,
      f.el,
      f.anchor
    );
  }, I = ({ el: f, anchor: h }, g, y) => {
    let b;
    for (; f && f !== h; )
      b = m(f), n(f, g, y), f = b;
    n(h, g, y);
  }, M = ({ el: f, anchor: h }) => {
    let g;
    for (; f && f !== h; )
      g = m(f), r(f), f = g;
    r(h);
  }, Y = (f, h, g, y, b, k, E, P, N) => {
    if (h.type === "svg" ? E = "svg" : h.type === "math" && (E = "mathml"), f == null)
      xe(
        h,
        g,
        y,
        b,
        k,
        E,
        P,
        N
      );
    else {
      const A = f.el && f.el._isVueCE ? f.el : null;
      try {
        A && A._beginPatch(), V(
          f,
          h,
          b,
          k,
          E,
          P,
          N
        );
      } finally {
        A && A._endPatch();
      }
    }
  }, xe = (f, h, g, y, b, k, E, P) => {
    let N, A;
    const { props: q, shapeFlag: j, transition: K, dirs: ee } = f;
    if (N = f.el = i(
      f.type,
      k,
      q && q.is,
      q
    ), j & 8 ? u(N, f.children) : j & 16 && v(
      f.children,
      N,
      null,
      y,
      b,
      $r(f, k),
      E,
      P
    ), ee && vs(f, null, y, "created"), ne(N, f, f.scopeId, E, y), q) {
      for (const Re in q)
        Re !== "value" && !an(Re) && o(N, Re, null, q[Re], k, y);
      "value" in q && o(N, "value", null, q.value, k), (A = q.onVnodeBeforeMount) && Ot(A, y, f);
    }
    ee && vs(f, null, y, "beforeMount");
    const ye = Rd(b, K);
    ye && K.beforeEnter(N), n(N, h, g), ((A = q && q.onVnodeMounted) || ye || ee) && it(() => {
      try {
        A && Ot(A, y, f), ye && K.enter(N), ee && vs(f, null, y, "mounted");
      } finally {
      }
    }, b);
  }, ne = (f, h, g, y, b) => {
    if (g && p(f, g), y)
      for (let k = 0; k < y.length; k++)
        p(f, y[k]);
    if (b) {
      let k = b.subTree;
      if (h === k || Wl(k.type) && (k.ssContent === h || k.ssFallback === h)) {
        const E = b.vnode;
        ne(
          f,
          E,
          E.scopeId,
          E.slotScopeIds,
          b.parent
        );
      }
    }
  }, v = (f, h, g, y, b, k, E, P, N = 0) => {
    for (let A = N; A < f.length; A++) {
      const q = f[A] = P ? qt(f[A]) : Pt(f[A]);
      x(
        null,
        q,
        h,
        g,
        y,
        b,
        k,
        E,
        P
      );
    }
  }, V = (f, h, g, y, b, k, E) => {
    const P = h.el = f.el;
    let { patchFlag: N, dynamicChildren: A, dirs: q } = h;
    N |= f.patchFlag & 16;
    const j = f.props || Oe, K = h.props || Oe;
    let ee;
    if (g && bs(g, !1), (ee = K.onVnodeBeforeUpdate) && Ot(ee, g, h, f), q && vs(h, f, g, "beforeUpdate"), g && bs(g, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    A && (!f.dynamicChildren || f.dynamicChildren.length !== A.length) && (N = 0, E = !1, A = null), (j.innerHTML && K.innerHTML == null || j.textContent && K.textContent == null) && u(P, ""), A ? ce(
      f.dynamicChildren,
      A,
      P,
      g,
      y,
      $r(h, b),
      k
    ) : E || he(
      f,
      h,
      P,
      null,
      g,
      y,
      $r(h, b),
      k,
      !1
    ), N > 0) {
      if (N & 16)
        ke(P, j, K, g, b);
      else if (N & 2 && j.class !== K.class && o(P, "class", null, K.class, b), N & 4 && o(P, "style", j.style, K.style, b), N & 8) {
        const ye = h.dynamicProps;
        for (let Re = 0; Re < ye.length; Re++) {
          const Ee = ye[Re], $e = j[Ee], Ze = K[Ee];
          (Ze !== $e || Ee === "value") && o(P, Ee, $e, Ze, b, g);
        }
      }
      N & 1 && f.children !== h.children && u(P, h.children);
    } else !E && A == null && ke(P, j, K, g, b);
    ((ee = K.onVnodeUpdated) || q) && it(() => {
      ee && Ot(ee, g, h, f), q && vs(h, f, g, "updated");
    }, y);
  }, ce = (f, h, g, y, b, k, E) => {
    for (let P = 0; P < h.length; P++) {
      const N = f[P], A = h[P], q = N.el || po(N), j = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        q && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (N.type === We || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !Xs(N, A) || // - In the case of a component, it could contain anything.
        N.shapeFlag & 198) ? d(q) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          g
        )
      );
      x(
        N,
        A,
        j,
        null,
        y,
        b,
        k,
        E,
        !0
      );
    }
  }, ke = (f, h, g, y, b) => {
    if (h !== g) {
      if (h !== Oe)
        for (const k in h)
          !an(k) && !(k in g) && o(
            f,
            k,
            h[k],
            null,
            b,
            y
          );
      for (const k in g) {
        if (an(k)) continue;
        const E = g[k], P = h[k];
        E !== P && k !== "value" && o(f, k, P, E, b, y);
      }
      "value" in g && o(f, "value", h.value, g.value, b);
    }
  }, Z = (f, h, g, y, b, k, E, P, N) => {
    const A = h.el = f ? f.el : a(""), q = h.anchor = f ? f.anchor : a("");
    let { patchFlag: j, dynamicChildren: K, slotScopeIds: ee } = h;
    ee && (P = P ? P.concat(ee) : ee), f == null ? (n(A, g, y), n(q, g, y), v(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      h.children || [],
      g,
      q,
      b,
      k,
      E,
      P,
      N
    )) : j > 0 && j & 64 && K && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    f.dynamicChildren && f.dynamicChildren.length === K.length ? (ce(
      f.dynamicChildren,
      K,
      g,
      b,
      k,
      E,
      P
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (h.key != null || b && h === b.subTree) && Ul(
      f,
      h,
      !0
      /* shallow */
    )) : he(
      f,
      h,
      g,
      q,
      b,
      k,
      E,
      P,
      N
    );
  }, ge = (f, h, g, y, b, k, E, P, N) => {
    h.slotScopeIds = P, f == null ? h.shapeFlag & 512 ? b.ctx.activate(
      h,
      g,
      y,
      E,
      N
    ) : Pe(
      h,
      g,
      y,
      b,
      k,
      E,
      N
    ) : ve(f, h, N);
  }, Pe = (f, h, g, y, b, k, E) => {
    const P = f.component = Dd(
      f,
      y,
      b
    );
    if (Go(f) && (P.ctx.renderer = R), Ld(P, !1, E), P.asyncDep) {
      if (b && b.registerDep(
        P,
        fe,
        E,
        k
      ), !f.el) {
        const N = P.subTree = J(bt);
        $(null, N, h, g), f.placeholder = N.el;
      }
    } else
      fe(
        P,
        f,
        h,
        g,
        b,
        k,
        E
      );
  }, ve = (f, h, g) => {
    const y = h.component = f.component;
    if (vd(f, h, g))
      if (y.asyncDep && !y.asyncResolved) {
        h.el = f.el, h.placeholder = f.placeholder, X(y, h, g);
        return;
      } else
        y.next = h, y.update();
    else
      h.el = f.el, h.placeholder = f.placeholder, y.vnode = h;
  }, fe = (f, h, g, y, b, k, E) => {
    const P = () => {
      if (f.isMounted) {
        let { next: j, bu: K, u: ee, parent: ye, vnode: Re } = f;
        {
          const Et = Bl(f);
          if (Et) {
            j && (j.el = Re.el, X(f, j, E)), Et.asyncDep.then(() => {
              it(() => {
                f.isUnmounted || A();
              }, b);
            });
            return;
          }
        }
        let Ee = j, $e;
        bs(f, !1), j ? (j.el = Re.el, X(f, j, E)) : j = Re, K && Wn(K), ($e = j.props && j.props.onVnodeBeforeUpdate) && Ot($e, ye, j, Re), bs(f, !0);
        const Ze = Ai(f), At = f.subTree;
        f.subTree = Ze, x(
          At,
          Ze,
          // parent may have changed if it's in a teleport
          d(At.el),
          // anchor may have changed if it's in a fragment
          _(At),
          f,
          b,
          k
        ), j.el = Ze.el, Ee === null && bd(f, Ze.el), ee && it(ee, b), ($e = j.props && j.props.onVnodeUpdated) && it(
          () => Ot($e, ye, j, Re),
          b
        );
      } else {
        let j;
        const { el: K, props: ee } = h, { bm: ye, m: Re, parent: Ee, root: $e, type: Ze } = f, At = Vs(h);
        bs(f, !1), ye && Wn(ye), !At && (j = ee && ee.onVnodeBeforeMount) && Ot(j, Ee, h), bs(f, !0);
        {
          $e.ce && $e.ce._hasShadowRoot() && $e.ce._injectChildStyle(
            Ze,
            f.parent ? f.parent.type : void 0
          );
          const Et = f.subTree = Ai(f);
          x(
            null,
            Et,
            g,
            y,
            f,
            b,
            k
          ), h.el = Et.el;
        }
        if (Re && it(Re, b), !At && (j = ee && ee.onVnodeMounted)) {
          const Et = h;
          it(
            () => Ot(j, Ee, Et),
            b
          );
        }
        (h.shapeFlag & 256 || Ee && Vs(Ee.vnode) && Ee.vnode.shapeFlag & 256) && f.a && it(f.a, b), f.isMounted = !0, h = g = y = null;
      }
    };
    f.scope.on();
    const N = f.effect = new Ja(P);
    f.scope.off();
    const A = f.update = N.run.bind(N), q = f.job = N.runIfDirty.bind(N);
    q.i = f, q.id = f.uid, N.scheduler = () => Wo(q), bs(f, !0), A();
  }, X = (f, h, g) => {
    h.component = f;
    const y = f.vnode.props;
    f.vnode = h, f.next = null, xd(f, h.props, y, g), Cd(f, h.children, g), Vt(), gl(f), zt();
  }, he = (f, h, g, y, b, k, E, P, N = !1) => {
    const A = f && f.children, q = f ? f.shapeFlag : 0, j = h.children, { patchFlag: K, shapeFlag: ee } = h;
    if (K > 0) {
      if (K & 128) {
        W(
          A,
          j,
          g,
          y,
          b,
          k,
          E,
          P,
          N
        );
        return;
      } else if (K & 256) {
        ct(
          A,
          j,
          g,
          y,
          b,
          k,
          E,
          P,
          N
        );
        return;
      }
    }
    ee & 8 ? (q & 16 && Ae(A, b, k), j !== A && u(g, j)) : q & 16 ? ee & 16 ? W(
      A,
      j,
      g,
      y,
      b,
      k,
      E,
      P,
      N
    ) : Ae(A, b, k, !0) : (q & 8 && u(g, ""), ee & 16 && v(
      j,
      g,
      y,
      b,
      k,
      E,
      P,
      N
    ));
  }, ct = (f, h, g, y, b, k, E, P, N) => {
    f = f || ks, h = h || ks;
    const A = f.length, q = h.length, j = Math.min(A, q);
    let K;
    for (K = 0; K < j; K++) {
      const ee = h[K] = N ? qt(h[K]) : Pt(h[K]);
      x(
        f[K],
        ee,
        g,
        null,
        b,
        k,
        E,
        P,
        N
      );
    }
    A > q ? Ae(
      f,
      b,
      k,
      !0,
      !1,
      j
    ) : v(
      h,
      g,
      y,
      b,
      k,
      E,
      P,
      N,
      j
    );
  }, W = (f, h, g, y, b, k, E, P, N) => {
    let A = 0;
    const q = h.length;
    let j = f.length - 1, K = q - 1;
    for (; A <= j && A <= K; ) {
      const ee = f[A], ye = h[A] = N ? qt(h[A]) : Pt(h[A]);
      if (Xs(ee, ye))
        x(
          ee,
          ye,
          g,
          null,
          b,
          k,
          E,
          P,
          N
        );
      else
        break;
      A++;
    }
    for (; A <= j && A <= K; ) {
      const ee = f[j], ye = h[K] = N ? qt(h[K]) : Pt(h[K]);
      if (Xs(ee, ye))
        x(
          ee,
          ye,
          g,
          null,
          b,
          k,
          E,
          P,
          N
        );
      else
        break;
      j--, K--;
    }
    if (A > j) {
      if (A <= K) {
        const ee = K + 1, ye = ee < q ? h[ee].el : y;
        for (; A <= K; )
          x(
            null,
            h[A] = N ? qt(h[A]) : Pt(h[A]),
            g,
            ye,
            b,
            k,
            E,
            P,
            N
          ), A++;
      }
    } else if (A > K)
      for (; A <= j; )
        He(f[A], b, k, !0), A++;
    else {
      const ee = A, ye = A, Re = /* @__PURE__ */ new Map();
      for (A = ye; A <= K; A++) {
        const dt = h[A] = N ? qt(h[A]) : Pt(h[A]);
        dt.key != null && Re.set(dt.key, A);
      }
      let Ee, $e = 0;
      const Ze = K - ye + 1;
      let At = !1, Et = 0;
      const Ys = new Array(Ze);
      for (A = 0; A < Ze; A++) Ys[A] = 0;
      for (A = ee; A <= j; A++) {
        const dt = f[A];
        if ($e >= Ze) {
          He(dt, b, k, !0);
          continue;
        }
        let Rt;
        if (dt.key != null)
          Rt = Re.get(dt.key);
        else
          for (Ee = ye; Ee <= K; Ee++)
            if (Ys[Ee - ye] === 0 && Xs(dt, h[Ee])) {
              Rt = Ee;
              break;
            }
        Rt === void 0 ? He(dt, b, k, !0) : (Ys[Rt - ye] = A + 1, Rt >= Et ? Et = Rt : At = !0, x(
          dt,
          h[Rt],
          g,
          null,
          b,
          k,
          E,
          P,
          N
        ), $e++);
      }
      const ci = At ? Od(Ys) : ks;
      for (Ee = ci.length - 1, A = Ze - 1; A >= 0; A--) {
        const dt = ye + A, Rt = h[dt], ui = h[dt + 1], di = dt + 1 < q ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          ui.el || po(ui)
        ) : y;
        Ys[A] === 0 ? x(
          null,
          Rt,
          g,
          di,
          b,
          k,
          E,
          P,
          N
        ) : At && (Ee < 0 || A !== ci[Ee] ? ut(Rt, g, di, 2) : Ee--);
      }
    }
  }, ut = (f, h, g, y, b = null) => {
    const { el: k, type: E, transition: P, children: N, shapeFlag: A } = f;
    if (A & 6) {
      ut(f.component.subTree, h, g, y);
      return;
    }
    if (A & 128) {
      f.suspense.move(h, g, y);
      return;
    }
    if (A & 64) {
      E.move(f, h, g, R);
      return;
    }
    if (E === We) {
      n(k, h, g);
      for (let j = 0; j < N.length; j++)
        ut(N[j], h, g, y);
      n(f.anchor, h, g);
      return;
    }
    if (E === Vr) {
      I(f, h, g);
      return;
    }
    if (y !== 2 && A & 1 && P)
      if (y === 0)
        P.persisted && !k[Dr] ? n(k, h, g) : (P.beforeEnter(k), n(k, h, g), it(() => P.enter(k), b));
      else {
        const { leave: j, delayLeave: K, afterLeave: ee } = P, ye = () => {
          f.ctx.isUnmounted ? r(k) : n(k, h, g);
        }, Re = () => {
          const Ee = k._isLeaving || !!k[Dr];
          k._isLeaving && k[Dr](
            !0
            /* cancelled */
          ), P.persisted && !Ee ? ye() : j(k, () => {
            ye(), ee && ee();
          });
        };
        K ? K(k, ye, Re) : Re();
      }
    else
      n(k, h, g);
  }, He = (f, h, g, y = !1, b = !1) => {
    const {
      type: k,
      props: E,
      ref: P,
      children: N,
      dynamicChildren: A,
      shapeFlag: q,
      patchFlag: j,
      dirs: K,
      cacheIndex: ee,
      memo: ye
    } = f;
    if ((j === -2 || A && A.hasOnce) && (b = !1), P != null && (Vt(), dn(P, null, g, f, !0), zt()), ee != null && (!f.ctx || f.ctx === h) && (h.renderCache[ee] = void 0), q & 256) {
      h.ctx.deactivate(f);
      return;
    }
    const Re = q & 1 && K, Ee = !Vs(f);
    let $e;
    if (Ee && ($e = E && E.onVnodeBeforeUnmount) && Ot($e, h, f), q & 6)
      Me(f.component, g, y);
    else {
      if (q & 128) {
        f.suspense.unmount(g, y);
        return;
      }
      Re && vs(f, null, h, "beforeUnmount"), q & 64 ? f.type.remove(
        f,
        h,
        g,
        R,
        y
      ) : A && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !A.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (k !== We || j > 0 && j & 64) ? Ae(
        A,
        h,
        g,
        !1,
        !0
      ) : (k === We && j & 384 || !b && q & 16) && Ae(N, h, g), y && Bt(f);
    }
    const Ze = ye != null && ee == null;
    (Ee && ($e = E && E.onVnodeUnmounted) || Re || Ze) && it(() => {
      $e && Ot($e, h, f), Re && vs(f, null, h, "unmounted"), Ze && (f.el = null);
    }, g);
  }, Bt = (f) => {
    const { type: h, el: g, anchor: y, transition: b } = f, k = h === We;
    if (k && !b) {
      xt(g, y);
      return;
    }
    if (h === Vr) {
      M(f), b && !b.persisted && b.afterLeave && b.afterLeave();
      return;
    }
    const E = k ? co(f) : f, P = () => {
      k ? d(g) && xt(g, y) : r(g), b && !b.persisted && b.afterLeave && b.afterLeave();
    };
    if (E && E.shapeFlag & 1 && b && !b.persisted) {
      const { leave: N, delayLeave: A } = b, q = E.el, j = () => N(q, P);
      A ? A(q, P, j) : j();
    } else
      P();
  }, xt = (f, h) => {
    let g;
    for (; f !== h; )
      g = m(f), r(f), f = g;
    r(h);
  }, Me = (f, h, g) => {
    const { bum: y, scope: b, job: k, subTree: E, um: P, m: N, a: A } = f;
    Oi(N), Oi(A), y && Wn(y), b.stop(), k ? (k.flags |= 8, He(E, f, h, g)) : f.vnode.el && E && (E.transition = f.vnode.transition, He(E, f, h, g)), P && it(P, h), it(() => {
      f.isUnmounted = !0;
    }, h);
  }, Ae = (f, h, g, y = !1, b = !1, k = 0) => {
    for (let E = k; E < f.length; E++)
      He(f[E], h, g, y, b);
  }, _ = (f) => {
    if (f.shapeFlag & 6)
      return _(f.component.subTree);
    if (f.shapeFlag & 128)
      return f.suspense.next();
    const h = m(f.anchor || f.el), g = h && h[Bu];
    return g ? m(g) : h;
  }, F = (f, h, g) => {
    const y = f && h._vnode ? void 0 : f && f.component ? f.component.uid : jd();
    $u(() => {
      f == null ? h._vnode && He(h._vnode, null, null, !0) : x(
        h._vnode || null,
        f,
        h,
        null,
        null,
        null,
        g
      ), h._vnode = f;
    }, y);
  }, R = {
    p: x,
    um: He,
    m: ut,
    r: Bt,
    mt: Pe,
    mc: v,
    pc: he,
    pbc: ce,
    n: _,
    o: e
  };
  return {
    render: F,
    hydrate: void 0,
    createApp: fd(F)
  };
}
function $r({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function bs({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function Rd(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function Ul(e, t, s = !1) {
  const n = e.children, r = t.children;
  if (G(n) && G(r))
    for (let o = 0; o < n.length; o++) {
      const i = n[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = qt(r[o]), a.el = i.el), !s && a.patchFlag !== -2 && Ul(i, a)), a.type === Cr && (a.patchFlag === -1 && (a = r[o] = qt(a)), a.el = i.el), a.type === bt && !a.el && (a.el = i.el);
    }
}
function Od(e) {
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
function Bl(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : Bl(t);
}
function Oi(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function po(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? po(t.subTree) : null;
}
const Wl = (e) => e.__isSuspense;
function Td(e, t) {
  t && t.pendingBranch ? G(e) ? t.effects.push(...e) : t.effects.push(e) : Lu(e);
}
const We = /* @__PURE__ */ Symbol.for("v-fgt"), Cr = /* @__PURE__ */ Symbol.for("v-txt"), bt = /* @__PURE__ */ Symbol.for("v-cmt"), Vr = /* @__PURE__ */ Symbol.for("v-stc"), Qt = [];
let mt = null;
function ae(e = !1) {
  Qt.push(mt = e ? null : []);
}
function Jo() {
  Qt.pop(), mt = Qt[Qt.length - 1] || null;
}
let vn = 1;
function er(e, t = !1) {
  vn += e, e < 0 && mt && t && (mt.hasOnce = !0);
}
function Hl(e) {
  return e.dynamicChildren = vn > 0 ? mt || ks : null, Jo(), vn > 0 && mt && mt.push(e), e;
}
function Se(e, t, s, n, r, o) {
  return Hl(
    S(
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
function ft(e, t, s, n, r) {
  return Hl(
    J(
      e,
      t,
      s,
      n,
      r,
      !0
    )
  );
}
function zs(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function Xs(e, t) {
  return e.type === t.type && e.key === t.key;
}
const Zl = ({ key: e }) => e ?? null, Zn = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? je(e) || /* @__PURE__ */ Le(e) || oe(e) ? { i: qe, r: e, k: t, f: !!s } : e : null);
function S(e, t = null, s = null, n = 0, r = null, o = e === We ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Zl(t),
    ref: t && Zn(t),
    scopeId: bl,
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
    ctx: qe
  };
  return a ? (tr(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= je(s) ? 8 : 16), vn > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  mt && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && mt.push(l), l;
}
const J = Id;
function Id(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === Cl) && (e = bt), zs(e)) {
    const a = Fs(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && tr(a, s), vn > 0 && !o && mt && (a.shapeFlag & 6 ? mt[mt.indexOf(e)] = a : mt.push(a)), a.patchFlag = -2, a;
  }
  if (Ud(e) && (e = e.__vccOpts), t) {
    t = Nd(t);
    let { class: a, style: l } = t;
    a && !je(a) && (t.class = lt(a)), Ce(l) && (/* @__PURE__ */ br(l) && !G(l) && (l = Ke({}, l)), t.style = Mo(l));
  }
  const i = je(e) ? 1 : Wl(e) ? 128 : wr(e) ? 64 : Ce(e) ? 4 : oe(e) ? 2 : 0;
  return S(
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
function Nd(e) {
  return e ? /* @__PURE__ */ br(e) || Dl(e) ? Ke({}, e) : e : null;
}
function Fs(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? Pd(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Zl(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? G(o) ? o.concat(Zn(t)) : [o, Zn(t)] : Zn(t)
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
    patchFlag: t && e.type !== We ? i === -1 ? 16 : i | 16 : i,
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
    ssContent: e.ssContent && Fs(e.ssContent),
    ssFallback: e.ssFallback && Fs(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && Yn(
    u,
    l.clone(u)
  ), u;
}
function ie(e = " ", t = 0) {
  return J(Cr, null, e, t);
}
function ht(e = "", t = !1) {
  return t ? (ae(), ft(bt, null, e)) : J(bt, null, e);
}
function Pt(e) {
  return e == null || typeof e == "boolean" ? J(bt) : G(e) ? J(
    We,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : zs(e) ? qt(e) : J(Cr, null, String(e));
}
function qt(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : Fs(e);
}
function tr(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (G(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), tr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !Dl(t) ? t._ctx = qe : r === 3 && qe && (qe.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (oe(t)) {
    if (n & 65) {
      tr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: qe }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [ie(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function Pd(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = lt([t.class, n.class]));
      else if (r === "style")
        t.style = Mo([t.style, n.style]);
      else if (dr(r)) {
        const o = t[r], i = n[r];
        i && o !== i && !(G(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !fr(r) && (t[r] = i);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function Ot(e, t, s, n = null) {
  St(e, t, 7, [
    s,
    n
  ]);
}
const Md = Tl();
let Gl = 0;
function jd() {
  return Gl;
}
function Dd(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || Md, o = {
    uid: Gl++,
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
    scope: new Ga(
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
    propsOptions: $l(n, r),
    emitsOptions: Il(n, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: Oe,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: Oe,
    data: Oe,
    props: Oe,
    attrs: Oe,
    slots: Oe,
    refs: Oe,
    setupState: Oe,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = hd.bind(null, o), e.ce && e.ce(o), o;
}
let Xe = null;
const Ar = () => Xe || qe;
let sr, bn;
{
  const e = yr(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  sr = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => Xe = s
  ), bn = t(
    "__VUE_SSR_SETTERS__",
    (s) => _n = s
  );
}
const In = (e) => {
  const t = Xe;
  return sr(e), e.scope.on(), () => {
    e.scope.off(), sr(t);
  };
}, Ti = () => {
  Xe && Xe.scope.off(), sr(null);
};
function ql(e) {
  return e.vnode.shapeFlag & 4;
}
let _n = !1;
function Ld(e, t = !1, s = !1) {
  t && bn(t);
  const { props: n, children: r } = e.vnode, o = ql(e);
  _d(e, n, o, t), Sd(e, r, s || t);
  const i = o ? $d(e, t) : void 0;
  return t && bn(!1), i;
}
function $d(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, od);
  const { setup: n } = s;
  if (n) {
    Vt();
    const r = e.setupContext = n.length > 1 ? zd(e) : null, o = In(e), i = Rn(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = za(i);
    if (zt(), o(), (a || e.sp) && !Vs(e) && wl(e), a) {
      if (i.then(Ti, Ti), t)
        return i.then((l) => {
          bn(!0);
          try {
            Ii(e, l, t);
          } finally {
            bn(!1);
          }
        }).catch((l) => {
          _r(l, e, 0);
        });
      e.asyncDep = i;
    } else
      Ii(e, i);
  } else
    Kl(e);
}
function Ii(e, t, s) {
  oe(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : Ce(t) && (e.setupState = ml(t)), Kl(e);
}
function Kl(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || Dt);
  {
    const r = In(e);
    Vt();
    try {
      id(e);
    } finally {
      zt(), r();
    }
  }
}
const Vd = {
  get(e, t) {
    return Qe(e, "get", ""), e[t];
  }
};
function zd(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Vd),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Er(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(ml(Bo(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in fn)
        return fn[s](e);
    },
    has(t, s) {
      return s in t || s in fn;
    }
  })) : e.proxy;
}
function Fd(e, t = !0) {
  return oe(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function Ud(e) {
  return oe(e) && "__vccOpts" in e;
}
const Ie = (e, t) => /* @__PURE__ */ Nu(e, t, _n);
function xn(e, t, s) {
  try {
    er(-1);
    const n = arguments.length;
    return n === 2 ? Ce(t) && !G(t) ? zs(t) ? J(e, null, [t]) : J(e, t) : J(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && zs(s) && (s = [s]), J(e, t, s));
  } finally {
    er(1);
  }
}
const Bd = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let go;
const Ni = typeof window < "u" && window.trustedTypes;
if (Ni)
  try {
    go = /* @__PURE__ */ Ni.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const Jl = go ? (e) => go.createHTML(e) : (e) => e, Wd = "http://www.w3.org/2000/svg", Hd = "http://www.w3.org/1998/Math/MathML", Gt = typeof document < "u" ? document : null, Pi = Gt && /* @__PURE__ */ Gt.createElement("template"), Zd = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? Gt.createElementNS(Wd, e) : t === "mathml" ? Gt.createElementNS(Hd, e) : s ? Gt.createElement(e, { is: s }) : Gt.createElement(e);
    return e === "select" && n && n.multiple != null && r.setAttribute("multiple", n.multiple), r;
  },
  createText: (e) => Gt.createTextNode(e),
  createComment: (e) => Gt.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => Gt.querySelector(e),
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
      Pi.innerHTML = Jl(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const a = Pi.content;
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
}, Gd = /* @__PURE__ */ Symbol("_vtc");
function qd(e, t, s) {
  const n = e[Gd];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const Mi = /* @__PURE__ */ Symbol("_vod"), Kd = /* @__PURE__ */ Symbol("_vsh"), Jd = /* @__PURE__ */ Symbol(""), Yd = /(?:^|;)\s*display\s*:/;
function Qd(e, t, s) {
  const n = e.style, r = je(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (je(t))
        for (const i of t.split(";")) {
          const a = i.slice(0, i.indexOf(":")).trim();
          s[a] == null && rn(n, a, "");
        }
      else
        for (const i in t)
          s[i] == null && rn(n, i, "");
    for (const i in s) {
      i === "display" && (o = !0);
      const a = s[i];
      a != null ? ef(
        e,
        i,
        !je(t) && t ? t[i] : void 0,
        a
      ) || rn(n, i, a) : rn(n, i, "");
    }
  } else if (r) {
    if (t !== s) {
      const i = n[Jd];
      i && (s += ";" + i), n.cssText = s, o = Yd.test(s);
    }
  } else t && e.removeAttribute("style");
  Mi in e && ((!r || t !== s) && (e[Mi] = o ? n.display : ""), e[Kd] && (n.display = "none"));
}
const Dn = /\s*!important$/;
function rn(e, t, s) {
  if (G(s))
    s.forEach((n) => rn(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    Dn.test(s) ? e.setProperty(t, s.replace(Dn, ""), "important") : e.setProperty(t, s);
  else {
    const n = Xd(e, t);
    Dn.test(s) ? e.setProperty(
      Ts(n),
      s.replace(Dn, ""),
      "important"
    ) : e[n] = s;
  }
}
const ji = ["Webkit", "Moz", "ms"], zr = {};
function Xd(e, t) {
  const s = zr[t];
  if (s)
    return s;
  let n = rt(t);
  if (n !== "filter" && n in e)
    return zr[t] = n;
  n = pr(n);
  for (let r = 0; r < ji.length; r++) {
    const o = ji[r] + n;
    if (o in e)
      return zr[t] = o;
  }
  return t;
}
function ef(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && je(n) && s === n;
}
const Di = "http://www.w3.org/1999/xlink";
function Li(e, t, s, n, r, o = iu(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(Di, t.slice(6, t.length)) : e.setAttributeNS(Di, t, s) : s == null || o && !Wa(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : gt(s) ? String(s) : s
  );
}
function $i(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? Jl(s) : s);
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
    a === "boolean" ? s = Wa(s) : s == null && a === "string" ? (s = "", i = !0) : a === "number" && (s = 0, i = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function us(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function tf(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const Vi = /* @__PURE__ */ Symbol("_vei");
function sf(e, t, s, n, r = null) {
  const o = e[Vi] || (e[Vi] = {}), i = o[t];
  if (n && i)
    i.value = n;
  else {
    const [a, l] = of(t);
    if (n) {
      const c = o[t] = cf(
        n,
        r
      );
      us(e, a, c, l);
    } else i && (tf(e, a, i, l), o[t] = void 0);
  }
}
const nf = /(Once|Passive|Capture)$/, rf = /^on:?(?:Once|Passive|Capture)$/;
function of(e) {
  let t, s;
  for (; (s = e.match(nf)) && !rf.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Ts(e.slice(2)), t];
}
let Fr = 0;
const af = /* @__PURE__ */ Promise.resolve(), lf = () => Fr || (af.then(() => Fr = 0), Fr = Date.now());
function cf(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if (G(r)) {
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
  return s.value = e, s.attached = lf(), s;
}
const zi = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, uf = (e, t, s, n, r, o) => {
  const i = r === "svg";
  t === "class" ? qd(e, n, i) : t === "style" ? Qd(e, s, n) : dr(t) ? fr(t) || sf(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : df(e, t, n, i)) ? ($i(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && Li(e, t, n, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (ff(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !je(n))) ? $i(e, rt(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), Li(e, t, n, i));
};
function df(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && zi(t) && oe(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return zi(t) && je(s) ? !1 : t in e;
}
function ff(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = rt(t);
  return Array.isArray(s) ? s.some((r) => rt(r) === n) : Object.keys(s).some((r) => rt(r) === n);
}
const Us = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return G(t) ? (s) => Wn(t, s) : t;
};
function mf(e) {
  e.target.composing = !0;
}
function Fi(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const jt = /* @__PURE__ */ Symbol("_assign"), Ln = /* @__PURE__ */ Symbol("_initialValue");
function Ur(e, t, s) {
  return t && (e = e.trim()), s && (e = gr(e)), e;
}
const nr = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[Ln] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[Ln] = e.defaultValue.replace(/\r\n?/g, `
`))), e[jt] = Us(r);
    const o = n || r.props && r.props.type === "number";
    us(e, t ? "change" : "input", (i) => {
      i.target.composing || e[jt](Ur(e.value, s, o));
    }), (s || o) && us(e, "change", () => {
      e.value = Ur(e.value, s, o);
    }), t || (us(e, "compositionstart", mf), us(e, "compositionend", Fi), us(e, "change", Fi));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[Ln];
    delete e[Ln], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[jt](Ur(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, i) {
    if (e[jt] = Us(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? gr(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, hf = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[jt] = Us(s), us(e, "change", () => {
      const n = e._modelValue, r = wn(e), o = e.checked, i = e[jt];
      if (G(n)) {
        const a = jo(n, r), l = a !== -1;
        if (o && !l)
          i(n.concat(r));
        else if (!o && l) {
          const c = [...n];
          c.splice(a, 1), i(c);
        }
      } else if (Xt(n)) {
        const a = new Set(n);
        o ? a.add(r) : a.delete(r), i(a);
      } else
        i(Yl(e, o));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: Ui,
  beforeUpdate(e, t, s) {
    e[jt] = Us(s), Ui(e, t, s);
  }
};
function Ui(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let r;
  if (G(t))
    r = jo(t, n.props.value) > -1;
  else if (Xt(t))
    r = t.has(n.props.value);
  else {
    if (t === s) return;
    r = es(t, Yl(e, !0));
  }
  e.checked !== r && (e.checked = r);
}
const Yo = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, us(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? gr(wn(l)) : wn(l)
      ), o = e.multiple, i = o ? Xt(e._modelValue) ? new Set(r) : r : r[0], a = e._pendingValue = [
        o,
        o ? G(i) ? r.slice() : r : i
      ];
      try {
        e[jt](i);
      } finally {
        xr(() => {
          e._pendingValue === a && (e._pendingValue = void 0);
        });
      }
    }), e[jt] = Us(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    Bi(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[jt] = Us(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !pf(t, s[1], s[0])) && Bi(e, t);
  }
};
function pf(e, t, s) {
  if (!s || G(e)) return es(e, t);
  if (Xt(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function Bi(e, t) {
  const s = e.multiple, n = G(t);
  if (!(s && !n && !Xt(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const i = e.options[r], a = wn(i);
      if (s)
        if (n) {
          const l = typeof a;
          l === "string" || l === "number" ? i.selected = t.some((c) => String(c) === String(a)) : i.selected = jo(t, a) > -1;
        } else
          i.selected = t.has(a);
      else if (es(wn(i), t)) {
        e.selectedIndex !== r && (e.selectedIndex = r);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function wn(e) {
  return "_value" in e ? e._value : e.value;
}
function Yl(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const gf = ["ctrl", "shift", "alt", "meta"], yf = {
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
  exact: (e, t) => gf.some((s) => e[`${s}Key`] && !t.includes(s))
}, vf = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = yf[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, bf = /* @__PURE__ */ Ke({ patchProp: uf }, Zd);
let Wi;
function _f() {
  return Wi || (Wi = Ad(bf));
}
const xf = ((...e) => {
  const t = _f().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = kf(n);
    if (!r) return;
    const o = t._component;
    !oe(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = s(r, !1, wf(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function wf(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function kf(e) {
  return je(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let Ql;
const Rr = (e) => Ql = e, Xl = (
  /* istanbul ignore next */
  Symbol()
);
function yo(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var mn;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(mn || (mn = {}));
function Sf() {
  const e = qa(!0), t = e.run(() => /* @__PURE__ */ te({}));
  let s = [], n = [];
  const r = Bo({
    install(o) {
      Rr(r), r._a = o, o.provide(Xl, r), o.config.globalProperties.$pinia = r, n.forEach((i) => s.push(i)), n = [];
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
const ec = () => {
};
function Hi(e, t, s, n = ec) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && Do() && Ka(r), r;
}
function Ps(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const Cf = (e) => e(), Zi = Symbol(), Br = Symbol();
function vo(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    yo(r) && yo(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ Le(n) && !/* @__PURE__ */ Lt(n) ? e[s] = vo(r, n) : e[s] = n;
  }
  return e;
}
const Af = (
  /* istanbul ignore next */
  Symbol()
);
function Ef(e) {
  return !yo(e) || !Object.prototype.hasOwnProperty.call(e, Af);
}
const { assign: is } = Object;
function Rf(e) {
  return !!(/* @__PURE__ */ Le(e) && e.effect);
}
function Of(e, t, s, n) {
  const { state: r, actions: o, getters: i } = t, a = s.state.value[e];
  let l;
  function c() {
    a || (s.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ Ru(s.state.value[e]);
    return is(u, o, Object.keys(i || {}).reduce((d, m) => (d[m] = Bo(Ie(() => {
      Rr(s);
      const p = s._s.get(e);
      return i[m].call(p, p);
    })), d), {}));
  }
  return l = tc(e, c, t, s, n, !0), l;
}
function tc(e, t, s = {}, n, r, o) {
  let i;
  const a = is({ actions: {} }, s), l = { deep: !0 };
  let c, u, d = /* @__PURE__ */ new Set(), m = /* @__PURE__ */ new Set(), p;
  const w = n.state.value[e];
  !o && !w && (n.state.value[e] = {});
  let x;
  function D(v) {
    let V;
    c = u = !1, typeof v == "function" ? (v(n.state.value[e]), V = {
      type: mn.patchFunction,
      storeId: e,
      events: p
    }) : (vo(n.state.value[e], v), V = {
      type: mn.patchObject,
      payload: v,
      storeId: e,
      events: p
    });
    const ce = x = Symbol();
    xr().then(() => {
      x === ce && (c = !0);
    }), u = !0, Ps(d, V, n.state.value[e]);
  }
  const $ = o ? function() {
    const { state: V } = s, ce = V ? V() : {};
    this.$patch((ke) => {
      is(ke, ce);
    });
  } : (
    /* istanbul ignore next */
    ec
  );
  function C() {
    i.stop(), d.clear(), m.clear(), n._s.delete(e);
  }
  const I = (v, V = "") => {
    if (Zi in v)
      return v[Br] = V, v;
    const ce = function() {
      Rr(n);
      const ke = Array.from(arguments), Z = /* @__PURE__ */ new Set(), ge = /* @__PURE__ */ new Set();
      function Pe(X) {
        Z.add(X);
      }
      function ve(X) {
        ge.add(X);
      }
      Ps(m, {
        args: ke,
        name: ce[Br],
        store: Y,
        after: Pe,
        onError: ve
      });
      let fe;
      try {
        fe = v.apply(this && this.$id === e ? this : Y, ke);
      } catch (X) {
        throw Ps(ge, X), X;
      }
      return fe instanceof Promise ? fe.then((X) => (Ps(Z, X), X)).catch((X) => (Ps(ge, X), Promise.reject(X))) : (Ps(Z, fe), fe);
    };
    return ce[Zi] = !0, ce[Br] = V, ce;
  }, M = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: Hi.bind(null, m),
    $patch: D,
    $reset: $,
    $subscribe(v, V = {}) {
      const ce = Hi(d, v, V.detached, () => ke()), ke = i.run(() => As(() => n.state.value[e], (Z) => {
        (V.flush === "sync" ? u : c) && v({
          storeId: e,
          type: mn.direct,
          events: p
        }, Z);
      }, is({}, l, V)));
      return ce;
    },
    $dispose: C
  }, Y = /* @__PURE__ */ En(M);
  n._s.set(e, Y);
  const ne = (n._a && n._a.runWithContext || Cf)(() => n._e.run(() => (i = qa()).run(() => t({ action: I }))));
  for (const v in ne) {
    const V = ne[v];
    if (/* @__PURE__ */ Le(V) && !Rf(V) || /* @__PURE__ */ Lt(V))
      o || (w && Ef(V) && (/* @__PURE__ */ Le(V) ? V.value = w[v] : vo(V, w[v])), n.state.value[e][v] = V);
    else if (typeof V == "function") {
      const ce = I(V, v);
      ne[v] = ce, a.actions[v] = V;
    }
  }
  return is(Y, ne), is(/* @__PURE__ */ be(Y), ne), Object.defineProperty(Y, "$state", {
    get: () => n.state.value[e],
    set: (v) => {
      D((V) => {
        is(V, v);
      });
    }
  }), n._p.forEach((v) => {
    is(Y, i.run(() => v({
      store: Y,
      app: n._a,
      pinia: n,
      options: a
    })));
  }), w && o && s.hydrate && s.hydrate(Y.$state, w), c = !0, u = !0, Y;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function Js(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(i, a) {
    const l = Ho();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? at(Xl, null) : null), i && Rr(i), i = Ql, i._s.has(e) || (r ? tc(e, t, n, i) : Of(e, n, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const Ds = typeof document < "u";
function sc(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function Tf(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && sc(e.default);
}
const Ne = Object.assign;
function Wr(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = Ct(r) ? r.map(e) : e(r);
  }
  return s;
}
const hn = () => {
}, Ct = Array.isArray;
function Gi(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const nc = /#/g, If = /&/g, Nf = /\//g, Pf = /=/g, Mf = /\?/g, rc = /\+/g, jf = /%5B/g, Df = /%5D/g, oc = /%5E/g, Lf = /%60/g, ic = /%7B/g, $f = /%7C/g, ac = /%7D/g, Vf = /%20/g;
function Qo(e) {
  return e == null ? "" : encodeURI("" + e).replace($f, "|").replace(jf, "[").replace(Df, "]");
}
function zf(e) {
  return Qo(e).replace(ic, "{").replace(ac, "}").replace(oc, "^");
}
function bo(e) {
  return Qo(e).replace(rc, "%2B").replace(Vf, "+").replace(nc, "%23").replace(If, "%26").replace(Lf, "`").replace(ic, "{").replace(ac, "}").replace(oc, "^");
}
function Ff(e) {
  return bo(e).replace(Pf, "%3D");
}
function Uf(e) {
  return Qo(e).replace(nc, "%23").replace(Mf, "%3F");
}
function Bf(e) {
  return Uf(e).replace(Nf, "%2F");
}
function kn(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const Wf = /\/$/, Hf = (e) => e.replace(Wf, "");
function Hr(e, t, s = "/") {
  let n, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (n = n || t.slice(0, a), i = t.slice(a, t.length)), n = Kf(n ?? t, s), {
    fullPath: n + o + i,
    path: n,
    query: r,
    hash: kn(i)
  };
}
function Zf(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Gf(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && Bs(t.matched[n], s.matched[r]) && lc(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function Bs(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function lc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!qf(e[s], t[s])) return !1;
  return !0;
}
function qf(e, t) {
  return Ct(e) ? qi(e, t) : Ct(t) ? qi(t, e) : e?.valueOf() === t?.valueOf();
}
function qi(e, t) {
  return Ct(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function Kf(e, t) {
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
const rs = {
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
let _o = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), Ki = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const Zr = "";
function Jf(e) {
  if (!e) if (Ds) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), Hf(e);
}
const Yf = /^[^#]+#/;
function Qf(e, t) {
  return e.replace(Yf, "#") + t;
}
function Xf(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const em = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function tm(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = Xf(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function Ji(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const xo = /* @__PURE__ */ new Map();
function sm(e, t) {
  xo.set(e, t);
}
function nm(e) {
  const t = xo.get(e);
  return xo.delete(e), t;
}
function rm(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function cc(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let De = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const uc = Symbol("");
De.MATCHER_NOT_FOUND + "", De.NAVIGATION_GUARD_REDIRECT + "", De.NAVIGATION_ABORTED + "", De.NAVIGATION_CANCELLED + "", De.NAVIGATION_DUPLICATED + "";
function Ws(e, t) {
  return Ne(/* @__PURE__ */ new Error(), {
    type: e,
    [uc]: !0
  }, t);
}
function Ht(e, t) {
  return e instanceof Error && uc in e && (t == null || !!(e.type & t));
}
const om = [
  "params",
  "query",
  "hash"
];
function im(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of om) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function am(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(rc, " "), o = r.indexOf("="), i = kn(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : kn(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      Ct(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function Yi(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Ff(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (Ct(n) ? n.map((r) => r && bo(r)) : [n && bo(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function lm(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = Ct(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const cm = Symbol(""), Qi = Symbol(""), Or = Symbol(""), Xo = Symbol(""), wo = Symbol("");
function en() {
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
function ls(e, t, s, n, r, o = (i) => i()) {
  const i = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (m) => {
      m === !1 ? l(Ws(De.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : m instanceof Error ? l(m) : rm(m) ? l(Ws(De.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: m
      })) : (i && n.enterCallbacks[r] === i && typeof m == "function" && i.push(m), a());
    }, u = o(() => e.call(n && n.instances[r], t, s, c));
    let d = Promise.resolve(u);
    e.length < 3 && (d = d.then(c)), d.catch((m) => l(m));
  });
}
function Gr(e, t, s, n, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (sc(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(ls(c, s, n, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const d = Tf(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = d;
            const m = (d.__vccOpts || d)[t];
            return m && ls(m, s, n, i, a, r)();
          }));
        }
    }
  return o;
}
function um(e, t) {
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
function dm(e = "") {
  let t = [], s = [[Zr, {}]], n = 0;
  e = Jf(e);
  function r(a, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const d = {
      direction: c,
      delta: u,
      type: _o.pop
    };
    for (const m of t) m(a, l, d);
  }
  const i = {
    location: Zr,
    state: {},
    base: e,
    createHref: Qf.bind(null, e),
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
      t = [], s = [[Zr, {}]], n = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? Ki.back : Ki.forward;
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
let Ss = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var Ue = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(Ue || {});
const fm = {
  type: Ss.Static,
  value: ""
}, mm = /[a-zA-Z0-9_]/;
function hm(e) {
  if (!e) return [[]];
  if (e === "/") return [[fm]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(p) {
    throw new Error(`ERR (${s})/"${c}": ${p}`);
  }
  let s = Ue.Static, n = s;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function d() {
    c && (s === Ue.Static ? o.push({
      type: Ss.Static,
      value: c
    }) : s === Ue.Param || s === Ue.ParamRegExp || s === Ue.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: Ss.Param,
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
    if (l = e[a++], l === "\\" && s !== Ue.ParamRegExp) {
      n = s, s = Ue.EscapeNext;
      continue;
    }
    switch (s) {
      case Ue.Static:
        l === "/" ? (c && d(), i()) : l === ":" ? (d(), s = Ue.Param) : m();
        break;
      case Ue.EscapeNext:
        m(), s = n;
        break;
      case Ue.Param:
        l === "(" ? s = Ue.ParamRegExp : mm.test(l) ? m() : (d(), s = Ue.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case Ue.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : s = Ue.ParamRegExpEnd : u += l;
        break;
      case Ue.ParamRegExpEnd:
        d(), s = Ue.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === Ue.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), d(), i(), r;
}
const Xi = "[^/]+?", pm = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var st = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(st || {});
const gm = /[.+*?^${}()[\]/\\]/g;
function ym(e, t) {
  const s = Ne({}, pm, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [st.Root];
    s.strict && !c.length && (r += "/");
    for (let d = 0; d < c.length; d++) {
      const m = c[d];
      let p = st.Segment + (s.sensitive ? st.BonusCaseSensitive : 0);
      if (m.type === Ss.Static)
        d || (r += "/"), r += m.value.replace(gm, "\\$&"), p += st.Static;
      else if (m.type === Ss.Param) {
        const { value: w, repeatable: x, optional: D, regexp: $ } = m;
        o.push({
          name: w,
          repeatable: x,
          optional: D
        });
        const C = $ || Xi;
        if (C !== Xi) {
          p += st.BonusCustomRegExp;
          try {
            `${C}`;
          } catch (M) {
            throw new Error(`Invalid custom RegExp for param "${w}" (${C}): ` + M.message);
          }
        }
        let I = x ? `((?:${C})(?:/(?:${C}))*)` : `(${C})`;
        d || (I = D && c.length < 2 ? `(?:/${I})` : "/" + I), D && (I += "?"), r += I, p += st.Dynamic, D && (p += st.BonusOptional), x && (p += st.BonusRepeatable), C === ".*" && (p += st.BonusWildcard);
      }
      u.push(p);
    }
    n.push(u);
  }
  if (s.strict && s.end) {
    const c = n.length - 1;
    n[c][n[c].length - 1] += st.BonusStrict;
  }
  s.strict || (r += "/?"), s.end ? r += "$" : s.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const i = new RegExp(r, s.sensitive ? "" : "i");
  function a(c) {
    const u = c.match(i), d = {};
    if (!u) return null;
    for (let m = 1; m < u.length; m++) {
      const p = u[m] || "", w = o[m - 1];
      d[w.name] = p && w.repeatable ? p.split("/") : p;
    }
    return d;
  }
  function l(c) {
    let u = "", d = !1;
    for (const m of e) {
      (!d || !u.endsWith("/")) && (u += "/"), d = !1;
      for (const p of m) if (p.type === Ss.Static) u += p.value;
      else if (p.type === Ss.Param) {
        const { value: w, repeatable: x, optional: D } = p, $ = w in c ? c[w] : "";
        if (Ct($) && !x) throw new Error(`Provided param "${w}" is an array but it is not repeatable (* or + modifiers)`);
        const C = Ct($) ? $.join("/") : $;
        if (!C) if (D)
          m.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : d = !0);
        else throw new Error(`Missing required param "${w}"`);
        u += C;
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
function vm(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === st.Static + st.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === st.Static + st.Segment ? 1 : -1 : 0;
}
function dc(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = vm(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (ea(n)) return 1;
    if (ea(r)) return -1;
  }
  return r.length - n.length;
}
function ea(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const bm = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function _m(e, t, s) {
  const n = ym(hm(e.path), s), r = Ne(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function xm(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = Gi(bm, t);
  function r(d) {
    return n.get(d);
  }
  function o(d, m, p) {
    const w = !p, x = sa(d);
    x.aliasOf = p && p.record;
    const D = Gi(t, d), $ = [x];
    if ("alias" in d) {
      const M = typeof d.alias == "string" ? [d.alias] : d.alias;
      for (const Y of M) $.push(sa(Ne({}, x, {
        components: p ? p.record.components : x.components,
        path: Y,
        aliasOf: p ? p.record : x
      })));
    }
    let C, I;
    for (const M of $) {
      const { path: Y } = M;
      if (m && Y[0] !== "/") {
        const xe = m.record.path, ne = xe[xe.length - 1] === "/" ? "" : "/";
        M.path = m.record.path + (Y && ne + Y);
      }
      if (C = _m(M, m, D), p ? p.alias.push(C) : (I = I || C, I !== C && I.alias.push(C), w && d.name && !na(C) && i(d.name)), fc(C) && l(C), x.children) {
        const xe = x.children;
        for (let ne = 0; ne < xe.length; ne++) o(xe[ne], C, p && p.children[ne]);
      }
      p = p || C;
    }
    return I ? () => {
      i(I);
    } : hn;
  }
  function i(d) {
    if (cc(d)) {
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
    const m = Sm(d, s);
    s.splice(m, 0, d), d.record.name && !na(d) && n.set(d.record.name, d);
  }
  function c(d, m) {
    let p, w = {}, x, D;
    if ("name" in d && d.name) {
      if (p = n.get(d.name), !p) throw Ws(De.MATCHER_NOT_FOUND, { location: d });
      D = p.record.name, w = Ne(ta(m.params, p.keys.filter((I) => !I.optional).concat(p.parent ? p.parent.keys.filter((I) => I.optional) : []).map((I) => I.name)), d.params && ta(d.params, p.keys.map((I) => I.name))), x = p.stringify(w);
    } else if (d.path != null)
      x = d.path, p = s.find((I) => I.re.test(x)), p && (w = p.parse(x), D = p.record.name);
    else {
      if (p = m.name ? n.get(m.name) : s.find((I) => I.re.test(m.path)), !p) throw Ws(De.MATCHER_NOT_FOUND, {
        location: d,
        currentLocation: m
      });
      D = p.record.name, w = Ne({}, m.params, d.params), x = p.stringify(w);
    }
    const $ = [];
    let C = p;
    for (; C; )
      $.unshift(C.record), C = C.parent;
    return {
      name: D,
      path: x,
      params: w,
      matched: $,
      meta: km($)
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
function ta(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function sa(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: wm(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function wm(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function na(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function km(e) {
  return e.reduce((t, s) => Ne(t, s.meta), {});
}
function Sm(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    dc(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = Cm(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function Cm(e) {
  let t = e;
  for (; t = t.parent; ) if (fc(t) && dc(e, t) === 0) return t;
}
function fc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function ra(e) {
  const t = at(Or), s = at(Xo), n = Ie(() => {
    const l = O(e.to);
    return t.resolve(l);
  }), r = Ie(() => {
    const { matched: l } = n.value, { length: c } = l, u = l[c - 1], d = s.matched;
    if (!u || !d.length) return -1;
    const m = d.findIndex(Bs.bind(null, u));
    if (m > -1) return m;
    const p = oa(l[c - 2]);
    return c > 1 && oa(u) === p && d[d.length - 1].path !== p ? d.findIndex(Bs.bind(null, l[c - 2])) : m;
  }), o = Ie(() => r.value > -1 && Om(s.params, n.value.params)), i = Ie(() => r.value > -1 && r.value === s.matched.length - 1 && lc(s.params, n.value.params));
  function a(l = {}) {
    if (Rm(l)) {
      const c = t[O(e.replace) ? "replace" : "push"](O(e.to)).catch(hn);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: Ie(() => n.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function Am(e) {
  return e.length === 1 ? e[0] : e;
}
const Em = /* @__PURE__ */ yt({
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
  useLink: ra,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ En(ra(e)), { options: n } = at(Or), r = Ie(() => ({
      [ia(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [ia(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && Am(t.default(s));
      return e.custom ? o : xn("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), mc = Em;
function Rm(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function Om(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!Ct(r) || r.length !== n.length || n.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function oa(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const ia = (e, t, s) => e ?? t ?? s, Tm = /* @__PURE__ */ yt({
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
    const n = at(wo), r = Ie(() => e.route || n.value), o = at(Qi, 0), i = Ie(() => {
      let c = O(o);
      const { matched: u } = r.value;
      let d;
      for (; (d = u[c]) && !d.components; ) c++;
      return c;
    }), a = Ie(() => r.value.matched[i.value]);
    Hn(Qi, Ie(() => i.value + 1)), Hn(cm, a), Hn(wo, r);
    const l = /* @__PURE__ */ te();
    return As(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, d], [m, p, w]) => {
      u && (u.instances[d] = c, p && p !== u && c && c === m && (u.leaveGuards.size || (u.leaveGuards = p.leaveGuards), u.updateGuards.size || (u.updateGuards = p.updateGuards))), c && u && (!p || !Bs(u, p) || !m) && (u.enterCallbacks[d] || []).forEach((x) => x(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, d = a.value, m = d && d.components[u];
      if (!m) return aa(s.default, {
        Component: m,
        route: c
      });
      const p = d.props[u], w = p ? p === !0 ? c.params : typeof p == "function" ? p(c) : p : null, D = xn(m, Ne({}, w, t, {
        onVnodeUnmounted: ($) => {
          $.component.isUnmounted && (d.instances[u] = null);
        },
        ref: l
      }));
      return aa(s.default, {
        Component: D,
        route: c
      }) || D;
    };
  }
});
function aa(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const hc = Tm;
function Im(e) {
  const t = xm(e.routes, e), s = e.parseQuery || am, n = e.stringifyQuery || Yi, r = e.history, o = en(), i = en(), a = en(), l = /* @__PURE__ */ un(rs);
  let c = rs;
  Ds && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = Wr.bind(null, (_) => "" + _), d = Wr.bind(null, Bf), m = Wr.bind(null, kn);
  function p(_, F) {
    let R, Q;
    return cc(_) ? (R = t.getRecordMatcher(_), Q = F) : Q = _, t.addRoute(Q, R);
  }
  function w(_) {
    const F = t.getRecordMatcher(_);
    F && t.removeRoute(F);
  }
  function x() {
    return t.getRoutes().map((_) => _.record);
  }
  function D(_) {
    return !!t.getRecordMatcher(_);
  }
  function $(_, F) {
    if (F = Ne({}, F || l.value), typeof _ == "string") {
      const y = Hr(s, _, F.path), b = t.resolve({ path: y.path }, F), k = r.createHref(y.fullPath);
      return Ne(y, b, {
        params: m(b.params),
        hash: kn(y.hash),
        redirectedFrom: void 0,
        href: k
      });
    }
    let R;
    if (_.path != null)
      R = Ne({}, _, { path: Hr(s, _.path, F.path).path });
    else {
      const y = Ne({}, _.params);
      for (const b in y) y[b] == null && delete y[b];
      R = Ne({}, _, { params: d(y) }), F.params = d(F.params);
    }
    const Q = t.resolve(R, F), f = _.hash || "";
    Q.params = u(m(Q.params));
    const h = Zf(n, Ne({}, _, {
      hash: zf(f),
      path: Q.path
    })), g = r.createHref(h);
    return Ne({
      fullPath: h,
      hash: f,
      query: n === Yi ? lm(_.query) : _.query || {}
    }, Q, {
      redirectedFrom: void 0,
      href: g
    });
  }
  function C(_) {
    return typeof _ == "string" ? Hr(s, _, l.value.path) : Ne({}, _);
  }
  function I(_, F) {
    if (c !== _) return Ws(De.NAVIGATION_CANCELLED, {
      from: F,
      to: _
    });
  }
  function M(_) {
    return ne(_);
  }
  function Y(_) {
    return M(Ne(C(_), { replace: !0 }));
  }
  function xe(_, F) {
    const R = _.matched[_.matched.length - 1];
    if (R && R.redirect) {
      const { redirect: Q } = R;
      let f = typeof Q == "function" ? Q(_, F) : Q;
      return typeof f == "string" && (f = f.includes("?") || f.includes("#") ? f = C(f) : { path: f }, f.params = {}), Ne({
        query: _.query,
        hash: _.hash,
        params: f.path != null ? {} : _.params
      }, f);
    }
  }
  function ne(_, F) {
    const R = c = $(_), Q = l.value, f = _.state, h = _.force, g = _.replace === !0, y = xe(R, Q);
    if (y) return ne(Ne(C(y), {
      state: typeof y == "object" ? Ne({}, f, y.state) : f,
      force: h,
      replace: g
    }), F || R);
    const b = R;
    b.redirectedFrom = F;
    let k;
    return !h && Gf(n, Q, R) && (k = Ws(De.NAVIGATION_DUPLICATED, {
      to: b,
      from: Q
    }), ut(Q, Q, !0, !1)), (k ? Promise.resolve(k) : ce(b, Q)).catch((E) => Ht(E) ? Ht(E, De.NAVIGATION_GUARD_REDIRECT) ? E : W(E) : he(E, b, Q)).then((E) => {
      if (E) {
        if (Ht(E, De.NAVIGATION_GUARD_REDIRECT))
          return ne(Ne({ replace: g }, C(E.to), {
            state: typeof E.to == "object" ? Ne({}, f, E.to.state) : f,
            force: h
          }), F || b);
      } else E = Z(b, Q, !0, g, f);
      return ke(b, Q, E), E;
    });
  }
  function v(_, F) {
    const R = I(_, F);
    return R ? Promise.reject(R) : Promise.resolve();
  }
  function V(_) {
    const F = xt.values().next().value;
    return F && typeof F.runWithContext == "function" ? F.runWithContext(_) : _();
  }
  function ce(_, F) {
    let R;
    const [Q, f, h] = um(_, F);
    R = Gr(Q.reverse(), "beforeRouteLeave", _, F);
    for (const y of Q) y.leaveGuards.forEach((b) => {
      R.push(ls(b, _, F));
    });
    const g = v.bind(null, _, F);
    return R.push(g), Ae(R).then(() => {
      R = [];
      for (const y of o.list()) R.push(ls(y, _, F));
      return R.push(g), Ae(R);
    }).then(() => {
      R = Gr(f, "beforeRouteUpdate", _, F);
      for (const y of f) y.updateGuards.forEach((b) => {
        R.push(ls(b, _, F));
      });
      return R.push(g), Ae(R);
    }).then(() => {
      R = [];
      for (const y of h) if (y.beforeEnter) if (Ct(y.beforeEnter)) for (const b of y.beforeEnter) R.push(ls(b, _, F));
      else R.push(ls(y.beforeEnter, _, F));
      return R.push(g), Ae(R);
    }).then(() => (_.matched.forEach((y) => y.enterCallbacks = {}), R = Gr(h, "beforeRouteEnter", _, F, V), R.push(g), Ae(R))).then(() => {
      R = [];
      for (const y of i.list()) R.push(ls(y, _, F));
      return R.push(g), Ae(R);
    }).catch((y) => Ht(y, De.NAVIGATION_CANCELLED) ? y : Promise.reject(y));
  }
  function ke(_, F, R) {
    a.list().forEach((Q) => V(() => Q(_, F, R)));
  }
  function Z(_, F, R, Q, f) {
    const h = I(_, F);
    if (h) return h;
    const g = F === rs, y = Ds ? history.state : {};
    R && (Q || g ? r.replace(_.fullPath, Ne({ scroll: g && y && y.scroll }, f)) : r.push(_.fullPath, f)), l.value = _, ut(_, F, R, g), W();
  }
  let ge;
  function Pe() {
    ge || (ge = r.listen((_, F, R) => {
      if (!Me.listening) return;
      const Q = $(_), f = xe(Q, Me.currentRoute.value);
      if (f) {
        ne(Ne(f, {
          replace: !0,
          force: !0
        }), Q).catch(hn);
        return;
      }
      c = Q;
      const h = l.value;
      Ds && sm(Ji(h.fullPath, R.delta), em()), ce(Q, h).catch((g) => Ht(g, De.NAVIGATION_ABORTED | De.NAVIGATION_CANCELLED) ? g : Ht(g, De.NAVIGATION_GUARD_REDIRECT) ? (ne(Ne(C(g.to), { force: !0 }), Q).then((y) => {
        Ht(y, De.NAVIGATION_ABORTED | De.NAVIGATION_DUPLICATED) && !R.delta && R.type === _o.pop && r.go(-1, !1);
      }).catch(hn), Promise.reject()) : (R.delta && r.go(-R.delta, !1), he(g, Q, h))).then((g) => {
        g = g || Z(Q, h, !1), g && (R.delta && !Ht(g, De.NAVIGATION_CANCELLED) ? r.go(-R.delta, !1) : R.type === _o.pop && Ht(g, De.NAVIGATION_ABORTED | De.NAVIGATION_DUPLICATED) && r.go(-1, !1)), ke(Q, h, g);
      }).catch(hn);
    }));
  }
  let ve = en(), fe = en(), X;
  function he(_, F, R) {
    W(_);
    const Q = fe.list();
    return Q.length ? Q.forEach((f) => f(_, F, R)) : console.error(_), Promise.reject(_);
  }
  function ct() {
    return X && l.value !== rs ? Promise.resolve() : new Promise((_, F) => {
      ve.add([_, F]);
    });
  }
  function W(_) {
    return X || (X = !_, Pe(), ve.list().forEach(([F, R]) => _ ? R(_) : F()), ve.reset()), _;
  }
  function ut(_, F, R, Q) {
    const { scrollBehavior: f } = e;
    if (!Ds || !f) return Promise.resolve();
    const h = !R && nm(Ji(_.fullPath, 0)) || (Q || !R) && history.state && history.state.scroll || null;
    return xr().then(() => f(_, F, h)).then((g) => g && tm(g)).catch((g) => he(g, _, F));
  }
  const He = (_) => r.go(_);
  let Bt;
  const xt = /* @__PURE__ */ new Set(), Me = {
    currentRoute: l,
    listening: !0,
    addRoute: p,
    removeRoute: w,
    clearRoutes: t.clearRoutes,
    hasRoute: D,
    getRoutes: x,
    resolve: $,
    options: e,
    push: M,
    replace: Y,
    go: He,
    back: () => He(-1),
    forward: () => He(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: fe.add,
    isReady: ct,
    install(_) {
      _.component("RouterLink", mc), _.component("RouterView", hc), _.config.globalProperties.$router = Me, Object.defineProperty(_.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => O(l)
      }), Ds && !Bt && l.value === rs && (Bt = !0, M(r.location).catch((Q) => {
      }));
      const F = {};
      for (const Q in rs) Object.defineProperty(F, Q, {
        get: () => l.value[Q],
        enumerable: !0
      });
      _.provide(Or, Me), _.provide(Xo, /* @__PURE__ */ dl(F)), _.provide(wo, l);
      const R = _.unmount;
      xt.add(_), _.unmount = function() {
        xt.delete(_), xt.size < 1 && (c = rs, ge && ge(), ge = null, l.value = rs, Bt = !1, X = !1), R();
      };
    }
  };
  function Ae(_) {
    return _.reduce((F, R) => F.then(() => V(R)), Promise.resolve());
  }
  return Me;
}
function Nm() {
  return at(Or);
}
function pc(e) {
  return at(Xo);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const _s = {
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
const la = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function qr(e) {
  return e != null;
}
function Pm(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (m) => s[m] ?? m, r = e.size ?? e.width ?? _s.width, o = e.size ?? e.height ?? _s.height, i = e.aliases?.filter((m) => typeof m == "string" && m.trim() !== "").map((m) => `lucide-${m}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? la(...l) : la("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? _s["stroke-width"]) * Number(e.size ?? e.width ?? _s.width) / Number(t.size ?? t.width ?? _s.width) : t.strokeWidth ?? _s["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(_s).reduce((m, [p, w]) => (m[n(p)] = w, m), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && qr(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && qr(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && qr(t.height) && {
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
      const [p, w, x] = m, D = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...w } : w;
      return x ? [p, D, x] : [p, D];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Mm = (e) => {
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
const $n = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const jm = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Dm = /* @__PURE__ */ Symbol("lucide-icons");
function Lm() {
  return at(Dm, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const $m = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && jm(e),
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
  color: p,
  ...w
}, { slots: x }) => {
  const {
    size: D,
    color: $,
    strokeWidth: C = 2,
    absoluteStrokeWidth: I = !1,
    nonScalingStroke: M = !1,
    class: Y = ""
  } = Lm(), xe = $n(r) || $n(o) || r === !0 || o === !0 || I === !0, ne = $n(i) || $n(a) || i === !0 || a === !0 || M === !0;
  delete w.class;
  const v = x.default?.(), [, V, ce = []] = Pm(n, {
    color: p ?? $,
    width: d ?? u ?? D,
    height: m ?? u ?? D,
    strokeWidth: l ?? c ?? C,
    absoluteStrokeWidth: xe,
    nonScalingStroke: ne,
    className: Y,
    hasA11yProp: v != null && v.length > 0 || Mm(w),
    attributes: w
  });
  return xn("svg", V, [
    ...ce.map(([ke, Z]) => xn(ke, Z)),
    ...v ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function ns(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => xn(
    $m,
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
const Vm = {
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
}, gc = ns(Vm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const zm = {
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
}, yc = ns(zm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Fm = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, Um = ns(Fm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Bm = {
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
}, Wm = ns(Bm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Hm = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, ei = ns(Hm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Zm = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, vc = ns(Zm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Gm = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, qm = ns(Gm);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Km = {
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
}, bc = ns(Km);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Jm = {
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
}, _c = ns(Jm);
function Ym(e) {
  return Do() ? (Ka(e), !0) : !1;
}
const Kr = /* @__PURE__ */ new WeakMap(), Qm = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const s = e[0], n = (t = Ar()) == null ? void 0 : t.proxy;
  if (n == null && !Ho())
    throw new Error("injectLocal must be called in setup");
  return n && Kr.has(n) && s in Kr.get(n) ? Kr.get(n)[s] : at(...e);
}, Xm = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const eh = Object.prototype.toString, th = (e) => eh.call(e) === "[object Object]";
function ca(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function Jr(e) {
  return Array.isArray(e) ? e : [e];
}
function sh(e, t, s) {
  return As(
    e,
    t,
    {
      ...s,
      immediate: !0
    }
  );
}
const xc = Xm ? window : void 0;
function nh(e) {
  var t;
  const s = $s(e);
  return (t = s?.$el) != null ? t : s;
}
function rh(...e) {
  const t = [], s = () => {
    t.forEach((a) => a()), t.length = 0;
  }, n = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = Ie(() => {
    const a = Jr($s(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = sh(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => nh(c))) != null ? l : [xc].filter((c) => c != null),
        Jr($s(r.value ? e[1] : e[0])),
        Jr(O(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        $s(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (s(), !a?.length || !l?.length || !c?.length)
        return;
      const d = th(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (m) => l.flatMap(
            (p) => c.map((w) => n(m, p, w, d))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), s();
  };
  return Ym(s), i;
}
// @__NO_SIDE_EFFECTS__
function oh() {
  const e = /* @__PURE__ */ un(!1), t = Ar();
  return t && On(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function ih(e) {
  const t = /* @__PURE__ */ oh();
  return Ie(() => (t.value, !!e()));
}
const ah = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function lh() {
  const e = Ho() ? /* @__PURE__ */ Qm(ah, null) : null;
  return typeof e == "number" ? e : void 0;
}
function ch(e, t = {}) {
  const { window: s = xc, ssrWidth: n = /* @__PURE__ */ lh() } = t, r = /* @__PURE__ */ ih(() => s && "matchMedia" in s && typeof s.matchMedia == "function"), o = /* @__PURE__ */ un(typeof n == "number"), i = /* @__PURE__ */ un(), a = /* @__PURE__ */ un(!1), l = (c) => {
    a.value = c.matches;
  };
  return Fu(() => {
    if (o.value) {
      o.value = !r.value;
      const c = $s(e).split(",");
      a.value = c.some((u) => {
        const d = u.includes("not all"), m = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), p = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let w = !!(m || p);
        return m && w && (w = n >= ca(m[1])), p && w && (w = n <= ca(p[1])), d ? !w : w;
      });
      return;
    }
    r.value && (i.value = s.matchMedia($s(e)), a.value = i.value.matches);
  }), rh(i, "change", l, { passive: !0 }), Ie(() => a.value);
}
const wc = "comfymodal", ti = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], uh = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function ps(e) {
  return typeof e == "string" && ti.indexOf(e) !== -1;
}
function Vn(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function kc(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || Vn(r.slice(0, o)) !== wc) return t;
  const i = Vn(r.slice(o + 1));
  if (!ps(i)) return t;
  let a = null;
  for (let l = 1; l < n.length; l++) {
    const c = n[l], u = c.indexOf("=");
    if (u === -1 || Vn(c.slice(0, u)) !== "focus") continue;
    const d = Vn(c.slice(u + 1));
    a = d === null || d === "" ? null : d;
    break;
  }
  return { matched: !0, page: i, focus: a };
}
function Sc(e) {
  if (!ps(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + wc + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function ua(e, t) {
  if (!t || !ps(t.page)) return "none";
  if (!e || !ps(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function dh(e, t) {
  if (e && ps(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = kc(t);
  return s.matched && ps(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
const fh = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function Yr(e) {
  return fh.has(e);
}
let da = 0;
function mh() {
  return da += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${da}`;
}
const si = /* @__PURE__ */ Js("studio-operations", () => {
  const e = /* @__PURE__ */ te(/* @__PURE__ */ new Map()), t = Ie(() => [...e.value.values()]), s = Ie(
    () => t.value.filter((m) => m.status === "pending" || m.status === "running")
  );
  function n(m) {
    return e.value.get(m);
  }
  function r(m) {
    const p = Date.now(), w = mh(), x = m.status === "pending" ? "pending" : "running";
    return e.value.set(w, {
      id: w,
      kind: m.kind,
      label: m.label,
      status: x,
      progress: m.progress,
      message: m.message,
      startedAt: p,
      finishedAt: void 0,
      workspaceId: m.workspaceId
    }), w;
  }
  function o(m, p) {
    const w = e.value.get(m);
    if (!w) return;
    const { status: x, ...D } = p, $ = { ...w, ...D };
    !Yr(w.status) && x !== void 0 && !Yr(x) && ($.status = x), e.value.set(m, $);
  }
  function i(m, p, w) {
    const x = e.value.get(m);
    !x || Yr(x.status) || e.value.set(m, {
      ...x,
      status: p,
      message: w === void 0 ? x.message : w,
      finishedAt: Date.now()
    });
  }
  function a(m, p) {
    i(m, "completed", p);
  }
  function l(m, p) {
    i(m, "failed", p);
  }
  function c(m, p) {
    i(m, "canceled", p);
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
var _e;
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
})(_e || (_e = {}));
var fa;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(fa || (fa = {}));
const B = _e.arrayToEnum([
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
]), cs = (e) => {
  switch (typeof e) {
    case "undefined":
      return B.undefined;
    case "string":
      return B.string;
    case "number":
      return Number.isNaN(e) ? B.nan : B.number;
    case "boolean":
      return B.boolean;
    case "function":
      return B.function;
    case "bigint":
      return B.bigint;
    case "symbol":
      return B.symbol;
    case "object":
      return Array.isArray(e) ? B.array : e === null ? B.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? B.promise : typeof Map < "u" && e instanceof Map ? B.map : typeof Set < "u" && e instanceof Set ? B.set : typeof Date < "u" && e instanceof Date ? B.date : B.object;
    default:
      return B.unknown;
  }
}, T = _e.arrayToEnum([
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
class ts extends Error {
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
    if (!(t instanceof ts))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, _e.jsonStringifyReplacer, 2);
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
ts.create = (e) => new ts(e);
const ko = (e, t) => {
  let s;
  switch (e.code) {
    case T.invalid_type:
      e.received === B.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case T.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, _e.jsonStringifyReplacer)}`;
      break;
    case T.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${_e.joinValues(e.keys, ", ")}`;
      break;
    case T.invalid_union:
      s = "Invalid input";
      break;
    case T.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${_e.joinValues(e.options)}`;
      break;
    case T.invalid_enum_value:
      s = `Invalid enum value. Expected ${_e.joinValues(e.options)}, received '${e.received}'`;
      break;
    case T.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case T.invalid_return_type:
      s = "Invalid function return type";
      break;
    case T.invalid_date:
      s = "Invalid date";
      break;
    case T.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : _e.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case T.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case T.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case T.custom:
      s = "Invalid input";
      break;
    case T.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case T.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case T.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, _e.assertNever(e);
  }
  return { message: s };
};
let hh = ko;
function ph() {
  return hh;
}
const gh = (e) => {
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
  const s = ph(), n = gh({
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
      s === ko ? void 0 : ko
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(n);
}
class ot {
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
        return re;
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
    return ot.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const r of s) {
      const { key: o, value: i } = r;
      if (o.status === "aborted" || i.status === "aborted")
        return re;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (n[o.value] = i.value);
    }
    return { status: t.value, value: n };
  }
}
const re = Object.freeze({
  status: "aborted"
}), on = (e) => ({ status: "dirty", value: e }), _t = (e) => ({ status: "valid", value: e }), ma = (e) => e.status === "aborted", ha = (e) => e.status === "dirty", Hs = (e) => e.status === "valid", rr = (e) => typeof Promise < "u" && e instanceof Promise;
var H;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(H || (H = {}));
class Ut {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const pa = (e, t) => {
  if (Hs(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new ts(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function le(e) {
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
class me {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return cs(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: cs(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new ot(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: cs(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (rr(s))
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
      parsedType: cs(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return pa(n, r);
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
      parsedType: cs(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return Hs(n) ? {
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
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => Hs(n) ? {
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
      parsedType: cs(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (rr(r) ? r : Promise.resolve(r));
    return pa(n, o);
  }
  refine(t, s) {
    const n = (r) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(r) : s;
    return this._refinement((r, o) => {
      const i = t(r), a = () => o.addIssue({
        code: T.custom,
        ...n(r)
      });
      return typeof Promise < "u" && i instanceof Promise ? i.then((l) => l ? !0 : (a(), !1)) : i ? !0 : (a(), !1);
    });
  }
  refinement(t, s) {
    return this._refinement((n, r) => t(n) ? !0 : (r.addIssue(typeof s == "function" ? s(n, r) : s), !1));
  }
  _refinement(t) {
    return new qs({
      schema: this,
      typeName: se.ZodEffects,
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
    return ms.create(this, this._def);
  }
  nullable() {
    return Ks.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return $t.create(this);
  }
  promise() {
    return cr.create(this, this._def);
  }
  or(t) {
    return ir.create([this, t], this._def);
  }
  and(t) {
    return ar.create(this, t, this._def);
  }
  transform(t) {
    return new qs({
      ...le(this._def),
      schema: this,
      typeName: se.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Ao({
      ...le(this._def),
      innerType: this,
      defaultValue: s,
      typeName: se.ZodDefault
    });
  }
  brand() {
    return new Vh({
      typeName: se.ZodBranded,
      type: this,
      ...le(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Eo({
      ...le(this._def),
      innerType: this,
      catchValue: s,
      typeName: se.ZodCatch
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
    return ni.create(this, t);
  }
  readonly() {
    return Ro.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const yh = /^c[^\s-]{8,}$/i, vh = /^[0-9a-z]+$/, bh = /^[0-9A-HJKMNP-TV-Z]{26}$/i, _h = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, xh = /^[a-z0-9_-]{21}$/i, wh = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, kh = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Sh = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, Ch = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let Qr;
const Ah = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, Eh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, Rh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, Oh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, Th = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, Ih = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, Cc = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", Nh = new RegExp(`^${Cc}$`);
function Ac(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function Ph(e) {
  return new RegExp(`^${Ac(e)}$`);
}
function Mh(e) {
  let t = `${Cc}T${Ac(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function jh(e, t) {
  return !!((t === "v4" || !t) && Ah.test(e) || (t === "v6" || !t) && Rh.test(e));
}
function Dh(e, t) {
  if (!wh.test(e))
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
function Lh(e, t) {
  return !!((t === "v4" || !t) && Eh.test(e) || (t === "v6" || !t) && Oh.test(e));
}
class Yt extends me {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== B.string) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: T.invalid_type,
        expected: B.string,
        received: o.parsedType
      }), re;
    }
    const n = new ot();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), L(r, {
          code: T.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), L(r, {
          code: T.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? L(r, {
          code: T.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && L(r, {
          code: T.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        Sh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "email",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        Qr || (Qr = new RegExp(Ch, "u")), Qr.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "emoji",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        _h.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "uuid",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        xh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "nanoid",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        yh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "cuid",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        vh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "cuid2",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        bh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
          validation: "ulid",
          code: T.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), L(r, {
            validation: "url",
            code: T.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "regex",
        code: T.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? Mh(o).test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? Nh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? Ph(o).test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? kh.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "duration",
        code: T.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? jh(t.data, o.version) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "ip",
        code: T.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? Dh(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "jwt",
        code: T.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Lh(t.data, o.version) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "cidr",
        code: T.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? Th.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "base64",
        code: T.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? Ih.test(t.data) || (r = this._getOrReturnCtx(t, r), L(r, {
        validation: "base64url",
        code: T.invalid_string,
        message: o.message
      }), n.dirty()) : _e.assertNever(o);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((r) => t.test(r), {
      validation: s,
      code: T.invalid_string,
      ...H.errToObj(n)
    });
  }
  _addCheck(t) {
    return new Yt({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...H.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...H.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...H.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...H.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...H.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...H.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...H.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...H.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...H.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...H.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...H.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...H.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...H.errToObj(t) });
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
      ...H.errToObj(t?.message)
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
      ...H.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...H.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...H.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...H.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...H.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...H.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...H.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...H.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...H.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, H.errToObj(t));
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
  typeName: se.ZodString,
  coerce: e?.coerce ?? !1,
  ...le(e)
});
function $h(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class Zs extends me {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== B.number) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: T.invalid_type,
        expected: B.number,
        received: o.parsedType
      }), re;
    }
    let n;
    const r = new ot();
    for (const o of this._def.checks)
      o.kind === "int" ? _e.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? $h(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.not_finite,
        message: o.message
      }), r.dirty()) : _e.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, H.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, H.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, H.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, H.toString(s));
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
          message: H.toString(r)
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
      message: H.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: H.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: H.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: H.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: H.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: H.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: H.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: H.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: H.toString(t)
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && _e.isInteger(t.value));
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
  typeName: se.ZodNumber,
  coerce: e?.coerce || !1,
  ...le(e)
});
class Sn extends me {
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
    if (this._getType(t) !== B.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new ot();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), L(n, {
        code: T.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : _e.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return L(s, {
      code: T.invalid_type,
      expected: B.bigint,
      received: s.parsedType
    }), re;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, H.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, H.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, H.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, H.toString(s));
  }
  setLimit(t, s, n, r) {
    return new Sn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: H.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Sn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: H.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: H.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: H.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: H.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: H.toString(s)
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
Sn.create = (e) => new Sn({
  checks: [],
  typeName: se.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...le(e)
});
class So extends me {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== B.boolean) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: T.invalid_type,
        expected: B.boolean,
        received: n.parsedType
      }), re;
    }
    return _t(t.data);
  }
}
So.create = (e) => new So({
  typeName: se.ZodBoolean,
  coerce: e?.coerce || !1,
  ...le(e)
});
class or extends me {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== B.date) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: T.invalid_type,
        expected: B.date,
        received: o.parsedType
      }), re;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return L(o, {
        code: T.invalid_date
      }), re;
    }
    const n = new ot();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), L(r, {
        code: T.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), n.dirty()) : _e.assertNever(o);
    return {
      status: n.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new or({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: H.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: H.toString(s)
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
or.create = (e) => new or({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: se.ZodDate,
  ...le(e)
});
class ga extends me {
  _parse(t) {
    if (this._getType(t) !== B.symbol) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: T.invalid_type,
        expected: B.symbol,
        received: n.parsedType
      }), re;
    }
    return _t(t.data);
  }
}
ga.create = (e) => new ga({
  typeName: se.ZodSymbol,
  ...le(e)
});
class ya extends me {
  _parse(t) {
    if (this._getType(t) !== B.undefined) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: T.invalid_type,
        expected: B.undefined,
        received: n.parsedType
      }), re;
    }
    return _t(t.data);
  }
}
ya.create = (e) => new ya({
  typeName: se.ZodUndefined,
  ...le(e)
});
class va extends me {
  _parse(t) {
    if (this._getType(t) !== B.null) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: T.invalid_type,
        expected: B.null,
        received: n.parsedType
      }), re;
    }
    return _t(t.data);
  }
}
va.create = (e) => new va({
  typeName: se.ZodNull,
  ...le(e)
});
class ba extends me {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return _t(t.data);
  }
}
ba.create = (e) => new ba({
  typeName: se.ZodAny,
  ...le(e)
});
class _a extends me {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return _t(t.data);
  }
}
_a.create = (e) => new _a({
  typeName: se.ZodUnknown,
  ...le(e)
});
class gs extends me {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return L(s, {
      code: T.invalid_type,
      expected: B.never,
      received: s.parsedType
    }), re;
  }
}
gs.create = (e) => new gs({
  typeName: se.ZodNever,
  ...le(e)
});
class xa extends me {
  _parse(t) {
    if (this._getType(t) !== B.undefined) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: T.invalid_type,
        expected: B.void,
        received: n.parsedType
      }), re;
    }
    return _t(t.data);
  }
}
xa.create = (e) => new xa({
  typeName: se.ZodVoid,
  ...le(e)
});
class $t extends me {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== B.array)
      return L(s, {
        code: T.invalid_type,
        expected: B.array,
        received: s.parsedType
      }), re;
    if (r.exactLength !== null) {
      const i = s.data.length > r.exactLength.value, a = s.data.length < r.exactLength.value;
      (i || a) && (L(s, {
        code: i ? T.too_big : T.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (L(s, {
      code: T.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (L(s, {
      code: T.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((i, a) => r.type._parseAsync(new Ut(s, i, s.path, a)))).then((i) => ot.mergeArray(n, i));
    const o = [...s.data].map((i, a) => r.type._parseSync(new Ut(s, i, s.path, a)));
    return ot.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new $t({
      ...this._def,
      minLength: { value: t, message: H.toString(s) }
    });
  }
  max(t, s) {
    return new $t({
      ...this._def,
      maxLength: { value: t, message: H.toString(s) }
    });
  }
  length(t, s) {
    return new $t({
      ...this._def,
      exactLength: { value: t, message: H.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
$t.create = (e, t) => new $t({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: se.ZodArray,
  ...le(t)
});
function Ls(e) {
  if (e instanceof Ve) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = ms.create(Ls(n));
    }
    return new Ve({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof $t ? new $t({
    ...e._def,
    type: Ls(e.element)
  }) : e instanceof ms ? ms.create(Ls(e.unwrap())) : e instanceof Ks ? Ks.create(Ls(e.unwrap())) : e instanceof Os ? Os.create(e.items.map((t) => Ls(t))) : e;
}
class Ve extends me {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = _e.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== B.object) {
      const c = this._getOrReturnCtx(t);
      return L(c, {
        code: T.invalid_type,
        expected: B.object,
        received: c.parsedType
      }), re;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof gs && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], d = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new Ut(r, d, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof gs) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && (L(r, {
          code: T.unrecognized_keys,
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
            new Ut(r, d, r.path, u)
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
    }).then((c) => ot.mergeObjectSync(n, c)) : ot.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return H.errToObj, new Ve({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: H.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new Ve({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new Ve({
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
    return new Ve({
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
    return new Ve({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: se.ZodObject
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
    return new Ve({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of _e.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new Ve({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of _e.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new Ve({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return Ls(this);
  }
  partial(t) {
    const s = {};
    for (const n of _e.objectKeys(this.shape)) {
      const r = this.shape[n];
      t && !t[n] ? s[n] = r : s[n] = r.optional();
    }
    return new Ve({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of _e.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let o = this.shape[n];
        for (; o instanceof ms; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new Ve({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return Ec(_e.objectKeys(this.shape));
  }
}
Ve.create = (e, t) => new Ve({
  shape: () => e,
  unknownKeys: "strip",
  catchall: gs.create(),
  typeName: se.ZodObject,
  ...le(t)
});
Ve.strictCreate = (e, t) => new Ve({
  shape: () => e,
  unknownKeys: "strict",
  catchall: gs.create(),
  typeName: se.ZodObject,
  ...le(t)
});
Ve.lazycreate = (e, t) => new Ve({
  shape: e,
  unknownKeys: "strip",
  catchall: gs.create(),
  typeName: se.ZodObject,
  ...le(t)
});
class ir extends me {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return s.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new ts(a.ctx.common.issues));
      return L(s, {
        code: T.invalid_union,
        unionErrors: i
      }), re;
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
      const a = i.map((l) => new ts(l));
      return L(s, {
        code: T.invalid_union,
        unionErrors: a
      }), re;
    }
  }
  get options() {
    return this._def.options;
  }
}
ir.create = (e, t) => new ir({
  options: e,
  typeName: se.ZodUnion,
  ...le(t)
});
function Co(e, t) {
  const s = cs(e), n = cs(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === B.object && n === B.object) {
    const r = _e.objectKeys(t), o = _e.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = Co(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (s === B.array && n === B.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = Co(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === B.date && n === B.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class ar extends me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, i) => {
      if (ma(o) || ma(i))
        return re;
      const a = Co(o.value, i.value);
      return a.valid ? ((ha(o) || ha(i)) && s.dirty(), { status: s.value, value: a.data }) : (L(n, {
        code: T.invalid_intersection_types
      }), re);
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
ar.create = (e, t, s) => new ar({
  left: e,
  right: t,
  typeName: se.ZodIntersection,
  ...le(s)
});
class Os extends me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== B.array)
      return L(n, {
        code: T.invalid_type,
        expected: B.array,
        received: n.parsedType
      }), re;
    if (n.data.length < this._def.items.length)
      return L(n, {
        code: T.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), re;
    !this._def.rest && n.data.length > this._def.items.length && (L(n, {
      code: T.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new Ut(n, i, n.path, a)) : null;
    }).filter((i) => !!i);
    return n.common.async ? Promise.all(o).then((i) => ot.mergeArray(s, i)) : ot.mergeArray(s, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Os({
      ...this._def,
      rest: t
    });
  }
}
Os.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Os({
    items: e,
    typeName: se.ZodTuple,
    rest: null,
    ...le(t)
  });
};
class lr extends me {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== B.object)
      return L(n, {
        code: T.invalid_type,
        expected: B.object,
        received: n.parsedType
      }), re;
    const r = [], o = this._def.keyType, i = this._def.valueType;
    for (const a in n.data)
      r.push({
        key: o._parse(new Ut(n, a, n.path, a)),
        value: i._parse(new Ut(n, n.data[a], n.path, a)),
        alwaysSet: a in n.data
      });
    return n.common.async ? ot.mergeObjectAsync(s, r) : ot.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof me ? new lr({
      keyType: t,
      valueType: s,
      typeName: se.ZodRecord,
      ...le(n)
    }) : new lr({
      keyType: Yt.create(),
      valueType: t,
      typeName: se.ZodRecord,
      ...le(s)
    });
  }
}
class wa extends me {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== B.map)
      return L(n, {
        code: T.invalid_type,
        expected: B.map,
        received: n.parsedType
      }), re;
    const r = this._def.keyType, o = this._def.valueType, i = [...n.data.entries()].map(([a, l], c) => ({
      key: r._parse(new Ut(n, a, n.path, [c, "key"])),
      value: o._parse(new Ut(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return re;
          (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
        }
        return { status: s.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return re;
        (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
      }
      return { status: s.value, value: a };
    }
  }
}
wa.create = (e, t, s) => new wa({
  valueType: t,
  keyType: e,
  typeName: se.ZodMap,
  ...le(s)
});
class Cn extends me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== B.set)
      return L(n, {
        code: T.invalid_type,
        expected: B.set,
        received: n.parsedType
      }), re;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (L(n, {
      code: T.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (L(n, {
      code: T.too_big,
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
          return re;
        u.status === "dirty" && s.dirty(), c.add(u.value);
      }
      return { status: s.value, value: c };
    }
    const a = [...n.data.values()].map((l, c) => o._parse(new Ut(n, l, n.path, c)));
    return n.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, s) {
    return new Cn({
      ...this._def,
      minSize: { value: t, message: H.toString(s) }
    });
  }
  max(t, s) {
    return new Cn({
      ...this._def,
      maxSize: { value: t, message: H.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Cn.create = (e, t) => new Cn({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: se.ZodSet,
  ...le(t)
});
class ka extends me {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
ka.create = (e, t) => new ka({
  getter: e,
  typeName: se.ZodLazy,
  ...le(t)
});
class Sa extends me {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return L(s, {
        received: s.data,
        code: T.invalid_literal,
        expected: this._def.value
      }), re;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Sa.create = (e, t) => new Sa({
  value: e,
  typeName: se.ZodLiteral,
  ...le(t)
});
function Ec(e, t) {
  return new Gs({
    values: e,
    typeName: se.ZodEnum,
    ...le(t)
  });
}
class Gs extends me {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return L(s, {
        expected: _e.joinValues(n),
        received: s.parsedType,
        code: T.invalid_type
      }), re;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return L(s, {
        received: s.data,
        code: T.invalid_enum_value,
        options: n
      }), re;
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
    return Gs.create(t, {
      ...this._def,
      ...s
    });
  }
  exclude(t, s = this._def) {
    return Gs.create(this.options.filter((n) => !t.includes(n)), {
      ...this._def,
      ...s
    });
  }
}
Gs.create = Ec;
class Ca extends me {
  _parse(t) {
    const s = _e.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== B.string && n.parsedType !== B.number) {
      const r = _e.objectValues(s);
      return L(n, {
        expected: _e.joinValues(r),
        received: n.parsedType,
        code: T.invalid_type
      }), re;
    }
    if (this._cache || (this._cache = new Set(_e.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = _e.objectValues(s);
      return L(n, {
        received: n.data,
        code: T.invalid_enum_value,
        options: r
      }), re;
    }
    return _t(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
Ca.create = (e, t) => new Ca({
  values: e,
  typeName: se.ZodNativeEnum,
  ...le(t)
});
class cr extends me {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== B.promise && s.common.async === !1)
      return L(s, {
        code: T.invalid_type,
        expected: B.promise,
        received: s.parsedType
      }), re;
    const n = s.parsedType === B.promise ? s.data : Promise.resolve(s.data);
    return _t(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
cr.create = (e, t) => new cr({
  type: e,
  typeName: se.ZodPromise,
  ...le(t)
});
class qs extends me {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === se.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
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
            return re;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? re : l.status === "dirty" || s.value === "dirty" ? on(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return re;
        const a = this._def.schema._parseSync({
          data: i,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? re : a.status === "dirty" || s.value === "dirty" ? on(a.value) : a;
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
        return a.status === "aborted" ? re : (a.status === "dirty" && s.dirty(), i(a.value), { status: s.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => a.status === "aborted" ? re : (a.status === "dirty" && s.dirty(), i(a.value).then(() => ({ status: s.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!Hs(i))
          return re;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => Hs(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: s.value,
          value: a
        })) : re);
    _e.assertNever(r);
  }
}
qs.create = (e, t, s) => new qs({
  schema: e,
  typeName: se.ZodEffects,
  effect: t,
  ...le(s)
});
qs.createWithPreprocess = (e, t, s) => new qs({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: se.ZodEffects,
  ...le(s)
});
class ms extends me {
  _parse(t) {
    return this._getType(t) === B.undefined ? _t(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
ms.create = (e, t) => new ms({
  innerType: e,
  typeName: se.ZodOptional,
  ...le(t)
});
class Ks extends me {
  _parse(t) {
    return this._getType(t) === B.null ? _t(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Ks.create = (e, t) => new Ks({
  innerType: e,
  typeName: se.ZodNullable,
  ...le(t)
});
class Ao extends me {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === B.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
Ao.create = (e, t) => new Ao({
  innerType: e,
  typeName: se.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...le(t)
});
class Eo extends me {
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
    return rr(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new ts(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new ts(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
Eo.create = (e, t) => new Eo({
  innerType: e,
  typeName: se.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...le(t)
});
class Aa extends me {
  _parse(t) {
    if (this._getType(t) !== B.nan) {
      const n = this._getOrReturnCtx(t);
      return L(n, {
        code: T.invalid_type,
        expected: B.nan,
        received: n.parsedType
      }), re;
    }
    return { status: "valid", value: t.data };
  }
}
Aa.create = (e) => new Aa({
  typeName: se.ZodNaN,
  ...le(e)
});
class Vh extends me {
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
class ni extends me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? re : o.status === "dirty" ? (s.dirty(), on(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? re : r.status === "dirty" ? (s.dirty(), {
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
    return new ni({
      in: t,
      out: s,
      typeName: se.ZodPipeline
    });
  }
}
class Ro extends me {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (Hs(r) && (r.value = Object.freeze(r.value)), r);
    return rr(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Ro.create = (e, t) => new Ro({
  innerType: e,
  typeName: se.ZodReadonly,
  ...le(t)
});
var se;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(se || (se = {}));
const Ge = Yt.create, Xr = Zs.create, zn = So.create;
gs.create;
const zh = $t.create, ri = Ve.create;
ir.create;
ar.create;
Os.create;
const Fh = lr.create, Oo = Gs.create;
cr.create;
ms.create;
Ks.create;
const Uh = "comfymodal.studio.vue.";
function Bh() {
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
function Wh() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return Bh();
}
function Rc(e, t, s, n) {
  const r = Uh + e, o = Wh();
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
const Hh = "/comfymodal";
class Zh extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function Gh(e, t) {
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
function qh(e, t) {
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
async function ze(e, t = {}, s = fetch) {
  const {
    method: n = "GET",
    body: r,
    signal: o,
    timeoutMs: i,
    headers: a = {}
  } = t, { signal: l, cleanup: c } = qh(o, i);
  try {
    if (l && l.aborted) throw l.reason;
    const u = await s(Hh + e, {
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
      throw new Zh(
        u.status,
        Gh(m, `Request failed with status ${u.status}`),
        m
      );
    return m;
  } finally {
    c();
  }
}
const Kh = ri({ value: Ge(), label: Ge() }).passthrough(), Jh = ri({
  gpu: Ge().default(""),
  default_gpu: Ge().default(""),
  available_gpus: zh(Kh).default([]),
  persisted_gpu: Ge().default(""),
  output_format: Ge().default("original"),
  quality: Xr().default(75),
  webp_lossless_compression: Ge().default("balanced"),
  auto_save_local: zn().default(!1),
  save_folder: Ge().default(""),
  save_metadata_sidecar: zn().default(!0),
  preview_default: Oo(["off", "on"]).default("off"),
  preview_codec: Ge().default("webp"),
  preview_quality: Xr().default(70),
  data_saver_default: Oo(["off", "on"]).default("off"),
  data_saver_codec: Ge().default("webp"),
  data_saver_quality: Xr().default(70),
  execution_mode: Ge().default("v2"),
  execution_mode_source: Ge().default(""),
  execution_mode_locked: zn().default(!1),
  engine_migration_notice: Ge().nullable().default(null),
  skip_plan_validation: zn().default(!1),
  golden_gpu_order: Fh(Ge()).default({})
}).passthrough(), Yh = ri({ status: Ge().optional(), level: Ge().default("off"), effective: Ge().default("off") }).passthrough();
async function Ea() {
  return Jh.parse(await ze("/config"));
}
async function Qh(e) {
  return ze("/config", { method: "POST", body: e });
}
async function Xh() {
  return Yh.parse(await ze("/profile/level"));
}
async function ep(e) {
  return ze("/profile/level", { method: "POST", body: { level: e } });
}
const tn = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function Ra(e) {
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
    localStorage.setItem(tn.outputFormat, s.output_format), localStorage.setItem(tn.quality, String(s.quality)), localStorage.setItem(tn.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(tn.saveFolder, s.save_folder), localStorage.setItem(tn.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const Oc = "comfymodal-studio";
function oi(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(Oc), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function Rs(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(Oc);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
const tp = Oo(["comfortable", "compact"]), eo = Rc(
  "shell.density",
  "comfortable",
  tp
), Tc = /* @__PURE__ */ Js("studio-settings", () => {
  const e = /* @__PURE__ */ te("studio"), t = /* @__PURE__ */ te(eo.read()), s = /* @__PURE__ */ te(null), n = /* @__PURE__ */ te("off"), r = /* @__PURE__ */ te(!1), o = /* @__PURE__ */ te(!1), i = /* @__PURE__ */ te(null), a = /* @__PURE__ */ te(!1);
  let l = null;
  const c = Ie(() => s.value?.gpu ?? ""), u = Ie(() => s.value ? {
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
      const [C, I] = await Promise.all([Ea(), Xh()]);
      s.value = C, n.value = I.effective || I.level, Ra(C), a.value = !0;
    } catch (C) {
      throw i.value = C instanceof Error ? C.message : "Could not load Settings", C;
    } finally {
      r.value = !1;
    }
  }
  async function m(C) {
    o.value = !0, i.value = null;
    try {
      await Qh(C);
      const I = await Ea();
      s.value = I, Ra(I), Rs("settings");
    } catch (I) {
      throw i.value = I instanceof Error ? I.message : "Could not save Settings", I;
    } finally {
      o.value = !1;
    }
  }
  async function p(C) {
    await ep(C), n.value = C, Rs("settings");
  }
  async function w() {
    l || (l = oi((C) => {
      C === "settings" && !r.value && d();
    })), a.value || await d();
  }
  function x(C) {
    e.value = C;
  }
  function D(C) {
    t.value = C, eo.write(C);
  }
  function $() {
    e.value = "studio", t.value = "comfortable", eo.write("comfortable");
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
    initialize: w,
    save: m,
    setProfile: p,
    setSection: x,
    setDensity: D,
    reset: $
  };
});
function sp(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const r = String(n.id ?? "");
    return { id: r, label: String(n.label ?? r), isActive: r !== "" && r === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function Ic(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function np(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function rp() {
  return ze("/workspaces");
}
async function op(e) {
  return ze("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function Oa() {
  return Ic(await ze("/deploy/status"));
}
async function ip() {
  return ze("/deploy", { method: "POST" });
}
async function ap() {
  return ze("/deploy/log");
}
async function lp(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return ze(`/studio/inventory/refresh${t}`);
}
async function cp(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return ze(`/studio/models${s}`);
}
async function up(e = !1) {
  return ze("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function dp() {
  return ze("/studio/custom-nodes");
}
async function fp() {
  return ze("/studio/custom-nodes/refresh", { method: "POST" });
}
function To() {
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
function mp(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function hp(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function Nc(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    mp(s), i += 1, o && o(i);
    const a = await n(s, i);
    if (r(a)) return a;
    await hp(t, s);
  }
}
const Pc = /* @__PURE__ */ Js("studio-infrastructure", () => {
  const e = /* @__PURE__ */ te("unknown"), t = /* @__PURE__ */ te(null), s = /* @__PURE__ */ te(null), n = /* @__PURE__ */ te([]), r = /* @__PURE__ */ te(null), o = /* @__PURE__ */ te(Ic(null)), i = /* @__PURE__ */ te(null), a = /* @__PURE__ */ te([]), l = /* @__PURE__ */ te([]), c = /* @__PURE__ */ te(!1), u = /* @__PURE__ */ te(null), d = To();
  let m = null;
  const p = Ie(() => n.value.find((Z) => Z.isActive) ?? null);
  function w(Z, ge) {
    e.value = Z, t.value = ge ?? null;
  }
  function x(Z) {
    s.value = Z;
  }
  function D() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  async function $() {
    const Z = sp(await rp());
    n.value = Z.rows, r.value = Z.activeId;
  }
  async function C() {
    o.value = await Oa(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function I() {
    const Z = await d.run(async (ge) => {
      const [Pe, ve] = await Promise.all([cp(), dp()]);
      return ge.aborted ? null : { modelResult: Pe, nodeResult: ve };
    });
    Z.stale || !Z.value || (a.value = Z.value.modelResult.models ?? [], l.value = Z.value.nodeResult.custom_nodes ?? []);
  }
  async function M() {
    c.value = !0, u.value = null;
    try {
      await Promise.all([$(), C(), I()]), s.value = "server inventory loaded";
    } catch (Z) {
      throw u.value = Z instanceof Error ? Z.message : "Could not load infrastructure", Z;
    } finally {
      c.value = !1;
    }
  }
  async function Y() {
    m || (m = oi((Z) => {
      Z === "workspace" && !c.value && M();
    })), n.value.length || await M();
  }
  async function xe(Z) {
    await op(Z), await $(), Rs("workspace");
  }
  async function ne() {
    const Z = si(), ge = Z.start({ kind: "deploy", label: "Deploy workspace" });
    try {
      await ip(), Z.patch(ge, { status: "running", message: "Deployment started" });
      const Pe = await Nc({
        intervalMs: 3e3,
        run: async () => {
          const ve = await Oa();
          return o.value = ve, e.value = ve.state, t.value = ve.message || null, Z.patch(ge, { message: ve.message || `Deployment: ${ve.state}` }), ve;
        },
        done: (ve) => ve.state === "ready" || ve.state === "deployed_unwarmed" || ve.state !== "deploying" && ve.state !== "starting" && ve.state !== "unknown"
      });
      if (!np(Pe.state)) throw new Error(Pe.message || `Deployment ended in ${Pe.state}`);
      Z.finish(ge, Pe.message || "Deployment completed");
    } catch (Pe) {
      const ve = Pe instanceof Error ? Pe.message : "Deployment failed";
      throw Z.fail(ge, ve), Pe;
    }
    return ge;
  }
  async function v() {
    await lp(0), await I(), s.value = "inventory refreshed", Rs("workspace");
  }
  async function V() {
    const Z = await up(!0);
    a.value = Z.models ?? a.value, await I();
  }
  async function ce() {
    const Z = await fp();
    l.value = Z.custom_nodes ?? l.value, await I();
  }
  async function ke() {
    i.value = await ap();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: r,
    activeWorkspace: p,
    deployStatus: o,
    deployLog: i,
    models: a,
    customNodes: l,
    loading: c,
    error: u,
    setDeploy: w,
    setSyncSummary: x,
    reset: D,
    load: M,
    initialize: Y,
    loadWorkspaces: $,
    loadDeployment: C,
    loadInventory: I,
    selectWorkspace: xe,
    deploy: ne,
    refreshRemoteInventoryNow: v,
    rescanModelsNow: V,
    refreshCustomNodesNow: ce,
    loadLog: ke
  };
});
function Mc(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = Mc(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function jc() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = Mc(e)) && (n && (n += " "), n += t);
  return n;
}
const pp = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, gp = (e, t) => ({
  classGroupId: e,
  validator: t
}), Dc = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), ur = "-", Ta = [], yp = "arbitrary..", vp = (e) => {
  const t = _p(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return bp(i);
      const a = i.split(ur), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return Lc(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = n[i], c = s[i];
        return l ? c ? pp(c, l) : l : c || Ta;
      }
      return s[i] || Ta;
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
  const a = t === 0 ? e.join(ur) : e.slice(t).join(ur), l = i.length;
  for (let c = 0; c < l; c++) {
    const u = i[c];
    if (u.validator(a))
      return u.classGroupId;
  }
}, bp = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? yp + n : void 0;
})(), _p = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return xp(s, t);
}, xp = (e, t) => {
  const s = Dc();
  for (const n in e) {
    const r = e[n];
    ii(r, s, n, t);
  }
  return s;
}, ii = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    wp(i, t, s, n);
  }
}, wp = (e, t, s, n) => {
  if (typeof e == "string") {
    kp(e, t, s);
    return;
  }
  if (typeof e == "function") {
    Sp(e, t, s, n);
    return;
  }
  Cp(e, t, s, n);
}, kp = (e, t, s) => {
  const n = e === "" ? t : $c(t, e);
  n.classGroupId = s;
}, Sp = (e, t, s, n) => {
  if (Ap(e)) {
    ii(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(gp(s, e));
}, Cp = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    ii(l, $c(t, a), s, n);
  }
}, $c = (e, t) => {
  let s = e;
  const n = t.split(ur), r = n.length;
  for (let o = 0; o < r; o++) {
    const i = n[o];
    let a = s.nextPart.get(i);
    a || (a = Dc(), s.nextPart.set(i, a)), s = a;
  }
  return s;
}, Ap = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Ep = (e) => {
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
}, Io = "!", Ia = ":", Rp = [], Na = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), Op = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let x = 0; x < u; x++) {
      const D = r[x];
      if (i === 0 && a === 0) {
        if (D === Ia) {
          o.push(r.slice(l, x)), l = x + 1;
          continue;
        }
        if (D === "/") {
          c = x;
          continue;
        }
      }
      D === "[" ? i++ : D === "]" ? i-- : D === "(" ? a++ : D === ")" && a--;
    }
    const d = o.length === 0 ? r : r.slice(l);
    let m = d, p = !1;
    d.endsWith(Io) ? (m = d.slice(0, -1), p = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      d.startsWith(Io) && (m = d.slice(1), p = !0)
    );
    const w = c && c > l ? c - l : void 0;
    return Na(o, p, m, w);
  };
  if (t) {
    const r = t + Ia, o = n;
    n = (i) => i.startsWith(r) ? o(i.slice(r.length)) : Na(Rp, !1, i, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, Tp = (e) => {
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
}, Ip = (e) => ({
  cache: Ep(e.cacheSize),
  parseClassName: Op(e),
  sortModifiers: Tp(e),
  postfixLookupClassGroupIds: Np(e),
  ...vp(e)
}), Np = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, Pp = /\s+/, Mp = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Pp);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const d = l[u], {
      isExternal: m,
      modifiers: p,
      hasImportantModifier: w,
      baseClassName: x,
      maybePostfixModifierPosition: D
    } = s(d);
    if (m) {
      c = d + (c.length > 0 ? " " + c : c);
      continue;
    }
    let $ = !!D, C;
    if ($) {
      const ne = x.substring(0, D);
      C = n(ne);
      const v = C && i[C] ? n(x) : void 0;
      v && v !== C && (C = v, $ = !1);
    } else
      C = n(x);
    if (!C) {
      if (!$) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (C = n(x), !C) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      $ = !1;
    }
    const I = p.length === 0 ? "" : p.length === 1 ? p[0] : o(p).join(":"), M = w ? I + Io : I, Y = M + C;
    if (a.indexOf(Y) > -1)
      continue;
    a.push(Y);
    const xe = r(C, $);
    for (let ne = 0; ne < xe.length; ++ne) {
      const v = xe[ne];
      a.push(M + v);
    }
    c = d + (c.length > 0 ? " " + c : c);
  }
  return c;
}, jp = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = Vc(s)) && (r && (r += " "), r += n);
  return r;
}, Vc = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = Vc(e[n])) && (s && (s += " "), s += t);
  return s;
}, Dp = (e, ...t) => {
  let s, n, r, o;
  const i = (l) => {
    const c = t.reduce((u, d) => d(u), e());
    return s = Ip(c), n = s.cache.get, r = s.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = n(l);
    if (c)
      return c;
    const u = Mp(l, s);
    return r(l, u), u;
  };
  return o = i, (...l) => o(jp(...l));
}, Lp = [], Fe = (e) => {
  const t = (s) => s[e] || Lp;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, zc = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, Fc = /^\((?:(\w[\w-]*):)?(.+)\)$/i, $p = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, Vp = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, zp = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Fp = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Up = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, Bp = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, os = (e) => $p.test(e), ue = (e) => !!e && !Number.isNaN(Number(e)), Tt = (e) => !!e && Number.isInteger(Number(e)), to = (e) => e.endsWith("%") && ue(e.slice(0, -1)), Zt = (e) => Vp.test(e), Uc = () => !0, Wp = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  zp.test(e) && !Fp.test(e)
), ai = () => !1, Hp = (e) => Up.test(e), Zp = (e) => Bp.test(e), Gp = (e) => !z(e) && !U(e), qp = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), Kp = (e) => ys(e, Hc, ai), z = (e) => zc.test(e), xs = (e) => ys(e, Zc, Wp), Pa = (e) => ys(e, ng, ue), Jp = (e) => ys(e, qc, Uc), Yp = (e) => ys(e, Gc, ai), Ma = (e) => ys(e, Bc, ai), Qp = (e) => ys(e, Wc, Zp), Fn = (e) => ys(e, Kc, Hp), U = (e) => Fc.test(e), sn = (e) => Is(e, Zc), Xp = (e) => Is(e, Gc), ja = (e) => Is(e, Bc), eg = (e) => Is(e, Hc), tg = (e) => Is(e, Wc), Un = (e) => Is(e, Kc, !0), sg = (e) => Is(e, qc, !0), ys = (e, t, s) => {
  const n = zc.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, Is = (e, t, s = !1) => {
  const n = Fc.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, Bc = (e) => e === "position" || e === "percentage", Wc = (e) => e === "image" || e === "url", Hc = (e) => e === "length" || e === "size" || e === "bg-size", Zc = (e) => e === "length", ng = (e) => e === "number", Gc = (e) => e === "family-name", qc = (e) => e === "number" || e === "weight", Kc = (e) => e === "shadow", rg = () => {
  const e = Fe("color"), t = Fe("font"), s = Fe("text"), n = Fe("font-weight"), r = Fe("tracking"), o = Fe("leading"), i = Fe("breakpoint"), a = Fe("container"), l = Fe("spacing"), c = Fe("radius"), u = Fe("shadow"), d = Fe("inset-shadow"), m = Fe("text-shadow"), p = Fe("drop-shadow"), w = Fe("blur"), x = Fe("perspective"), D = Fe("aspect"), $ = Fe("ease"), C = Fe("animate"), I = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], M = () => [
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
  ], Y = () => [...M(), U, z], xe = () => ["auto", "hidden", "clip", "visible", "scroll"], ne = () => ["auto", "contain", "none"], v = () => [U, z, l], V = () => [os, "full", "auto", ...v()], ce = () => [Tt, "none", "subgrid", U, z], ke = () => ["auto", {
    span: ["full", Tt, U, z]
  }, Tt, U, z], Z = () => [Tt, "auto", U, z], ge = () => ["auto", "min", "max", "fr", U, z], Pe = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], ve = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], fe = () => ["auto", ...v()], X = () => [os, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...v()], he = () => [a, os, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...v()], ct = () => [os, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...v()], W = () => [e, U, z], ut = () => [...M(), ja, Ma, {
    position: [U, z]
  }], He = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], Bt = () => ["auto", "cover", "contain", eg, Kp, {
    size: [U, z]
  }], xt = () => [to, sn, xs], Me = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    U,
    z
  ], Ae = () => ["", ue, sn, xs], _ = () => ["solid", "dashed", "dotted", "double"], F = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], R = () => [ue, to, ja, Ma], Q = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    w,
    U,
    z
  ], f = () => ["none", ue, U, z], h = () => ["none", ue, U, z], g = () => [ue, U, z], y = () => [os, "full", ...v()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [Zt],
      breakpoint: [Zt],
      color: [Uc],
      container: [Zt],
      "drop-shadow": [Zt],
      ease: ["in", "out", "in-out"],
      font: [Gp],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [Zt],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [Zt],
      shadow: [Zt],
      spacing: ["px", ue],
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
        aspect: ["auto", "square", os, z, U, D]
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
        "@container": ["", "normal", "size", U, z]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [qp],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [ue, "auto", z, U, a]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": I()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": I()
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
        object: Y()
      }],
      /**
       * Overflow
       * @see https://tailwindcss.com/docs/overflow
       */
      overflow: [{
        overflow: xe()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": xe()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": xe()
      }],
      /**
       * Overscroll Behavior
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      overscroll: [{
        overscroll: ne()
      }],
      /**
       * Overscroll Behavior X
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-x": [{
        "overscroll-x": ne()
      }],
      /**
       * Overscroll Behavior Y
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-y": [{
        "overscroll-y": ne()
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
        z: [Tt, "auto", U, z]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [os, "full", "auto", a, ...v()]
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
        flex: [ue, os, "auto", "initial", "none", z]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", ue, U, z]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", ue, U, z]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [Tt, "first", "last", "none", U, z]
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
        col: ke()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": Z()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": Z()
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
        row: ke()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": Z()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": Z()
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
        "auto-cols": ge()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": ge()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: v()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": v()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": v()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...Pe(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...ve(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...ve()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...Pe()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...ve(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...ve(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": Pe()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...ve(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...ve()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: v()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: v()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: v()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: v()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: v()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: v()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: v()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: v()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: v()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: v()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: v()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: fe()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: fe()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: fe()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: fe()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: fe()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: fe()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: fe()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: fe()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: fe()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: fe()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: fe()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": v()
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
        "space-y": v()
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
        inline: ["auto", ...he()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...he()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...he()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...ct()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...ct()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...ct()]
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
        text: ["base", s, sn, xs]
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
        font: [n, sg, Jp]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", to, z]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [Xp, Yp, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [z]
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
        tracking: [r, U, z]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [ue, "none", U, Pa]
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
          ...v()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", U, z]
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
        list: ["disc", "decimal", "none", U, z]
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
        placeholder: W()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: W()
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
        decoration: [..._(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [ue, "from-font", "auto", U, xs]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: W()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [ue, "auto", U, z]
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
        indent: v()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [Tt, U, z]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", U, z]
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
        content: ["none", U, z]
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
        bg: ut()
      }],
      /**
       * Background Repeat
       * @see https://tailwindcss.com/docs/background-repeat
       */
      "bg-repeat": [{
        bg: He()
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
          }, Tt, U, z],
          radial: ["", U, z],
          conic: ["", Tt, U, z]
        }, tg, Qp]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: W()
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
        from: W()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: W()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: W()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: Me()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": Me()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": Me()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": Me()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": Me()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": Me()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": Me()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": Me()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": Me()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": Me()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": Me()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": Me()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": Me()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": Me()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": Me()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: Ae()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": Ae()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": Ae()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": Ae()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": Ae()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": Ae()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": Ae()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": Ae()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": Ae()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": Ae()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": Ae()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": Ae()
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
        "divide-y": Ae()
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
        border: [..._(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [..._(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: W()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": W()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": W()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": W()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": W()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": W()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": W()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": W()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": W()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": W()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": W()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: W()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [..._(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [ue, U, z]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", ue, sn, xs]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: W()
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
          Un,
          Fn
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: W()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", d, Un, Fn]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": W()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: Ae()
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
        ring: W()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [ue, xs]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": W()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": Ae()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": W()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", m, Un, Fn]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": W()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [ue, U, z]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...F(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": F()
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
        "mask-linear": [ue]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": R()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": R()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": W()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": W()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": R()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": R()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": W()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": W()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": R()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": R()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": W()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": W()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": R()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": R()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": W()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": W()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": R()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": R()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": W()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": W()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": R()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": R()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": W()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": W()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": R()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": R()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": W()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": W()
      }],
      "mask-image-radial": [{
        "mask-radial": [U, z]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": R()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": R()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": W()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": W()
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
        "mask-radial-at": M()
      }],
      "mask-image-conic-pos": [{
        "mask-conic": [ue]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": R()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": R()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": W()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": W()
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
        mask: ut()
      }],
      /**
       * Mask Repeat
       * @see https://tailwindcss.com/docs/mask-repeat
       */
      "mask-repeat": [{
        mask: He()
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
        mask: ["none", U, z]
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
          U,
          z
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: Q()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [ue, U, z]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [ue, U, z]
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
          p,
          Un,
          Fn
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": W()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", ue, U, z]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [ue, U, z]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", ue, U, z]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [ue, U, z]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", ue, U, z]
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
          U,
          z
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": Q()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [ue, U, z]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [ue, U, z]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", ue, U, z]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [ue, U, z]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", ue, U, z]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [ue, U, z]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [ue, U, z]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", ue, U, z]
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
        "border-spacing": v()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": v()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": v()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", U, z]
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
        duration: [ue, "initial", U, z]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", $, U, z]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [ue, U, z]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", C, U, z]
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
        perspective: [x, U, z]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": Y()
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
        scale: h()
      }],
      /**
       * Scale X
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-x": [{
        "scale-x": h()
      }],
      /**
       * Scale Y
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-y": [{
        "scale-y": h()
      }],
      /**
       * Scale Z
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-z": [{
        "scale-z": h()
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
        skew: g()
      }],
      /**
       * Skew X
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-x": [{
        "skew-x": g()
      }],
      /**
       * Skew Y
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-y": [{
        "skew-y": g()
      }],
      /**
       * Transform
       * @see https://tailwindcss.com/docs/transform
       */
      transform: [{
        transform: [U, z, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: Y()
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
        translate: y()
      }],
      /**
       * Translate X
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-x": [{
        "translate-x": y()
      }],
      /**
       * Translate Y
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-y": [{
        "translate-y": y()
      }],
      /**
       * Translate Z
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-z": [{
        "translate-z": y()
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
        zoom: [Tt, U, z]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: W()
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
        caret: W()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", U, z]
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
        "scrollbar-thumb": W()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": W()
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
        "scroll-m": v()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": v()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": v()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": v()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": v()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": v()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": v()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": v()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": v()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": v()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": v()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": v()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": v()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": v()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": v()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": v()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": v()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": v()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": v()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": v()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": v()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": v()
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
        "will-change": ["auto", "scroll", "contents", "transform", U, z]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...W()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [ue, sn, xs, Pa]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...W()]
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
}, og = /* @__PURE__ */ Dp(rg);
function li(...e) {
  return og(jc(e));
}
const ig = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, ag = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, lg = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, cg = { class: "cmst:flex-1" }, ug = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, dg = { "data-testid": "vue-status-route" }, fg = { "data-testid": "vue-status-ops" }, mg = { "data-testid": "vue-status-density" }, hg = { class: "cmst:flex cmst:items-center cmst:gap-1" }, pg = /* @__PURE__ */ yt({
  __name: "StudioApp",
  setup(e) {
    const t = pc(), s = si(), n = Tc(), r = Pc();
    On(() => {
      n.initialize(), r.initialize();
    });
    const o = ch("(min-width: 768px)"), i = {
      playground: gc,
      history: vc,
      workflows: yc,
      backend: bc,
      settings: _c
    }, a = Ie(() => String(t.name ?? "playground"));
    function l(c) {
      const u = a.value === c;
      return li(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        u ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (c, u) => (ae(), Se("div", ig, [
      S("header", ag, [
        u[0] || (u[0] = S("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          ie(" Modal Studio "),
          S("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        S("nav", lg, [
          (ae(!0), Se(We, null, Tn(O(ti), (d) => (ae(), ft(O(mc), {
            key: d,
            to: { name: d },
            class: lt(l(d)),
            "data-testid": `vue-nav-${d}`
          }, {
            default: pe(() => [
              (ae(), ft(nd(i[d]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              ie(" " + de(O(uh)[d]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      S("main", cg, [
        J(O(hc))
      ]),
      S("footer", ug, [
        S("span", null, [
          u[1] || (u[1] = ie("route: ", -1)),
          S("strong", dg, de(a.value), 1)
        ]),
        S("span", null, [
          u[2] || (u[2] = ie(" operations: ", -1)),
          S("strong", fg, de(O(s).active.length) + " active", 1),
          ie(" / " + de(O(s).all.length) + " total ", 1)
        ]),
        S("span", null, [
          u[3] || (u[3] = ie(" density: ", -1)),
          S("strong", mg, de(O(n).density), 1)
        ]),
        S("span", hg, [
          J(O(Um), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          u[4] || (u[4] = ie(" viewport: ", -1)),
          S("strong", null, de(O(o) ? "wide" : "narrow"), 1),
          u[5] || (u[5] = ie(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), gg = "/", Jc = { page: "playground", focus: null };
function Bn(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function so(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = ps(n) ? n : Jc.page;
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
function no(e) {
  const t = kc(e.location.hash);
  return !t.matched || !ps(t.page) ? null : { page: t.page, focus: t.focus };
}
function ro(e, t, s) {
  const n = Sc(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function yg(e, t) {
  let s = dh(t, e.location.hash), n = Bn(s), r = {};
  const o = n, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = n;
    s = no(e) ?? { ...Jc }, n = Bn(s), i.forEach((m) => m(n, u));
  }, c = (u, d) => u === null && d === o;
  return {
    get base() {
      return gg;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const d = Sc(so(u));
      return d === "" ? "#" + u : d;
    },
    replace: (u, d) => {
      const m = no(e), p = so(u), w = Bn(p);
      s = p, d !== void 0 && (r = d), n = w, !c(m, w) && ua(m, p) !== "none" && ro(e, p, "replace");
    },
    push: (u, d) => {
      const m = no(e), p = so(u), w = Bn(p);
      if (s = p, d !== void 0 && (r = d), n = w, c(m, w)) return;
      const x = ua(m, p);
      x === "push" ? ro(e, p, "push") : x === "replace" && ro(e, p, "replace");
    },
    go: (u) => {
      e.history.go(u);
    },
    listen: (u) => {
      const d = (m, p) => {
        u(m, p, { type: "pop", direction: "unknown", delta: 0 });
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
const Da = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, La = jc, vg = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return La(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = s?.[c], d = o?.[c];
    if (u === null) return null;
    const m = Da(u) || Da(d);
    return r[c][m];
  }), a = s && Object.entries(s).reduce((c, u) => {
    let [d, m] = u;
    return m === void 0 || (c[d] = m), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, u) => {
    let { class: d, className: m, ...p } = u;
    return Object.entries(p).every((w) => {
      let [x, D] = w;
      return Array.isArray(D) ? D.includes({
        ...o,
        ...a
      }[x]) : {
        ...o,
        ...a
      }[x] === D;
    }) ? [
      ...c,
      d,
      m
    ] : c;
  }, []);
  return La(e, i, l, s?.class, s?.className);
}, bg = vg(
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
), _g = ["type", "disabled"], Ye = /* @__PURE__ */ yt({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (ae(), Se("button", {
      type: e.type,
      disabled: e.disabled,
      class: lt(O(bg)({ variant: e.variant, size: e.size }))
    }, [
      Al(t.$slots, "default")
    ], 10, _g));
  }
}), et = /* @__PURE__ */ yt({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (ae(), Se("div", {
      class: lt(
        O(li)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      Al(t.$slots, "default")
    ], 2));
  }
});
function Nn(e) {
  return li(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const xg = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, wg = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, kg = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Sg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, Cg = { value: "" }, Ag = ["value"], Eg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, Rg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Og = { class: "cmst:mt-1 cmst:text-sm" }, Tg = { "data-testid": "vue-deploy-state" }, Ig = {
  key: 0,
  class: "cmst:text-sm cmst:opacity-80"
}, Ng = { class: "cmst:flex cmst:gap-2" }, Pg = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, Mg = { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, jg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Dg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, Lg = /* @__PURE__ */ yt({
  __name: "BackendView",
  setup(e) {
    const t = Pc(), s = /* @__PURE__ */ te(""), n = /* @__PURE__ */ te(!1), r = Ie(() => t.models.length), o = Ie(() => t.customNodes.length);
    On(() => {
      t.workspaces.length || t.initialize();
    });
    async function i() {
      s.value && await t.selectWorkspace(s.value);
    }
    async function a() {
      await t.deploy();
    }
    return (l, c) => (ae(), Se("section", {
      class: lt(O(Nn)()),
      "data-testid": "vue-page-backend"
    }, [
      O(t).error ? (ae(), Se("div", xg, de(O(t).error), 1)) : ht("", !0),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          S("div", wg, [
            S("div", null, [
              S("h2", kg, [
                J(O(bc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[2] || (c[2] = ie(" Manage Modal ", -1))
              ]),
              c[3] || (c[3] = S("p", { class: "cmst:text-sm cmst:opacity-80" }, [
                ie("Route key remains "),
                S("code", null, "backend"),
                ie(". Workspace and readiness state come from the server.")
              ], -1))
            ]),
            J(Ye, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload infrastructure",
              disabled: O(t).loading,
              onClick: O(t).load
            }, {
              default: pe(() => [
                J(O(ei), {
                  class: lt(["cmst:size-4", O(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ])
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          c[5] || (c[5] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Workspaces", -1)),
          S("div", Sg, [
            fs(S("select", {
              "onUpdate:modelValue": c[0] || (c[0] = (u) => s.value = u),
              class: "cmst:h-9 cmst:min-w-52 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              "data-testid": "vue-workspace-select"
            }, [
              S("option", Cg, de(O(t).activeWorkspace?.label ?? "Select workspace"), 1),
              (ae(!0), Se(We, null, Tn(O(t).workspaces, (u) => (ae(), Se("option", {
                key: u.id,
                value: u.id
              }, de(u.label) + de(u.isActive ? " (active)" : ""), 9, Ag))), 128))
            ], 512), [
              [Yo, s.value]
            ]),
            J(Ye, {
              size: "sm",
              variant: "secondary",
              disabled: !s.value,
              "data-testid": "vue-workspace-activate",
              onClick: i
            }, {
              default: pe(() => [...c[4] || (c[4] = [
                ie(" Activate workspace ", -1)
              ])]),
              _: 1
            }, 8, ["disabled"])
          ]),
          S("p", Eg, "Active ID: " + de(O(t).activeWorkspaceId ?? "none"), 1)
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          S("div", Rg, [
            S("div", null, [
              c[7] || (c[7] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Deployment readiness", -1)),
              S("p", Og, [
                c[6] || (c[6] = ie("State: ", -1)),
                S("strong", Tg, de(O(t).deployStatus.state), 1)
              ]),
              O(t).deployMessage ? (ae(), Se("p", Ig, de(O(t).deployMessage), 1)) : ht("", !0)
            ]),
            S("div", Ng, [
              J(Ye, {
                size: "sm",
                disabled: O(t).loading,
                "data-testid": "vue-deploy",
                onClick: a
              }, {
                default: pe(() => [...c[8] || (c[8] = [
                  ie("Deploy / redeploy", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              J(Ye, {
                size: "sm",
                variant: "outline",
                onClick: c[1] || (c[1] = (u) => n.value = !n.value)
              }, {
                default: pe(() => [
                  ie(de(n.value ? "Hide" : "Show") + " log", 1)
                ]),
                _: 1
              })
            ])
          ]),
          n.value ? (ae(), Se("pre", Pg, de(O(t).deployLog ?? "Loading…"), 1)) : ht("", !0),
          n.value && !O(t).deployLog ? (ae(), ft(Ye, {
            key: 1,
            class: "cmst:mt-2",
            size: "sm",
            variant: "ghost",
            onClick: O(t).loadLog
          }, {
            default: pe(() => [...c[9] || (c[9] = [
              ie("Load deployment log", -1)
            ])]),
            _: 1
          }, 8, ["onClick"])) : ht("", !0)
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          c[13] || (c[13] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared inventory", -1)),
          S("p", Mg, "Models: " + de(r.value) + " · Custom nodes: " + de(o.value), 1),
          S("div", jg, [
            J(Ye, {
              size: "sm",
              variant: "outline",
              onClick: O(t).refreshRemoteInventoryNow
            }, {
              default: pe(() => [...c[10] || (c[10] = [
                ie("Refresh remote inventory", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            J(Ye, {
              size: "sm",
              variant: "outline",
              onClick: O(t).rescanModelsNow
            }, {
              default: pe(() => [...c[11] || (c[11] = [
                ie("Rescan models", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            J(Ye, {
              size: "sm",
              variant: "outline",
              onClick: O(t).refreshCustomNodesNow
            }, {
              default: pe(() => [...c[12] || (c[12] = [
                ie("Refresh custom nodes", -1)
              ])]),
              _: 1
            }, 8, ["onClick"])
          ]),
          S("p", Dg, de(O(t).syncSummary ?? "Not loaded"), 1)
        ]),
        _: 1
      })
    ], 2));
  }
});
function Je(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function $g(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = Je(s, "asset_id", "assetId"), r = (o) => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}?variant=${o}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: Je(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: Je(s, "logical_key", "logicalKey"),
    thumbUrl: Je(s, "thumb_url", "thumbnail_url") || r("thumbnail"),
    previewUrl: Je(s, "preview_url", "data_saver_url") || r("data_saver"),
    originalUrl: Je(s, "original_url") || r("original"),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: Je(s, "filename", "name")
  };
}
function $a(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((r, o) => $g(r, o));
  return {
    id: Je(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: Je(t, "status", "outcome") || "unknown",
    workflow: Je(t, "workflow", "workflow_name"),
    workflowVersion: Je(t, "workflow_version", "workflowVersion", "version_id"),
    preset: Je(t, "preset", "preset_name"),
    prompt: Je(t, "prompt", "positive_prompt"),
    startedAt: Je(t, "started_at", "created_at") || null,
    completedAt: Je(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: Je(t, "note"),
    outputs: n,
    featuredOutput: n[0] ?? null,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    raw: t
  };
}
async function Vg(e = {}) {
  const t = new URLSearchParams();
  for (const [s, n] of Object.entries({ limit: 24, ...e }))
    n !== void 0 && String(n) !== "" && t.set(s, String(n));
  return ze(`/history-v2/feed?${t}`);
}
async function zg(e) {
  return ze(`/history-v2/generations/${encodeURIComponent(e)}`);
}
async function Fg(e) {
  return ze(`/history-v2/experiments/${encodeURIComponent(e)}`);
}
async function Ug(e, t) {
  return ze(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function Bg(e, t) {
  return ze(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function Wg(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return ze(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const Ms = Rc("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1 }), Hg = /* @__PURE__ */ Js("studio-history", () => {
  const e = /* @__PURE__ */ te([]), t = /* @__PURE__ */ te(null), s = /* @__PURE__ */ te(null), n = /* @__PURE__ */ te(Ms.read().query), r = /* @__PURE__ */ te(Ms.read().sort), o = /* @__PURE__ */ te(Ms.read().favoriteOnly), i = /* @__PURE__ */ te(null), a = /* @__PURE__ */ te(!1), l = /* @__PURE__ */ te(!1), c = /* @__PURE__ */ te(null), u = To(), d = To();
  let m = null;
  function p(v) {
    s.value = v, t.value = e.value.find((V) => V.id === v) ?? t.value;
  }
  function w(v) {
    n.value = v, Ms.write({ query: v, sort: r.value, favoriteOnly: o.value });
  }
  function x(v) {
    r.value = v, Ms.write({ query: n.value, sort: v, favoriteOnly: o.value });
  }
  function D(v) {
    o.value = v, Ms.write({ query: n.value, sort: r.value, favoriteOnly: v });
  }
  async function $(v = !1) {
    l.value = !0, c.value = null;
    const V = await u.run(async (Z) => {
      const ge = await Vg({ search: n.value, sort: r.value, favorite_only: o.value, cursor: v ? i.value ?? void 0 : void 0 });
      return Z.aborted ? null : ge;
    });
    if (V.stale || !V.value) return;
    const ce = V.value, ke = (ce.items ?? ce.records ?? []).map($a);
    e.value = v ? e.value.concat(ke) : ke, i.value = ce.next_cursor ?? null, a.value = ce.has_more === !0 || !!i.value, l.value = !1;
  }
  async function C(v, V = "generation") {
    const ce = await d.run(async (ge) => {
      const Pe = V === "experiment" ? await Fg(v) : await zg(v);
      return ge.aborted ? null : Pe;
    });
    if (ce.stale || !ce.value) return;
    const ke = $a(ce.value);
    t.value = ke;
    const Z = e.value.findIndex((ge) => ge.id === ke.id);
    Z >= 0 && (e.value[Z] = ke);
  }
  async function I(v, V) {
    await Ug(v.id, V), v.favorite = V, Rs("history");
  }
  async function M(v, V) {
    await Bg(v.id, V), v.note = V, Rs("history");
  }
  async function Y(v) {
    await Wg(v), e.value = e.value.filter((V) => V.id !== v.id), t.value?.id === v.id && (t.value = null), Rs("history");
  }
  async function xe() {
    m || (m = oi((v) => {
      v === "history" && $();
    })), e.value.length || await $();
  }
  function ne() {
    e.value = [], t.value = null, s.value = null, i.value = null;
  }
  return { records: e, selected: t, focusId: s, query: n, sort: r, favoriteOnly: o, cursor: i, hasMore: a, loading: l, error: c, setFocus: p, setQuery: w, setSort: x, setFavoriteOnly: D, loadFeed: $, loadDetail: C, setFavorite: I, setNote: M, remove: Y, initialize: xe, clear: ne };
}), Zg = ["src", "alt"], Gg = { class: "cmst:p-3 cmst:text-sm" }, qg = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, Kg = { class: "cmst:truncate" }, Jg = { class: "cmst:text-xs cmst:opacity-70" }, Yg = { class: "cmst:mt-1 cmst:truncate cmst:text-xs cmst:opacity-70" }, Qg = /* @__PURE__ */ yt({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (ae(), ft(et, {
      class: "cmst:overflow-hidden cmst:cursor-pointer",
      onClick: r[0] || (r[0] = (o) => s("select", e.record))
    }, {
      default: pe(() => [
        e.record.featuredOutput ? (ae(), Se("img", {
          key: 0,
          src: e.record.featuredOutput.thumbUrl,
          alt: e.record.workflow || e.record.id,
          class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
          loading: "lazy"
        }, null, 8, Zg)) : ht("", !0),
        S("div", Gg, [
          S("div", qg, [
            S("strong", Kg, de(e.record.workflow || e.record.id), 1),
            S("span", Jg, de(e.record.status), 1)
          ]),
          S("p", Yg, de(e.record.id), 1)
        ])
      ]),
      _: 1
    }));
  }
}), Xg = {
  class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2 cmst:lg:grid-cols-3",
  "data-testid": "vue-history-grid"
}, ey = /* @__PURE__ */ yt({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (ae(), Se("div", Xg, [
      (ae(!0), Se(We, null, Tn(e.records, (o) => (ae(), ft(Qg, {
        key: `${o.kind}:${o.id}`,
        record: o,
        onSelect: r[0] || (r[0] = (i) => s("select", i))
      }, null, 8, ["record"]))), 128))
    ]));
  }
}), ty = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, sy = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, ny = { class: "cmst:text-lg cmst:font-semibold" }, ry = { class: "cmst:text-xs cmst:opacity-70" }, oy = ["src", "alt"], iy = {
  key: 1,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, ay = /* @__PURE__ */ yt({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => e.record ? (ae(), Se("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-testid": "vue-history-viewer",
      onClick: r[1] || (r[1] = vf((o) => s("close"), ["self"]))
    }, [
      S("div", ty, [
        S("div", sy, [
          S("div", null, [
            S("h2", ny, de(e.record.workflow || e.record.id), 1),
            S("p", ry, de(e.record.status) + " · " + de(e.record.kind), 1)
          ]),
          J(Ye, {
            variant: "outline",
            size: "sm",
            onClick: r[0] || (r[0] = (o) => s("close"))
          }, {
            default: pe(() => [...r[2] || (r[2] = [
              ie("Close", -1)
            ])]),
            _: 1
          })
        ]),
        e.record.featuredOutput ? (ae(), Se("img", {
          key: 0,
          src: e.record.featuredOutput.previewUrl,
          alt: e.record.workflow || e.record.id,
          class: "cmst:mt-4 cmst:mx-auto cmst:max-h-[70vh] cmst:max-w-full cmst:object-contain"
        }, null, 8, oy)) : (ae(), Se("p", iy, "No projected image asset."))
      ])
    ])) : ht("", !0);
  }
}), ly = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, cy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, uy = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, dy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, fy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, my = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, hy = /* @__PURE__ */ yt({
  __name: "HistoryView",
  setup(e) {
    const t = Hg(), s = pc(), n = Nm(), r = /* @__PURE__ */ te(t.query), o = /* @__PURE__ */ te(!1);
    On(async () => {
      await t.initialize();
      const l = typeof s.query.focus == "string" ? s.query.focus : null;
      l && (t.setFocus(l), await t.loadDetail(l));
    });
    let i;
    As(r, (l) => {
      window.clearTimeout(i), i = window.setTimeout(() => {
        t.setQuery(l), t.loadFeed();
      }, 250);
    });
    async function a(l) {
      t.setFocus(l.id), await n.replace({ name: "history", query: { focus: l.id } }), await t.loadDetail(l.id, l.kind), o.value = !0;
    }
    return (l, c) => (ae(), Se("section", {
      class: lt(O(Nn)()),
      "data-testid": "vue-page-history"
    }, [
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          S("div", ly, [
            S("div", null, [
              S("h2", cy, [
                J(O(vc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[8] || (c[8] = ie("History V2", -1))
              ]),
              c[9] || (c[9] = S("p", { class: "cmst:text-sm cmst:opacity-80" }, "History V2 is the Vue production data source; the server cursor remains authoritative.", -1))
            ]),
            J(Ye, {
              variant: "outline",
              size: "icon",
              "aria-label": "Refresh history",
              disabled: O(t).loading,
              onClick: c[0] || (c[0] = (u) => O(t).loadFeed())
            }, {
              default: pe(() => [
                J(O(ei), {
                  class: lt(["cmst:size-4", O(t).loading ? "cmst:animate-spin" : ""])
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          S("div", uy, [
            S("label", dy, [
              J(O(qm), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              }),
              fs(S("input", {
                "onUpdate:modelValue": c[1] || (c[1] = (u) => r.value = u),
                class: "cmst:h-9 cmst:w-64 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search history",
                "data-testid": "vue-history-search"
              }, null, 512), [
                [nr, r.value]
              ])
            ]),
            fs(S("select", {
              "onUpdate:modelValue": c[2] || (c[2] = (u) => O(t).sort = u),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              onChange: c[3] || (c[3] = (u) => {
                O(t).setSort(O(t).sort), O(t).loadFeed();
              })
            }, [...c[10] || (c[10] = [
              S("option", { value: "newest" }, "Newest", -1),
              S("option", { value: "oldest" }, "Oldest", -1),
              S("option", { value: "fastest" }, "Fastest", -1),
              S("option", { value: "slowest" }, "Slowest", -1)
            ])], 544), [
              [Yo, O(t).sort]
            ]),
            S("label", fy, [
              fs(S("input", {
                "onUpdate:modelValue": c[4] || (c[4] = (u) => O(t).favoriteOnly = u),
                type: "checkbox",
                onChange: c[5] || (c[5] = (u) => {
                  O(t).setFavoriteOnly(O(t).favoriteOnly), O(t).loadFeed();
                })
              }, null, 544), [
                [hf, O(t).favoriteOnly]
              ]),
              c[11] || (c[11] = ie(" Favorites", -1))
            ])
          ])
        ]),
        _: 1
      }),
      O(t).error ? (ae(), Se("div", my, de(O(t).error), 1)) : ht("", !0),
      O(t).loading && !O(t).records.length ? (ae(), ft(et, {
        key: 1,
        class: "cmst:p-6 cmst:text-sm"
      }, {
        default: pe(() => [...c[12] || (c[12] = [
          ie("Loading History V2…", -1)
        ])]),
        _: 1
      })) : O(t).records.length ? (ae(), ft(ey, {
        key: 3,
        records: O(t).records,
        onSelect: a
      }, null, 8, ["records"])) : (ae(), ft(et, {
        key: 2,
        class: "cmst:p-6 cmst:text-sm cmst:opacity-75"
      }, {
        default: pe(() => [...c[13] || (c[13] = [
          ie("No History V2 records match this query.", -1)
        ])]),
        _: 1
      })),
      O(t).hasMore ? (ae(), ft(Ye, {
        key: 4,
        variant: "outline",
        class: "cmst:self-center",
        onClick: c[6] || (c[6] = (u) => O(t).loadFeed(!0))
      }, {
        default: pe(() => [...c[14] || (c[14] = [
          ie("Load more", -1)
        ])]),
        _: 1
      })) : ht("", !0),
      o.value ? (ae(), ft(ay, {
        key: 5,
        record: O(t).selected,
        onClose: c[7] || (c[7] = (u) => o.value = !1)
      }, null, 8, ["record"])) : ht("", !0)
    ], 2));
  }
}), py = /* @__PURE__ */ Js("studio-playground", () => {
  const e = /* @__PURE__ */ te("txt2img"), t = /* @__PURE__ */ te(!1);
  function s(r) {
    e.value = r;
  }
  function n(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: s, setExperimentMode: n };
}), gy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, yy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, vy = ["checked"], by = { class: "cmst:text-sm cmst:opacity-80" }, _y = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, xy = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, wy = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, ky = { key: 0 }, Sy = /* @__PURE__ */ yt({
  __name: "PlaygroundView",
  setup(e) {
    const t = py(), s = si(), n = /* @__PURE__ */ te(null), r = Ie(() => n.value ? s.get(n.value)?.progress ?? null : null);
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
    return (i, a) => (ae(), Se("section", {
      class: lt(O(Nn)()),
      "data-testid": "vue-page-playground"
    }, [
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          S("h2", gy, [
            J(O(gc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = ie(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = S("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          S("label", yy, [
            S("input", {
              type: "checkbox",
              checked: O(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => O(t).setExperimentMode(l.target.checked))
            }, null, 40, vy),
            a[2] || (a[2] = ie(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          a[5] || (a[5] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          S("p", by, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + de(O(s).active.length) + ". ", 1),
          S("div", _y, [
            J(Ye, {
              variant: "default",
              size: "sm",
              disabled: n.value !== null,
              onClick: o
            }, {
              default: pe(() => [
                J(O(Wm), { "aria-hidden": "true" }),
                a[4] || (a[4] = ie(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? (ae(), Se("span", xy, de(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : ht("", !0)
          ]),
          S("ul", wy, [
            (ae(!0), Se(We, null, Tn(O(s).all.slice(-5), (l) => (ae(), Se("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              S("strong", null, de(l.label), 1),
              ie(" — " + de(l.status), 1),
              l.message ? (ae(), Se("span", ky, " — " + de(l.message), 1)) : ht("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), Cy = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Ay = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, Ey = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Ry = { class: "cmst:mt-3 cmst:text-sm" }, Oy = { key: 0 }, Ty = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Iy = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Ny = ["value"], Py = ["value"], My = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, jy = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Dy = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Ly = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, $y = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-3" }, Vy = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, zy = ["checked"], Fy = /* @__PURE__ */ yt({
  __name: "SettingsView",
  setup(e) {
    const t = Tc(), s = /* @__PURE__ */ te(75), n = /* @__PURE__ */ te(""), r = /* @__PURE__ */ te("off"), o = Ie(() => t.config), i = Ie(() => o.value?.available_gpus ?? []);
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
    return (d, m) => (ae(), Se("section", {
      class: lt(O(Nn)()),
      "data-testid": "vue-page-settings"
    }, [
      O(t).error ? (ae(), Se("div", Cy, de(O(t).error), 1)) : ht("", !0),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          S("div", Ay, [
            S("div", null, [
              S("h2", Ey, [
                J(O(_c), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                m[3] || (m[3] = ie(" Settings ", -1))
              ]),
              m[4] || (m[4] = S("p", { class: "cmst:text-sm cmst:opacity-80" }, " Server-backed Settings authority. Vue reads `/config` and projects proven output values one-way to legacy canvas consumers. ", -1))
            ]),
            J(Ye, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload settings",
              disabled: O(t).loading,
              onClick: O(t).load
            }, {
              default: pe(() => [
                J(O(ei), {
                  class: lt(["cmst:size-4", O(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ]),
          S("p", Ry, [
            m[5] || (m[5] = ie(" Active section: ", -1)),
            S("strong", null, de(O(t).activeSection), 1),
            O(t).config ? (ae(), Se("span", Oy, " · server config loaded")) : ht("", !0)
          ])
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          m[9] || (m[9] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Generation", -1)),
          S("div", Ty, [
            S("label", Iy, [
              m[6] || (m[6] = ie(" GPU ", -1)),
              S("select", {
                value: o.value?.gpu ?? "",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-settings-gpu",
                onChange: l
              }, [
                (ae(!0), Se(We, null, Tn(i.value, (p) => (ae(), Se("option", {
                  key: p.value,
                  value: p.value
                }, de(p.label), 9, Py))), 128))
              ], 40, Ny)
            ]),
            S("label", My, [
              m[8] || (m[8] = ie(" Profile/tracing level ", -1)),
              fs(S("select", {
                "onUpdate:modelValue": m[0] || (m[0] = (p) => r.value = p),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: u
              }, [...m[7] || (m[7] = [
                S("option", { value: "off" }, "Off", -1),
                S("option", { value: "summary" }, "Summary", -1),
                S("option", { value: "detailed" }, "Detailed", -1),
                S("option", { value: "trace" }, "Trace", -1),
                S("option", { value: "trace_verbose" }, "Trace verbose", -1)
              ])], 544), [
                [Yo, r.value]
              ])
            ])
          ])
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          m[13] || (m[13] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Outputs / Data Saver", -1)),
          S("div", jy, [
            S("label", Dy, [
              m[10] || (m[10] = ie(" Quality ", -1)),
              fs(S("input", {
                "onUpdate:modelValue": m[1] || (m[1] = (p) => s.value = p),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [
                  nr,
                  s.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            S("label", Ly, [
              m[11] || (m[11] = ie(" Save folder ", -1)),
              fs(S("input", {
                "onUpdate:modelValue": m[2] || (m[2] = (p) => n.value = p),
                type: "text",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [nr, n.value]
              ])
            ])
          ]),
          S("div", $y, [
            J(Ye, {
              size: "sm",
              disabled: O(t).saving,
              "data-testid": "vue-settings-save-output",
              onClick: a
            }, {
              default: pe(() => [
                ie(de(O(t).saving ? "Saving…" : "Save output settings"), 1)
              ]),
              _: 1
            }, 8, ["disabled"]),
            m[12] || (m[12] = S("span", { class: "cmst:text-xs cmst:opacity-70" }, "Server truth is reread after every save.", -1))
          ])
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          m[15] || (m[15] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Advanced", -1)),
          S("label", Vy, [
            S("input", {
              type: "checkbox",
              checked: o.value?.skip_plan_validation ?? !1,
              onChange: c
            }, null, 40, zy),
            m[14] || (m[14] = ie(" Skip plan validation (preserves current backend semantics) ", -1))
          ]),
          m[16] || (m[16] = S("p", { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, "Execution mode remains server-owned and V2-only.", -1))
        ]),
        _: 1
      })
    ], 2));
  }
}), Uy = /* @__PURE__ */ Js("studio-workflows", () => {
  const e = /* @__PURE__ */ te(null);
  function t(n) {
    e.value = n;
  }
  function s() {
    e.value = null;
  }
  return { selectedId: e, select: t, clear: s };
}), By = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Wy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, Hy = { class: "cmst:text-sm cmst:mt-2" }, Zy = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, Gy = {
  class: "cmst:text-sm",
  "data-testid": "vue-poll-status"
}, qy = /* @__PURE__ */ yt({
  __name: "WorkflowsView",
  setup(e) {
    const t = Uy(), s = /* @__PURE__ */ te(""), n = /* @__PURE__ */ te("idle"), r = /* @__PURE__ */ te(0);
    async function o() {
      n.value = "polling…", r.value = 0;
      let i = 0;
      const a = await Nc({
        intervalMs: 120,
        run: async (l, c) => (r.value = c, i += 1, i >= 3 ? "ready" : "warming"),
        done: (l) => l === "ready"
      });
      n.value = a;
    }
    return (i, a) => (ae(), Se("section", {
      class: lt(O(Nn)()),
      "data-testid": "vue-page-workflows"
    }, [
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          S("h2", By, [
            J(O(yc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[2] || (a[2] = ie(" Workflows (Phase-1 proof) ", -1))
          ]),
          a[5] || (a[5] = S("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Selection identity lives in the workflows store. ", -1)),
          S("div", Wy, [
            fs(S("input", {
              "onUpdate:modelValue": a[0] || (a[0] = (l) => s.value = l),
              type: "text",
              placeholder: "Workflow id",
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm"
            }, null, 512), [
              [nr, s.value]
            ]),
            J(Ye, {
              variant: "secondary",
              size: "sm",
              onClick: a[1] || (a[1] = (l) => O(t).select(s.value.trim() || null))
            }, {
              default: pe(() => [...a[3] || (a[3] = [
                ie(" Select ", -1)
              ])]),
              _: 1
            })
          ]),
          S("p", Hy, [
            a[4] || (a[4] = ie(" Store selection: ", -1)),
            S("strong", null, de(O(t).selectedId ?? "none"), 1)
          ])
        ]),
        _: 1
      }),
      J(et, { class: "cmst:p-4" }, {
        default: pe(() => [
          a[7] || (a[7] = S("h3", { class: "cmst:text-sm cmst:font-semibold" }, "polling demo (local only)", -1)),
          a[8] || (a[8] = S("p", { class: "cmst:text-sm cmst:opacity-80" }, " Repeats a local status check until the completion predicate holds. ", -1)),
          S("div", Zy, [
            J(Ye, {
              variant: "outline",
              size: "sm",
              "data-testid": "vue-poll-run",
              onClick: o
            }, {
              default: pe(() => [...a[6] || (a[6] = [
                ie(" Start local poll ", -1)
              ])]),
              _: 1
            }),
            S("span", Gy, de(n.value) + " (" + de(r.value) + " attempts) ", 1)
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), Ky = {
  playground: Sy,
  history: hy,
  workflows: qy,
  backend: Lg,
  settings: Fy
};
function Jy(e = {}) {
  let t;
  return e.memory || !e.win ? t = dm() : t = yg(e.win, e.initial), Im({
    history: t,
    routes: ti.map((n) => ({
      path: `/${n}`,
      name: n,
      component: Ky[n]
    }))
  });
}
function Yy(e, t = {}) {
  const s = Sf(), n = Jy({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = xf(pg);
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
  Yy as mountStudioPreview
};

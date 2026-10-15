/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function Oo(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const Ee = {}, vs = [], It = () => {
}, Ta = () => !1, ar = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), lr = (e) => e.startsWith("onUpdate:"), qe = Object.assign, To = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, Bc = Object.prototype.hasOwnProperty, ye = (e, t) => Bc.call(e, t), q = Array.isArray, rs = (e) => xn(e) === "[object Map]", ks = (e) => xn(e) === "[object Set]", oi = (e) => xn(e) === "[object Date]", ne = (e) => typeof e == "function", Ne = (e) => typeof e == "string", ft = (e) => typeof e == "symbol", xe = (e) => e !== null && typeof e == "object", Ia = (e) => (xe(e) || ne(e)) && ne(e.then) && ne(e.catch), Na = Object.prototype.toString, xn = (e) => Na.call(e), Wc = (e) => xn(e).slice(8, -1), Pa = (e) => xn(e) === "[object Object]", cr = (e) => Ne(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, sn = /* @__PURE__ */ Oo(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), ur = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, Hc = /-\w/g, et = ur(
  (e) => e.replace(Hc, (t) => t.slice(1).toUpperCase())
), Zc = /\B([A-Z])/g, Cs = ur(
  (e) => e.replace(Zc, "-$1").toLowerCase()
), dr = ur((e) => e.charAt(0).toUpperCase() + e.slice(1)), Rr = ur(
  (e) => e ? `on${dr(e)}` : ""
), Tt = (e, t) => !Object.is(e, t), Dn = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Ma = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, fr = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let ii;
const hr = () => ii || (ii = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Io(e) {
  if (q(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = Ne(n) ? Jc(n) : Io(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (Ne(e) || xe(e))
    return e;
}
const Gc = /;(?![^(]*\))/g, qc = /:([^]+)/, Kc = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function Jc(e) {
  const t = {};
  return e.replace(Kc, (s) => s.startsWith("/*") ? "" : s).split(Gc).forEach((s) => {
    if (s) {
      const n = s.split(qc);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function ht(e) {
  let t = "";
  if (Ne(e))
    t = e;
  else if (q(e))
    for (let s = 0; s < e.length; s++) {
      const n = ht(e[s]);
      n && (t += n + " ");
    }
  else if (xe(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const Yc = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", Qc = /* @__PURE__ */ Oo(Yc);
function ja(e) {
  return !!e || e === "";
}
function Xc(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = is(e[r], t[r], s);
  return n;
}
function ai(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < n.length; a++)
      if (!r[a] && is(o, n[a], s)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function eu(e, t, s) {
  let n = rs(e), r = rs(t);
  if (n || r || (n = ks(e), r = ks(t), n || r))
    return n && r ? ai(e, t, s) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !is(e[a], t[a], s))
      return !1;
  }
  return String(e) === String(t);
}
function li(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = n(e, t, s);
  return r.delete(e), o.delete(t), i;
}
function is(e, t, s) {
  if (e === t) return !0;
  let n = oi(e), r = oi(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = ft(e), r = ft(t), n || r ? e === t : (n = q(e), r = q(t), n || r ? n && r ? li(e, t, s, Xc) : !1 : (n = xe(e), r = xe(t), n || r ? !n || !r ? !1 : li(e, t, s, eu) : String(e) === String(t))));
}
function tu(e, t) {
  return e.findIndex((s) => is(s, t));
}
const La = (e) => !!(e && e.__v_isRef === !0), fe = (e) => Ne(e) ? e : e == null ? "" : q(e) || xe(e) && (e.toString === Na || !ne(e.toString)) ? La(e) ? fe(e.value) : JSON.stringify(e, Da, 2) : String(e), Da = (e, t) => La(t) ? Da(e, t.value) : rs(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[Or(n, o) + " =>"] = r, s),
    {}
  )
} : ks(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => Or(s))
} : ft(t) ? Or(t) : xe(t) && !q(t) && !Pa(t) ? String(t) : t, Or = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    ft(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Ue;
class Va {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && Ue && (Ue.active ? (this.parent = Ue, this.index = (Ue.scopes || (Ue.scopes = [])).push(
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
      const s = Ue;
      try {
        return Ue = this, t();
      } finally {
        Ue = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = Ue, Ue = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (Ue === this)
        Ue = this.prevScope;
      else {
        let t = Ue;
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
function za(e) {
  return new Va(e);
}
function No() {
  return Ue;
}
function $a(e, t = !1) {
  Ue && Ue.cleanups.push(e);
}
let Re;
const Tr = /* @__PURE__ */ new WeakSet();
class Fa {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, Ue && (Ue.active ? Ue.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, Tr.has(this) && (Tr.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || Ba(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, ci(this), Wa(this);
    const t = Re, s = bt;
    Re = this, bt = !0;
    try {
      return this.fn();
    } finally {
      Ha(this), Re = t, bt = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        jo(t);
      this.deps = this.depsTail = void 0, ci(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? Tr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    no(this) && this.run();
  }
  get dirty() {
    return no(this);
  }
}
let Ua = 0, nn, rn;
function Ba(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = rn, rn = e;
    return;
  }
  e.next = nn, nn = e;
}
function Po() {
  Ua++;
}
function Mo() {
  if (--Ua > 0)
    return;
  if (rn) {
    let t = rn;
    for (rn = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; nn; ) {
    let t = nn;
    for (nn = void 0; t; ) {
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
function Wa(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function Ha(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), jo(n), su(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function no(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (Za(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function Za(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === dn) || (e.globalVersion = dn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !no(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = Re, n = bt;
  Re = e, bt = !0;
  try {
    Wa(e);
    const r = e.fn(e._value);
    (t.version === 0 || Tt(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Re = s, bt = n, Ha(e), e.flags &= -3;
  }
}
function jo(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      jo(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function su(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let bt = !0;
const Ga = [];
function Mt() {
  Ga.push(bt), bt = !1;
}
function jt() {
  const e = Ga.pop();
  bt = e === void 0 ? !0 : e;
}
function ci(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = Re;
    Re = void 0;
    try {
      t();
    } finally {
      Re = s;
    }
  }
}
let dn = 0;
class nu {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Lo {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!Re || !bt || Re === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== Re)
      s = this.activeLink = new nu(Re, this), Re.deps ? (s.prevDep = Re.depsTail, Re.depsTail.nextDep = s, Re.depsTail = s) : Re.deps = Re.depsTail = s, qa(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = Re.depsTail, s.nextDep = void 0, Re.depsTail.nextDep = s, Re.depsTail = s, Re.deps === s && (Re.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, dn++, this.notify(t);
  }
  notify(t) {
    Po();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      Mo();
    }
  }
}
function qa(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        qa(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const $n = /* @__PURE__ */ new WeakMap(), xs = /* @__PURE__ */ Symbol(
  ""
), ro = /* @__PURE__ */ Symbol(
  ""
), fn = /* @__PURE__ */ Symbol(
  ""
);
function Ke(e, t, s) {
  if (bt && Re) {
    let n = $n.get(e);
    n || $n.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new Lo()), r.map = n, r.key = s), r.track();
  }
}
function Ht(e, t, s, n, r, o) {
  const i = $n.get(e);
  if (!i) {
    dn++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (Po(), t === "clear")
    i.forEach(a);
  else {
    const l = q(e), c = l && cr(s);
    if (l && s === "length") {
      const u = Number(n);
      i.forEach((d, h) => {
        (h === "length" || h === fn || !ft(h) && h >= u) && a(d);
      });
    } else
      switch ((s !== void 0 || i.has(void 0)) && a(i.get(s)), c && a(i.get(fn)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(xs)), rs(e) && a(i.get(ro)));
          break;
        case "delete":
          l || (a(i.get(xs)), rs(e) && a(i.get(ro)));
          break;
        case "set":
          rs(e) && a(i.get(xs));
          break;
      }
  }
  Mo();
}
function ru(e, t) {
  const s = $n.get(e);
  return s && s.get(t);
}
function Es(e) {
  const t = /* @__PURE__ */ pe(e);
  return t === e || (Ke(t, "iterate", fn), /* @__PURE__ */ dt(e)) ? t : /* @__PURE__ */ Lt(e) ? /* @__PURE__ */ Nt(e) ? t.map((s) => as(mt(s))) : t.map(as) : t.map(mt);
}
function mr(e) {
  return Ke(e = /* @__PURE__ */ pe(e), "iterate", fn), e;
}
function Et(e, t) {
  return /* @__PURE__ */ Lt(e) ? as(/* @__PURE__ */ Nt(e) ? mt(t) : t) : mt(t);
}
const ou = {
  __proto__: null,
  [Symbol.iterator]() {
    return Ir(this, Symbol.iterator, (e) => Et(this, e));
  },
  concat(...e) {
    return Es(this).concat(
      ...e.map((t) => q(t) ? Es(t) : t)
    );
  },
  entries() {
    return Ir(this, "entries", (e) => (e[1] = Et(this, e[1]), e));
  },
  every(e, t) {
    return $t(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return $t(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => Et(this, n)),
      arguments
    );
  },
  find(e, t) {
    return $t(
      this,
      "find",
      e,
      t,
      (s) => Et(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return $t(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return $t(
      this,
      "findLast",
      e,
      t,
      (s) => Et(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return $t(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return $t(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return Nr(this, "includes", e);
  },
  indexOf(...e) {
    return Nr(this, "indexOf", e);
  },
  join(e) {
    return Es(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return Nr(this, "lastIndexOf", e);
  },
  map(e, t) {
    return $t(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return qs(this, "pop");
  },
  push(...e) {
    return qs(this, "push", e);
  },
  reduce(e, ...t) {
    return di(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return di(this, "reduceRight", e, t);
  },
  shift() {
    return qs(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return $t(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return qs(this, "splice", e);
  },
  toReversed() {
    return Es(this).toReversed();
  },
  toSorted(e) {
    return Es(this).toSorted(e);
  },
  toSpliced(...e) {
    return Es(this).toSpliced(...e);
  },
  unshift(...e) {
    return qs(this, "unshift", e);
  },
  values() {
    return Ir(this, "values", (e) => Et(this, e));
  }
};
function Ir(e, t, s) {
  const n = mr(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ dt(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => ui(o.next(), s), r !== Ka[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => ui(o._next(), s);
  }
  return o;
}
function ui(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const Ka = Array.prototype;
function $t(e, t, s, n, r, o) {
  const i = mr(e), a = i !== e && !/* @__PURE__ */ dt(e), l = i[t];
  if (l !== Ka[t]) {
    const d = l.apply(e, o);
    return a ? mt(d) : d;
  }
  let c = s;
  i !== e && (a ? c = function(d, h) {
    return s.call(this, Et(e, d), h, e);
  } : s.length > 2 && (c = function(d, h) {
    return s.call(this, d, h, e);
  }));
  const u = l.call(i, c, n);
  return a && r ? r(u) : u;
}
function di(e, t, s, n) {
  const r = mr(e), o = r !== e && !/* @__PURE__ */ dt(e);
  let i = s, a = !1;
  r !== e && (o ? (a = n.length === 0, i = function(c, u, d) {
    return a && (a = !1, c = Et(e, c)), s.call(this, c, Et(e, u), d, e);
  }) : s.length > 3 && (i = function(c, u, d) {
    return s.call(this, c, u, d, e);
  }));
  const l = r[t](i, ...n);
  return a ? Et(e, l) : l;
}
function Nr(e, t, s) {
  const n = /* @__PURE__ */ pe(e);
  Ke(n, "iterate", fn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ pr(s[0]) ? (s[0] = /* @__PURE__ */ pe(s[0]), n[t](...s)) : r;
}
function qs(e, t, s = []) {
  Mt(), Po();
  const n = (/* @__PURE__ */ pe(e))[t].apply(e, s);
  return Mo(), jt(), n;
}
const iu = /* @__PURE__ */ Oo("__proto__,__v_isRef,__isVue"), Ja = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(ft)
);
function au(e) {
  ft(e) || (e = String(e));
  const t = /* @__PURE__ */ pe(this);
  return Ke(t, "has", e), t.hasOwnProperty(e);
}
class Ya {
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
      return n === (r ? o ? yu : tl : o ? el : Xa).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const i = q(t);
    if (!r) {
      let l;
      if (i && (l = ou[s]))
        return l;
      if (s === "hasOwnProperty")
        return au;
    }
    const a = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ De(t) ? t : n
    );
    if ((ft(s) ? Ja.has(s) : iu(s)) || (r || Ke(t, "get", s), o))
      return a;
    if (/* @__PURE__ */ De(a)) {
      const l = i && cr(s) ? a : a.value;
      return r && xe(l) ? /* @__PURE__ */ io(l) : l;
    }
    return xe(a) ? r ? /* @__PURE__ */ io(a) : /* @__PURE__ */ wn(a) : a;
  }
}
class Qa extends Ya {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const i = q(t) && cr(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ Lt(o);
      if (!/* @__PURE__ */ dt(n) && !/* @__PURE__ */ Lt(n) && (o = /* @__PURE__ */ pe(o), n = /* @__PURE__ */ pe(n)), !i && /* @__PURE__ */ De(o) && !/* @__PURE__ */ De(n))
        return c || (o.value = n), !0;
    }
    const a = i ? Number(s) < t.length : ye(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ De(t) ? t : r
    );
    return t === /* @__PURE__ */ pe(r) && l && (a ? Tt(n, o) && Ht(t, "set", s, n) : Ht(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = ye(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && Ht(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!ft(s) || !Ja.has(s)) && Ke(t, "has", s), n;
  }
  ownKeys(t) {
    return Ke(
      t,
      "iterate",
      q(t) ? "length" : xs
    ), Reflect.ownKeys(t);
  }
}
class lu extends Ya {
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
const cu = /* @__PURE__ */ new Qa(), uu = /* @__PURE__ */ new lu(), du = /* @__PURE__ */ new Qa(!0);
const oo = (e) => e, An = (e) => Reflect.getPrototypeOf(e);
function fu(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ pe(r), i = rs(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...n), u = s ? oo : t ? as : mt;
    return !t && Ke(
      o,
      "iterate",
      l ? ro : xs
    ), qe(
      // inheriting all iterator properties
      Object.create(c),
      {
        // iterator protocol
        next() {
          const { value: d, done: h } = c.next();
          return h ? { value: d, done: h } : {
            value: a ? [u(d[0]), u(d[1])] : u(d),
            done: h
          };
        }
      }
    );
  };
}
function En(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function hu(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ pe(o), a = /* @__PURE__ */ pe(r);
      e || (Tt(r, a) && Ke(i, "get", r), Ke(i, "get", a));
      const { has: l } = An(i), c = t ? oo : e ? as : mt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && Ke(/* @__PURE__ */ pe(r), "iterate", xs), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ pe(o), a = /* @__PURE__ */ pe(r);
      return e || (Tt(r, a) && Ke(i, "has", r), Ke(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ pe(a), c = t ? oo : e ? as : mt;
      return !e && Ke(l, "iterate", xs), a.forEach((u, d) => r.call(o, c(u), c(d), i));
    }
  };
  return qe(
    s,
    e ? {
      add: En("add"),
      set: En("set"),
      delete: En("delete"),
      clear: En("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ pe(this), i = An(o), a = /* @__PURE__ */ pe(r), l = !t && !/* @__PURE__ */ dt(r) && !/* @__PURE__ */ Lt(r) ? a : r;
        return i.has.call(o, l) || Tt(r, l) && i.has.call(o, r) || Tt(a, l) && i.has.call(o, a) || (o.add(l), Ht(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ dt(o) && !/* @__PURE__ */ Lt(o) && (o = /* @__PURE__ */ pe(o));
        const i = /* @__PURE__ */ pe(this), { has: a, get: l } = An(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ pe(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? Tt(o, u) && Ht(i, "set", r, o) : Ht(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ pe(this), { has: i, get: a } = An(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ pe(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && Ht(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ pe(this), o = r.size !== 0, i = r.clear();
        return o && Ht(
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
    s[r] = fu(r, e, t);
  }), s;
}
function Do(e, t) {
  const s = hu(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    ye(s, r) && r in n ? s : n,
    r,
    o
  );
}
const mu = {
  get: /* @__PURE__ */ Do(!1, !1)
}, pu = {
  get: /* @__PURE__ */ Do(!1, !0)
}, gu = {
  get: /* @__PURE__ */ Do(!0, !1)
};
const Xa = /* @__PURE__ */ new WeakMap(), el = /* @__PURE__ */ new WeakMap(), tl = /* @__PURE__ */ new WeakMap(), yu = /* @__PURE__ */ new WeakMap();
function vu(e) {
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
function wn(e) {
  return /* @__PURE__ */ Lt(e) ? e : Vo(
    e,
    !1,
    cu,
    mu,
    Xa
  );
}
// @__NO_SIDE_EFFECTS__
function sl(e) {
  return Vo(
    e,
    !1,
    du,
    pu,
    el
  );
}
// @__NO_SIDE_EFFECTS__
function io(e) {
  return Vo(
    e,
    !0,
    uu,
    gu,
    tl
  );
}
function Vo(e, t, s, n, r) {
  if (!xe(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = vu(Wc(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? n : s
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Nt(e) {
  return /* @__PURE__ */ Lt(e) ? /* @__PURE__ */ Nt(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function Lt(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function dt(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function pr(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function pe(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ pe(t) : e;
}
function zo(e) {
  return !ye(e, "__v_skip") && Object.isExtensible(e) && Ma(e, "__v_skip", !0), e;
}
const mt = (e) => xe(e) ? /* @__PURE__ */ wn(e) : e, as = (e) => xe(e) ? /* @__PURE__ */ io(e) : e;
// @__NO_SIDE_EFFECTS__
function De(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function le(e) {
  return nl(e, !1);
}
// @__NO_SIDE_EFFECTS__
function on(e) {
  return nl(e, !0);
}
function nl(e, t) {
  return /* @__PURE__ */ De(e) ? e : new bu(e, t);
}
class bu {
  constructor(t, s) {
    this.dep = new Lo(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ pe(t), this._value = s ? t : mt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ dt(t) || /* @__PURE__ */ Lt(t);
    t = n ? t : /* @__PURE__ */ pe(t), Tt(t, s) && (this._rawValue = t, this._value = n ? t : mt(t), this.dep.trigger());
  }
}
function D(e) {
  return /* @__PURE__ */ De(e) ? e.value : e;
}
function Ns(e) {
  return ne(e) ? e() : D(e);
}
const _u = {
  get: (e, t, s) => t === "__v_raw" ? e : D(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ De(r) && !/* @__PURE__ */ De(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function rl(e) {
  return /* @__PURE__ */ Nt(e) ? e : new Proxy(e, _u);
}
// @__NO_SIDE_EFFECTS__
function xu(e) {
  const t = q(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = ku(e, s);
  return t;
}
class wu {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = ft(s) ? s : String(s), this._raw = /* @__PURE__ */ pe(t);
    let r = !0, o = t;
    if (!q(t) || ft(this._key) || !cr(this._key))
      do
        r = !/* @__PURE__ */ pr(o) || /* @__PURE__ */ dt(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = D(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ De(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ De(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return ru(this._raw, this._key);
  }
}
function ku(e, t, s) {
  return new wu(e, t, s);
}
class Su {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new Lo(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = dn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Re !== this)
      return Ba(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return Za(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function Cu(e, t, s = !1) {
  let n, r;
  return ne(e) ? n = e : (n = e.get, r = e.set), new Su(n, r, s);
}
const Rn = {}, Fn = /* @__PURE__ */ new WeakMap();
let gs;
function Au(e, t = !1, s = gs) {
  if (s) {
    let n = Fn.get(s);
    n || Fn.set(s, n = []), n.push(e);
  }
}
function Eu(e, t, s = Ee) {
  const { immediate: n, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = s, c = (P) => r ? P : /* @__PURE__ */ dt(P) || r === !1 || r === 0 ? Zt(P, 1) : Zt(P);
  let u, d, h, p, w = !1, _ = !1;
  if (/* @__PURE__ */ De(e) ? (d = () => e.value, w = /* @__PURE__ */ dt(e)) : /* @__PURE__ */ Nt(e) ? (d = () => c(e), w = !0) : q(e) ? (_ = !0, w = e.some((P) => /* @__PURE__ */ Nt(P) || /* @__PURE__ */ dt(P)), d = () => e.map((P) => {
    if (/* @__PURE__ */ De(P))
      return P.value;
    if (/* @__PURE__ */ Nt(P))
      return c(P);
    if (ne(P))
      return l ? l(P, 2) : P();
  })) : ne(e) ? t ? d = l ? () => l(e, 2) : e : d = () => {
    if (h) {
      Mt();
      try {
        h();
      } finally {
        jt();
      }
    }
    const P = gs;
    gs = u;
    try {
      return l ? l(e, 3, [p]) : e(p);
    } finally {
      gs = P;
    }
  } : d = It, t && r) {
    const P = d, Q = r === !0 ? 1 / 0 : r;
    d = () => Zt(P(), Q);
  }
  const L = No(), z = () => {
    u.stop(), L && L.active && To(L.effects, u);
  };
  if (o && t) {
    const P = t;
    t = (...Q) => {
      try {
        return P(...Q);
      } finally {
        z();
      }
    };
  }
  let S = _ ? new Array(e.length).fill(Rn) : Rn;
  const T = (P) => {
    if (!(!(u.flags & 1) || !u.dirty && !P))
      if (t) {
        const Q = u.run();
        if (P || r || w || (_ ? Q.some((be, re) => Tt(be, S[re])) : Tt(Q, S))) {
          const be = gs;
          Mt();
          try {
            h && h(), gs = u;
            const re = [
              Q,
              // pass undefined as the old value when it's changed for the first time
              S === Rn ? void 0 : _ && S[0] === Rn ? [] : S,
              p
            ];
            S = Q, l ? l(t, 3, re) : (
              // @ts-expect-error
              t(...re)
            );
          } finally {
            gs = be, jt();
          }
        }
      } else
        u.run();
  };
  return a && a(T), u = new Fa(d), u.scheduler = i ? () => i(T, !1) : T, p = (P) => Au(P, !1, u), h = u.onStop = () => {
    const P = Fn.get(u);
    if (P) {
      if (l)
        l(P, 4);
      else
        for (const Q of P) Q();
      Fn.delete(u);
    }
  }, t ? n ? T(!0) : S = u.run() : i ? i(T.bind(null, !0), !0) : u.run(), z.pause = u.pause.bind(u), z.resume = u.resume.bind(u), z.stop = z, z;
}
function Zt(e, t = 1 / 0, s) {
  if (t <= 0 || !xe(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ De(e))
    Zt(e.value, t, s);
  else if (q(e))
    for (let n = 0; n < e.length; n++)
      Zt(e[n], t, s);
  else if (ks(e) || rs(e))
    e.forEach((n) => {
      Zt(n, t, s);
    });
  else if (Pa(e)) {
    for (const n in e)
      Zt(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && Zt(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function kn(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (r) {
    gr(r, t, s);
  }
}
function _t(e, t, s, n) {
  if (ne(e)) {
    const r = kn(e, t, s, n);
    return r && Ia(r) && r.catch((o) => {
      gr(o, t, s);
    }), r;
  }
  if (q(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(_t(e[o], t, s, n));
    return r;
  }
}
function gr(e, t, s, n = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || Ee;
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
      Mt(), kn(o, null, 10, [
        e,
        l,
        c
      ]), jt();
      return;
    }
  }
  Ru(e, s, r, n, i);
}
function Ru(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const Xe = [];
let vt = -1;
const Rt = [];
let es = null, Os = 0;
const ol = /* @__PURE__ */ Promise.resolve();
let Un = null;
function yr(e) {
  const t = Un || ol;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function Ou(e) {
  let t = vt + 1, s = Xe.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = Xe[n], o = hn(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function $o(e) {
  if (!(e.flags & 1)) {
    const t = hn(e), s = Xe[Xe.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= hn(s) ? Xe.push(e) : Xe.splice(Ou(t), 0, e), e.flags |= 1, il();
  }
}
function il() {
  Un || (Un = ol.then(cl));
}
function Tu(e) {
  if (!q(e))
    es && e.id === -1 ? es.splice(Os + 1, 0, e) : e.flags & 1 || (Rt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Rt.push(e[t]);
  il();
}
function al(e, t, s, n = vt + 1) {
  for (; n < Xe.length; n++) {
    const r = Xe[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      Xe.splice(n, 1), n = e ? n - 1 : vt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function ll(e, t, s = 0) {
  if (Rt.length) {
    let n = Rt, r = 0;
    if (t) {
      n = [];
      for (let i = 0; i < Rt.length; i++) {
        const a = Rt[i];
        (a.i !== void 0 ? !a.i || a.i.uid < s : t.has(a)) ? Rt[r++] = a : n.push(a);
      }
    }
    const o = [...new Set(n)].sort((i, a) => hn(i) - hn(a));
    if (Rt.length = r, es) {
      for (let i = 0; i < o.length; i++)
        es.push(o[i]);
      return;
    }
    for (es = o, Os = 0; Os < es.length; Os++) {
      const i = es[Os];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    es = null, Os = 0;
  }
}
let Pr = !1;
function Iu(e, t) {
  if (Pr) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Rt);
  e(), Pr = !0;
  try {
    al(void 0, t), ll(void 0, s, t);
  } finally {
    Pr = !1;
  }
}
const hn = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function cl(e) {
  try {
    for (vt = 0; vt < Xe.length; vt++) {
      const t = Xe[vt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), kn(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; vt < Xe.length; vt++) {
      const t = Xe[vt];
      t && (t.flags &= -2);
    }
    vt = -1, Xe.length = 0, ll(), Un = null, (Xe.length || Rt.length) && cl();
  }
}
let Ge = null, ul = null;
function Bn(e) {
  const t = Ge;
  return Ge = e, ul = e && e.type.__scopeId || null, t;
}
function _e(e, t = Ge, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && Gn(-1);
    const o = Bn(t), i = qt.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = qt.length; l > i; l--) Zo();
      Bn(o), n._d && Gn(1);
    }
    return a;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Ps(e, t) {
  if (Ge === null)
    return e;
  const s = Cr(Ge), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = Ee] = t[r];
    o && (ne(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && Zt(i), n.push({
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
function fs(e, t, s, n) {
  const r = e.dirs, o = t && t.dirs;
  for (let i = 0; i < r.length; i++) {
    const a = r[i];
    o && (a.oldValue = o[i].value);
    let l = a.dir[n];
    l && (Mt(), _t(l, s, 8, [
      e.el,
      a,
      e,
      t
    ]), jt());
  }
}
function Vn(e, t) {
  if (Je) {
    let s = Je.provides;
    const n = Je.parent && Je.parent.provides;
    n === s && (s = Je.provides = Object.create(n)), s[e] = t;
  }
}
function rt(e, t, s = !1) {
  const n = Sr();
  if (n || ws) {
    let r = ws ? ws._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && ne(t) ? t.call(n && n.proxy) : t;
  }
}
function Fo() {
  return !!(Sr() || ws);
}
const Nu = /* @__PURE__ */ Symbol.for("v-scx"), Pu = () => rt(Nu);
function Mu(e, t) {
  return Uo(e, null, t);
}
function Ms(e, t, s) {
  return Uo(e, t, s);
}
function Uo(e, t, s = Ee) {
  const { immediate: n, deep: r, flush: o, once: i } = s, a = qe({}, s), l = t && n || !t && o !== "post";
  let c;
  if (gn) {
    if (o === "sync") {
      const p = Pu();
      c = p.__watcherHandles || (p.__watcherHandles = []);
    } else if (!l) {
      const p = () => {
      };
      return p.stop = It, p.resume = It, p.pause = It, p;
    }
  }
  const u = Je;
  a.call = (p, w, _) => _t(p, u, w, _);
  let d = !1;
  o === "post" ? a.scheduler = (p) => {
    p.i = u, st(p, u && u.suspense);
  } : o !== "sync" && (d = !0, a.scheduler = (p, w) => {
    w ? p() : $o(p);
  }), a.augmentJob = (p) => {
    t && (p.flags |= 4), d && (p.flags |= 2, u && (p.id = u.uid, p.i = u));
  };
  const h = Eu(e, t, a);
  return gn && (c ? c.push(h) : l && h()), h;
}
function ju(e, t, s) {
  const n = this.proxy, r = Ne(e) ? e.includes(".") ? dl(n, e) : () => n[e] : e.bind(n, n);
  let o;
  ne(t) ? o = t : (o = t.handler, s = t);
  const i = Sn(this), a = Uo(r, o.bind(n), s);
  return i(), a;
}
function dl(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const Lu = /* @__PURE__ */ Symbol("_vte"), vr = (e) => e.__isTeleport, Mr = /* @__PURE__ */ Symbol("_leaveCb");
function Du(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const s of e)
      if (s.type !== pt) {
        t = s;
        break;
      }
  }
  return t;
}
function fl(e) {
  if (!Bo(e))
    return vr(e.type) && e.children ? Du(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && ne(s.default))
      return s.default();
  }
}
function Wn(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    Wn(
      vr(s.type) && fl(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === We && q(e.children)) {
    const s = kl(e.children, !1);
    s && Wn(s, t);
  }
}
function ao(e) {
  if (e.component)
    return ao(e.component.subTree);
  if (e.type === We) {
    const t = q(e.children) && kl(e.children, !1);
    return t ? ao(t) : void 0;
  }
  if (e.type !== pt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function Vt(e, t) {
  return ne(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    qe({ name: e.name }, t, { setup: e })
  ) : e;
}
function hl(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function fi(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const Hn = /* @__PURE__ */ new WeakMap();
function an(e, t, s, n, r = !1) {
  if (q(e)) {
    e.forEach(
      (_, L) => an(
        _,
        t && (q(t) ? t[L] : t),
        s,
        n,
        r
      )
    );
    return;
  }
  if (js(n) && !r) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && an(e, t, s, n.component.subTree);
    return;
  }
  const o = n.shapeFlag & 4 ? Cr(n.component) : n.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === Ee ? a.refs = {} : a.refs, d = a.setupState, h = /* @__PURE__ */ pe(d), p = d === Ee ? Ta : (_) => fi(u, _) ? !1 : ye(h, _), w = (_, L) => !(L && fi(u, L));
  if (c != null && c !== l) {
    if (hi(t), Ne(c))
      u[c] = null, p(c) && (d[c] = null);
    else if (/* @__PURE__ */ De(c)) {
      const _ = t;
      w(c, _.k) && (c.value = null), _.k && (u[_.k] = null);
    }
  }
  if (ne(l))
    kn(l, a, 12, [i, u]);
  else {
    const _ = Ne(l), L = /* @__PURE__ */ De(l);
    if (_ || L) {
      const z = () => {
        if (e.f) {
          const S = _ ? p(l) ? d[l] : u[l] : w() || !e.k ? l.value : u[e.k];
          if (r)
            q(S) && To(S, o);
          else if (q(S))
            S.includes(o) || S.push(o);
          else if (_)
            u[l] = [o], p(l) && (d[l] = u[l]);
          else {
            const T = [o];
            w(l, e.k) && (l.value = T), e.k && (u[e.k] = T);
          }
        } else _ ? (u[l] = i, p(l) && (d[l] = i)) : L && (w(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const S = () => {
          z(), Hn.delete(e);
        };
        S.id = -1, Hn.set(e, S), st(S, s);
      } else
        hi(e), z();
    }
  }
}
function hi(e) {
  const t = Hn.get(e);
  t && (t.flags |= 8, Hn.delete(e));
}
hr().requestIdleCallback;
hr().cancelIdleCallback;
const js = (e) => !!e.type.__asyncLoader, Bo = (e) => e.type.__isKeepAlive;
function Vu(e, t) {
  ml(e, "a", t);
}
function zu(e, t) {
  ml(e, "da", t);
}
function ml(e, t, s = Je) {
  const n = e.__wdc || (e.__wdc = () => {
    let r = s;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (br(t, n, s), s) {
    let r = s.parent;
    for (; r && r.parent; )
      Bo(r.parent.vnode) && $u(n, t, s, r), r = r.parent;
  }
}
function $u(e, t, s, n) {
  const r = br(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  pl(() => {
    To(n[t], r);
  }, s);
}
function br(e, t, s = Je, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Mt();
      const a = Sn(s), l = _t(t, s, e, i);
      return a(), jt(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const Jt = (e) => (t, s = Je) => {
  (!gn || e === "sp") && br(e, (...n) => t(...n), s);
}, Fu = Jt("bm"), _r = Jt("m"), Uu = Jt(
  "bu"
), Bu = Jt("u"), Wu = Jt(
  "bum"
), pl = Jt("um"), Hu = Jt(
  "sp"
), Zu = Jt("rtg"), Gu = Jt("rtc");
function qu(e, t = Je) {
  br("ec", e, t);
}
const Ku = "components", gl = /* @__PURE__ */ Symbol.for("v-ndc");
function Ju(e) {
  return Ne(e) ? Yu(Ku, e, !1) || e : e || gl;
}
function Yu(e, t, s = !0, n = !1) {
  const r = Ge || Je;
  if (r) {
    const o = r.type;
    {
      const a = Md(
        o,
        !1
      );
      if (a && (a === t || a === et(t) || a === dr(et(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      mi(r[e] || o[e], t) || // global registration
      mi(r.appContext[e], t)
    );
    return !i && n ? o : i;
  }
}
function mi(e, t) {
  return e && (e[t] || e[et(t)] || e[dr(et(t))]);
}
function xr(e, t, s, n) {
  let r;
  const o = s, i = q(e);
  if (i || Ne(e)) {
    const a = i && /* @__PURE__ */ Nt(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ dt(e), c = /* @__PURE__ */ Lt(e), e = mr(e)), r = new Array(e.length);
    for (let u = 0, d = e.length; u < d; u++)
      r[u] = t(
        l ? c ? as(mt(e[u])) : mt(e[u]) : e[u],
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
  else if (xe(e))
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
function yl(e, t, s, n, r, o) {
  if (s == null && (s = {}), Ge.ce || Ge.parent && js(Ge.parent) && Ge.parent.ce) {
    const c = s, u = Object.keys(c).length > 0;
    return Se(), Ls(
      We,
      null,
      [Y("slot", c, n)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = qt.length;
  Se();
  let l;
  try {
    const c = i && vl(i(s)), u = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = Ls(
      We,
      {
        key: (u && !ft(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = qt.length; u > a; u--) Zo();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function vl(e) {
  return e.some((t) => Ds(t) ? !(t.type === pt || t.type === We && !vl(t.children)) : !0) ? e : null;
}
const lo = (e) => e ? zl(e) ? Cr(e) : lo(e.parent) : null, ln = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ qe(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => lo(e.parent),
    $root: (e) => lo(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => _l(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      $o(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = yr.bind(e.proxy)),
    $watch: (e) => ju.bind(e)
  })
), jr = (e, t) => e !== Ee && !e.__isScriptSetup && ye(e, t), Qu = {
  get({ _: e }, t) {
    if (t === "__v_skip")
      return !0;
    const { ctx: s, setupState: n, data: r, props: o, accessCache: i, type: a, appContext: l } = e;
    if (t[0] !== "$") {
      const h = i[t];
      if (h !== void 0)
        switch (h) {
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
        if (jr(n, t))
          return i[t] = 1, n[t];
        if (r !== Ee && ye(r, t))
          return i[t] = 2, r[t];
        if (ye(o, t))
          return i[t] = 3, o[t];
        if (s !== Ee && ye(s, t))
          return i[t] = 4, s[t];
        co && (i[t] = 0);
      }
    }
    const c = ln[t];
    let u, d;
    if (c)
      return t === "$attrs" && Ke(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (u = a.__cssModules) && (u = u[t])
    )
      return u;
    if (s !== Ee && ye(s, t))
      return i[t] = 4, s[t];
    if (
      // global properties
      d = l.config.globalProperties, ye(d, t)
    )
      return d[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: r, ctx: o } = e;
    return jr(r, t) ? (r[t] = s, !0) : n !== Ee && ye(n, t) ? (n[t] = s, !0) : ye(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(s[a] || e !== Ee && a[0] !== "$" && ye(e, a) || jr(t, a) || ye(o, a) || ye(n, a) || ye(ln, a) || ye(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : ye(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function pi(e) {
  return q(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let co = !0;
function Xu(e) {
  const t = _l(e), s = e.proxy, n = e.ctx;
  co = !1, t.beforeCreate && gi(t.beforeCreate, e, "bc");
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
    mounted: h,
    beforeUpdate: p,
    updated: w,
    activated: _,
    deactivated: L,
    beforeDestroy: z,
    beforeUnmount: S,
    destroyed: T,
    unmounted: P,
    render: Q,
    renderTracked: be,
    renderTriggered: re,
    errorCaptured: C,
    serverPrefetch: H,
    // public API
    expose: ve,
    inheritAttrs: Pe,
    // assets
    components: K,
    directives: Ce,
    filters: Me
  } = t;
  if (c && ed(c, n, null), i)
    for (const X in i) {
      const de = i[X];
      ne(de) && (n[X] = de.bind(s));
    }
  if (r) {
    const X = r.call(s, s);
    xe(X) && (e.data = /* @__PURE__ */ wn(X));
  }
  if (co = !0, o)
    for (const X in o) {
      const de = o[X], it = ne(de) ? de.bind(s, s) : ne(de.get) ? de.get.bind(s, s) : It, B = !ne(de) && ne(de.set) ? de.set.bind(s) : It, at = Oe({
        get: it,
        set: B
      });
      Object.defineProperty(n, X, {
        enumerable: !0,
        configurable: !0,
        get: () => at.value,
        set: (Be) => at.value = Be
      });
    }
  if (a)
    for (const X in a)
      bl(a[X], n, s, X);
  if (l) {
    const X = ne(l) ? l.call(s) : l;
    Reflect.ownKeys(X).forEach((de) => {
      Vn(de, X[de]);
    });
  }
  u && gi(u, e, "c");
  function ce(X, de) {
    q(de) ? de.forEach((it) => X(it.bind(s))) : de && X(de.bind(s));
  }
  if (ce(Fu, d), ce(_r, h), ce(Uu, p), ce(Bu, w), ce(Vu, _), ce(zu, L), ce(qu, C), ce(Gu, be), ce(Zu, re), ce(Wu, S), ce(pl, P), ce(Hu, H), q(ve))
    if (ve.length) {
      const X = e.exposed || (e.exposed = {});
      ve.forEach((de) => {
        Object.defineProperty(X, de, {
          get: () => s[de],
          set: (it) => s[de] = it,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  Q && e.render === It && (e.render = Q), Pe != null && (e.inheritAttrs = Pe), K && (e.components = K), Ce && (e.directives = Ce), H && hl(e);
}
function ed(e, t, s = It) {
  q(e) && (e = uo(e));
  for (const n in e) {
    const r = e[n];
    let o;
    xe(r) ? "default" in r ? o = rt(
      r.from || n,
      r.default,
      !0
    ) : o = rt(r.from || n) : o = rt(r), /* @__PURE__ */ De(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[n] = o;
  }
}
function gi(e, t, s) {
  _t(
    q(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function bl(e, t, s, n) {
  let r = n.includes(".") ? dl(s, n) : () => s[n];
  if (Ne(e)) {
    const o = t[e];
    ne(o) && Ms(r, o);
  } else if (ne(e))
    Ms(r, e.bind(s));
  else if (xe(e))
    if (q(e))
      e.forEach((o) => bl(o, t, s, n));
    else {
      const o = ne(e.handler) ? e.handler.bind(s) : t[e.handler];
      ne(o) && Ms(r, o, e);
    }
}
function _l(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !s && !n ? l = t : (l = {}, r.length && r.forEach(
    (c) => Zn(l, c, i, !0)
  ), Zn(l, t, i)), xe(t) && o.set(t, l), l;
}
function Zn(e, t, s, n = !1) {
  const { mixins: r, extends: o } = t;
  o && Zn(e, o, s, !0), r && r.forEach(
    (i) => Zn(e, i, s, !0)
  );
  for (const i in t)
    if (!(n && i === "expose")) {
      const a = td[i] || s && s[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const td = {
  data: yi,
  props: vi,
  emits: vi,
  // objects
  methods: Xs,
  computed: Xs,
  // lifecycle
  beforeCreate: Ye,
  created: Ye,
  beforeMount: Ye,
  mounted: Ye,
  beforeUpdate: Ye,
  updated: Ye,
  beforeDestroy: Ye,
  beforeUnmount: Ye,
  destroyed: Ye,
  unmounted: Ye,
  activated: Ye,
  deactivated: Ye,
  errorCaptured: Ye,
  serverPrefetch: Ye,
  // assets
  components: Xs,
  directives: Xs,
  // watch
  watch: nd,
  // provide / inject
  provide: yi,
  inject: sd
};
function yi(e, t) {
  return t ? e ? function() {
    return qe(
      ne(e) ? e.call(this, this) : e,
      ne(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function sd(e, t) {
  return Xs(uo(e), uo(t));
}
function uo(e) {
  if (q(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function Ye(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function Xs(e, t) {
  return e ? qe(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function vi(e, t) {
  return e ? q(e) && q(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : qe(
    /* @__PURE__ */ Object.create(null),
    pi(e),
    pi(t ?? {})
  ) : t;
}
function nd(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = qe(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = Ye(e[n], t[n]);
  return s;
}
function xl() {
  return {
    app: null,
    config: {
      isNativeTag: Ta,
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
let rd = 0;
function od(e, t) {
  return function(n, r = null) {
    ne(n) || (n = qe({}, n)), r != null && !xe(r) && (r = null);
    const o = xl(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: rd++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: Ld,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...d) {
        return i.has(u) || (u && ne(u.install) ? (i.add(u), u.install(c, ...d)) : ne(u) && (i.add(u), u(c, ...d))), c;
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
      mount(u, d, h) {
        if (!l) {
          const p = c._ceVNode || Y(n, r);
          return p.appContext = o, h === !0 ? h = "svg" : h === !1 && (h = void 0), e(p, u, h), l = !0, c._container = u, u.__vue_app__ = c, Cr(p.component);
        }
      },
      onUnmount(u) {
        a.push(u);
      },
      unmount() {
        l && (_t(
          a,
          c._instance,
          16
        ), e(null, c._container), delete c._container.__vue_app__);
      },
      provide(u, d) {
        return o.provides[u] = d, c;
      },
      runWithContext(u) {
        const d = ws;
        ws = c;
        try {
          return u();
        } finally {
          ws = d;
        }
      }
    };
    return c;
  };
}
let ws = null;
const id = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${et(t)}Modifiers`] || e[`${Cs(t)}Modifiers`];
function ad(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || Ee;
  let r = s;
  const o = t.startsWith("update:"), i = o && id(n, t.slice(7));
  i && (i.trim && (r = s.map((u) => Ne(u) ? u.trim() : u)), i.number && (r = r.map(fr)));
  let a, l = n[a = Rr(t)] || // also try camelCase event handler (#2249)
  n[a = Rr(et(t))];
  !l && o && (l = n[a = Rr(Cs(t))]), l && _t(
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
    e.emitted[a] = !0, _t(
      c,
      e,
      6,
      r
    );
  }
}
const ld = /* @__PURE__ */ new WeakMap();
function wl(e, t, s = !1) {
  const n = s ? ld : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!ne(e)) {
    const l = (c) => {
      const u = wl(c, t, !0);
      u && (a = !0, qe(i, u));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (xe(e) && n.set(e, null), null) : (q(o) ? o.forEach((l) => i[l] = null) : qe(i, o), xe(e) && n.set(e, i), i);
}
function wr(e, t) {
  return !e || !ar(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), ye(e, t[0].toLowerCase() + t.slice(1)) || ye(e, Cs(t)) || ye(e, t));
}
function bi(e) {
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
    data: h,
    setupState: p,
    ctx: w,
    inheritAttrs: _
  } = e, L = Bn(e);
  let z, S;
  try {
    if (s.shapeFlag & 4) {
      const P = r || n, Q = P;
      z = Ot(
        c.call(
          Q,
          P,
          u,
          d,
          p,
          h,
          w
        )
      ), S = a;
    } else {
      const P = t;
      z = Ot(
        P.length > 1 ? P(
          d,
          { attrs: a, slots: i, emit: l }
        ) : P(
          d,
          null
        )
      ), S = t.props ? a : cd(a);
    }
  } catch (P) {
    qt.length = 0, gr(P, e, 1), z = Y(pt);
  }
  let T = z;
  if (S && _ !== !1) {
    const P = Object.keys(S), { shapeFlag: Q } = T;
    P.length && Q & 7 && (o && P.some(lr) && (S = ud(
      S,
      o
    )), T = Vs(T, S, !1, !0));
  }
  if (s.dirs && (T = Vs(T, null, !1, !0), T.dirs = T.dirs ? T.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const P = vr(T.type) && fl(T) || T;
    Wn(P, s.transition);
  }
  return z = T, Bn(L), z;
}
function kl(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const r = e[n];
    if (Ds(r)) {
      if (r.type !== pt || r.children === "v-if") {
        if (s)
          return;
        s = r;
      }
    } else
      return;
  }
  return s;
}
const cd = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || ar(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, ud = (e, t) => {
  const s = {};
  for (const n in e)
    (!lr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function dd(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? _i(n, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let d = 0; d < u.length; d++) {
        const h = u[d];
        if (Sl(i, n, h) && !wr(c, h))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : n === i ? !1 : n ? i ? _i(n, i, c) : !0 : !!i;
  return !1;
}
function _i(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!ye(e, o) || Sl(t, e, o) && !wr(s, o))
      return !0;
  }
  return !1;
}
function Sl(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && xe(n) && xe(r) ? !is(n, r) : n !== r;
}
function fd({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const Cl = {}, Al = () => Object.create(Cl), El = (e) => Object.getPrototypeOf(e) === Cl;
function hd(e, t, s, n = !1) {
  const r = {}, o = Al();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), Rl(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ sl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function md(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ pe(r), [l] = e.propsOptions;
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
        let h = u[d];
        if (wr(e.emitsOptions, h))
          continue;
        const p = t[h];
        if (l)
          if (ye(o, h))
            p !== o[h] && (o[h] = p, c = !0);
          else {
            const w = et(h);
            r[w] = fo(
              l,
              a,
              w,
              p,
              e,
              !1
            );
          }
        else
          p !== o[h] && (o[h] = p, c = !0);
      }
    }
  } else {
    Rl(e, t, r, o) && (c = !0);
    let u;
    for (const d in a)
      (!t || // for camelCase
      !ye(t, d) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = Cs(d)) === d || !ye(t, u))) && (l ? s && // for camelCase
      (s[d] !== void 0 || // for kebab-case
      s[u] !== void 0) && (r[d] = fo(
        l,
        a,
        d,
        void 0,
        e,
        !0
      )) : delete r[d]);
    if (o !== a)
      for (const d in o)
        (!t || !ye(t, d)) && (delete o[d], c = !0);
  }
  c && Ht(e.attrs, "set", "");
}
function Rl(e, t, s, n) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (sn(l))
        continue;
      const c = t[l];
      let u;
      r && ye(r, u = et(l)) ? !o || !o.includes(u) ? s[u] = c : (a || (a = {}))[u] = c : wr(e.emitsOptions, l) || (!(l in n) || c !== n[l]) && (n[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ pe(s), c = a || Ee;
    for (let u = 0; u < o.length; u++) {
      const d = o[u];
      s[d] = fo(
        r,
        l,
        d,
        c[d],
        e,
        !ye(c, d)
      );
    }
  }
  return i;
}
function fo(e, t, s, n, r, o) {
  const i = e[s];
  if (i != null) {
    const a = ye(i, "default");
    if (a && n === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && ne(l)) {
        const { propsDefaults: c } = r;
        if (s in c)
          n = c[s];
        else {
          const u = Sn(r);
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
    ] && (n === "" || n === Cs(s)) && (n = !0));
  }
  return n;
}
const pd = /* @__PURE__ */ new WeakMap();
function Ol(e, t, s = !1) {
  const n = s ? pd : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!ne(e)) {
    const u = (d) => {
      l = !0;
      const [h, p] = Ol(d, t, !0);
      qe(i, h), p && a.push(...p);
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return xe(e) && n.set(e, vs), vs;
  if (q(o))
    for (let u = 0; u < o.length; u++) {
      const d = et(o[u]);
      xi(d) && (i[d] = Ee);
    }
  else if (o)
    for (const u in o) {
      const d = et(u);
      if (xi(d)) {
        const h = o[u], p = i[d] = q(h) || ne(h) ? { type: h } : qe({}, h), w = p.type;
        let _ = !1, L = !0;
        if (q(w))
          for (let z = 0; z < w.length; ++z) {
            const S = w[z], T = ne(S) && S.name;
            if (T === "Boolean") {
              _ = !0;
              break;
            } else T === "String" && (L = !1);
          }
        else
          _ = ne(w) && w.name === "Boolean";
        p[
          0
          /* shouldCast */
        ] = _, p[
          1
          /* shouldCastTrue */
        ] = L, (_ || ye(p, "default")) && a.push(d);
      }
    }
  const c = [i, a];
  return xe(e) && n.set(e, c), c;
}
function xi(e) {
  return e[0] !== "$" && !sn(e);
}
const Wo = (e) => e === "_" || e === "_ctx" || e === "$stable", Ho = (e) => q(e) ? e.map(Ot) : [Ot(e)], gd = (e, t, s) => {
  if (t._n)
    return t;
  const n = _e((...r) => Ho(t(...r)), s);
  return n._c = !1, n;
}, Tl = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (Wo(r)) continue;
    const o = e[r];
    if (ne(o))
      t[r] = gd(r, o, n);
    else if (o != null) {
      const i = Ho(o);
      t[r] = () => i;
    }
  }
}, Il = (e, t) => {
  const s = Ho(t);
  e.slots.default = () => s;
}, Nl = (e, t, s) => {
  for (const n in t)
    (s || !Wo(n)) && (e[n] = t[n]);
}, yd = (e, t, s) => {
  const n = e.slots = Al();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (Nl(n, t, s), s && Ma(n, "_", r, !0)) : Tl(t, n);
  } else t && Il(e, t);
}, vd = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, i = Ee;
  if (n.shapeFlag & 32) {
    const a = t._;
    a ? s && a === 1 ? o = !1 : Nl(r, t, s) : (o = !t.$stable, Tl(t, r)), i = t;
  } else t && (Il(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !Wo(a) && i[a] == null && delete r[a];
}, st = kd;
function bd(e) {
  return _d(e);
}
function _d(e, t) {
  const s = hr();
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
    nextSibling: h,
    setScopeId: p = It,
    insertStaticContent: w
  } = e, _ = (f, m, g, y = null, v = null, x = null, A = void 0, N = null, I = !!m.dynamicChildren) => {
    if (f === m)
      return;
    f && !Ks(f, m) && (y = b(f), Be(f, v, x, !0), f = null), m.patchFlag === -2 && (I = !1, m.dynamicChildren = null), m.dynamicChildren && f && f.dynamicChildren && f.dynamicChildren.hasOnce && (m.dynamicChildren === vs && (m.dynamicChildren = []), m.dynamicChildren.hasOnce = !0);
    const { type: k, ref: Z, shapeFlag: M } = m;
    switch (k) {
      case kr:
        L(f, m, g, y);
        break;
      case pt:
        z(f, m, g, y);
        break;
      case Dr:
        f == null && S(m, g, y, A);
        break;
      case We:
        K(
          f,
          m,
          g,
          y,
          v,
          x,
          A,
          N,
          I
        );
        break;
      default:
        M & 1 ? Q(
          f,
          m,
          g,
          y,
          v,
          x,
          A,
          N,
          I
        ) : M & 6 ? Ce(
          f,
          m,
          g,
          y,
          v,
          x,
          A,
          N,
          I
        ) : (M & 64 || M & 128) && k.process(
          f,
          m,
          g,
          y,
          v,
          x,
          A,
          N,
          I,
          E
        );
    }
    Z != null && v ? an(Z, f && f.ref, x, m || f, !m) : Z == null && f && f.ref != null && an(f.ref, null, x, f, !0);
  }, L = (f, m, g, y) => {
    if (f == null)
      n(
        m.el = a(m.children),
        g,
        y
      );
    else {
      const v = m.el = f.el;
      m.children !== f.children && c(v, m.children);
    }
  }, z = (f, m, g, y) => {
    f == null ? n(
      m.el = l(m.children || ""),
      g,
      y
    ) : m.el = f.el;
  }, S = (f, m, g, y) => {
    [f.el, f.anchor] = w(
      f.children,
      m,
      g,
      y,
      f.el,
      f.anchor
    );
  }, T = ({ el: f, anchor: m }, g, y) => {
    let v;
    for (; f && f !== m; )
      v = h(f), n(f, g, y), f = v;
    n(m, g, y);
  }, P = ({ el: f, anchor: m }) => {
    let g;
    for (; f && f !== m; )
      g = h(f), r(f), f = g;
    r(m);
  }, Q = (f, m, g, y, v, x, A, N, I) => {
    if (m.type === "svg" ? A = "svg" : m.type === "math" && (A = "mathml"), f == null)
      be(
        m,
        g,
        y,
        v,
        x,
        A,
        N,
        I
      );
    else {
      const k = f.el && f.el._isVueCE ? f.el : null;
      try {
        k && k._beginPatch(), H(
          f,
          m,
          v,
          x,
          A,
          N,
          I
        );
      } finally {
        k && k._endPatch();
      }
    }
  }, be = (f, m, g, y, v, x, A, N) => {
    let I, k;
    const { props: Z, shapeFlag: M, transition: G, dirs: ee } = f;
    if (I = f.el = i(
      f.type,
      x,
      Z && Z.is,
      Z
    ), M & 8 ? u(I, f.children) : M & 16 && C(
      f.children,
      I,
      null,
      y,
      v,
      Lr(f, x),
      A,
      N
    ), ee && fs(f, null, y, "created"), re(I, f, f.scopeId, A, y), Z) {
      for (const Ae in Z)
        Ae !== "value" && !sn(Ae) && o(I, Ae, null, Z[Ae], x, y);
      "value" in Z && o(I, "value", null, Z.value, x), (k = Z.onVnodeBeforeMount) && Ct(k, y, f);
    }
    ee && fs(f, null, y, "beforeMount");
    const he = xd(v, G);
    he && G.beforeEnter(I), n(I, m, g), ((k = Z && Z.onVnodeMounted) || he || ee) && st(() => {
      try {
        k && Ct(k, y, f), he && G.enter(I), ee && fs(f, null, y, "mounted");
      } finally {
      }
    }, v);
  }, re = (f, m, g, y, v) => {
    if (g && p(f, g), y)
      for (let x = 0; x < y.length; x++)
        p(f, y[x]);
    if (v) {
      let x = v.subTree;
      if (m === x || jl(x.type) && (x.ssContent === m || x.ssFallback === m)) {
        const A = v.vnode;
        re(
          f,
          A,
          A.scopeId,
          A.slotScopeIds,
          v.parent
        );
      }
    }
  }, C = (f, m, g, y, v, x, A, N, I = 0) => {
    for (let k = I; k < f.length; k++) {
      const Z = f[k] = N ? Wt(f[k]) : Ot(f[k]);
      _(
        null,
        Z,
        m,
        g,
        y,
        v,
        x,
        A,
        N
      );
    }
  }, H = (f, m, g, y, v, x, A) => {
    const N = m.el = f.el;
    let { patchFlag: I, dynamicChildren: k, dirs: Z } = m;
    I |= f.patchFlag & 16;
    const M = f.props || Ee, G = m.props || Ee;
    let ee;
    if (g && hs(g, !1), (ee = G.onVnodeBeforeUpdate) && Ct(ee, g, m, f), Z && fs(m, f, g, "beforeUpdate"), g && hs(g, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    k && (!f.dynamicChildren || f.dynamicChildren.length !== k.length) && (I = 0, A = !1, k = null), (M.innerHTML && G.innerHTML == null || M.textContent && G.textContent == null) && u(N, ""), k ? ve(
      f.dynamicChildren,
      k,
      N,
      g,
      y,
      Lr(m, v),
      x
    ) : A || de(
      f,
      m,
      N,
      null,
      g,
      y,
      Lr(m, v),
      x,
      !1
    ), I > 0) {
      if (I & 16)
        Pe(N, M, G, g, v);
      else if (I & 2 && M.class !== G.class && o(N, "class", null, G.class, v), I & 4 && o(N, "style", M.style, G.style, v), I & 8) {
        const he = m.dynamicProps;
        for (let Ae = 0; Ae < he.length; Ae++) {
          const ke = he[Ae], Ve = M[ke], He = G[ke];
          (He !== Ve || ke === "value") && o(N, ke, Ve, He, v, g);
        }
      }
      I & 1 && f.children !== m.children && u(N, m.children);
    } else !A && k == null && Pe(N, M, G, g, v);
    ((ee = G.onVnodeUpdated) || Z) && st(() => {
      ee && Ct(ee, g, m, f), Z && fs(m, f, g, "updated");
    }, y);
  }, ve = (f, m, g, y, v, x, A) => {
    for (let N = 0; N < m.length; N++) {
      const I = f[N], k = m[N], Z = I.el || ho(I), M = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        Z && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (I.type === We || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !Ks(I, k) || // - In the case of a component, it could contain anything.
        I.shapeFlag & 198) ? d(Z) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          g
        )
      );
      _(
        I,
        k,
        M,
        null,
        y,
        v,
        x,
        A,
        !0
      );
    }
  }, Pe = (f, m, g, y, v) => {
    if (m !== g) {
      if (m !== Ee)
        for (const x in m)
          !sn(x) && !(x in g) && o(
            f,
            x,
            m[x],
            null,
            v,
            y
          );
      for (const x in g) {
        if (sn(x)) continue;
        const A = g[x], N = m[x];
        A !== N && x !== "value" && o(f, x, N, A, v, y);
      }
      "value" in g && o(f, "value", m.value, g.value, v);
    }
  }, K = (f, m, g, y, v, x, A, N, I) => {
    const k = m.el = f ? f.el : a(""), Z = m.anchor = f ? f.anchor : a("");
    let { patchFlag: M, dynamicChildren: G, slotScopeIds: ee } = m;
    ee && (N = N ? N.concat(ee) : ee), f == null ? (n(k, g, y), n(Z, g, y), C(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      m.children || [],
      g,
      Z,
      v,
      x,
      A,
      N,
      I
    )) : M > 0 && M & 64 && G && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    f.dynamicChildren && f.dynamicChildren.length === G.length ? (ve(
      f.dynamicChildren,
      G,
      g,
      v,
      x,
      A,
      N
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (m.key != null || v && m === v.subTree) && Pl(
      f,
      m,
      !0
      /* shallow */
    )) : de(
      f,
      m,
      g,
      Z,
      v,
      x,
      A,
      N,
      I
    );
  }, Ce = (f, m, g, y, v, x, A, N, I) => {
    m.slotScopeIds = N, f == null ? m.shapeFlag & 512 ? v.ctx.activate(
      m,
      g,
      y,
      A,
      I
    ) : Me(
      m,
      g,
      y,
      v,
      x,
      A,
      I
    ) : me(f, m, I);
  }, Me = (f, m, g, y, v, x, A) => {
    const N = f.component = Od(
      f,
      y,
      v
    );
    if (Bo(f) && (N.ctx.renderer = E), Td(N, !1, A), N.asyncDep) {
      if (v && v.registerDep(
        N,
        ce,
        A,
        x
      ), !f.el) {
        const I = N.subTree = Y(pt);
        z(null, I, m, g), f.placeholder = I.el;
      }
    } else
      ce(
        N,
        f,
        m,
        g,
        v,
        x,
        A
      );
  }, me = (f, m, g) => {
    const y = m.component = f.component;
    if (dd(f, m, g))
      if (y.asyncDep && !y.asyncResolved) {
        m.el = f.el, m.placeholder = f.placeholder, X(y, m, g);
        return;
      } else
        y.next = m, y.update();
    else
      m.el = f.el, m.placeholder = f.placeholder, y.vnode = m;
  }, ce = (f, m, g, y, v, x, A) => {
    const N = () => {
      if (f.isMounted) {
        let { next: M, bu: G, u: ee, parent: he, vnode: Ae } = f;
        {
          const kt = Ml(f);
          if (kt) {
            M && (M.el = Ae.el, X(f, M, A)), kt.asyncDep.then(() => {
              st(() => {
                f.isUnmounted || k();
              }, v);
            });
            return;
          }
        }
        let ke = M, Ve;
        hs(f, !1), M ? (M.el = Ae.el, X(f, M, A)) : M = Ae, G && Dn(G), (Ve = M.props && M.props.onVnodeBeforeUpdate) && Ct(Ve, he, M, Ae), hs(f, !0);
        const He = bi(f), wt = f.subTree;
        f.subTree = He, _(
          wt,
          He,
          // parent may have changed if it's in a teleport
          d(wt.el),
          // anchor may have changed if it's in a fragment
          b(wt),
          f,
          v,
          x
        ), M.el = He.el, ke === null && fd(f, He.el), ee && st(ee, v), (Ve = M.props && M.props.onVnodeUpdated) && st(
          () => Ct(Ve, he, M, Ae),
          v
        );
      } else {
        let M;
        const { el: G, props: ee } = m, { bm: he, m: Ae, parent: ke, root: Ve, type: He } = f, wt = js(m);
        hs(f, !1), he && Dn(he), !wt && (M = ee && ee.onVnodeBeforeMount) && Ct(M, ke, m), hs(f, !0);
        {
          Ve.ce && Ve.ce._hasShadowRoot() && Ve.ce._injectChildStyle(
            He,
            f.parent ? f.parent.type : void 0
          );
          const kt = f.subTree = bi(f);
          _(
            null,
            kt,
            g,
            y,
            f,
            v,
            x
          ), m.el = kt.el;
        }
        if (Ae && st(Ae, v), !wt && (M = ee && ee.onVnodeMounted)) {
          const kt = m;
          st(
            () => Ct(M, ke, kt),
            v
          );
        }
        (m.shapeFlag & 256 || ke && js(ke.vnode) && ke.vnode.shapeFlag & 256) && f.a && st(f.a, v), f.isMounted = !0, m = g = y = null;
      }
    };
    f.scope.on();
    const I = f.effect = new Fa(N);
    f.scope.off();
    const k = f.update = I.run.bind(I), Z = f.job = I.runIfDirty.bind(I);
    Z.i = f, Z.id = f.uid, I.scheduler = () => $o(Z), hs(f, !0), k();
  }, X = (f, m, g) => {
    m.component = f;
    const y = f.vnode.props;
    f.vnode = m, f.next = null, md(f, m.props, y, g), vd(f, m.children, g), Mt(), al(f), jt();
  }, de = (f, m, g, y, v, x, A, N, I = !1) => {
    const k = f && f.children, Z = f ? f.shapeFlag : 0, M = m.children, { patchFlag: G, shapeFlag: ee } = m;
    if (G > 0) {
      if (G & 128) {
        B(
          k,
          M,
          g,
          y,
          v,
          x,
          A,
          N,
          I
        );
        return;
      } else if (G & 256) {
        it(
          k,
          M,
          g,
          y,
          v,
          x,
          A,
          N,
          I
        );
        return;
      }
    }
    ee & 8 ? (Z & 16 && we(k, v, x), M !== k && u(g, M)) : Z & 16 ? ee & 16 ? B(
      k,
      M,
      g,
      y,
      v,
      x,
      A,
      N,
      I
    ) : we(k, v, x, !0) : (Z & 8 && u(g, ""), ee & 16 && C(
      M,
      g,
      y,
      v,
      x,
      A,
      N,
      I
    ));
  }, it = (f, m, g, y, v, x, A, N, I) => {
    f = f || vs, m = m || vs;
    const k = f.length, Z = m.length, M = Math.min(k, Z);
    let G;
    for (G = 0; G < M; G++) {
      const ee = m[G] = I ? Wt(m[G]) : Ot(m[G]);
      _(
        f[G],
        ee,
        g,
        null,
        v,
        x,
        A,
        N,
        I
      );
    }
    k > Z ? we(
      f,
      v,
      x,
      !0,
      !1,
      M
    ) : C(
      m,
      g,
      y,
      v,
      x,
      A,
      N,
      I,
      M
    );
  }, B = (f, m, g, y, v, x, A, N, I) => {
    let k = 0;
    const Z = m.length;
    let M = f.length - 1, G = Z - 1;
    for (; k <= M && k <= G; ) {
      const ee = f[k], he = m[k] = I ? Wt(m[k]) : Ot(m[k]);
      if (Ks(ee, he))
        _(
          ee,
          he,
          g,
          null,
          v,
          x,
          A,
          N,
          I
        );
      else
        break;
      k++;
    }
    for (; k <= M && k <= G; ) {
      const ee = f[M], he = m[G] = I ? Wt(m[G]) : Ot(m[G]);
      if (Ks(ee, he))
        _(
          ee,
          he,
          g,
          null,
          v,
          x,
          A,
          N,
          I
        );
      else
        break;
      M--, G--;
    }
    if (k > M) {
      if (k <= G) {
        const ee = G + 1, he = ee < Z ? m[ee].el : y;
        for (; k <= G; )
          _(
            null,
            m[k] = I ? Wt(m[k]) : Ot(m[k]),
            g,
            he,
            v,
            x,
            A,
            N,
            I
          ), k++;
      }
    } else if (k > G)
      for (; k <= M; )
        Be(f[k], v, x, !0), k++;
    else {
      const ee = k, he = k, Ae = /* @__PURE__ */ new Map();
      for (k = he; k <= G; k++) {
        const lt = m[k] = I ? Wt(m[k]) : Ot(m[k]);
        lt.key != null && Ae.set(lt.key, k);
      }
      let ke, Ve = 0;
      const He = G - he + 1;
      let wt = !1, kt = 0;
      const Gs = new Array(He);
      for (k = 0; k < He; k++) Gs[k] = 0;
      for (k = ee; k <= M; k++) {
        const lt = f[k];
        if (Ve >= He) {
          Be(lt, v, x, !0);
          continue;
        }
        let St;
        if (lt.key != null)
          St = Ae.get(lt.key);
        else
          for (ke = he; ke <= G; ke++)
            if (Gs[ke - he] === 0 && Ks(lt, m[ke])) {
              St = ke;
              break;
            }
        St === void 0 ? Be(lt, v, x, !0) : (Gs[St - he] = k + 1, St >= kt ? kt = St : wt = !0, _(
          lt,
          m[St],
          g,
          null,
          v,
          x,
          A,
          N,
          I
        ), Ve++);
      }
      const si = wt ? wd(Gs) : vs;
      for (ke = si.length - 1, k = He - 1; k >= 0; k--) {
        const lt = he + k, St = m[lt], ni = m[lt + 1], ri = lt + 1 < Z ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          ni.el || ho(ni)
        ) : y;
        Gs[k] === 0 ? _(
          null,
          St,
          g,
          ri,
          v,
          x,
          A,
          N,
          I
        ) : wt && (ke < 0 || k !== si[ke] ? at(St, g, ri, 2) : ke--);
      }
    }
  }, at = (f, m, g, y, v = null) => {
    const { el: x, type: A, transition: N, children: I, shapeFlag: k } = f;
    if (k & 6) {
      at(f.component.subTree, m, g, y);
      return;
    }
    if (k & 128) {
      f.suspense.move(m, g, y);
      return;
    }
    if (k & 64) {
      A.move(f, m, g, E);
      return;
    }
    if (A === We) {
      n(x, m, g);
      for (let M = 0; M < I.length; M++)
        at(I[M], m, g, y);
      n(f.anchor, m, g);
      return;
    }
    if (A === Dr) {
      T(f, m, g);
      return;
    }
    if (y !== 2 && k & 1 && N)
      if (y === 0)
        N.persisted && !x[Mr] ? n(x, m, g) : (N.beforeEnter(x), n(x, m, g), st(() => N.enter(x), v));
      else {
        const { leave: M, delayLeave: G, afterLeave: ee } = N, he = () => {
          f.ctx.isUnmounted ? r(x) : n(x, m, g);
        }, Ae = () => {
          const ke = x._isLeaving || !!x[Mr];
          x._isLeaving && x[Mr](
            !0
            /* cancelled */
          ), N.persisted && !ke ? he() : M(x, () => {
            he(), ee && ee();
          });
        };
        G ? G(x, he, Ae) : Ae();
      }
    else
      n(x, m, g);
  }, Be = (f, m, g, y = !1, v = !1) => {
    const {
      type: x,
      props: A,
      ref: N,
      children: I,
      dynamicChildren: k,
      shapeFlag: Z,
      patchFlag: M,
      dirs: G,
      cacheIndex: ee,
      memo: he
    } = f;
    if ((M === -2 || k && k.hasOnce) && (v = !1), N != null && (Mt(), an(N, null, g, f, !0), jt()), ee != null && (!f.ctx || f.ctx === m) && (m.renderCache[ee] = void 0), Z & 256) {
      m.ctx.deactivate(f);
      return;
    }
    const Ae = Z & 1 && G, ke = !js(f);
    let Ve;
    if (ke && (Ve = A && A.onVnodeBeforeUnmount) && Ct(Ve, m, f), Z & 6)
      Ie(f.component, g, y);
    else {
      if (Z & 128) {
        f.suspense.unmount(g, y);
        return;
      }
      Ae && fs(f, null, m, "beforeUnmount"), Z & 64 ? f.type.remove(
        f,
        m,
        g,
        E,
        y
      ) : k && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !k.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (x !== We || M > 0 && M & 64) ? we(
        k,
        m,
        g,
        !1,
        !0
      ) : (x === We && M & 384 || !v && Z & 16) && we(I, m, g), y && zt(f);
    }
    const He = he != null && ee == null;
    (ke && (Ve = A && A.onVnodeUnmounted) || Ae || He) && st(() => {
      Ve && Ct(Ve, m, f), Ae && fs(f, null, m, "unmounted"), He && (f.el = null);
    }, g);
  }, zt = (f) => {
    const { type: m, el: g, anchor: y, transition: v } = f, x = m === We;
    if (x && !v) {
      yt(g, y);
      return;
    }
    if (m === Dr) {
      P(f), v && !v.persisted && v.afterLeave && v.afterLeave();
      return;
    }
    const A = x ? ao(f) : f, N = () => {
      x ? d(g) && yt(g, y) : r(g), v && !v.persisted && v.afterLeave && v.afterLeave();
    };
    if (A && A.shapeFlag & 1 && v && !v.persisted) {
      const { leave: I, delayLeave: k } = v, Z = A.el, M = () => I(Z, N);
      k ? k(Z, N, M) : M();
    } else
      N();
  }, yt = (f, m) => {
    let g;
    for (; f !== m; )
      g = h(f), r(f), f = g;
    r(m);
  }, Ie = (f, m, g) => {
    const { bum: y, scope: v, job: x, subTree: A, um: N, m: I, a: k } = f;
    wi(I), wi(k), y && Dn(y), v.stop(), x ? (x.flags |= 8, Be(A, f, m, g)) : f.vnode.el && A && (A.transition = f.vnode.transition, Be(A, f, m, g)), N && st(N, m), st(() => {
      f.isUnmounted = !0;
    }, m);
  }, we = (f, m, g, y = !1, v = !1, x = 0) => {
    for (let A = x; A < f.length; A++)
      Be(f[A], m, g, y, v);
  }, b = (f) => {
    if (f.shapeFlag & 6)
      return b(f.component.subTree);
    if (f.shapeFlag & 128)
      return f.suspense.next();
    const m = h(f.anchor || f.el), g = m && m[Lu];
    return g ? h(g) : m;
  }, $ = (f, m, g) => {
    const y = f && m._vnode ? void 0 : f && f.component ? f.component.uid : Rd();
    Iu(() => {
      f == null ? m._vnode && Be(m._vnode, null, null, !0) : _(
        m._vnode || null,
        f,
        m,
        null,
        null,
        null,
        g
      ), m._vnode = f;
    }, y);
  }, E = {
    p: _,
    um: Be,
    m: at,
    r: zt,
    mt: Me,
    mc: C,
    pc: de,
    pbc: ve,
    n: b,
    o: e
  };
  return {
    render: $,
    hydrate: void 0,
    createApp: od($)
  };
}
function Lr({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function hs({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function xd(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function Pl(e, t, s = !1) {
  const n = e.children, r = t.children;
  if (q(n) && q(r))
    for (let o = 0; o < n.length; o++) {
      const i = n[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = Wt(r[o]), a.el = i.el), !s && a.patchFlag !== -2 && Pl(i, a)), a.type === kr && (a.patchFlag === -1 && (a = r[o] = Wt(a)), a.el = i.el), a.type === pt && !a.el && (a.el = i.el);
    }
}
function wd(e) {
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
function Ml(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : Ml(t);
}
function wi(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function ho(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? ho(t.subTree) : null;
}
const jl = (e) => e.__isSuspense;
function kd(e, t) {
  t && t.pendingBranch ? q(e) ? t.effects.push(...e) : t.effects.push(e) : Tu(e);
}
const We = /* @__PURE__ */ Symbol.for("v-fgt"), kr = /* @__PURE__ */ Symbol.for("v-txt"), pt = /* @__PURE__ */ Symbol.for("v-cmt"), Dr = /* @__PURE__ */ Symbol.for("v-stc"), qt = [];
let ct = null;
function Se(e = !1) {
  qt.push(ct = e ? null : []);
}
function Zo() {
  qt.pop(), ct = qt[qt.length - 1] || null;
}
let mn = 1;
function Gn(e, t = !1) {
  mn += e, e < 0 && ct && t && (ct.hasOnce = !0);
}
function Ll(e) {
  return e.dynamicChildren = mn > 0 ? ct || vs : null, Zo(), mn > 0 && ct && ct.push(e), e;
}
function Le(e, t, s, n, r, o) {
  return Ll(
    R(
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
function Ls(e, t, s, n, r) {
  return Ll(
    Y(
      e,
      t,
      s,
      n,
      r,
      !0
    )
  );
}
function Ds(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function Ks(e, t) {
  return e.type === t.type && e.key === t.key;
}
const Dl = ({ key: e }) => e ?? null, zn = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? Ne(e) || /* @__PURE__ */ De(e) || ne(e) ? { i: Ge, r: e, k: t, f: !!s } : e : null);
function R(e, t = null, s = null, n = 0, r = null, o = e === We ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Dl(t),
    ref: t && zn(t),
    scopeId: ul,
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
    ctx: Ge
  };
  return a ? (qn(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= Ne(s) ? 8 : 16), mn > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  ct && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && ct.push(l), l;
}
const Y = Sd;
function Sd(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === gl) && (e = pt), Ds(e)) {
    const a = Vs(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && qn(a, s), mn > 0 && !o && ct && (a.shapeFlag & 6 ? ct[ct.indexOf(e)] = a : ct.push(a)), a.patchFlag = -2, a;
  }
  if (jd(e) && (e = e.__vccOpts), t) {
    t = Cd(t);
    let { class: a, style: l } = t;
    a && !Ne(a) && (t.class = ht(a)), xe(l) && (/* @__PURE__ */ pr(l) && !q(l) && (l = qe({}, l)), t.style = Io(l));
  }
  const i = Ne(e) ? 1 : jl(e) ? 128 : vr(e) ? 64 : xe(e) ? 4 : ne(e) ? 2 : 0;
  return R(
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
function Cd(e) {
  return e ? /* @__PURE__ */ pr(e) || El(e) ? qe({}, e) : e : null;
}
function Vs(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? Ad(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Dl(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? q(o) ? o.concat(zn(t)) : [o, zn(t)] : zn(t)
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
    ssContent: e.ssContent && Vs(e.ssContent),
    ssFallback: e.ssFallback && Vs(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && Wn(
    u,
    l.clone(u)
  ), u;
}
function oe(e = " ", t = 0) {
  return Y(kr, null, e, t);
}
function ns(e = "", t = !1) {
  return t ? (Se(), Ls(pt, null, e)) : Y(pt, null, e);
}
function Ot(e) {
  return e == null || typeof e == "boolean" ? Y(pt) : q(e) ? Y(
    We,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : Ds(e) ? Wt(e) : Y(kr, null, String(e));
}
function Wt(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : Vs(e);
}
function qn(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (q(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), qn(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !El(t) ? t._ctx = Ge : r === 3 && Ge && (Ge.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (ne(t)) {
    if (n & 65) {
      qn(e, { default: t });
      return;
    }
    t = { default: t, _ctx: Ge }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [oe(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function Ad(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = ht([t.class, n.class]));
      else if (r === "style")
        t.style = Io([t.style, n.style]);
      else if (ar(r)) {
        const o = t[r], i = n[r];
        i && o !== i && !(q(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !lr(r) && (t[r] = i);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function Ct(e, t, s, n = null) {
  _t(e, t, 7, [
    s,
    n
  ]);
}
const Ed = xl();
let Vl = 0;
function Rd() {
  return Vl;
}
function Od(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || Ed, o = {
    uid: Vl++,
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
    scope: new Va(
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
    propsOptions: Ol(n, r),
    emitsOptions: wl(n, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: Ee,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: Ee,
    data: Ee,
    props: Ee,
    attrs: Ee,
    slots: Ee,
    refs: Ee,
    setupState: Ee,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = ad.bind(null, o), e.ce && e.ce(o), o;
}
let Je = null;
const Sr = () => Je || Ge;
let Kn, pn;
{
  const e = hr(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  Kn = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => Je = s
  ), pn = t(
    "__VUE_SSR_SETTERS__",
    (s) => gn = s
  );
}
const Sn = (e) => {
  const t = Je;
  return Kn(e), e.scope.on(), () => {
    e.scope.off(), Kn(t);
  };
}, ki = () => {
  Je && Je.scope.off(), Kn(null);
};
function zl(e) {
  return e.vnode.shapeFlag & 4;
}
let gn = !1;
function Td(e, t = !1, s = !1) {
  t && pn(t);
  const { props: n, children: r } = e.vnode, o = zl(e);
  hd(e, n, o, t), yd(e, r, s || t);
  const i = o ? Id(e, t) : void 0;
  return t && pn(!1), i;
}
function Id(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Qu);
  const { setup: n } = s;
  if (n) {
    Mt();
    const r = e.setupContext = n.length > 1 ? Pd(e) : null, o = Sn(e), i = kn(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = Ia(i);
    if (jt(), o(), (a || e.sp) && !js(e) && hl(e), a) {
      if (i.then(ki, ki), t)
        return i.then((l) => {
          pn(!0);
          try {
            Si(e, l, t);
          } finally {
            pn(!1);
          }
        }).catch((l) => {
          gr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      Si(e, i);
  } else
    $l(e);
}
function Si(e, t, s) {
  ne(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : xe(t) && (e.setupState = rl(t)), $l(e);
}
function $l(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || It);
  {
    const r = Sn(e);
    Mt();
    try {
      Xu(e);
    } finally {
      jt(), r();
    }
  }
}
const Nd = {
  get(e, t) {
    return Ke(e, "get", ""), e[t];
  }
};
function Pd(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Nd),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Cr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(rl(zo(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in ln)
        return ln[s](e);
    },
    has(t, s) {
      return s in t || s in ln;
    }
  })) : e.proxy;
}
function Md(e, t = !0) {
  return ne(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function jd(e) {
  return ne(e) && "__vccOpts" in e;
}
const Oe = (e, t) => /* @__PURE__ */ Cu(e, t, gn);
function yn(e, t, s) {
  try {
    Gn(-1);
    const n = arguments.length;
    return n === 2 ? xe(t) && !q(t) ? Ds(t) ? Y(e, null, [t]) : Y(e, t) : Y(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && Ds(s) && (s = [s]), Y(e, t, s));
  } finally {
    Gn(1);
  }
}
const Ld = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let mo;
const Ci = typeof window < "u" && window.trustedTypes;
if (Ci)
  try {
    mo = /* @__PURE__ */ Ci.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const Fl = mo ? (e) => mo.createHTML(e) : (e) => e, Dd = "http://www.w3.org/2000/svg", Vd = "http://www.w3.org/1998/Math/MathML", Bt = typeof document < "u" ? document : null, Ai = Bt && /* @__PURE__ */ Bt.createElement("template"), zd = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? Bt.createElementNS(Dd, e) : t === "mathml" ? Bt.createElementNS(Vd, e) : s ? Bt.createElement(e, { is: s }) : Bt.createElement(e);
    return e === "select" && n && n.multiple != null && r.setAttribute("multiple", n.multiple), r;
  },
  createText: (e) => Bt.createTextNode(e),
  createComment: (e) => Bt.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => Bt.querySelector(e),
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
      Ai.innerHTML = Fl(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const a = Ai.content;
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
}, $d = /* @__PURE__ */ Symbol("_vtc");
function Fd(e, t, s) {
  const n = e[$d];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const Ei = /* @__PURE__ */ Symbol("_vod"), Ud = /* @__PURE__ */ Symbol("_vsh"), Bd = /* @__PURE__ */ Symbol(""), Wd = /(?:^|;)\s*display\s*:/;
function Hd(e, t, s) {
  const n = e.style, r = Ne(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (Ne(t))
        for (const i of t.split(";")) {
          const a = i.slice(0, i.indexOf(":")).trim();
          s[a] == null && en(n, a, "");
        }
      else
        for (const i in t)
          s[i] == null && en(n, i, "");
    for (const i in s) {
      i === "display" && (o = !0);
      const a = s[i];
      a != null ? Gd(
        e,
        i,
        !Ne(t) && t ? t[i] : void 0,
        a
      ) || en(n, i, a) : en(n, i, "");
    }
  } else if (r) {
    if (t !== s) {
      const i = n[Bd];
      i && (s += ";" + i), n.cssText = s, o = Wd.test(s);
    }
  } else t && e.removeAttribute("style");
  Ei in e && ((!r || t !== s) && (e[Ei] = o ? n.display : ""), e[Ud] && (n.display = "none"));
}
const On = /\s*!important$/;
function en(e, t, s) {
  if (q(s))
    s.forEach((n) => en(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    On.test(s) ? e.setProperty(t, s.replace(On, ""), "important") : e.setProperty(t, s);
  else {
    const n = Zd(e, t);
    On.test(s) ? e.setProperty(
      Cs(n),
      s.replace(On, ""),
      "important"
    ) : e[n] = s;
  }
}
const Ri = ["Webkit", "Moz", "ms"], Vr = {};
function Zd(e, t) {
  const s = Vr[t];
  if (s)
    return s;
  let n = et(t);
  if (n !== "filter" && n in e)
    return Vr[t] = n;
  n = dr(n);
  for (let r = 0; r < Ri.length; r++) {
    const o = Ri[r] + n;
    if (o in e)
      return Vr[t] = o;
  }
  return t;
}
function Gd(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && Ne(n) && s === n;
}
const Oi = "http://www.w3.org/1999/xlink";
function Ti(e, t, s, n, r, o = Qc(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(Oi, t.slice(6, t.length)) : e.setAttributeNS(Oi, t, s) : s == null || o && !ja(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : ft(s) ? String(s) : s
  );
}
function Ii(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? Fl(s) : s);
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
    a === "boolean" ? s = ja(s) : s == null && a === "string" ? (s = "", i = !0) : a === "number" && (s = 0, i = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function ys(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function qd(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const Ni = /* @__PURE__ */ Symbol("_vei");
function Kd(e, t, s, n, r = null) {
  const o = e[Ni] || (e[Ni] = {}), i = o[t];
  if (n && i)
    i.value = n;
  else {
    const [a, l] = Qd(t);
    if (n) {
      const c = o[t] = tf(
        n,
        r
      );
      ys(e, a, c, l);
    } else i && (qd(e, a, i, l), o[t] = void 0);
  }
}
const Jd = /(Once|Passive|Capture)$/, Yd = /^on:?(?:Once|Passive|Capture)$/;
function Qd(e) {
  let t, s;
  for (; (s = e.match(Jd)) && !Yd.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Cs(e.slice(2)), t];
}
let zr = 0;
const Xd = /* @__PURE__ */ Promise.resolve(), ef = () => zr || (Xd.then(() => zr = 0), zr = Date.now());
function tf(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if (q(r)) {
      const o = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        o.call(n), n._stopped = !0;
      };
      const i = r.slice(), a = [n];
      for (let l = 0; l < i.length && !n._stopped; l++) {
        const c = i[l];
        c && _t(
          c,
          t,
          5,
          a
        );
      }
    } else
      _t(
        r,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = ef(), s;
}
const Pi = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, sf = (e, t, s, n, r, o) => {
  const i = r === "svg";
  t === "class" ? Fd(e, n, i) : t === "style" ? Hd(e, s, n) : ar(t) ? lr(t) || Kd(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : nf(e, t, n, i)) ? (Ii(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && Ti(e, t, n, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (rf(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !Ne(n))) ? Ii(e, et(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), Ti(e, t, n, i));
};
function nf(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && Pi(t) && ne(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return Pi(t) && Ne(s) ? !1 : t in e;
}
function rf(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = et(t);
  return Array.isArray(s) ? s.some((r) => et(r) === n) : Object.keys(s).some((r) => et(r) === n);
}
const Jn = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return q(t) ? (s) => Dn(t, s) : t;
};
function of(e) {
  e.target.composing = !0;
}
function Mi(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const bs = /* @__PURE__ */ Symbol("_assign"), Tn = /* @__PURE__ */ Symbol("_initialValue");
function $r(e, t, s) {
  return t && (e = e.trim()), s && (e = fr(e)), e;
}
const Yn = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[Tn] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[Tn] = e.defaultValue.replace(/\r\n?/g, `
`))), e[bs] = Jn(r);
    const o = n || r.props && r.props.type === "number";
    ys(e, t ? "change" : "input", (i) => {
      i.target.composing || e[bs]($r(e.value, s, o));
    }), (s || o) && ys(e, "change", () => {
      e.value = $r(e.value, s, o);
    }), t || (ys(e, "compositionstart", of), ys(e, "compositionend", Mi), ys(e, "change", Mi));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[Tn];
    delete e[Tn], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[bs]($r(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, i) {
    if (e[bs] = Jn(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? fr(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, Ul = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, ys(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? fr(Qn(l)) : Qn(l)
      ), o = e.multiple, i = o ? ks(e._modelValue) ? new Set(r) : r : r[0], a = e._pendingValue = [
        o,
        o ? q(i) ? r.slice() : r : i
      ];
      try {
        e[bs](i);
      } finally {
        yr(() => {
          e._pendingValue === a && (e._pendingValue = void 0);
        });
      }
    }), e[bs] = Jn(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    ji(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[bs] = Jn(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !af(t, s[1], s[0])) && ji(e, t);
  }
};
function af(e, t, s) {
  if (!s || q(e)) return is(e, t);
  if (ks(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function ji(e, t) {
  const s = e.multiple, n = q(t);
  if (!(s && !n && !ks(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const i = e.options[r], a = Qn(i);
      if (s)
        if (n) {
          const l = typeof a;
          l === "string" || l === "number" ? i.selected = t.some((c) => String(c) === String(a)) : i.selected = tu(t, a) > -1;
        } else
          i.selected = t.has(a);
      else if (is(Qn(i), t)) {
        e.selectedIndex !== r && (e.selectedIndex = r);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function Qn(e) {
  return "_value" in e ? e._value : e.value;
}
const lf = /* @__PURE__ */ qe({ patchProp: sf }, zd);
let Li;
function cf() {
  return Li || (Li = bd(lf));
}
const uf = ((...e) => {
  const t = cf().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = ff(n);
    if (!r) return;
    const o = t._component;
    !ne(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = s(r, !1, df(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function df(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function ff(e) {
  return Ne(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let Bl;
const Ar = (e) => Bl = e, Wl = (
  /* istanbul ignore next */
  Symbol()
);
function po(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var cn;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(cn || (cn = {}));
function hf() {
  const e = za(!0), t = e.run(() => /* @__PURE__ */ le({}));
  let s = [], n = [];
  const r = zo({
    install(o) {
      Ar(r), r._a = o, o.provide(Wl, r), o.config.globalProperties.$pinia = r, n.forEach((i) => s.push(i)), n = [];
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
const Hl = () => {
};
function Di(e, t, s, n = Hl) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && No() && $a(r), r;
}
function Rs(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const mf = (e) => e(), Vi = Symbol(), Fr = Symbol();
function go(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    po(r) && po(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ De(n) && !/* @__PURE__ */ Nt(n) ? e[s] = go(r, n) : e[s] = n;
  }
  return e;
}
const pf = (
  /* istanbul ignore next */
  Symbol()
);
function gf(e) {
  return !po(e) || !Object.prototype.hasOwnProperty.call(e, pf);
}
const { assign: Xt } = Object;
function yf(e) {
  return !!(/* @__PURE__ */ De(e) && e.effect);
}
function vf(e, t, s, n) {
  const { state: r, actions: o, getters: i } = t, a = s.state.value[e];
  let l;
  function c() {
    a || (s.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ xu(s.state.value[e]);
    return Xt(u, o, Object.keys(i || {}).reduce((d, h) => (d[h] = zo(Oe(() => {
      Ar(s);
      const p = s._s.get(e);
      return i[h].call(p, p);
    })), d), {}));
  }
  return l = Zl(e, c, t, s, n, !0), l;
}
function Zl(e, t, s = {}, n, r, o) {
  let i;
  const a = Xt({ actions: {} }, s), l = { deep: !0 };
  let c, u, d = /* @__PURE__ */ new Set(), h = /* @__PURE__ */ new Set(), p;
  const w = n.state.value[e];
  !o && !w && (n.state.value[e] = {});
  let _;
  function L(C) {
    let H;
    c = u = !1, typeof C == "function" ? (C(n.state.value[e]), H = {
      type: cn.patchFunction,
      storeId: e,
      events: p
    }) : (go(n.state.value[e], C), H = {
      type: cn.patchObject,
      payload: C,
      storeId: e,
      events: p
    });
    const ve = _ = Symbol();
    yr().then(() => {
      _ === ve && (c = !0);
    }), u = !0, Rs(d, H, n.state.value[e]);
  }
  const z = o ? function() {
    const { state: H } = s, ve = H ? H() : {};
    this.$patch((Pe) => {
      Xt(Pe, ve);
    });
  } : (
    /* istanbul ignore next */
    Hl
  );
  function S() {
    i.stop(), d.clear(), h.clear(), n._s.delete(e);
  }
  const T = (C, H = "") => {
    if (Vi in C)
      return C[Fr] = H, C;
    const ve = function() {
      Ar(n);
      const Pe = Array.from(arguments), K = /* @__PURE__ */ new Set(), Ce = /* @__PURE__ */ new Set();
      function Me(X) {
        K.add(X);
      }
      function me(X) {
        Ce.add(X);
      }
      Rs(h, {
        args: Pe,
        name: ve[Fr],
        store: Q,
        after: Me,
        onError: me
      });
      let ce;
      try {
        ce = C.apply(this && this.$id === e ? this : Q, Pe);
      } catch (X) {
        throw Rs(Ce, X), X;
      }
      return ce instanceof Promise ? ce.then((X) => (Rs(K, X), X)).catch((X) => (Rs(Ce, X), Promise.reject(X))) : (Rs(K, ce), ce);
    };
    return ve[Vi] = !0, ve[Fr] = H, ve;
  }, P = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: Di.bind(null, h),
    $patch: L,
    $reset: z,
    $subscribe(C, H = {}) {
      const ve = Di(d, C, H.detached, () => Pe()), Pe = i.run(() => Ms(() => n.state.value[e], (K) => {
        (H.flush === "sync" ? u : c) && C({
          storeId: e,
          type: cn.direct,
          events: p
        }, K);
      }, Xt({}, l, H)));
      return ve;
    },
    $dispose: S
  }, Q = /* @__PURE__ */ wn(P);
  n._s.set(e, Q);
  const re = (n._a && n._a.runWithContext || mf)(() => n._e.run(() => (i = za()).run(() => t({ action: T }))));
  for (const C in re) {
    const H = re[C];
    if (/* @__PURE__ */ De(H) && !yf(H) || /* @__PURE__ */ Nt(H))
      o || (w && gf(H) && (/* @__PURE__ */ De(H) ? H.value = w[C] : go(H, w[C])), n.state.value[e][C] = H);
    else if (typeof H == "function") {
      const ve = T(H, C);
      re[C] = ve, a.actions[C] = H;
    }
  }
  return Xt(Q, re), Xt(/* @__PURE__ */ pe(Q), re), Object.defineProperty(Q, "$state", {
    get: () => n.state.value[e],
    set: (C) => {
      L((H) => {
        Xt(H, C);
      });
    }
  }), n._p.forEach((C) => {
    Xt(Q, i.run(() => C({
      store: Q,
      app: n._a,
      pinia: n,
      options: a
    })));
  }), w && o && s.hydrate && s.hydrate(Q.$state, w), c = !0, u = !0, Q;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function Zs(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(i, a) {
    const l = Fo();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? rt(Wl, null) : null), i && Ar(i), i = Bl, i._s.has(e) || (r ? Zl(e, t, n, i) : vf(e, n, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const Ts = typeof document < "u";
function Gl(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function bf(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && Gl(e.default);
}
const Te = Object.assign;
function Ur(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = xt(r) ? r.map(e) : e(r);
  }
  return s;
}
const un = () => {
}, xt = Array.isArray;
function zi(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const ql = /#/g, _f = /&/g, xf = /\//g, wf = /=/g, kf = /\?/g, Kl = /\+/g, Sf = /%5B/g, Cf = /%5D/g, Jl = /%5E/g, Af = /%60/g, Yl = /%7B/g, Ef = /%7C/g, Ql = /%7D/g, Rf = /%20/g;
function Go(e) {
  return e == null ? "" : encodeURI("" + e).replace(Ef, "|").replace(Sf, "[").replace(Cf, "]");
}
function Of(e) {
  return Go(e).replace(Yl, "{").replace(Ql, "}").replace(Jl, "^");
}
function yo(e) {
  return Go(e).replace(Kl, "%2B").replace(Rf, "+").replace(ql, "%23").replace(_f, "%26").replace(Af, "`").replace(Yl, "{").replace(Ql, "}").replace(Jl, "^");
}
function Tf(e) {
  return yo(e).replace(wf, "%3D");
}
function If(e) {
  return Go(e).replace(ql, "%23").replace(kf, "%3F");
}
function Nf(e) {
  return If(e).replace(xf, "%2F");
}
function vn(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const Pf = /\/$/, Mf = (e) => e.replace(Pf, "");
function Br(e, t, s = "/") {
  let n, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (n = n || t.slice(0, a), i = t.slice(a, t.length)), n = Vf(n ?? t, s), {
    fullPath: n + o + i,
    path: n,
    query: r,
    hash: vn(i)
  };
}
function jf(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Lf(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && zs(t.matched[n], s.matched[r]) && Xl(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function zs(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function Xl(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!Df(e[s], t[s])) return !1;
  return !0;
}
function Df(e, t) {
  return xt(e) ? $i(e, t) : xt(t) ? $i(t, e) : e?.valueOf() === t?.valueOf();
}
function $i(e, t) {
  return xt(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function Vf(e, t) {
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
const Yt = {
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
let vo = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), Fi = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const Wr = "";
function zf(e) {
  if (!e) if (Ts) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), Mf(e);
}
const $f = /^[^#]+#/;
function Ff(e, t) {
  return e.replace($f, "#") + t;
}
function Uf(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const Bf = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function Wf(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = Uf(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function Ui(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const bo = /* @__PURE__ */ new Map();
function Hf(e, t) {
  bo.set(e, t);
}
function Zf(e) {
  const t = bo.get(e);
  return bo.delete(e), t;
}
function Gf(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function ec(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let je = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const tc = Symbol("");
je.MATCHER_NOT_FOUND + "", je.NAVIGATION_GUARD_REDIRECT + "", je.NAVIGATION_ABORTED + "", je.NAVIGATION_CANCELLED + "", je.NAVIGATION_DUPLICATED + "";
function $s(e, t) {
  return Te(/* @__PURE__ */ new Error(), {
    type: e,
    [tc]: !0
  }, t);
}
function Ft(e, t) {
  return e instanceof Error && tc in e && (t == null || !!(e.type & t));
}
const qf = [
  "params",
  "query",
  "hash"
];
function Kf(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of qf) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function Jf(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(Kl, " "), o = r.indexOf("="), i = vn(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : vn(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      xt(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function Bi(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Tf(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (xt(n) ? n.map((r) => r && yo(r)) : [n && yo(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function Yf(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = xt(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const Qf = Symbol(""), Wi = Symbol(""), Er = Symbol(""), qo = Symbol(""), _o = Symbol("");
function Js() {
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
function ts(e, t, s, n, r, o = (i) => i()) {
  const i = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (h) => {
      h === !1 ? l($s(je.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : h instanceof Error ? l(h) : Gf(h) ? l($s(je.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: h
      })) : (i && n.enterCallbacks[r] === i && typeof h == "function" && i.push(h), a());
    }, u = o(() => e.call(n && n.instances[r], t, s, c));
    let d = Promise.resolve(u);
    e.length < 3 && (d = d.then(c)), d.catch((h) => l(h));
  });
}
function Hr(e, t, s, n, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (Gl(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(ts(c, s, n, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const d = bf(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = d;
            const h = (d.__vccOpts || d)[t];
            return h && ts(h, s, n, i, a, r)();
          }));
        }
    }
  return o;
}
function Xf(e, t) {
  const s = [], n = [], r = [], o = Math.max(t.matched.length, e.matched.length);
  for (let i = 0; i < o; i++) {
    const a = t.matched[i];
    a && (e.matched.find((c) => zs(c, a)) ? n.push(a) : s.push(a));
    const l = e.matched[i];
    l && (t.matched.find((c) => zs(c, l)) || r.push(l));
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
function eh(e = "") {
  let t = [], s = [[Wr, {}]], n = 0;
  e = zf(e);
  function r(a, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const d = {
      direction: c,
      delta: u,
      type: vo.pop
    };
    for (const h of t) h(a, l, d);
  }
  const i = {
    location: Wr,
    state: {},
    base: e,
    createHref: Ff.bind(null, e),
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
      t = [], s = [[Wr, {}]], n = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? Fi.back : Fi.forward;
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
let _s = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var Fe = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(Fe || {});
const th = {
  type: _s.Static,
  value: ""
}, sh = /[a-zA-Z0-9_]/;
function nh(e) {
  if (!e) return [[]];
  if (e === "/") return [[th]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(p) {
    throw new Error(`ERR (${s})/"${c}": ${p}`);
  }
  let s = Fe.Static, n = s;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function d() {
    c && (s === Fe.Static ? o.push({
      type: _s.Static,
      value: c
    }) : s === Fe.Param || s === Fe.ParamRegExp || s === Fe.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: _s.Param,
      value: c,
      regexp: u,
      repeatable: l === "*" || l === "+",
      optional: l === "*" || l === "?"
    })) : t("Invalid state to consume buffer"), c = "");
  }
  function h() {
    c += l;
  }
  for (; a < e.length; ) {
    if (l = e[a++], l === "\\" && s !== Fe.ParamRegExp) {
      n = s, s = Fe.EscapeNext;
      continue;
    }
    switch (s) {
      case Fe.Static:
        l === "/" ? (c && d(), i()) : l === ":" ? (d(), s = Fe.Param) : h();
        break;
      case Fe.EscapeNext:
        h(), s = n;
        break;
      case Fe.Param:
        l === "(" ? s = Fe.ParamRegExp : sh.test(l) ? h() : (d(), s = Fe.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case Fe.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : s = Fe.ParamRegExpEnd : u += l;
        break;
      case Fe.ParamRegExpEnd:
        d(), s = Fe.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === Fe.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), d(), i(), r;
}
const Hi = "[^/]+?", rh = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var Qe = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(Qe || {});
const oh = /[.+*?^${}()[\]/\\]/g;
function ih(e, t) {
  const s = Te({}, rh, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [Qe.Root];
    s.strict && !c.length && (r += "/");
    for (let d = 0; d < c.length; d++) {
      const h = c[d];
      let p = Qe.Segment + (s.sensitive ? Qe.BonusCaseSensitive : 0);
      if (h.type === _s.Static)
        d || (r += "/"), r += h.value.replace(oh, "\\$&"), p += Qe.Static;
      else if (h.type === _s.Param) {
        const { value: w, repeatable: _, optional: L, regexp: z } = h;
        o.push({
          name: w,
          repeatable: _,
          optional: L
        });
        const S = z || Hi;
        if (S !== Hi) {
          p += Qe.BonusCustomRegExp;
          try {
            `${S}`;
          } catch (P) {
            throw new Error(`Invalid custom RegExp for param "${w}" (${S}): ` + P.message);
          }
        }
        let T = _ ? `((?:${S})(?:/(?:${S}))*)` : `(${S})`;
        d || (T = L && c.length < 2 ? `(?:/${T})` : "/" + T), L && (T += "?"), r += T, p += Qe.Dynamic, L && (p += Qe.BonusOptional), _ && (p += Qe.BonusRepeatable), S === ".*" && (p += Qe.BonusWildcard);
      }
      u.push(p);
    }
    n.push(u);
  }
  if (s.strict && s.end) {
    const c = n.length - 1;
    n[c][n[c].length - 1] += Qe.BonusStrict;
  }
  s.strict || (r += "/?"), s.end ? r += "$" : s.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const i = new RegExp(r, s.sensitive ? "" : "i");
  function a(c) {
    const u = c.match(i), d = {};
    if (!u) return null;
    for (let h = 1; h < u.length; h++) {
      const p = u[h] || "", w = o[h - 1];
      d[w.name] = p && w.repeatable ? p.split("/") : p;
    }
    return d;
  }
  function l(c) {
    let u = "", d = !1;
    for (const h of e) {
      (!d || !u.endsWith("/")) && (u += "/"), d = !1;
      for (const p of h) if (p.type === _s.Static) u += p.value;
      else if (p.type === _s.Param) {
        const { value: w, repeatable: _, optional: L } = p, z = w in c ? c[w] : "";
        if (xt(z) && !_) throw new Error(`Provided param "${w}" is an array but it is not repeatable (* or + modifiers)`);
        const S = xt(z) ? z.join("/") : z;
        if (!S) if (L)
          h.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : d = !0);
        else throw new Error(`Missing required param "${w}"`);
        u += S;
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
function ah(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === Qe.Static + Qe.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === Qe.Static + Qe.Segment ? 1 : -1 : 0;
}
function sc(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = ah(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (Zi(n)) return 1;
    if (Zi(r)) return -1;
  }
  return r.length - n.length;
}
function Zi(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const lh = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function ch(e, t, s) {
  const n = ih(nh(e.path), s), r = Te(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function uh(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = zi(lh, t);
  function r(d) {
    return n.get(d);
  }
  function o(d, h, p) {
    const w = !p, _ = qi(d);
    _.aliasOf = p && p.record;
    const L = zi(t, d), z = [_];
    if ("alias" in d) {
      const P = typeof d.alias == "string" ? [d.alias] : d.alias;
      for (const Q of P) z.push(qi(Te({}, _, {
        components: p ? p.record.components : _.components,
        path: Q,
        aliasOf: p ? p.record : _
      })));
    }
    let S, T;
    for (const P of z) {
      const { path: Q } = P;
      if (h && Q[0] !== "/") {
        const be = h.record.path, re = be[be.length - 1] === "/" ? "" : "/";
        P.path = h.record.path + (Q && re + Q);
      }
      if (S = ch(P, h, L), p ? p.alias.push(S) : (T = T || S, T !== S && T.alias.push(S), w && d.name && !Ki(S) && i(d.name)), nc(S) && l(S), _.children) {
        const be = _.children;
        for (let re = 0; re < be.length; re++) o(be[re], S, p && p.children[re]);
      }
      p = p || S;
    }
    return T ? () => {
      i(T);
    } : un;
  }
  function i(d) {
    if (ec(d)) {
      const h = n.get(d);
      h && (n.delete(d), s.splice(s.indexOf(h), 1), h.children.forEach(i), h.alias.forEach(i));
    } else {
      const h = s.indexOf(d);
      h > -1 && (s.splice(h, 1), d.record.name && n.delete(d.record.name), d.children.forEach(i), d.alias.forEach(i));
    }
  }
  function a() {
    return s;
  }
  function l(d) {
    const h = hh(d, s);
    s.splice(h, 0, d), d.record.name && !Ki(d) && n.set(d.record.name, d);
  }
  function c(d, h) {
    let p, w = {}, _, L;
    if ("name" in d && d.name) {
      if (p = n.get(d.name), !p) throw $s(je.MATCHER_NOT_FOUND, { location: d });
      L = p.record.name, w = Te(Gi(h.params, p.keys.filter((T) => !T.optional).concat(p.parent ? p.parent.keys.filter((T) => T.optional) : []).map((T) => T.name)), d.params && Gi(d.params, p.keys.map((T) => T.name))), _ = p.stringify(w);
    } else if (d.path != null)
      _ = d.path, p = s.find((T) => T.re.test(_)), p && (w = p.parse(_), L = p.record.name);
    else {
      if (p = h.name ? n.get(h.name) : s.find((T) => T.re.test(h.path)), !p) throw $s(je.MATCHER_NOT_FOUND, {
        location: d,
        currentLocation: h
      });
      L = p.record.name, w = Te({}, h.params, d.params), _ = p.stringify(w);
    }
    const z = [];
    let S = p;
    for (; S; )
      z.unshift(S.record), S = S.parent;
    return {
      name: L,
      path: _,
      params: w,
      matched: z,
      meta: fh(z)
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
function Gi(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function qi(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: dh(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function dh(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function Ki(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function fh(e) {
  return e.reduce((t, s) => Te(t, s.meta), {});
}
function hh(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    sc(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = mh(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function mh(e) {
  let t = e;
  for (; t = t.parent; ) if (nc(t) && sc(e, t) === 0) return t;
}
function nc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function Ji(e) {
  const t = rt(Er), s = rt(qo), n = Oe(() => {
    const l = D(e.to);
    return t.resolve(l);
  }), r = Oe(() => {
    const { matched: l } = n.value, { length: c } = l, u = l[c - 1], d = s.matched;
    if (!u || !d.length) return -1;
    const h = d.findIndex(zs.bind(null, u));
    if (h > -1) return h;
    const p = Yi(l[c - 2]);
    return c > 1 && Yi(u) === p && d[d.length - 1].path !== p ? d.findIndex(zs.bind(null, l[c - 2])) : h;
  }), o = Oe(() => r.value > -1 && vh(s.params, n.value.params)), i = Oe(() => r.value > -1 && r.value === s.matched.length - 1 && Xl(s.params, n.value.params));
  function a(l = {}) {
    if (yh(l)) {
      const c = t[D(e.replace) ? "replace" : "push"](D(e.to)).catch(un);
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
function ph(e) {
  return e.length === 1 ? e[0] : e;
}
const gh = /* @__PURE__ */ Vt({
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
  useLink: Ji,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ wn(Ji(e)), { options: n } = rt(Er), r = Oe(() => ({
      [Qi(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [Qi(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && ph(t.default(s));
      return e.custom ? o : yn("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), rc = gh;
function yh(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function vh(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!xt(r) || r.length !== n.length || n.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function Yi(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const Qi = (e, t, s) => e ?? t ?? s, bh = /* @__PURE__ */ Vt({
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
    const n = rt(_o), r = Oe(() => e.route || n.value), o = rt(Wi, 0), i = Oe(() => {
      let c = D(o);
      const { matched: u } = r.value;
      let d;
      for (; (d = u[c]) && !d.components; ) c++;
      return c;
    }), a = Oe(() => r.value.matched[i.value]);
    Vn(Wi, Oe(() => i.value + 1)), Vn(Qf, a), Vn(_o, r);
    const l = /* @__PURE__ */ le();
    return Ms(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, d], [h, p, w]) => {
      u && (u.instances[d] = c, p && p !== u && c && c === h && (u.leaveGuards.size || (u.leaveGuards = p.leaveGuards), u.updateGuards.size || (u.updateGuards = p.updateGuards))), c && u && (!p || !zs(u, p) || !h) && (u.enterCallbacks[d] || []).forEach((_) => _(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, d = a.value, h = d && d.components[u];
      if (!h) return Xi(s.default, {
        Component: h,
        route: c
      });
      const p = d.props[u], w = p ? p === !0 ? c.params : typeof p == "function" ? p(c) : p : null, L = yn(h, Te({}, w, t, {
        onVnodeUnmounted: (z) => {
          z.component.isUnmounted && (d.instances[u] = null);
        },
        ref: l
      }));
      return Xi(s.default, {
        Component: L,
        route: c
      }) || L;
    };
  }
});
function Xi(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const oc = bh;
function _h(e) {
  const t = uh(e.routes, e), s = e.parseQuery || Jf, n = e.stringifyQuery || Bi, r = e.history, o = Js(), i = Js(), a = Js(), l = /* @__PURE__ */ on(Yt);
  let c = Yt;
  Ts && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = Ur.bind(null, (b) => "" + b), d = Ur.bind(null, Nf), h = Ur.bind(null, vn);
  function p(b, $) {
    let E, J;
    return ec(b) ? (E = t.getRecordMatcher(b), J = $) : J = b, t.addRoute(J, E);
  }
  function w(b) {
    const $ = t.getRecordMatcher(b);
    $ && t.removeRoute($);
  }
  function _() {
    return t.getRoutes().map((b) => b.record);
  }
  function L(b) {
    return !!t.getRecordMatcher(b);
  }
  function z(b, $) {
    if ($ = Te({}, $ || l.value), typeof b == "string") {
      const y = Br(s, b, $.path), v = t.resolve({ path: y.path }, $), x = r.createHref(y.fullPath);
      return Te(y, v, {
        params: h(v.params),
        hash: vn(y.hash),
        redirectedFrom: void 0,
        href: x
      });
    }
    let E;
    if (b.path != null)
      E = Te({}, b, { path: Br(s, b.path, $.path).path });
    else {
      const y = Te({}, b.params);
      for (const v in y) y[v] == null && delete y[v];
      E = Te({}, b, { params: d(y) }), $.params = d($.params);
    }
    const J = t.resolve(E, $), f = b.hash || "";
    J.params = u(h(J.params));
    const m = jf(n, Te({}, b, {
      hash: Of(f),
      path: J.path
    })), g = r.createHref(m);
    return Te({
      fullPath: m,
      hash: f,
      query: n === Bi ? Yf(b.query) : b.query || {}
    }, J, {
      redirectedFrom: void 0,
      href: g
    });
  }
  function S(b) {
    return typeof b == "string" ? Br(s, b, l.value.path) : Te({}, b);
  }
  function T(b, $) {
    if (c !== b) return $s(je.NAVIGATION_CANCELLED, {
      from: $,
      to: b
    });
  }
  function P(b) {
    return re(b);
  }
  function Q(b) {
    return P(Te(S(b), { replace: !0 }));
  }
  function be(b, $) {
    const E = b.matched[b.matched.length - 1];
    if (E && E.redirect) {
      const { redirect: J } = E;
      let f = typeof J == "function" ? J(b, $) : J;
      return typeof f == "string" && (f = f.includes("?") || f.includes("#") ? f = S(f) : { path: f }, f.params = {}), Te({
        query: b.query,
        hash: b.hash,
        params: f.path != null ? {} : b.params
      }, f);
    }
  }
  function re(b, $) {
    const E = c = z(b), J = l.value, f = b.state, m = b.force, g = b.replace === !0, y = be(E, J);
    if (y) return re(Te(S(y), {
      state: typeof y == "object" ? Te({}, f, y.state) : f,
      force: m,
      replace: g
    }), $ || E);
    const v = E;
    v.redirectedFrom = $;
    let x;
    return !m && Lf(n, J, E) && (x = $s(je.NAVIGATION_DUPLICATED, {
      to: v,
      from: J
    }), at(J, J, !0, !1)), (x ? Promise.resolve(x) : ve(v, J)).catch((A) => Ft(A) ? Ft(A, je.NAVIGATION_GUARD_REDIRECT) ? A : B(A) : de(A, v, J)).then((A) => {
      if (A) {
        if (Ft(A, je.NAVIGATION_GUARD_REDIRECT))
          return re(Te({ replace: g }, S(A.to), {
            state: typeof A.to == "object" ? Te({}, f, A.to.state) : f,
            force: m
          }), $ || v);
      } else A = K(v, J, !0, g, f);
      return Pe(v, J, A), A;
    });
  }
  function C(b, $) {
    const E = T(b, $);
    return E ? Promise.reject(E) : Promise.resolve();
  }
  function H(b) {
    const $ = yt.values().next().value;
    return $ && typeof $.runWithContext == "function" ? $.runWithContext(b) : b();
  }
  function ve(b, $) {
    let E;
    const [J, f, m] = Xf(b, $);
    E = Hr(J.reverse(), "beforeRouteLeave", b, $);
    for (const y of J) y.leaveGuards.forEach((v) => {
      E.push(ts(v, b, $));
    });
    const g = C.bind(null, b, $);
    return E.push(g), we(E).then(() => {
      E = [];
      for (const y of o.list()) E.push(ts(y, b, $));
      return E.push(g), we(E);
    }).then(() => {
      E = Hr(f, "beforeRouteUpdate", b, $);
      for (const y of f) y.updateGuards.forEach((v) => {
        E.push(ts(v, b, $));
      });
      return E.push(g), we(E);
    }).then(() => {
      E = [];
      for (const y of m) if (y.beforeEnter) if (xt(y.beforeEnter)) for (const v of y.beforeEnter) E.push(ts(v, b, $));
      else E.push(ts(y.beforeEnter, b, $));
      return E.push(g), we(E);
    }).then(() => (b.matched.forEach((y) => y.enterCallbacks = {}), E = Hr(m, "beforeRouteEnter", b, $, H), E.push(g), we(E))).then(() => {
      E = [];
      for (const y of i.list()) E.push(ts(y, b, $));
      return E.push(g), we(E);
    }).catch((y) => Ft(y, je.NAVIGATION_CANCELLED) ? y : Promise.reject(y));
  }
  function Pe(b, $, E) {
    a.list().forEach((J) => H(() => J(b, $, E)));
  }
  function K(b, $, E, J, f) {
    const m = T(b, $);
    if (m) return m;
    const g = $ === Yt, y = Ts ? history.state : {};
    E && (J || g ? r.replace(b.fullPath, Te({ scroll: g && y && y.scroll }, f)) : r.push(b.fullPath, f)), l.value = b, at(b, $, E, g), B();
  }
  let Ce;
  function Me() {
    Ce || (Ce = r.listen((b, $, E) => {
      if (!Ie.listening) return;
      const J = z(b), f = be(J, Ie.currentRoute.value);
      if (f) {
        re(Te(f, {
          replace: !0,
          force: !0
        }), J).catch(un);
        return;
      }
      c = J;
      const m = l.value;
      Ts && Hf(Ui(m.fullPath, E.delta), Bf()), ve(J, m).catch((g) => Ft(g, je.NAVIGATION_ABORTED | je.NAVIGATION_CANCELLED) ? g : Ft(g, je.NAVIGATION_GUARD_REDIRECT) ? (re(Te(S(g.to), { force: !0 }), J).then((y) => {
        Ft(y, je.NAVIGATION_ABORTED | je.NAVIGATION_DUPLICATED) && !E.delta && E.type === vo.pop && r.go(-1, !1);
      }).catch(un), Promise.reject()) : (E.delta && r.go(-E.delta, !1), de(g, J, m))).then((g) => {
        g = g || K(J, m, !1), g && (E.delta && !Ft(g, je.NAVIGATION_CANCELLED) ? r.go(-E.delta, !1) : E.type === vo.pop && Ft(g, je.NAVIGATION_ABORTED | je.NAVIGATION_DUPLICATED) && r.go(-1, !1)), Pe(J, m, g);
      }).catch(un);
    }));
  }
  let me = Js(), ce = Js(), X;
  function de(b, $, E) {
    B(b);
    const J = ce.list();
    return J.length ? J.forEach((f) => f(b, $, E)) : console.error(b), Promise.reject(b);
  }
  function it() {
    return X && l.value !== Yt ? Promise.resolve() : new Promise((b, $) => {
      me.add([b, $]);
    });
  }
  function B(b) {
    return X || (X = !b, Me(), me.list().forEach(([$, E]) => b ? E(b) : $()), me.reset()), b;
  }
  function at(b, $, E, J) {
    const { scrollBehavior: f } = e;
    if (!Ts || !f) return Promise.resolve();
    const m = !E && Zf(Ui(b.fullPath, 0)) || (J || !E) && history.state && history.state.scroll || null;
    return yr().then(() => f(b, $, m)).then((g) => g && Wf(g)).catch((g) => de(g, b, $));
  }
  const Be = (b) => r.go(b);
  let zt;
  const yt = /* @__PURE__ */ new Set(), Ie = {
    currentRoute: l,
    listening: !0,
    addRoute: p,
    removeRoute: w,
    clearRoutes: t.clearRoutes,
    hasRoute: L,
    getRoutes: _,
    resolve: z,
    options: e,
    push: P,
    replace: Q,
    go: Be,
    back: () => Be(-1),
    forward: () => Be(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: ce.add,
    isReady: it,
    install(b) {
      b.component("RouterLink", rc), b.component("RouterView", oc), b.config.globalProperties.$router = Ie, Object.defineProperty(b.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => D(l)
      }), Ts && !zt && l.value === Yt && (zt = !0, P(r.location).catch((J) => {
      }));
      const $ = {};
      for (const J in Yt) Object.defineProperty($, J, {
        get: () => l.value[J],
        enumerable: !0
      });
      b.provide(Er, Ie), b.provide(qo, /* @__PURE__ */ sl($)), b.provide(_o, l);
      const E = b.unmount;
      yt.add(b), b.unmount = function() {
        yt.delete(b), yt.size < 1 && (c = Yt, Ce && Ce(), Ce = null, l.value = Yt, zt = !1, X = !1), E();
      };
    }
  };
  function we(b) {
    return b.reduce(($, E) => $.then(() => H(E)), Promise.resolve());
  }
  return Ie;
}
function xh() {
  return rt(Er);
}
function wh(e) {
  return rt(qo);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ms = {
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
const ea = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Zr(e) {
  return e != null;
}
function kh(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (h) => s[h] ?? h, r = e.size ?? e.width ?? ms.width, o = e.size ?? e.height ?? ms.height, i = e.aliases?.filter((h) => typeof h == "string" && h.trim() !== "").map((h) => `lucide-${h}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? ea(...l) : ea("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? ms["stroke-width"]) * Number(e.size ?? e.width ?? ms.width) / Number(t.size ?? t.width ?? ms.width) : t.strokeWidth ?? ms["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(ms).reduce((h, [p, w]) => (h[n(p)] = w, h), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && Zr(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && Zr(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && Zr(t.height) && {
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
    e.node.map((h) => {
      const [p, w, _] = h, L = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...w } : w;
      return _ ? [p, L, _] : [p, L];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Sh = (e) => {
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
const In = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ch = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ah = /* @__PURE__ */ Symbol("lucide-icons");
function Eh() {
  return rt(Ah, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Rh = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && Ch(e),
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
  height: h = u,
  color: p,
  ...w
}, { slots: _ }) => {
  const {
    size: L,
    color: z,
    strokeWidth: S = 2,
    absoluteStrokeWidth: T = !1,
    nonScalingStroke: P = !1,
    class: Q = ""
  } = Eh(), be = In(r) || In(o) || r === !0 || o === !0 || T === !0, re = In(i) || In(a) || i === !0 || a === !0 || P === !0;
  delete w.class;
  const C = _.default?.(), [, H, ve = []] = kh(n, {
    color: p ?? z,
    width: d ?? u ?? L,
    height: h ?? u ?? L,
    strokeWidth: l ?? c ?? S,
    absoluteStrokeWidth: be,
    nonScalingStroke: re,
    className: Q,
    hasA11yProp: C != null && C.length > 0 || Sh(w),
    attributes: w
  });
  return yn("svg", H, [
    ...ve.map(([Pe, K]) => yn(Pe, K)),
    ...C ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function us(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => yn(
    Rh,
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
const Oh = {
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
}, ic = us(Oh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Th = {
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
}, ac = us(Th);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ih = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, Nh = us(Ih);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ph = {
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
}, Mh = us(Ph);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const jh = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, lc = us(jh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Lh = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, cc = us(Lh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Dh = {
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
}, uc = us(Dh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Vh = {
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
}, dc = us(Vh);
function zh(e) {
  return No() ? ($a(e), !0) : !1;
}
const Gr = /* @__PURE__ */ new WeakMap(), $h = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const s = e[0], n = (t = Sr()) == null ? void 0 : t.proxy;
  if (n == null && !Fo())
    throw new Error("injectLocal must be called in setup");
  return n && Gr.has(n) && s in Gr.get(n) ? Gr.get(n)[s] : rt(...e);
}, Fh = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const Uh = Object.prototype.toString, Bh = (e) => Uh.call(e) === "[object Object]";
function ta(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function qr(e) {
  return Array.isArray(e) ? e : [e];
}
function Wh(e, t, s) {
  return Ms(
    e,
    t,
    {
      ...s,
      immediate: !0
    }
  );
}
const fc = Fh ? window : void 0;
function Hh(e) {
  var t;
  const s = Ns(e);
  return (t = s?.$el) != null ? t : s;
}
function Zh(...e) {
  const t = [], s = () => {
    t.forEach((a) => a()), t.length = 0;
  }, n = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = Oe(() => {
    const a = qr(Ns(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = Wh(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => Hh(c))) != null ? l : [fc].filter((c) => c != null),
        qr(Ns(r.value ? e[1] : e[0])),
        qr(D(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Ns(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (s(), !a?.length || !l?.length || !c?.length)
        return;
      const d = Bh(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (h) => l.flatMap(
            (p) => c.map((w) => n(h, p, w, d))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), s();
  };
  return zh(s), i;
}
// @__NO_SIDE_EFFECTS__
function Gh() {
  const e = /* @__PURE__ */ on(!1), t = Sr();
  return t && _r(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function qh(e) {
  const t = /* @__PURE__ */ Gh();
  return Oe(() => (t.value, !!e()));
}
const Kh = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function Jh() {
  const e = Fo() ? /* @__PURE__ */ $h(Kh, null) : null;
  return typeof e == "number" ? e : void 0;
}
function Yh(e, t = {}) {
  const { window: s = fc, ssrWidth: n = /* @__PURE__ */ Jh() } = t, r = /* @__PURE__ */ qh(() => s && "matchMedia" in s && typeof s.matchMedia == "function"), o = /* @__PURE__ */ on(typeof n == "number"), i = /* @__PURE__ */ on(), a = /* @__PURE__ */ on(!1), l = (c) => {
    a.value = c.matches;
  };
  return Mu(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Ns(e).split(",");
      a.value = c.some((u) => {
        const d = u.includes("not all"), h = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), p = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let w = !!(h || p);
        return h && w && (w = n >= ta(h[1])), p && w && (w = n <= ta(p[1])), d ? !w : w;
      });
      return;
    }
    r.value && (i.value = s.matchMedia(Ns(e)), a.value = i.value.matches);
  }), Zh(i, "change", l, { passive: !0 }), Oe(() => a.value);
}
const hc = "comfymodal", Ko = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], Qh = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function ls(e) {
  return typeof e == "string" && Ko.indexOf(e) !== -1;
}
function Nn(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function mc(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || Nn(r.slice(0, o)) !== hc) return t;
  const i = Nn(r.slice(o + 1));
  if (!ls(i)) return t;
  let a = null;
  for (let l = 1; l < n.length; l++) {
    const c = n[l], u = c.indexOf("=");
    if (u === -1 || Nn(c.slice(0, u)) !== "focus") continue;
    const d = Nn(c.slice(u + 1));
    a = d === null || d === "" ? null : d;
    break;
  }
  return { matched: !0, page: i, focus: a };
}
function pc(e) {
  if (!ls(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + hc + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function sa(e, t) {
  if (!t || !ls(t.page)) return "none";
  if (!e || !ls(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function Xh(e, t) {
  if (e && ls(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = mc(t);
  return s.matched && ls(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
const em = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function Kr(e) {
  return em.has(e);
}
let na = 0;
function tm() {
  return na += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${na}`;
}
const Jo = /* @__PURE__ */ Zs("studio-operations", () => {
  const e = /* @__PURE__ */ le(/* @__PURE__ */ new Map()), t = Oe(() => [...e.value.values()]), s = Oe(
    () => t.value.filter((h) => h.status === "pending" || h.status === "running")
  );
  function n(h) {
    return e.value.get(h);
  }
  function r(h) {
    const p = Date.now(), w = tm(), _ = h.status === "pending" ? "pending" : "running";
    return e.value.set(w, {
      id: w,
      kind: h.kind,
      label: h.label,
      status: _,
      progress: h.progress,
      message: h.message,
      startedAt: p,
      finishedAt: void 0,
      workspaceId: h.workspaceId
    }), w;
  }
  function o(h, p) {
    const w = e.value.get(h);
    if (!w) return;
    const { status: _, ...L } = p, z = { ...w, ...L };
    !Kr(w.status) && _ !== void 0 && !Kr(_) && (z.status = _), e.value.set(h, z);
  }
  function i(h, p, w) {
    const _ = e.value.get(h);
    !_ || Kr(_.status) || e.value.set(h, {
      ..._,
      status: p,
      message: w === void 0 ? _.message : w,
      finishedAt: Date.now()
    });
  }
  function a(h, p) {
    i(h, "completed", p);
  }
  function l(h, p) {
    i(h, "failed", p);
  }
  function c(h, p) {
    i(h, "canceled", p);
  }
  function u(h) {
    e.value.delete(h);
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
var ge;
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
})(ge || (ge = {}));
var ra;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(ra || (ra = {}));
const U = ge.arrayToEnum([
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
]), ss = (e) => {
  switch (typeof e) {
    case "undefined":
      return U.undefined;
    case "string":
      return U.string;
    case "number":
      return Number.isNaN(e) ? U.nan : U.number;
    case "boolean":
      return U.boolean;
    case "function":
      return U.function;
    case "bigint":
      return U.bigint;
    case "symbol":
      return U.symbol;
    case "object":
      return Array.isArray(e) ? U.array : e === null ? U.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? U.promise : typeof Map < "u" && e instanceof Map ? U.map : typeof Set < "u" && e instanceof Set ? U.set : typeof Date < "u" && e instanceof Date ? U.date : U.object;
    default:
      return U.unknown;
  }
}, O = ge.arrayToEnum([
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
class Kt extends Error {
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
    if (!(t instanceof Kt))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, ge.jsonStringifyReplacer, 2);
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
Kt.create = (e) => new Kt(e);
const xo = (e, t) => {
  let s;
  switch (e.code) {
    case O.invalid_type:
      e.received === U.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case O.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, ge.jsonStringifyReplacer)}`;
      break;
    case O.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${ge.joinValues(e.keys, ", ")}`;
      break;
    case O.invalid_union:
      s = "Invalid input";
      break;
    case O.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${ge.joinValues(e.options)}`;
      break;
    case O.invalid_enum_value:
      s = `Invalid enum value. Expected ${ge.joinValues(e.options)}, received '${e.received}'`;
      break;
    case O.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case O.invalid_return_type:
      s = "Invalid function return type";
      break;
    case O.invalid_date:
      s = "Invalid date";
      break;
    case O.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : ge.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case O.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case O.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case O.custom:
      s = "Invalid input";
      break;
    case O.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case O.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case O.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, ge.assertNever(e);
  }
  return { message: s };
};
let sm = xo;
function nm() {
  return sm;
}
const rm = (e) => {
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
function j(e, t) {
  const s = nm(), n = rm({
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
      s === xo ? void 0 : xo
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(n);
}
class tt {
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
        return se;
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
    return tt.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const r of s) {
      const { key: o, value: i } = r;
      if (o.status === "aborted" || i.status === "aborted")
        return se;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (n[o.value] = i.value);
    }
    return { status: t.value, value: n };
  }
}
const se = Object.freeze({
  status: "aborted"
}), tn = (e) => ({ status: "dirty", value: e }), gt = (e) => ({ status: "valid", value: e }), oa = (e) => e.status === "aborted", ia = (e) => e.status === "dirty", Fs = (e) => e.status === "valid", Xn = (e) => typeof Promise < "u" && e instanceof Promise;
var W;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(W || (W = {}));
class Dt {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const aa = (e, t) => {
  if (Fs(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new Kt(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function ie(e) {
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
class ue {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return ss(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: ss(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new tt(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: ss(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (Xn(s))
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
      parsedType: ss(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return aa(n, r);
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
      parsedType: ss(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return Fs(n) ? {
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
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => Fs(n) ? {
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
      parsedType: ss(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (Xn(r) ? r : Promise.resolve(r));
    return aa(n, o);
  }
  refine(t, s) {
    const n = (r) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(r) : s;
    return this._refinement((r, o) => {
      const i = t(r), a = () => o.addIssue({
        code: O.custom,
        ...n(r)
      });
      return typeof Promise < "u" && i instanceof Promise ? i.then((l) => l ? !0 : (a(), !1)) : i ? !0 : (a(), !1);
    });
  }
  refinement(t, s) {
    return this._refinement((n, r) => t(n) ? !0 : (r.addIssue(typeof s == "function" ? s(n, r) : s), !1));
  }
  _refinement(t) {
    return new Ws({
      schema: this,
      typeName: te.ZodEffects,
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
    return os.create(this, this._def);
  }
  nullable() {
    return Hs.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return Pt.create(this);
  }
  promise() {
    return rr.create(this, this._def);
  }
  or(t) {
    return tr.create([this, t], this._def);
  }
  and(t) {
    return sr.create(this, t, this._def);
  }
  transform(t) {
    return new Ws({
      ...ie(this._def),
      schema: this,
      typeName: te.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new So({
      ...ie(this._def),
      innerType: this,
      defaultValue: s,
      typeName: te.ZodDefault
    });
  }
  brand() {
    return new Em({
      typeName: te.ZodBranded,
      type: this,
      ...ie(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Co({
      ...ie(this._def),
      innerType: this,
      catchValue: s,
      typeName: te.ZodCatch
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
    return Yo.create(this, t);
  }
  readonly() {
    return Ao.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const om = /^c[^\s-]{8,}$/i, im = /^[0-9a-z]+$/, am = /^[0-9A-HJKMNP-TV-Z]{26}$/i, lm = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, cm = /^[a-z0-9_-]{21}$/i, um = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, dm = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, fm = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, hm = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let Jr;
const mm = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, pm = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, gm = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, ym = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, vm = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, bm = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, gc = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", _m = new RegExp(`^${gc}$`);
function yc(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function xm(e) {
  return new RegExp(`^${yc(e)}$`);
}
function wm(e) {
  let t = `${gc}T${yc(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function km(e, t) {
  return !!((t === "v4" || !t) && mm.test(e) || (t === "v6" || !t) && gm.test(e));
}
function Sm(e, t) {
  if (!um.test(e))
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
function Cm(e, t) {
  return !!((t === "v4" || !t) && pm.test(e) || (t === "v6" || !t) && ym.test(e));
}
class Gt extends ue {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== U.string) {
      const o = this._getOrReturnCtx(t);
      return j(o, {
        code: O.invalid_type,
        expected: U.string,
        received: o.parsedType
      }), se;
    }
    const n = new tt();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), j(r, {
          code: O.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), j(r, {
          code: O.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? j(r, {
          code: O.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && j(r, {
          code: O.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        fm.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "email",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        Jr || (Jr = new RegExp(hm, "u")), Jr.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "emoji",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        lm.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "uuid",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        cm.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "nanoid",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        om.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "cuid",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        im.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "cuid2",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        am.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
          validation: "ulid",
          code: O.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), j(r, {
            validation: "url",
            code: O.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "regex",
        code: O.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? wm(o).test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? _m.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? xm(o).test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? dm.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "duration",
        code: O.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? km(t.data, o.version) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "ip",
        code: O.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? Sm(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "jwt",
        code: O.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Cm(t.data, o.version) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "cidr",
        code: O.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? vm.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "base64",
        code: O.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? bm.test(t.data) || (r = this._getOrReturnCtx(t, r), j(r, {
        validation: "base64url",
        code: O.invalid_string,
        message: o.message
      }), n.dirty()) : ge.assertNever(o);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((r) => t.test(r), {
      validation: s,
      code: O.invalid_string,
      ...W.errToObj(n)
    });
  }
  _addCheck(t) {
    return new Gt({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...W.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...W.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...W.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...W.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...W.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...W.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...W.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...W.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...W.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...W.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...W.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...W.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...W.errToObj(t) });
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
      ...W.errToObj(t?.message)
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
      ...W.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...W.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...W.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...W.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...W.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...W.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...W.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...W.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...W.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, W.errToObj(t));
  }
  trim() {
    return new Gt({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new Gt({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new Gt({
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
Gt.create = (e) => new Gt({
  checks: [],
  typeName: te.ZodString,
  coerce: e?.coerce ?? !1,
  ...ie(e)
});
function Am(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class Us extends ue {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== U.number) {
      const o = this._getOrReturnCtx(t);
      return j(o, {
        code: O.invalid_type,
        expected: U.number,
        received: o.parsedType
      }), se;
    }
    let n;
    const r = new tt();
    for (const o of this._def.checks)
      o.kind === "int" ? ge.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? Am(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.not_finite,
        message: o.message
      }), r.dirty()) : ge.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, W.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, W.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, W.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, W.toString(s));
  }
  setLimit(t, s, n, r) {
    return new Us({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: W.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Us({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: W.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: W.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: W.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: W.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: W.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: W.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: W.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: W.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: W.toString(t)
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && ge.isInteger(t.value));
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
Us.create = (e) => new Us({
  checks: [],
  typeName: te.ZodNumber,
  coerce: e?.coerce || !1,
  ...ie(e)
});
class bn extends ue {
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
    if (this._getType(t) !== U.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new tt();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), j(n, {
        code: O.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : ge.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return j(s, {
      code: O.invalid_type,
      expected: U.bigint,
      received: s.parsedType
    }), se;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, W.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, W.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, W.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, W.toString(s));
  }
  setLimit(t, s, n, r) {
    return new bn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: W.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new bn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: W.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: W.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: W.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: W.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: W.toString(s)
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
bn.create = (e) => new bn({
  checks: [],
  typeName: te.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...ie(e)
});
class wo extends ue {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== U.boolean) {
      const n = this._getOrReturnCtx(t);
      return j(n, {
        code: O.invalid_type,
        expected: U.boolean,
        received: n.parsedType
      }), se;
    }
    return gt(t.data);
  }
}
wo.create = (e) => new wo({
  typeName: te.ZodBoolean,
  coerce: e?.coerce || !1,
  ...ie(e)
});
class er extends ue {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== U.date) {
      const o = this._getOrReturnCtx(t);
      return j(o, {
        code: O.invalid_type,
        expected: U.date,
        received: o.parsedType
      }), se;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return j(o, {
        code: O.invalid_date
      }), se;
    }
    const n = new tt();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), j(r, {
        code: O.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), n.dirty()) : ge.assertNever(o);
    return {
      status: n.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new er({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: W.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: W.toString(s)
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
er.create = (e) => new er({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: te.ZodDate,
  ...ie(e)
});
class la extends ue {
  _parse(t) {
    if (this._getType(t) !== U.symbol) {
      const n = this._getOrReturnCtx(t);
      return j(n, {
        code: O.invalid_type,
        expected: U.symbol,
        received: n.parsedType
      }), se;
    }
    return gt(t.data);
  }
}
la.create = (e) => new la({
  typeName: te.ZodSymbol,
  ...ie(e)
});
class ca extends ue {
  _parse(t) {
    if (this._getType(t) !== U.undefined) {
      const n = this._getOrReturnCtx(t);
      return j(n, {
        code: O.invalid_type,
        expected: U.undefined,
        received: n.parsedType
      }), se;
    }
    return gt(t.data);
  }
}
ca.create = (e) => new ca({
  typeName: te.ZodUndefined,
  ...ie(e)
});
class ua extends ue {
  _parse(t) {
    if (this._getType(t) !== U.null) {
      const n = this._getOrReturnCtx(t);
      return j(n, {
        code: O.invalid_type,
        expected: U.null,
        received: n.parsedType
      }), se;
    }
    return gt(t.data);
  }
}
ua.create = (e) => new ua({
  typeName: te.ZodNull,
  ...ie(e)
});
class da extends ue {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return gt(t.data);
  }
}
da.create = (e) => new da({
  typeName: te.ZodAny,
  ...ie(e)
});
class fa extends ue {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return gt(t.data);
  }
}
fa.create = (e) => new fa({
  typeName: te.ZodUnknown,
  ...ie(e)
});
class cs extends ue {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return j(s, {
      code: O.invalid_type,
      expected: U.never,
      received: s.parsedType
    }), se;
  }
}
cs.create = (e) => new cs({
  typeName: te.ZodNever,
  ...ie(e)
});
class ha extends ue {
  _parse(t) {
    if (this._getType(t) !== U.undefined) {
      const n = this._getOrReturnCtx(t);
      return j(n, {
        code: O.invalid_type,
        expected: U.void,
        received: n.parsedType
      }), se;
    }
    return gt(t.data);
  }
}
ha.create = (e) => new ha({
  typeName: te.ZodVoid,
  ...ie(e)
});
class Pt extends ue {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== U.array)
      return j(s, {
        code: O.invalid_type,
        expected: U.array,
        received: s.parsedType
      }), se;
    if (r.exactLength !== null) {
      const i = s.data.length > r.exactLength.value, a = s.data.length < r.exactLength.value;
      (i || a) && (j(s, {
        code: i ? O.too_big : O.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (j(s, {
      code: O.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (j(s, {
      code: O.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((i, a) => r.type._parseAsync(new Dt(s, i, s.path, a)))).then((i) => tt.mergeArray(n, i));
    const o = [...s.data].map((i, a) => r.type._parseSync(new Dt(s, i, s.path, a)));
    return tt.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new Pt({
      ...this._def,
      minLength: { value: t, message: W.toString(s) }
    });
  }
  max(t, s) {
    return new Pt({
      ...this._def,
      maxLength: { value: t, message: W.toString(s) }
    });
  }
  length(t, s) {
    return new Pt({
      ...this._def,
      exactLength: { value: t, message: W.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Pt.create = (e, t) => new Pt({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: te.ZodArray,
  ...ie(t)
});
function Is(e) {
  if (e instanceof ze) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = os.create(Is(n));
    }
    return new ze({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof Pt ? new Pt({
    ...e._def,
    type: Is(e.element)
  }) : e instanceof os ? os.create(Is(e.unwrap())) : e instanceof Hs ? Hs.create(Is(e.unwrap())) : e instanceof Ss ? Ss.create(e.items.map((t) => Is(t))) : e;
}
class ze extends ue {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = ge.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== U.object) {
      const c = this._getOrReturnCtx(t);
      return j(c, {
        code: O.invalid_type,
        expected: U.object,
        received: c.parsedType
      }), se;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof cs && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], d = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new Dt(r, d, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof cs) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && (j(r, {
          code: O.unrecognized_keys,
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
            new Dt(r, d, r.path, u)
            //, ctx.child(key), value, getParsedType(value)
          ),
          alwaysSet: u in r.data
        });
      }
    }
    return r.common.async ? Promise.resolve().then(async () => {
      const c = [];
      for (const u of l) {
        const d = await u.key, h = await u.value;
        c.push({
          key: d,
          value: h,
          alwaysSet: u.alwaysSet
        });
      }
      return c;
    }).then((c) => tt.mergeObjectSync(n, c)) : tt.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return W.errToObj, new ze({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: W.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new ze({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new ze({
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
    return new ze({
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
    return new ze({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: te.ZodObject
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
    return new ze({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of ge.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new ze({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of ge.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new ze({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return Is(this);
  }
  partial(t) {
    const s = {};
    for (const n of ge.objectKeys(this.shape)) {
      const r = this.shape[n];
      t && !t[n] ? s[n] = r : s[n] = r.optional();
    }
    return new ze({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of ge.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let o = this.shape[n];
        for (; o instanceof os; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new ze({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return vc(ge.objectKeys(this.shape));
  }
}
ze.create = (e, t) => new ze({
  shape: () => e,
  unknownKeys: "strip",
  catchall: cs.create(),
  typeName: te.ZodObject,
  ...ie(t)
});
ze.strictCreate = (e, t) => new ze({
  shape: () => e,
  unknownKeys: "strict",
  catchall: cs.create(),
  typeName: te.ZodObject,
  ...ie(t)
});
ze.lazycreate = (e, t) => new ze({
  shape: e,
  unknownKeys: "strip",
  catchall: cs.create(),
  typeName: te.ZodObject,
  ...ie(t)
});
class tr extends ue {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return s.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new Kt(a.ctx.common.issues));
      return j(s, {
        code: O.invalid_union,
        unionErrors: i
      }), se;
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
      const a = i.map((l) => new Kt(l));
      return j(s, {
        code: O.invalid_union,
        unionErrors: a
      }), se;
    }
  }
  get options() {
    return this._def.options;
  }
}
tr.create = (e, t) => new tr({
  options: e,
  typeName: te.ZodUnion,
  ...ie(t)
});
function ko(e, t) {
  const s = ss(e), n = ss(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === U.object && n === U.object) {
    const r = ge.objectKeys(t), o = ge.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = ko(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (s === U.array && n === U.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = ko(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === U.date && n === U.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class sr extends ue {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, i) => {
      if (oa(o) || oa(i))
        return se;
      const a = ko(o.value, i.value);
      return a.valid ? ((ia(o) || ia(i)) && s.dirty(), { status: s.value, value: a.data }) : (j(n, {
        code: O.invalid_intersection_types
      }), se);
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
sr.create = (e, t, s) => new sr({
  left: e,
  right: t,
  typeName: te.ZodIntersection,
  ...ie(s)
});
class Ss extends ue {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== U.array)
      return j(n, {
        code: O.invalid_type,
        expected: U.array,
        received: n.parsedType
      }), se;
    if (n.data.length < this._def.items.length)
      return j(n, {
        code: O.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), se;
    !this._def.rest && n.data.length > this._def.items.length && (j(n, {
      code: O.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new Dt(n, i, n.path, a)) : null;
    }).filter((i) => !!i);
    return n.common.async ? Promise.all(o).then((i) => tt.mergeArray(s, i)) : tt.mergeArray(s, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Ss({
      ...this._def,
      rest: t
    });
  }
}
Ss.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Ss({
    items: e,
    typeName: te.ZodTuple,
    rest: null,
    ...ie(t)
  });
};
class nr extends ue {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== U.object)
      return j(n, {
        code: O.invalid_type,
        expected: U.object,
        received: n.parsedType
      }), se;
    const r = [], o = this._def.keyType, i = this._def.valueType;
    for (const a in n.data)
      r.push({
        key: o._parse(new Dt(n, a, n.path, a)),
        value: i._parse(new Dt(n, n.data[a], n.path, a)),
        alwaysSet: a in n.data
      });
    return n.common.async ? tt.mergeObjectAsync(s, r) : tt.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof ue ? new nr({
      keyType: t,
      valueType: s,
      typeName: te.ZodRecord,
      ...ie(n)
    }) : new nr({
      keyType: Gt.create(),
      valueType: t,
      typeName: te.ZodRecord,
      ...ie(s)
    });
  }
}
class ma extends ue {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== U.map)
      return j(n, {
        code: O.invalid_type,
        expected: U.map,
        received: n.parsedType
      }), se;
    const r = this._def.keyType, o = this._def.valueType, i = [...n.data.entries()].map(([a, l], c) => ({
      key: r._parse(new Dt(n, a, n.path, [c, "key"])),
      value: o._parse(new Dt(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return se;
          (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
        }
        return { status: s.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return se;
        (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
      }
      return { status: s.value, value: a };
    }
  }
}
ma.create = (e, t, s) => new ma({
  valueType: t,
  keyType: e,
  typeName: te.ZodMap,
  ...ie(s)
});
class _n extends ue {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== U.set)
      return j(n, {
        code: O.invalid_type,
        expected: U.set,
        received: n.parsedType
      }), se;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (j(n, {
      code: O.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (j(n, {
      code: O.too_big,
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
          return se;
        u.status === "dirty" && s.dirty(), c.add(u.value);
      }
      return { status: s.value, value: c };
    }
    const a = [...n.data.values()].map((l, c) => o._parse(new Dt(n, l, n.path, c)));
    return n.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, s) {
    return new _n({
      ...this._def,
      minSize: { value: t, message: W.toString(s) }
    });
  }
  max(t, s) {
    return new _n({
      ...this._def,
      maxSize: { value: t, message: W.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
_n.create = (e, t) => new _n({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: te.ZodSet,
  ...ie(t)
});
class pa extends ue {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
pa.create = (e, t) => new pa({
  getter: e,
  typeName: te.ZodLazy,
  ...ie(t)
});
class ga extends ue {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return j(s, {
        received: s.data,
        code: O.invalid_literal,
        expected: this._def.value
      }), se;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
ga.create = (e, t) => new ga({
  value: e,
  typeName: te.ZodLiteral,
  ...ie(t)
});
function vc(e, t) {
  return new Bs({
    values: e,
    typeName: te.ZodEnum,
    ...ie(t)
  });
}
class Bs extends ue {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return j(s, {
        expected: ge.joinValues(n),
        received: s.parsedType,
        code: O.invalid_type
      }), se;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return j(s, {
        received: s.data,
        code: O.invalid_enum_value,
        options: n
      }), se;
    }
    return gt(t.data);
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
    return Bs.create(t, {
      ...this._def,
      ...s
    });
  }
  exclude(t, s = this._def) {
    return Bs.create(this.options.filter((n) => !t.includes(n)), {
      ...this._def,
      ...s
    });
  }
}
Bs.create = vc;
class ya extends ue {
  _parse(t) {
    const s = ge.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== U.string && n.parsedType !== U.number) {
      const r = ge.objectValues(s);
      return j(n, {
        expected: ge.joinValues(r),
        received: n.parsedType,
        code: O.invalid_type
      }), se;
    }
    if (this._cache || (this._cache = new Set(ge.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = ge.objectValues(s);
      return j(n, {
        received: n.data,
        code: O.invalid_enum_value,
        options: r
      }), se;
    }
    return gt(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
ya.create = (e, t) => new ya({
  values: e,
  typeName: te.ZodNativeEnum,
  ...ie(t)
});
class rr extends ue {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== U.promise && s.common.async === !1)
      return j(s, {
        code: O.invalid_type,
        expected: U.promise,
        received: s.parsedType
      }), se;
    const n = s.parsedType === U.promise ? s.data : Promise.resolve(s.data);
    return gt(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
rr.create = (e, t) => new rr({
  type: e,
  typeName: te.ZodPromise,
  ...ie(t)
});
class Ws extends ue {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === te.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (i) => {
        j(n, i), i.fatal ? s.abort() : s.dirty();
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
            return se;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? se : l.status === "dirty" || s.value === "dirty" ? tn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return se;
        const a = this._def.schema._parseSync({
          data: i,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? se : a.status === "dirty" || s.value === "dirty" ? tn(a.value) : a;
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
        return a.status === "aborted" ? se : (a.status === "dirty" && s.dirty(), i(a.value), { status: s.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => a.status === "aborted" ? se : (a.status === "dirty" && s.dirty(), i(a.value).then(() => ({ status: s.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!Fs(i))
          return se;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => Fs(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: s.value,
          value: a
        })) : se);
    ge.assertNever(r);
  }
}
Ws.create = (e, t, s) => new Ws({
  schema: e,
  typeName: te.ZodEffects,
  effect: t,
  ...ie(s)
});
Ws.createWithPreprocess = (e, t, s) => new Ws({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: te.ZodEffects,
  ...ie(s)
});
class os extends ue {
  _parse(t) {
    return this._getType(t) === U.undefined ? gt(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
os.create = (e, t) => new os({
  innerType: e,
  typeName: te.ZodOptional,
  ...ie(t)
});
class Hs extends ue {
  _parse(t) {
    return this._getType(t) === U.null ? gt(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Hs.create = (e, t) => new Hs({
  innerType: e,
  typeName: te.ZodNullable,
  ...ie(t)
});
class So extends ue {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === U.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
So.create = (e, t) => new So({
  innerType: e,
  typeName: te.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...ie(t)
});
class Co extends ue {
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
    return Xn(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new Kt(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new Kt(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
Co.create = (e, t) => new Co({
  innerType: e,
  typeName: te.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...ie(t)
});
class va extends ue {
  _parse(t) {
    if (this._getType(t) !== U.nan) {
      const n = this._getOrReturnCtx(t);
      return j(n, {
        code: O.invalid_type,
        expected: U.nan,
        received: n.parsedType
      }), se;
    }
    return { status: "valid", value: t.data };
  }
}
va.create = (e) => new va({
  typeName: te.ZodNaN,
  ...ie(e)
});
class Em extends ue {
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
class Yo extends ue {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? se : o.status === "dirty" ? (s.dirty(), tn(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? se : r.status === "dirty" ? (s.dirty(), {
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
    return new Yo({
      in: t,
      out: s,
      typeName: te.ZodPipeline
    });
  }
}
class Ao extends ue {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (Fs(r) && (r.value = Object.freeze(r.value)), r);
    return Xn(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Ao.create = (e, t) => new Ao({
  innerType: e,
  typeName: te.ZodReadonly,
  ...ie(t)
});
var te;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(te || (te = {}));
const Ze = Gt.create, Yr = Us.create, Pn = wo.create;
cs.create;
const Rm = Pt.create, Qo = ze.create;
tr.create;
sr.create;
Ss.create;
const Om = nr.create, Eo = Bs.create;
rr.create;
os.create;
Hs.create;
const Tm = "comfymodal.studio.vue.";
function Im() {
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
function Nm() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return Im();
}
function Pm(e, t, s, n) {
  const r = Tm + e, o = Nm();
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
const Mm = "/comfymodal";
class jm extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function Lm(e, t) {
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
function Dm(e, t) {
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
async function ot(e, t = {}, s = fetch) {
  const {
    method: n = "GET",
    body: r,
    signal: o,
    timeoutMs: i,
    headers: a = {}
  } = t, { signal: l, cleanup: c } = Dm(o, i);
  try {
    if (l && l.aborted) throw l.reason;
    const u = await s(Mm + e, {
      method: n,
      headers: {
        "Content-Type": "application/json",
        ...a
      },
      body: r === void 0 ? void 0 : JSON.stringify(r),
      signal: l
    }), d = await u.text();
    let h = null;
    if (d !== "")
      try {
        h = JSON.parse(d);
      } catch {
        h = d;
      }
    if (!u.ok)
      throw new jm(
        u.status,
        Lm(h, `Request failed with status ${u.status}`),
        h
      );
    return h;
  } finally {
    c();
  }
}
const Vm = Qo({ value: Ze(), label: Ze() }).passthrough(), zm = Qo({
  gpu: Ze().default(""),
  default_gpu: Ze().default(""),
  available_gpus: Rm(Vm).default([]),
  persisted_gpu: Ze().default(""),
  output_format: Ze().default("original"),
  quality: Yr().default(75),
  webp_lossless_compression: Ze().default("balanced"),
  auto_save_local: Pn().default(!1),
  save_folder: Ze().default(""),
  save_metadata_sidecar: Pn().default(!0),
  preview_default: Eo(["off", "on"]).default("off"),
  preview_codec: Ze().default("webp"),
  preview_quality: Yr().default(70),
  data_saver_default: Eo(["off", "on"]).default("off"),
  data_saver_codec: Ze().default("webp"),
  data_saver_quality: Yr().default(70),
  execution_mode: Ze().default("v2"),
  execution_mode_source: Ze().default(""),
  execution_mode_locked: Pn().default(!1),
  engine_migration_notice: Ze().nullable().default(null),
  skip_plan_validation: Pn().default(!1),
  golden_gpu_order: Om(Ze()).default({})
}).passthrough(), $m = Qo({ status: Ze().optional(), level: Ze().default("off"), effective: Ze().default("off") }).passthrough();
async function ba() {
  return zm.parse(await ot("/config"));
}
async function Fm(e) {
  return ot("/config", { method: "POST", body: e });
}
async function Um() {
  return $m.parse(await ot("/profile/level"));
}
async function Bm(e) {
  return ot("/profile/level", { method: "POST", body: { level: e } });
}
const Ys = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function _a(e) {
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
    localStorage.setItem(Ys.outputFormat, s.output_format), localStorage.setItem(Ys.quality, String(s.quality)), localStorage.setItem(Ys.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(Ys.saveFolder, s.save_folder), localStorage.setItem(Ys.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const bc = "comfymodal-studio";
function _c(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(bc), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function or(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(bc);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
const Wm = Eo(["comfortable", "compact"]), Qr = Pm(
  "shell.density",
  "comfortable",
  Wm
), xc = /* @__PURE__ */ Zs("studio-settings", () => {
  const e = /* @__PURE__ */ le("studio"), t = /* @__PURE__ */ le(Qr.read()), s = /* @__PURE__ */ le(null), n = /* @__PURE__ */ le("off"), r = /* @__PURE__ */ le(!1), o = /* @__PURE__ */ le(!1), i = /* @__PURE__ */ le(null), a = /* @__PURE__ */ le(!1);
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
      const [S, T] = await Promise.all([ba(), Um()]);
      s.value = S, n.value = T.effective || T.level, _a(S), a.value = !0;
    } catch (S) {
      throw i.value = S instanceof Error ? S.message : "Could not load Settings", S;
    } finally {
      r.value = !1;
    }
  }
  async function h(S) {
    o.value = !0, i.value = null;
    try {
      await Fm(S);
      const T = await ba();
      s.value = T, _a(T), or("settings");
    } catch (T) {
      throw i.value = T instanceof Error ? T.message : "Could not save Settings", T;
    } finally {
      o.value = !1;
    }
  }
  async function p(S) {
    await Bm(S), n.value = S, or("settings");
  }
  async function w() {
    l || (l = _c((S) => {
      S === "settings" && !r.value && d();
    })), a.value || await d();
  }
  function _(S) {
    e.value = S;
  }
  function L(S) {
    t.value = S, Qr.write(S);
  }
  function z() {
    e.value = "studio", t.value = "comfortable", Qr.write("comfortable");
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
    save: h,
    setProfile: p,
    setSection: _,
    setDensity: L,
    reset: z
  };
});
function Hm(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const r = String(n.id ?? "");
    return { id: r, label: String(n.label ?? r), isActive: r !== "" && r === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function wc(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function Zm(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function Gm() {
  return ot("/workspaces");
}
async function qm(e) {
  return ot("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function xa() {
  return wc(await ot("/deploy/status"));
}
async function Km() {
  return ot("/deploy", { method: "POST" });
}
async function Jm() {
  return ot("/deploy/log");
}
async function Ym(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return ot(`/studio/inventory/refresh${t}`);
}
async function Qm(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return ot(`/studio/models${s}`);
}
async function Xm(e = !1) {
  return ot("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function ep() {
  return ot("/studio/custom-nodes");
}
async function tp() {
  return ot("/studio/custom-nodes/refresh", { method: "POST" });
}
function kc() {
  let e = 0, t = null;
  return {
    run: (n) => {
      e += 1;
      const r = e, o = t;
      o && (o.superseded = !0, o.controller.abort());
      const i = new AbortController(), a = { controller: i, superseded: !1 };
      let l;
      const c = new Promise((h) => {
        l = () => h({ stale: !0 });
      }), u = () => l();
      i.signal.addEventListener("abort", u, { once: !0 }), t = a;
      const d = () => {
        i.signal.removeEventListener("abort", u), t === a && (t = null);
      };
      return (async () => {
        try {
          return await Promise.race([
            n(i.signal).then((h) => r !== e || a.superseded || i.signal.aborted ? { stale: !0 } : { stale: !1, value: h }),
            c
          ]);
        } catch (h) {
          if (a.superseded || r !== e || i.signal.aborted)
            return { stale: !0 };
          throw h;
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
function sp(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function np(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function Sc(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    sp(s), i += 1, o && o(i);
    const a = await n(s, i);
    if (r(a)) return a;
    await np(t, s);
  }
}
const Cc = /* @__PURE__ */ Zs("studio-infrastructure", () => {
  const e = /* @__PURE__ */ le("unknown"), t = /* @__PURE__ */ le(null), s = /* @__PURE__ */ le(null), n = /* @__PURE__ */ le([]), r = /* @__PURE__ */ le(null), o = /* @__PURE__ */ le(wc(null)), i = /* @__PURE__ */ le(null), a = /* @__PURE__ */ le([]), l = /* @__PURE__ */ le([]), c = /* @__PURE__ */ le(!1), u = /* @__PURE__ */ le(null), d = kc();
  let h = null;
  const p = Oe(() => n.value.find((K) => K.isActive) ?? null);
  function w(K, Ce) {
    e.value = K, t.value = Ce ?? null;
  }
  function _(K) {
    s.value = K;
  }
  function L() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  async function z() {
    const K = Hm(await Gm());
    n.value = K.rows, r.value = K.activeId;
  }
  async function S() {
    o.value = await xa(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function T() {
    const K = await d.run(async (Ce) => {
      const [Me, me] = await Promise.all([Qm(), ep()]);
      return Ce.aborted ? null : { modelResult: Me, nodeResult: me };
    });
    K.stale || !K.value || (a.value = K.value.modelResult.models ?? [], l.value = K.value.nodeResult.custom_nodes ?? []);
  }
  async function P() {
    c.value = !0, u.value = null;
    try {
      await Promise.all([z(), S(), T()]), s.value = "server inventory loaded";
    } catch (K) {
      throw u.value = K instanceof Error ? K.message : "Could not load infrastructure", K;
    } finally {
      c.value = !1;
    }
  }
  async function Q() {
    h || (h = _c((K) => {
      K === "workspace" && !c.value && P();
    })), n.value.length || await P();
  }
  async function be(K) {
    await qm(K), await z(), or("workspace");
  }
  async function re() {
    const K = Jo(), Ce = K.start({ kind: "deploy", label: "Deploy workspace" });
    try {
      await Km(), K.patch(Ce, { status: "running", message: "Deployment started" });
      const Me = await Sc({
        intervalMs: 3e3,
        run: async () => {
          const me = await xa();
          return o.value = me, e.value = me.state, t.value = me.message || null, K.patch(Ce, { message: me.message || `Deployment: ${me.state}` }), me;
        },
        done: (me) => me.state === "ready" || me.state === "deployed_unwarmed" || me.state !== "deploying" && me.state !== "starting" && me.state !== "unknown"
      });
      if (!Zm(Me.state)) throw new Error(Me.message || `Deployment ended in ${Me.state}`);
      K.finish(Ce, Me.message || "Deployment completed");
    } catch (Me) {
      const me = Me instanceof Error ? Me.message : "Deployment failed";
      throw K.fail(Ce, me), Me;
    }
    return Ce;
  }
  async function C() {
    await Ym(0), await T(), s.value = "inventory refreshed", or("workspace");
  }
  async function H() {
    const K = await Xm(!0);
    a.value = K.models ?? a.value, await T();
  }
  async function ve() {
    const K = await tp();
    l.value = K.custom_nodes ?? l.value, await T();
  }
  async function Pe() {
    i.value = await Jm();
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
    setSyncSummary: _,
    reset: L,
    load: P,
    initialize: Q,
    loadWorkspaces: z,
    loadDeployment: S,
    loadInventory: T,
    selectWorkspace: be,
    deploy: re,
    refreshRemoteInventoryNow: C,
    rescanModelsNow: H,
    refreshCustomNodesNow: ve,
    loadLog: Pe
  };
});
function Ac(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = Ac(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function Ec() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = Ac(e)) && (n && (n += " "), n += t);
  return n;
}
const rp = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, op = (e, t) => ({
  classGroupId: e,
  validator: t
}), Rc = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), ir = "-", wa = [], ip = "arbitrary..", ap = (e) => {
  const t = cp(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return lp(i);
      const a = i.split(ir), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return Oc(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = n[i], c = s[i];
        return l ? c ? rp(c, l) : l : c || wa;
      }
      return s[i] || wa;
    }
  };
}, Oc = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const r = e[t], o = s.nextPart.get(r);
  if (o) {
    const c = Oc(e, t + 1, o);
    if (c) return c;
  }
  const i = s.validators;
  if (i === null)
    return;
  const a = t === 0 ? e.join(ir) : e.slice(t).join(ir), l = i.length;
  for (let c = 0; c < l; c++) {
    const u = i[c];
    if (u.validator(a))
      return u.classGroupId;
  }
}, lp = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? ip + n : void 0;
})(), cp = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return up(s, t);
}, up = (e, t) => {
  const s = Rc();
  for (const n in e) {
    const r = e[n];
    Xo(r, s, n, t);
  }
  return s;
}, Xo = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    dp(i, t, s, n);
  }
}, dp = (e, t, s, n) => {
  if (typeof e == "string") {
    fp(e, t, s);
    return;
  }
  if (typeof e == "function") {
    hp(e, t, s, n);
    return;
  }
  mp(e, t, s, n);
}, fp = (e, t, s) => {
  const n = e === "" ? t : Tc(t, e);
  n.classGroupId = s;
}, hp = (e, t, s, n) => {
  if (pp(e)) {
    Xo(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(op(s, e));
}, mp = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    Xo(l, Tc(t, a), s, n);
  }
}, Tc = (e, t) => {
  let s = e;
  const n = t.split(ir), r = n.length;
  for (let o = 0; o < r; o++) {
    const i = n[o];
    let a = s.nextPart.get(i);
    a || (a = Rc(), s.nextPart.set(i, a)), s = a;
  }
  return s;
}, pp = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, gp = (e) => {
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
}, Ro = "!", ka = ":", yp = [], Sa = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), vp = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let _ = 0; _ < u; _++) {
      const L = r[_];
      if (i === 0 && a === 0) {
        if (L === ka) {
          o.push(r.slice(l, _)), l = _ + 1;
          continue;
        }
        if (L === "/") {
          c = _;
          continue;
        }
      }
      L === "[" ? i++ : L === "]" ? i-- : L === "(" ? a++ : L === ")" && a--;
    }
    const d = o.length === 0 ? r : r.slice(l);
    let h = d, p = !1;
    d.endsWith(Ro) ? (h = d.slice(0, -1), p = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      d.startsWith(Ro) && (h = d.slice(1), p = !0)
    );
    const w = c && c > l ? c - l : void 0;
    return Sa(o, p, h, w);
  };
  if (t) {
    const r = t + ka, o = n;
    n = (i) => i.startsWith(r) ? o(i.slice(r.length)) : Sa(yp, !1, i, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, bp = (e) => {
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
}, _p = (e) => ({
  cache: gp(e.cacheSize),
  parseClassName: vp(e),
  sortModifiers: bp(e),
  postfixLookupClassGroupIds: xp(e),
  ...ap(e)
}), xp = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, wp = /\s+/, kp = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(wp);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const d = l[u], {
      isExternal: h,
      modifiers: p,
      hasImportantModifier: w,
      baseClassName: _,
      maybePostfixModifierPosition: L
    } = s(d);
    if (h) {
      c = d + (c.length > 0 ? " " + c : c);
      continue;
    }
    let z = !!L, S;
    if (z) {
      const re = _.substring(0, L);
      S = n(re);
      const C = S && i[S] ? n(_) : void 0;
      C && C !== S && (S = C, z = !1);
    } else
      S = n(_);
    if (!S) {
      if (!z) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (S = n(_), !S) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      z = !1;
    }
    const T = p.length === 0 ? "" : p.length === 1 ? p[0] : o(p).join(":"), P = w ? T + Ro : T, Q = P + S;
    if (a.indexOf(Q) > -1)
      continue;
    a.push(Q);
    const be = r(S, z);
    for (let re = 0; re < be.length; ++re) {
      const C = be[re];
      a.push(P + C);
    }
    c = d + (c.length > 0 ? " " + c : c);
  }
  return c;
}, Sp = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = Ic(s)) && (r && (r += " "), r += n);
  return r;
}, Ic = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = Ic(e[n])) && (s && (s += " "), s += t);
  return s;
}, Cp = (e, ...t) => {
  let s, n, r, o;
  const i = (l) => {
    const c = t.reduce((u, d) => d(u), e());
    return s = _p(c), n = s.cache.get, r = s.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = n(l);
    if (c)
      return c;
    const u = kp(l, s);
    return r(l, u), u;
  };
  return o = i, (...l) => o(Sp(...l));
}, Ap = [], $e = (e) => {
  const t = (s) => s[e] || Ap;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, Nc = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, Pc = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Ep = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, Rp = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, Op = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Tp = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Ip = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, Np = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, Qt = (e) => Ep.test(e), ae = (e) => !!e && !Number.isNaN(Number(e)), At = (e) => !!e && Number.isInteger(Number(e)), Xr = (e) => e.endsWith("%") && ae(e.slice(0, -1)), Ut = (e) => Rp.test(e), Mc = () => !0, Pp = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  Op.test(e) && !Tp.test(e)
), ei = () => !1, Mp = (e) => Ip.test(e), jp = (e) => Np.test(e), Lp = (e) => !V(e) && !F(e), Dp = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), Vp = (e) => ds(e, Dc, ei), V = (e) => Nc.test(e), ps = (e) => ds(e, Vc, Pp), Ca = (e) => ds(e, Zp, ae), zp = (e) => ds(e, $c, Mc), $p = (e) => ds(e, zc, ei), Aa = (e) => ds(e, jc, ei), Fp = (e) => ds(e, Lc, jp), Mn = (e) => ds(e, Fc, Mp), F = (e) => Pc.test(e), Qs = (e) => As(e, Vc), Up = (e) => As(e, zc), Ea = (e) => As(e, jc), Bp = (e) => As(e, Dc), Wp = (e) => As(e, Lc), jn = (e) => As(e, Fc, !0), Hp = (e) => As(e, $c, !0), ds = (e, t, s) => {
  const n = Nc.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, As = (e, t, s = !1) => {
  const n = Pc.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, jc = (e) => e === "position" || e === "percentage", Lc = (e) => e === "image" || e === "url", Dc = (e) => e === "length" || e === "size" || e === "bg-size", Vc = (e) => e === "length", Zp = (e) => e === "number", zc = (e) => e === "family-name", $c = (e) => e === "number" || e === "weight", Fc = (e) => e === "shadow", Gp = () => {
  const e = $e("color"), t = $e("font"), s = $e("text"), n = $e("font-weight"), r = $e("tracking"), o = $e("leading"), i = $e("breakpoint"), a = $e("container"), l = $e("spacing"), c = $e("radius"), u = $e("shadow"), d = $e("inset-shadow"), h = $e("text-shadow"), p = $e("drop-shadow"), w = $e("blur"), _ = $e("perspective"), L = $e("aspect"), z = $e("ease"), S = $e("animate"), T = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], P = () => [
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
  ], Q = () => [...P(), F, V], be = () => ["auto", "hidden", "clip", "visible", "scroll"], re = () => ["auto", "contain", "none"], C = () => [F, V, l], H = () => [Qt, "full", "auto", ...C()], ve = () => [At, "none", "subgrid", F, V], Pe = () => ["auto", {
    span: ["full", At, F, V]
  }, At, F, V], K = () => [At, "auto", F, V], Ce = () => ["auto", "min", "max", "fr", F, V], Me = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], me = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], ce = () => ["auto", ...C()], X = () => [Qt, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...C()], de = () => [a, Qt, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...C()], it = () => [Qt, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...C()], B = () => [e, F, V], at = () => [...P(), Ea, Aa, {
    position: [F, V]
  }], Be = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], zt = () => ["auto", "cover", "contain", Bp, Vp, {
    size: [F, V]
  }], yt = () => [Xr, Qs, ps], Ie = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    F,
    V
  ], we = () => ["", ae, Qs, ps], b = () => ["solid", "dashed", "dotted", "double"], $ = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], E = () => [ae, Xr, Ea, Aa], J = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    w,
    F,
    V
  ], f = () => ["none", ae, F, V], m = () => ["none", ae, F, V], g = () => [ae, F, V], y = () => [Qt, "full", ...C()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [Ut],
      breakpoint: [Ut],
      color: [Mc],
      container: [Ut],
      "drop-shadow": [Ut],
      ease: ["in", "out", "in-out"],
      font: [Lp],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [Ut],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [Ut],
      shadow: [Ut],
      spacing: ["px", ae],
      text: [Ut],
      "text-shadow": [Ut],
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
        aspect: ["auto", "square", Qt, V, F, L]
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
        "@container": ["", "normal", "size", F, V]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [Dp],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [ae, "auto", V, F, a]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": T()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": T()
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
        object: Q()
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
        overscroll: re()
      }],
      /**
       * Overscroll Behavior X
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-x": [{
        "overscroll-x": re()
      }],
      /**
       * Overscroll Behavior Y
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-y": [{
        "overscroll-y": re()
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
        inset: H()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": H()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": H()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": H(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: H()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": H(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: H()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": H()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": H()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: H()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: H()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: H()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: H()
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
        z: [At, "auto", F, V]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [Qt, "full", "auto", a, ...C()]
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
        flex: [ae, Qt, "auto", "initial", "none", V]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", ae, F, V]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", ae, F, V]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [At, "first", "last", "none", F, V]
      }],
      /**
       * Grid Template Columns
       * @see https://tailwindcss.com/docs/grid-template-columns
       */
      "grid-cols": [{
        "grid-cols": ve()
      }],
      /**
       * Grid Column Start / End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start-end": [{
        col: Pe()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": K()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": K()
      }],
      /**
       * Grid Template Rows
       * @see https://tailwindcss.com/docs/grid-template-rows
       */
      "grid-rows": [{
        "grid-rows": ve()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: Pe()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": K()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": K()
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
        "auto-cols": Ce()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": Ce()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: C()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": C()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": C()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...Me(), "normal"]
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
        content: ["normal", ...Me()]
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
        "place-content": Me()
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
        p: C()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: C()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: C()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: C()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: C()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: C()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: C()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: C()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: C()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: C()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: C()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: ce()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: ce()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: ce()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: ce()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: ce()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: ce()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: ce()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: ce()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: ce()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: ce()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: ce()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": C()
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
        "space-y": C()
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
        inline: ["auto", ...de()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...de()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...de()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...it()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...it()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...it()]
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
        text: ["base", s, Qs, ps]
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
        font: [n, Hp, zp]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", Xr, V]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [Up, $p, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [V]
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
        tracking: [r, F, V]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [ae, "none", F, Ca]
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
          ...C()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", F, V]
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
        list: ["disc", "decimal", "none", F, V]
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
        placeholder: B()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: B()
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
        decoration: [...b(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [ae, "from-font", "auto", F, ps]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: B()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [ae, "auto", F, V]
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
        indent: C()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [At, F, V]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", F, V]
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
        content: ["none", F, V]
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
        bg: at()
      }],
      /**
       * Background Repeat
       * @see https://tailwindcss.com/docs/background-repeat
       */
      "bg-repeat": [{
        bg: Be()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: zt()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, At, F, V],
          radial: ["", F, V],
          conic: ["", At, F, V]
        }, Wp, Fp]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: B()
      }],
      /**
       * Gradient Color Stops From Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from-pos": [{
        from: yt()
      }],
      /**
       * Gradient Color Stops Via Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via-pos": [{
        via: yt()
      }],
      /**
       * Gradient Color Stops To Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to-pos": [{
        to: yt()
      }],
      /**
       * Gradient Color Stops From
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from": [{
        from: B()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: B()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: B()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: Ie()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": Ie()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": Ie()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": Ie()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": Ie()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": Ie()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": Ie()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": Ie()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": Ie()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": Ie()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": Ie()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": Ie()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": Ie()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": Ie()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": Ie()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: we()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": we()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": we()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": we()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": we()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": we()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": we()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": we()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": we()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": we()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": we()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": we()
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
        "divide-y": we()
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
        border: [...b(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...b(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: B()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": B()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": B()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": B()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": B()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": B()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": B()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": B()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": B()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": B()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": B()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: B()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [...b(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [ae, F, V]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", ae, Qs, ps]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: B()
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
          jn,
          Mn
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: B()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", d, jn, Mn]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": B()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: we()
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
        ring: B()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [ae, ps]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": B()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": we()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": B()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", h, jn, Mn]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": B()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [ae, F, V]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...$(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": $()
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
        "mask-linear": [ae]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": E()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": E()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": B()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": B()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": E()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": E()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": B()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": B()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": E()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": E()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": B()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": B()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": E()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": E()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": B()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": B()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": E()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": E()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": B()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": B()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": E()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": E()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": B()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": B()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": E()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": E()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": B()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": B()
      }],
      "mask-image-radial": [{
        "mask-radial": [F, V]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": E()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": E()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": B()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": B()
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
        "mask-conic": [ae]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": E()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": E()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": B()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": B()
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
        mask: at()
      }],
      /**
       * Mask Repeat
       * @see https://tailwindcss.com/docs/mask-repeat
       */
      "mask-repeat": [{
        mask: Be()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: zt()
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
        mask: ["none", F, V]
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
          F,
          V
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: J()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [ae, F, V]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [ae, F, V]
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
          jn,
          Mn
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": B()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", ae, F, V]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [ae, F, V]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", ae, F, V]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [ae, F, V]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", ae, F, V]
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
          F,
          V
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": J()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [ae, F, V]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [ae, F, V]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", ae, F, V]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [ae, F, V]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", ae, F, V]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [ae, F, V]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [ae, F, V]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", ae, F, V]
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
        "border-spacing": C()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": C()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": C()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", F, V]
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
        duration: [ae, "initial", F, V]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", z, F, V]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [ae, F, V]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", S, F, V]
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
        perspective: [_, F, V]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": Q()
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
        scale: m()
      }],
      /**
       * Scale X
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-x": [{
        "scale-x": m()
      }],
      /**
       * Scale Y
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-y": [{
        "scale-y": m()
      }],
      /**
       * Scale Z
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-z": [{
        "scale-z": m()
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
        transform: [F, V, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: Q()
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
        zoom: [At, F, V]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: B()
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
        caret: B()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", F, V]
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
        "scrollbar-thumb": B()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": B()
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
        "scroll-m": C()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": C()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": C()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": C()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": C()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": C()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": C()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": C()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": C()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": C()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": C()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": C()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": C()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": C()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": C()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": C()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": C()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": C()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": C()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": C()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": C()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": C()
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
        "will-change": ["auto", "scroll", "contents", "transform", F, V]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...B()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [ae, Qs, ps, Ca]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...B()]
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
}, qp = /* @__PURE__ */ Cp(Gp);
function ti(...e) {
  return qp(Ec(e));
}
const Kp = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, Jp = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, Yp = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, Qp = { class: "cmst:flex-1" }, Xp = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, eg = { "data-testid": "vue-status-route" }, tg = { "data-testid": "vue-status-ops" }, sg = { "data-testid": "vue-status-density" }, ng = { class: "cmst:flex cmst:items-center cmst:gap-1" }, rg = /* @__PURE__ */ Vt({
  __name: "StudioApp",
  setup(e) {
    const t = wh(), s = Jo(), n = xc(), r = Cc();
    _r(() => {
      n.initialize(), r.initialize();
    });
    const o = Yh("(min-width: 768px)"), i = {
      playground: ic,
      history: cc,
      workflows: ac,
      backend: uc,
      settings: dc
    }, a = Oe(() => String(t.name ?? "playground"));
    function l(c) {
      const u = a.value === c;
      return ti(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        u ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (c, u) => (Se(), Le("div", Kp, [
      R("header", Jp, [
        u[0] || (u[0] = R("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          oe(" Modal Studio "),
          R("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        R("nav", Yp, [
          (Se(!0), Le(We, null, xr(D(Ko), (d) => (Se(), Ls(D(rc), {
            key: d,
            to: { name: d },
            class: ht(l(d)),
            "data-testid": `vue-nav-${d}`
          }, {
            default: _e(() => [
              (Se(), Ls(Ju(i[d]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              oe(" " + fe(D(Qh)[d]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      R("main", Qp, [
        Y(D(oc))
      ]),
      R("footer", Xp, [
        R("span", null, [
          u[1] || (u[1] = oe("route: ", -1)),
          R("strong", eg, fe(a.value), 1)
        ]),
        R("span", null, [
          u[2] || (u[2] = oe(" operations: ", -1)),
          R("strong", tg, fe(D(s).active.length) + " active", 1),
          oe(" / " + fe(D(s).all.length) + " total ", 1)
        ]),
        R("span", null, [
          u[3] || (u[3] = oe(" density: ", -1)),
          R("strong", sg, fe(D(n).density), 1)
        ]),
        R("span", ng, [
          Y(D(Nh), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          u[4] || (u[4] = oe(" viewport: ", -1)),
          R("strong", null, fe(D(o) ? "wide" : "narrow"), 1),
          u[5] || (u[5] = oe(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), og = "/", Uc = { page: "playground", focus: null };
function Ln(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function eo(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = ls(n) ? n : Uc.page;
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
function to(e) {
  const t = mc(e.location.hash);
  return !t.matched || !ls(t.page) ? null : { page: t.page, focus: t.focus };
}
function so(e, t, s) {
  const n = pc(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function ig(e, t) {
  let s = Xh(t, e.location.hash), n = Ln(s), r = {};
  const o = n, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = n;
    s = to(e) ?? { ...Uc }, n = Ln(s), i.forEach((h) => h(n, u));
  }, c = (u, d) => u === null && d === o;
  return {
    get base() {
      return og;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const d = pc(eo(u));
      return d === "" ? "#" + u : d;
    },
    replace: (u, d) => {
      const h = to(e), p = eo(u), w = Ln(p);
      s = p, d !== void 0 && (r = d), n = w, !c(h, w) && sa(h, p) !== "none" && so(e, p, "replace");
    },
    push: (u, d) => {
      const h = to(e), p = eo(u), w = Ln(p);
      if (s = p, d !== void 0 && (r = d), n = w, c(h, w)) return;
      const _ = sa(h, p);
      _ === "push" ? so(e, p, "push") : _ === "replace" && so(e, p, "replace");
    },
    go: (u) => {
      e.history.go(u);
    },
    listen: (u) => {
      const d = (h, p) => {
        u(h, p, { type: "pop", direction: "unknown", delta: 0 });
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
const Ra = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, Oa = Ec, ag = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return Oa(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = s?.[c], d = o?.[c];
    if (u === null) return null;
    const h = Ra(u) || Ra(d);
    return r[c][h];
  }), a = s && Object.entries(s).reduce((c, u) => {
    let [d, h] = u;
    return h === void 0 || (c[d] = h), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, u) => {
    let { class: d, className: h, ...p } = u;
    return Object.entries(p).every((w) => {
      let [_, L] = w;
      return Array.isArray(L) ? L.includes({
        ...o,
        ...a
      }[_]) : {
        ...o,
        ...a
      }[_] === L;
    }) ? [
      ...c,
      d,
      h
    ] : c;
  }, []);
  return Oa(e, i, l, s?.class, s?.className);
}, lg = ag(
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
), cg = ["type", "disabled"], nt = /* @__PURE__ */ Vt({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (Se(), Le("button", {
      type: e.type,
      disabled: e.disabled,
      class: ht(D(lg)({ variant: e.variant, size: e.size }))
    }, [
      yl(t.$slots, "default")
    ], 10, cg));
  }
}), ut = /* @__PURE__ */ Vt({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (Se(), Le("div", {
      class: ht(
        D(ti)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      yl(t.$slots, "default")
    ], 2));
  }
});
function Cn(e) {
  return ti(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const ug = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, dg = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, fg = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, hg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, mg = { value: "" }, pg = ["value"], gg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, yg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, vg = { class: "cmst:mt-1 cmst:text-sm" }, bg = { "data-testid": "vue-deploy-state" }, _g = {
  key: 0,
  class: "cmst:text-sm cmst:opacity-80"
}, xg = { class: "cmst:flex cmst:gap-2" }, wg = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, kg = { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, Sg = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Cg = { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, Ag = /* @__PURE__ */ Vt({
  __name: "BackendView",
  setup(e) {
    const t = Cc(), s = /* @__PURE__ */ le(""), n = /* @__PURE__ */ le(!1), r = Oe(() => t.models.length), o = Oe(() => t.customNodes.length);
    _r(() => {
      t.workspaces.length || t.initialize();
    });
    async function i() {
      s.value && await t.selectWorkspace(s.value);
    }
    async function a() {
      await t.deploy();
    }
    return (l, c) => (Se(), Le("section", {
      class: ht(D(Cn)()),
      "data-testid": "vue-page-backend"
    }, [
      D(t).error ? (Se(), Le("div", ug, fe(D(t).error), 1)) : ns("", !0),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          R("div", dg, [
            R("div", null, [
              R("h2", fg, [
                Y(D(uc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                c[2] || (c[2] = oe(" Manage Modal ", -1))
              ]),
              c[3] || (c[3] = R("p", { class: "cmst:text-sm cmst:opacity-80" }, [
                oe("Route key remains "),
                R("code", null, "backend"),
                oe(". Workspace and readiness state come from the server.")
              ], -1))
            ]),
            Y(nt, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload infrastructure",
              disabled: D(t).loading,
              onClick: D(t).load
            }, {
              default: _e(() => [
                Y(D(lc), {
                  class: ht(["cmst:size-4", D(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ])
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          c[5] || (c[5] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Workspaces", -1)),
          R("div", hg, [
            Ps(R("select", {
              "onUpdate:modelValue": c[0] || (c[0] = (u) => s.value = u),
              class: "cmst:h-9 cmst:min-w-52 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              "data-testid": "vue-workspace-select"
            }, [
              R("option", mg, fe(D(t).activeWorkspace?.label ?? "Select workspace"), 1),
              (Se(!0), Le(We, null, xr(D(t).workspaces, (u) => (Se(), Le("option", {
                key: u.id,
                value: u.id
              }, fe(u.label) + fe(u.isActive ? " (active)" : ""), 9, pg))), 128))
            ], 512), [
              [Ul, s.value]
            ]),
            Y(nt, {
              size: "sm",
              variant: "secondary",
              disabled: !s.value,
              "data-testid": "vue-workspace-activate",
              onClick: i
            }, {
              default: _e(() => [...c[4] || (c[4] = [
                oe(" Activate workspace ", -1)
              ])]),
              _: 1
            }, 8, ["disabled"])
          ]),
          R("p", gg, "Active ID: " + fe(D(t).activeWorkspaceId ?? "none"), 1)
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          R("div", yg, [
            R("div", null, [
              c[7] || (c[7] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Deployment readiness", -1)),
              R("p", vg, [
                c[6] || (c[6] = oe("State: ", -1)),
                R("strong", bg, fe(D(t).deployStatus.state), 1)
              ]),
              D(t).deployMessage ? (Se(), Le("p", _g, fe(D(t).deployMessage), 1)) : ns("", !0)
            ]),
            R("div", xg, [
              Y(nt, {
                size: "sm",
                disabled: D(t).loading,
                "data-testid": "vue-deploy",
                onClick: a
              }, {
                default: _e(() => [...c[8] || (c[8] = [
                  oe("Deploy / redeploy", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              Y(nt, {
                size: "sm",
                variant: "outline",
                onClick: c[1] || (c[1] = (u) => n.value = !n.value)
              }, {
                default: _e(() => [
                  oe(fe(n.value ? "Hide" : "Show") + " log", 1)
                ]),
                _: 1
              })
            ])
          ]),
          n.value ? (Se(), Le("pre", wg, fe(D(t).deployLog ?? "Loading…"), 1)) : ns("", !0),
          n.value && !D(t).deployLog ? (Se(), Ls(nt, {
            key: 1,
            class: "cmst:mt-2",
            size: "sm",
            variant: "ghost",
            onClick: D(t).loadLog
          }, {
            default: _e(() => [...c[9] || (c[9] = [
              oe("Load deployment log", -1)
            ])]),
            _: 1
          }, 8, ["onClick"])) : ns("", !0)
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          c[13] || (c[13] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared inventory", -1)),
          R("p", kg, "Models: " + fe(r.value) + " · Custom nodes: " + fe(o.value), 1),
          R("div", Sg, [
            Y(nt, {
              size: "sm",
              variant: "outline",
              onClick: D(t).refreshRemoteInventoryNow
            }, {
              default: _e(() => [...c[10] || (c[10] = [
                oe("Refresh remote inventory", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            Y(nt, {
              size: "sm",
              variant: "outline",
              onClick: D(t).rescanModelsNow
            }, {
              default: _e(() => [...c[11] || (c[11] = [
                oe("Rescan models", -1)
              ])]),
              _: 1
            }, 8, ["onClick"]),
            Y(nt, {
              size: "sm",
              variant: "outline",
              onClick: D(t).refreshCustomNodesNow
            }, {
              default: _e(() => [...c[12] || (c[12] = [
                oe("Refresh custom nodes", -1)
              ])]),
              _: 1
            }, 8, ["onClick"])
          ]),
          R("p", Cg, fe(D(t).syncSummary ?? "Not loaded"), 1)
        ]),
        _: 1
      })
    ], 2));
  }
}), Eg = /* @__PURE__ */ Zs("studio-history", () => {
  const e = /* @__PURE__ */ le(null), t = /* @__PURE__ */ le("");
  function s(o) {
    e.value = o;
  }
  function n(o) {
    t.value = o;
  }
  function r() {
    e.value = null, t.value = "";
  }
  return { focusId: e, query: t, setFocus: s, setQuery: n, clear: r };
}), Rg = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Og = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, Tg = { class: "cmst:text-sm cmst:mt-2" }, Ig = { "data-testid": "vue-history-stale" }, Ng = /* @__PURE__ */ Vt({
  __name: "HistoryView",
  setup(e) {
    const t = xh(), s = Eg(), n = /* @__PURE__ */ le(""), r = /* @__PURE__ */ le(null), o = /* @__PURE__ */ le(0);
    function i(c, u) {
      return new Promise((d, h) => {
        const p = setTimeout(() => d(`detail:${c}`), 300);
        u.addEventListener(
          "abort",
          () => {
            clearTimeout(p), h(new DOMException("Aborted", "AbortError"));
          },
          { once: !0 }
        );
      });
    }
    const a = kc();
    async function l() {
      const c = n.value.trim();
      if (!c) return;
      s.setFocus(c), await t.push({ name: "history", query: { focus: c } });
      const u = await a.run((d) => i(c, d));
      if (u.stale) {
        o.value += 1;
        return;
      }
      r.value = u.value;
    }
    return (c, u) => (Se(), Le("section", {
      class: ht(D(Cn)()),
      "data-testid": "vue-page-history"
    }, [
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          R("h2", Rg, [
            Y(D(cc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            u[1] || (u[1] = oe(" History (Phase-1 proof) ", -1))
          ]),
          u[6] || (u[6] = R("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Focus identity lives in the history store; detail reads go through the shared latest-read-wins primitive. ", -1)),
          R("div", Og, [
            Ps(R("input", {
              "onUpdate:modelValue": u[0] || (u[0] = (d) => n.value = d),
              type: "text",
              placeholder: "Focus id (e.g. gen_123)",
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm",
              "data-testid": "vue-history-focus-input"
            }, null, 512), [
              [Yn, n.value]
            ]),
            Y(nt, {
              variant: "secondary",
              size: "sm",
              "data-testid": "vue-history-focus-apply",
              onClick: l
            }, {
              default: _e(() => [...u[2] || (u[2] = [
                oe(" Load focus ", -1)
              ])]),
              _: 1
            })
          ]),
          R("p", Tg, [
            u[3] || (u[3] = oe(" Store focus: ", -1)),
            R("strong", null, fe(D(s).focusId ?? "none"), 1),
            u[4] || (u[4] = oe(" · Committed read: ", -1)),
            R("strong", null, fe(r.value ?? "none"), 1),
            u[5] || (u[5] = oe(" · Stale drops: ", -1)),
            R("strong", Ig, fe(o.value), 1)
          ]),
          u[7] || (u[7] = R("p", { class: "cmst:text-xs cmst:opacity-70" }, " Tip: click “Load focus” rapidly with different ids — only the newest read commits; older ones are dropped as stale. ", -1))
        ]),
        _: 1
      })
    ], 2));
  }
}), Pg = /* @__PURE__ */ Zs("studio-playground", () => {
  const e = /* @__PURE__ */ le("txt2img"), t = /* @__PURE__ */ le(!1);
  function s(r) {
    e.value = r;
  }
  function n(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: s, setExperimentMode: n };
}), Mg = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, jg = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, Lg = ["checked"], Dg = { class: "cmst:text-sm cmst:opacity-80" }, Vg = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, zg = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, $g = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Fg = { key: 0 }, Ug = /* @__PURE__ */ Vt({
  __name: "PlaygroundView",
  setup(e) {
    const t = Pg(), s = Jo(), n = /* @__PURE__ */ le(null), r = Oe(() => n.value ? s.get(n.value)?.progress ?? null : null);
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
    return (i, a) => (Se(), Le("section", {
      class: ht(D(Cn)()),
      "data-testid": "vue-page-playground"
    }, [
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          R("h2", Mg, [
            Y(D(ic), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = oe(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = R("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          R("label", jg, [
            R("input", {
              type: "checkbox",
              checked: D(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => D(t).setExperimentMode(l.target.checked))
            }, null, 40, Lg),
            a[2] || (a[2] = oe(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          a[5] || (a[5] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          R("p", Dg, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + fe(D(s).active.length) + ". ", 1),
          R("div", Vg, [
            Y(nt, {
              variant: "default",
              size: "sm",
              disabled: n.value !== null,
              onClick: o
            }, {
              default: _e(() => [
                Y(D(Mh), { "aria-hidden": "true" }),
                a[4] || (a[4] = oe(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? (Se(), Le("span", zg, fe(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : ns("", !0)
          ]),
          R("ul", $g, [
            (Se(!0), Le(We, null, xr(D(s).all.slice(-5), (l) => (Se(), Le("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              R("strong", null, fe(l.label), 1),
              oe(" — " + fe(l.status), 1),
              l.message ? (Se(), Le("span", Fg, " — " + fe(l.message), 1)) : ns("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), Bg = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Wg = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-3" }, Hg = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Zg = { class: "cmst:mt-3 cmst:text-sm" }, Gg = { key: 0 }, qg = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Kg = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Jg = ["value"], Yg = ["value"], Qg = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Xg = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, ey = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, ty = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, sy = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-3" }, ny = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, ry = ["checked"], oy = /* @__PURE__ */ Vt({
  __name: "SettingsView",
  setup(e) {
    const t = xc(), s = /* @__PURE__ */ le(75), n = /* @__PURE__ */ le(""), r = /* @__PURE__ */ le("off"), o = Oe(() => t.config), i = Oe(() => o.value?.available_gpus ?? []);
    async function a() {
      await t.save({
        quality: Number(s.value),
        save_folder: n.value
      });
    }
    async function l(d) {
      const h = d.target.value;
      await t.save({ gpu: h });
    }
    async function c(d) {
      await t.save({ skip_plan_validation: d.target.checked });
    }
    async function u() {
      await t.setProfile(r.value);
    }
    return (d, h) => (Se(), Le("section", {
      class: ht(D(Cn)()),
      "data-testid": "vue-page-settings"
    }, [
      D(t).error ? (Se(), Le("div", Bg, fe(D(t).error), 1)) : ns("", !0),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          R("div", Wg, [
            R("div", null, [
              R("h2", Hg, [
                Y(D(dc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                h[3] || (h[3] = oe(" Settings ", -1))
              ]),
              h[4] || (h[4] = R("p", { class: "cmst:text-sm cmst:opacity-80" }, " Server-backed Settings authority. Vue reads `/config` and projects proven output values one-way to legacy canvas consumers. ", -1))
            ]),
            Y(nt, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload settings",
              disabled: D(t).loading,
              onClick: D(t).load
            }, {
              default: _e(() => [
                Y(D(lc), {
                  class: ht(["cmst:size-4", D(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled", "onClick"])
          ]),
          R("p", Zg, [
            h[5] || (h[5] = oe(" Active section: ", -1)),
            R("strong", null, fe(D(t).activeSection), 1),
            D(t).config ? (Se(), Le("span", Gg, " · server config loaded")) : ns("", !0)
          ])
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          h[9] || (h[9] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Generation", -1)),
          R("div", qg, [
            R("label", Kg, [
              h[6] || (h[6] = oe(" GPU ", -1)),
              R("select", {
                value: o.value?.gpu ?? "",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-settings-gpu",
                onChange: l
              }, [
                (Se(!0), Le(We, null, xr(i.value, (p) => (Se(), Le("option", {
                  key: p.value,
                  value: p.value
                }, fe(p.label), 9, Yg))), 128))
              ], 40, Jg)
            ]),
            R("label", Qg, [
              h[8] || (h[8] = oe(" Profile/tracing level ", -1)),
              Ps(R("select", {
                "onUpdate:modelValue": h[0] || (h[0] = (p) => r.value = p),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: u
              }, [...h[7] || (h[7] = [
                R("option", { value: "off" }, "Off", -1),
                R("option", { value: "summary" }, "Summary", -1),
                R("option", { value: "detailed" }, "Detailed", -1),
                R("option", { value: "trace" }, "Trace", -1),
                R("option", { value: "trace_verbose" }, "Trace verbose", -1)
              ])], 544), [
                [Ul, r.value]
              ])
            ])
          ])
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          h[13] || (h[13] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Outputs / Data Saver", -1)),
          R("div", Xg, [
            R("label", ey, [
              h[10] || (h[10] = oe(" Quality ", -1)),
              Ps(R("input", {
                "onUpdate:modelValue": h[1] || (h[1] = (p) => s.value = p),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [
                  Yn,
                  s.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            R("label", ty, [
              h[11] || (h[11] = oe(" Save folder ", -1)),
              Ps(R("input", {
                "onUpdate:modelValue": h[2] || (h[2] = (p) => n.value = p),
                type: "text",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [Yn, n.value]
              ])
            ])
          ]),
          R("div", sy, [
            Y(nt, {
              size: "sm",
              disabled: D(t).saving,
              "data-testid": "vue-settings-save-output",
              onClick: a
            }, {
              default: _e(() => [
                oe(fe(D(t).saving ? "Saving…" : "Save output settings"), 1)
              ]),
              _: 1
            }, 8, ["disabled"]),
            h[12] || (h[12] = R("span", { class: "cmst:text-xs cmst:opacity-70" }, "Server truth is reread after every save.", -1))
          ])
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          h[15] || (h[15] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Advanced", -1)),
          R("label", ny, [
            R("input", {
              type: "checkbox",
              checked: o.value?.skip_plan_validation ?? !1,
              onChange: c
            }, null, 40, ry),
            h[14] || (h[14] = oe(" Skip plan validation (preserves current backend semantics) ", -1))
          ]),
          h[16] || (h[16] = R("p", { class: "cmst:mt-2 cmst:text-xs cmst:opacity-70" }, "Execution mode remains server-owned and V2-only.", -1))
        ]),
        _: 1
      })
    ], 2));
  }
}), iy = /* @__PURE__ */ Zs("studio-workflows", () => {
  const e = /* @__PURE__ */ le(null);
  function t(n) {
    e.value = n;
  }
  function s() {
    e.value = null;
  }
  return { selectedId: e, select: t, clear: s };
}), ay = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, ly = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, cy = { class: "cmst:text-sm cmst:mt-2" }, uy = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, dy = {
  class: "cmst:text-sm",
  "data-testid": "vue-poll-status"
}, fy = /* @__PURE__ */ Vt({
  __name: "WorkflowsView",
  setup(e) {
    const t = iy(), s = /* @__PURE__ */ le(""), n = /* @__PURE__ */ le("idle"), r = /* @__PURE__ */ le(0);
    async function o() {
      n.value = "polling…", r.value = 0;
      let i = 0;
      const a = await Sc({
        intervalMs: 120,
        run: async (l, c) => (r.value = c, i += 1, i >= 3 ? "ready" : "warming"),
        done: (l) => l === "ready"
      });
      n.value = a;
    }
    return (i, a) => (Se(), Le("section", {
      class: ht(D(Cn)()),
      "data-testid": "vue-page-workflows"
    }, [
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          R("h2", ay, [
            Y(D(ac), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[2] || (a[2] = oe(" Workflows (Phase-1 proof) ", -1))
          ]),
          a[5] || (a[5] = R("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Selection identity lives in the workflows store. ", -1)),
          R("div", ly, [
            Ps(R("input", {
              "onUpdate:modelValue": a[0] || (a[0] = (l) => s.value = l),
              type: "text",
              placeholder: "Workflow id",
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm"
            }, null, 512), [
              [Yn, s.value]
            ]),
            Y(nt, {
              variant: "secondary",
              size: "sm",
              onClick: a[1] || (a[1] = (l) => D(t).select(s.value.trim() || null))
            }, {
              default: _e(() => [...a[3] || (a[3] = [
                oe(" Select ", -1)
              ])]),
              _: 1
            })
          ]),
          R("p", cy, [
            a[4] || (a[4] = oe(" Store selection: ", -1)),
            R("strong", null, fe(D(t).selectedId ?? "none"), 1)
          ])
        ]),
        _: 1
      }),
      Y(ut, { class: "cmst:p-4" }, {
        default: _e(() => [
          a[7] || (a[7] = R("h3", { class: "cmst:text-sm cmst:font-semibold" }, "polling demo (local only)", -1)),
          a[8] || (a[8] = R("p", { class: "cmst:text-sm cmst:opacity-80" }, " Repeats a local status check until the completion predicate holds. ", -1)),
          R("div", uy, [
            Y(nt, {
              variant: "outline",
              size: "sm",
              "data-testid": "vue-poll-run",
              onClick: o
            }, {
              default: _e(() => [...a[6] || (a[6] = [
                oe(" Start local poll ", -1)
              ])]),
              _: 1
            }),
            R("span", dy, fe(n.value) + " (" + fe(r.value) + " attempts) ", 1)
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), hy = {
  playground: Ug,
  history: Ng,
  workflows: fy,
  backend: Ag,
  settings: oy
};
function my(e = {}) {
  let t;
  return e.memory || !e.win ? t = eh() : t = ig(e.win, e.initial), _h({
    history: t,
    routes: Ko.map((n) => ({
      path: `/${n}`,
      name: n,
      component: hy[n]
    }))
  });
}
function py(e, t = {}) {
  const s = hf(), n = my({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = uf(rg);
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
  py as mountStudioPreview
};

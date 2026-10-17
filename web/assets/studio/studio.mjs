/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function Fa(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const pt = {}, rn = [], ms = () => {
}, nc = () => !1, dr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), fr = (e) => e.startsWith("onUpdate:"), Pt = Object.assign, Ba = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, bd = Object.prototype.hasOwnProperty, ct = (e, t) => bd.call(e, t), Pe = Array.isArray, Gs = (e) => yo(e) === "[object Map]", Os = (e) => yo(e) === "[object Set]", vi = (e) => yo(e) === "[object Date]", Ge = (e) => typeof e == "function", yt = (e) => typeof e == "string", Kt = (e) => typeof e == "symbol", dt = (e) => e !== null && typeof e == "object", oc = (e) => (dt(e) || Ge(e)) && Ge(e.then) && Ge(e.catch), rc = Object.prototype.toString, yo = (e) => rc.call(e), wd = (e) => yo(e).slice(8, -1), ac = (e) => yo(e) === "[object Object]", mr = (e) => yt(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, Jn = /* @__PURE__ */ Fa(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), pr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, _d = /-\w/g, Vt = pr(
  (e) => e.replace(_d, (t) => t.slice(1).toUpperCase())
), xd = /\B([A-Z])/g, Qs = pr(
  (e) => e.replace(xd, "-$1").toLowerCase()
), vr = pr((e) => e.charAt(0).toUpperCase() + e.slice(1)), Mr = pr(
  (e) => e ? `on${vr(e)}` : ""
), us = (e, t) => !Object.is(e, t), Uo = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, ic = (e, t, s, n = !1) => {
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
let gi;
const hr = () => gi || (gi = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Pn(e) {
  if (Pe(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], o = yt(n) ? $d(n) : Pn(n);
      if (o)
        for (const r in o)
          t[r] = o[r];
    }
    return t;
  } else if (yt(e) || dt(e))
    return e;
}
const kd = /;(?![^(]*\))/g, Sd = /:([^]+)/, Cd = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function $d(e) {
  const t = {};
  return e.replace(Cd, (s) => s.startsWith("/*") ? "" : s).split(kd).forEach((s) => {
    if (s) {
      const n = s.split(Sd);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function Ve(e) {
  let t = "";
  if (yt(e))
    t = e;
  else if (Pe(e))
    for (let s = 0; s < e.length; s++) {
      const n = Ve(e[s]);
      n && (t += n + " ");
    }
  else if (dt(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const Id = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", Rd = /* @__PURE__ */ Fa(Id);
function lc(e) {
  return !!e || e === "";
}
function Ad(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let o = 0; n && o < e.length; o++)
    n = Ts(e[o], t[o], s);
  return n;
}
function hi(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), o = new Uint8Array(n.length);
  for (const r of e) {
    let a = -1;
    for (let i = 0; i < n.length; i++)
      if (!o[i] && Ts(r, n[i], s)) {
        a = i;
        break;
      }
    if (a < 0) return !1;
    o[a] = 1;
  }
  return !0;
}
function Ed(e, t, s) {
  let n = Gs(e), o = Gs(t);
  if (n || o || (n = Os(e), o = Os(t), n || o))
    return n && o ? hi(e, t, s) : !1;
  const r = Object.keys(e).length, a = Object.keys(t).length;
  if (r !== a)
    return !1;
  for (const i in e) {
    const l = e.hasOwnProperty(i), u = t.hasOwnProperty(i);
    if (l && !u || !l && u || !Ts(e[i], t[i], s))
      return !1;
  }
  return String(e) === String(t);
}
function yi(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [o, r] = s;
  if (o.has(e) || r.has(t))
    return o.get(e) === t && r.get(t) === e;
  o.set(e, t), r.set(t, e);
  const a = n(e, t, s);
  return o.delete(e), r.delete(t), a;
}
function Ts(e, t, s) {
  if (e === t) return !0;
  let n = vi(e), o = vi(t);
  return n || o ? n && o ? e.getTime() === t.getTime() : !1 : (n = Kt(e), o = Kt(t), n || o ? e === t : (n = Pe(e), o = Pe(t), n || o ? n && o ? yi(e, t, s, Ad) : !1 : (n = dt(e), o = dt(t), n || o ? !n || !o ? !1 : yi(e, t, s, Ed) : String(e) === String(t))));
}
function Wa(e, t) {
  return e.findIndex((s) => Ts(s, t));
}
const cc = (e) => !!(e && e.__v_isRef === !0), M = (e) => yt(e) ? e : e == null ? "" : Pe(e) || dt(e) && (e.toString === rc || !Ge(e.toString)) ? cc(e) ? M(e.value) : JSON.stringify(e, uc, 2) : String(e), uc = (e, t) => cc(t) ? uc(e, t.value) : Gs(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, o], r) => (s[Nr(n, r) + " =>"] = o, s),
    {}
  )
} : Os(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => Nr(s))
} : Kt(t) ? Nr(t) : dt(t) && !Pe(t) && !ac(t) ? String(t) : t, Nr = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    Kt(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let It;
class dc {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && It && (It.active ? (this.parent = It, this.index = (It.scopes || (It.scopes = [])).push(
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
        const o = this.scopes.slice();
        for (t = 0, s = o.length; t < s; t++)
          o[t].resume();
      }
      const n = this.effects.slice();
      for (t = 0, s = n.length; t < s; t++)
        n[t].resume();
    }
  }
  run(t) {
    if (this._active) {
      const s = It;
      try {
        return It = this, t();
      } finally {
        It = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = It, It = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (It === this)
        It = this.prevScope;
      else {
        let t = It;
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
        const o = this.scopes.slice();
        for (s = 0, n = o.length; s < n; s++)
          o[s].stop(!0);
        this.scopes.length = 0;
      }
      if (!this.detached && this.parent && !t) {
        const o = this.parent.scopes.pop();
        o && o !== this && (this.parent.scopes[this.index] = o, o.index = this.index);
      }
      this.parent = void 0;
    }
  }
}
function fc(e) {
  return new dc(e);
}
function mc() {
  return It;
}
function Od(e, t = !1) {
  It && It.cleanups.push(e);
}
let vt;
const zr = /* @__PURE__ */ new WeakSet();
class pc {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, It && (It.active ? It.effects.push(this) : this.flags &= -2);
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
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || gc(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, bi(this), hc(this);
    const t = vt, s = ts;
    vt = this, ts = !0;
    try {
      return this.fn();
    } finally {
      yc(this), vt = t, ts = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        Ha(t);
      this.deps = this.depsTail = void 0, bi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? zr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    ua(this) && this.run();
  }
  get dirty() {
    return ua(this);
  }
}
let vc = 0, Yn, Xn;
function gc(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = Xn, Xn = e;
    return;
  }
  e.next = Yn, Yn = e;
}
function Ga() {
  vc++;
}
function qa() {
  if (--vc > 0)
    return;
  if (Xn) {
    let t = Xn;
    for (Xn = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; Yn; ) {
    let t = Yn;
    for (Yn = void 0; t; ) {
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
function hc(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function yc(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const o = n.prevDep;
    n.version === -1 ? (n === s && (s = o), Ha(n), Td(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = o;
  }
  e.deps = t, e.depsTail = s;
}
function ua(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (bc(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function bc(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === oo) || (e.globalVersion = oo, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !ua(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = vt, n = ts;
  vt = e, ts = !0;
  try {
    hc(e);
    const o = e.fn(e._value);
    (t.version === 0 || us(o, e._value)) && (e.flags |= 128, e._value = o, t.version++);
  } catch (o) {
    throw t.version++, o;
  } finally {
    vt = s, ts = n, yc(e), e.flags &= -3;
  }
}
function Ha(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: o } = e;
  if (n && (n.nextSub = o, e.prevSub = void 0), o && (o.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let r = s.computed.deps; r; r = r.nextDep)
      Ha(r, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function Td(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let ts = !0;
const wc = [];
function gs() {
  wc.push(ts), ts = !1;
}
function hs() {
  const e = wc.pop();
  ts = e === void 0 ? !0 : e;
}
function bi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = vt;
    vt = void 0;
    try {
      t();
    } finally {
      vt = s;
    }
  }
}
let oo = 0;
class Pd {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Za {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!vt || !ts || vt === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== vt)
      s = this.activeLink = new Pd(vt, this), vt.deps ? (s.prevDep = vt.depsTail, vt.depsTail.nextDep = s, vt.depsTail = s) : vt.deps = vt.depsTail = s, _c(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = vt.depsTail, s.nextDep = void 0, vt.depsTail.nextDep = s, vt.depsTail = s, vt.deps === s && (vt.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, oo++, this.notify(t);
  }
  notify(t) {
    Ga();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      qa();
    }
  }
}
function _c(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        _c(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const Wo = /* @__PURE__ */ new WeakMap(), ln = /* @__PURE__ */ Symbol(
  ""
), da = /* @__PURE__ */ Symbol(
  ""
), ro = /* @__PURE__ */ Symbol(
  ""
);
function Nt(e, t, s) {
  if (ts && vt) {
    let n = Wo.get(e);
    n || Wo.set(e, n = /* @__PURE__ */ new Map());
    let o = n.get(s);
    o || (n.set(s, o = new Za()), o.map = n, o.key = s), o.track();
  }
}
function $s(e, t, s, n, o, r) {
  const a = Wo.get(e);
  if (!a) {
    oo++;
    return;
  }
  const i = (l) => {
    l && l.trigger();
  };
  if (Ga(), t === "clear")
    a.forEach(i);
  else {
    const l = Pe(e), u = l && mr(s);
    if (l && s === "length") {
      const d = Number(n);
      a.forEach((f, b) => {
        (b === "length" || b === ro || !Kt(b) && b >= d) && i(f);
      });
    } else
      switch ((s !== void 0 || a.has(void 0)) && i(a.get(s)), u && i(a.get(ro)), t) {
        case "add":
          l ? u && i(a.get("length")) : (i(a.get(ln)), Gs(e) && i(a.get(da)));
          break;
        case "delete":
          l || (i(a.get(ln)), Gs(e) && i(a.get(da)));
          break;
        case "set":
          Gs(e) && i(a.get(ln));
          break;
      }
  }
  qa();
}
function Md(e, t) {
  const s = Wo.get(e);
  return s && s.get(t);
}
function pn(e) {
  const t = /* @__PURE__ */ rt(e);
  return t === e || (Nt(t, "iterate", ro), /* @__PURE__ */ Ht(e)) ? t : /* @__PURE__ */ ys(e) ? /* @__PURE__ */ ps(e) ? t.map((s) => Hs(Jt(s))) : t.map(Hs) : t.map(Jt);
}
function yr(e) {
  return Nt(e = /* @__PURE__ */ rt(e), "iterate", ro), e;
}
function is(e, t) {
  return /* @__PURE__ */ ys(e) ? Hs(/* @__PURE__ */ ps(e) ? Jt(t) : t) : Jt(t);
}
const Nd = {
  __proto__: null,
  [Symbol.iterator]() {
    return Dr(this, Symbol.iterator, (e) => is(this, e));
  },
  concat(...e) {
    return pn(this).concat(
      ...e.map((t) => Pe(t) ? pn(t) : t)
    );
  },
  entries() {
    return Dr(this, "entries", (e) => (e[1] = is(this, e[1]), e));
  },
  every(e, t) {
    return ws(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return ws(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => is(this, n)),
      arguments
    );
  },
  find(e, t) {
    return ws(
      this,
      "find",
      e,
      t,
      (s) => is(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return ws(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return ws(
      this,
      "findLast",
      e,
      t,
      (s) => is(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return ws(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return ws(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return jr(this, "includes", e);
  },
  indexOf(...e) {
    return jr(this, "indexOf", e);
  },
  join(e) {
    return pn(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return jr(this, "lastIndexOf", e);
  },
  map(e, t) {
    return ws(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return zn(this, "pop");
  },
  push(...e) {
    return zn(this, "push", e);
  },
  reduce(e, ...t) {
    return _i(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return _i(this, "reduceRight", e, t);
  },
  shift() {
    return zn(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return ws(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return zn(this, "splice", e);
  },
  toReversed() {
    return pn(this).toReversed();
  },
  toSorted(e) {
    return pn(this).toSorted(e);
  },
  toSpliced(...e) {
    return pn(this).toSpliced(...e);
  },
  unshift(...e) {
    return zn(this, "unshift", e);
  },
  values() {
    return Dr(this, "values", (e) => is(this, e));
  }
};
function Dr(e, t, s) {
  const n = yr(e), o = n[t], r = o.call(n);
  if (n !== e && !/* @__PURE__ */ Ht(e)) {
    if (r[Symbol.toStringTag] === "Array Iterator") {
      const a = Object.create(Object.getPrototypeOf(r));
      return a.next = () => wi(r.next(), s), o !== xc[t] && Object.defineProperties(a, {
        return: {
          get() {
            const i = r.return;
            return typeof i == "function" ? i.bind(r) : i;
          }
        },
        throw: {
          get() {
            const i = r.throw;
            return typeof i == "function" ? i.bind(r) : i;
          }
        }
      }), a;
    }
    r._next = r.next, r.next = () => wi(r._next(), s);
  }
  return r;
}
function wi(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const xc = Array.prototype;
function ws(e, t, s, n, o, r) {
  const a = yr(e), i = a !== e && !/* @__PURE__ */ Ht(e), l = a[t];
  if (l !== xc[t]) {
    const f = l.apply(e, r);
    return i ? Jt(f) : f;
  }
  let u = s;
  a !== e && (i ? u = function(f, b) {
    return s.call(this, is(e, f), b, e);
  } : s.length > 2 && (u = function(f, b) {
    return s.call(this, f, b, e);
  }));
  const d = l.call(a, u, n);
  return i && o ? o(d) : d;
}
function _i(e, t, s, n) {
  const o = yr(e), r = o !== e && !/* @__PURE__ */ Ht(e);
  let a = s, i = !1;
  o !== e && (r ? (i = n.length === 0, a = function(u, d, f) {
    return i && (i = !1, u = is(e, u)), s.call(this, u, is(e, d), f, e);
  }) : s.length > 3 && (a = function(u, d, f) {
    return s.call(this, u, d, f, e);
  }));
  const l = o[t](a, ...n);
  return i ? is(e, l) : l;
}
function jr(e, t, s) {
  const n = /* @__PURE__ */ rt(e);
  Nt(n, "iterate", ro);
  const o = n[t](...s);
  return (o === -1 || o === !1) && /* @__PURE__ */ br(s[0]) ? (s[0] = /* @__PURE__ */ rt(s[0]), n[t](...s)) : o;
}
function zn(e, t, s = []) {
  gs(), Ga();
  const n = (/* @__PURE__ */ rt(e))[t].apply(e, s);
  return qa(), hs(), n;
}
const zd = /* @__PURE__ */ Fa("__proto__,__v_isRef,__isVue"), kc = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(Kt)
);
function Dd(e) {
  Kt(e) || (e = String(e));
  const t = /* @__PURE__ */ rt(this);
  return Nt(t, "has", e), t.hasOwnProperty(e);
}
class Sc {
  constructor(t = !1, s = !1) {
    this._isReadonly = t, this._isShallow = s;
  }
  get(t, s, n) {
    if (s === "__v_skip") return t.__v_skip;
    const o = this._isReadonly, r = this._isShallow;
    if (s === "__v_isReactive")
      return !o;
    if (s === "__v_isReadonly")
      return o;
    if (s === "__v_isShallow")
      return r;
    if (s === "__v_raw")
      return n === (o ? r ? Hd : Rc : r ? Ic : $c).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const a = Pe(t);
    if (!o) {
      let l;
      if (a && (l = Nd[s]))
        return l;
      if (s === "hasOwnProperty")
        return Dd;
    }
    const i = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ xt(t) ? t : n
    );
    if ((Kt(s) ? kc.has(s) : zd(s)) || (o || Nt(t, "get", s), r))
      return i;
    if (/* @__PURE__ */ xt(i)) {
      const l = a && mr(s) ? i : i.value;
      return o && dt(l) ? /* @__PURE__ */ ma(l) : l;
    }
    return dt(i) ? o ? /* @__PURE__ */ ma(i) : /* @__PURE__ */ bo(i) : i;
  }
}
class Cc extends Sc {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, o) {
    let r = t[s];
    const a = Pe(t) && mr(s);
    if (!this._isShallow) {
      const u = /* @__PURE__ */ ys(r);
      if (!/* @__PURE__ */ Ht(n) && !/* @__PURE__ */ ys(n) && (r = /* @__PURE__ */ rt(r), n = /* @__PURE__ */ rt(n)), !a && /* @__PURE__ */ xt(r) && !/* @__PURE__ */ xt(n))
        return u || (r.value = n), !0;
    }
    const i = a ? Number(s) < t.length : ct(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ xt(t) ? t : o
    );
    return t === /* @__PURE__ */ rt(o) && l && (i ? us(n, r) && $s(t, "set", s, n) : $s(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = ct(t, s);
    t[s];
    const o = Reflect.deleteProperty(t, s);
    return o && n && $s(t, "delete", s, void 0), o;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!Kt(s) || !kc.has(s)) && Nt(t, "has", s), n;
  }
  ownKeys(t) {
    return Nt(
      t,
      "iterate",
      Pe(t) ? "length" : ln
    ), Reflect.ownKeys(t);
  }
}
class jd extends Sc {
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
const Ld = /* @__PURE__ */ new Cc(), Ud = /* @__PURE__ */ new jd(), Vd = /* @__PURE__ */ new Cc(!0);
const fa = (e) => e, Co = (e) => Reflect.getPrototypeOf(e);
function Fd(e, t, s) {
  return function(...n) {
    const o = this.__v_raw, r = /* @__PURE__ */ rt(o), a = Gs(r), i = e === "entries" || e === Symbol.iterator && a, l = e === "keys" && a, u = o[e](...n), d = s ? fa : t ? Hs : Jt;
    return !t && Nt(
      r,
      "iterate",
      l ? da : ln
    ), Pt(
      // inheriting all iterator properties
      Object.create(u),
      {
        // iterator protocol
        next() {
          const { value: f, done: b } = u.next();
          return b ? { value: f, done: b } : {
            value: i ? [d(f[0]), d(f[1])] : d(f),
            done: b
          };
        }
      }
    );
  };
}
function $o(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function Bd(e, t) {
  const s = {
    get(o) {
      const r = this.__v_raw, a = /* @__PURE__ */ rt(r), i = /* @__PURE__ */ rt(o);
      e || (us(o, i) && Nt(a, "get", o), Nt(a, "get", i));
      const { has: l } = Co(a), u = t ? fa : e ? Hs : Jt;
      if (l.call(a, o))
        return u(r.get(o));
      if (l.call(a, i))
        return u(r.get(i));
      r !== a && r.get(o);
    },
    get size() {
      const o = this.__v_raw;
      return !e && Nt(/* @__PURE__ */ rt(o), "iterate", ln), o.size;
    },
    has(o) {
      const r = this.__v_raw, a = /* @__PURE__ */ rt(r), i = /* @__PURE__ */ rt(o);
      return e || (us(o, i) && Nt(a, "has", o), Nt(a, "has", i)), o === i ? r.has(o) : r.has(o) || r.has(i);
    },
    forEach(o, r) {
      const a = this, i = a.__v_raw, l = /* @__PURE__ */ rt(i), u = t ? fa : e ? Hs : Jt;
      return !e && Nt(l, "iterate", ln), i.forEach((d, f) => o.call(r, u(d), u(f), a));
    }
  };
  return Pt(
    s,
    e ? {
      add: $o("add"),
      set: $o("set"),
      delete: $o("delete"),
      clear: $o("clear")
    } : {
      add(o) {
        const r = /* @__PURE__ */ rt(this), a = Co(r), i = /* @__PURE__ */ rt(o), l = !t && !/* @__PURE__ */ Ht(o) && !/* @__PURE__ */ ys(o) ? i : o;
        return a.has.call(r, l) || us(o, l) && a.has.call(r, o) || us(i, l) && a.has.call(r, i) || (r.add(l), $s(r, "add", l, l)), this;
      },
      set(o, r) {
        !t && !/* @__PURE__ */ Ht(r) && !/* @__PURE__ */ ys(r) && (r = /* @__PURE__ */ rt(r));
        const a = /* @__PURE__ */ rt(this), { has: i, get: l } = Co(a);
        let u = i.call(a, o);
        u || (o = /* @__PURE__ */ rt(o), u = i.call(a, o));
        const d = l.call(a, o);
        return a.set(o, r), u ? us(r, d) && $s(a, "set", o, r) : $s(a, "add", o, r), this;
      },
      delete(o) {
        const r = /* @__PURE__ */ rt(this), { has: a, get: i } = Co(r);
        let l = a.call(r, o);
        l || (o = /* @__PURE__ */ rt(o), l = a.call(r, o)), i && i.call(r, o);
        const u = r.delete(o);
        return l && $s(r, "delete", o, void 0), u;
      },
      clear() {
        const o = /* @__PURE__ */ rt(this), r = o.size !== 0, a = o.clear();
        return r && $s(
          o,
          "clear",
          void 0,
          void 0
        ), a;
      }
    }
  ), [
    "keys",
    "values",
    "entries",
    Symbol.iterator
  ].forEach((o) => {
    s[o] = Fd(o, e, t);
  }), s;
}
function Ka(e, t) {
  const s = Bd(e, t);
  return (n, o, r) => o === "__v_isReactive" ? !e : o === "__v_isReadonly" ? e : o === "__v_isShallow" ? t : o === "__v_raw" ? n : Reflect.get(
    ct(s, o) && o in n ? s : n,
    o,
    r
  );
}
const Wd = {
  get: /* @__PURE__ */ Ka(!1, !1)
}, Gd = {
  get: /* @__PURE__ */ Ka(!1, !0)
}, qd = {
  get: /* @__PURE__ */ Ka(!0, !1)
};
const $c = /* @__PURE__ */ new WeakMap(), Ic = /* @__PURE__ */ new WeakMap(), Rc = /* @__PURE__ */ new WeakMap(), Hd = /* @__PURE__ */ new WeakMap();
function Zd(e) {
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
function bo(e) {
  return /* @__PURE__ */ ys(e) ? e : Qa(
    e,
    !1,
    Ld,
    Wd,
    $c
  );
}
// @__NO_SIDE_EFFECTS__
function Ac(e) {
  return Qa(
    e,
    !1,
    Vd,
    Gd,
    Ic
  );
}
// @__NO_SIDE_EFFECTS__
function ma(e) {
  return Qa(
    e,
    !0,
    Ud,
    qd,
    Rc
  );
}
function Qa(e, t, s, n, o) {
  if (!dt(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const r = o.get(e);
  if (r)
    return r;
  const a = Zd(wd(e));
  if (a === 0)
    return e;
  const i = new Proxy(
    e,
    a === 2 ? n : s
  );
  return o.set(e, i), i;
}
// @__NO_SIDE_EFFECTS__
function ps(e) {
  return /* @__PURE__ */ ys(e) ? /* @__PURE__ */ ps(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function ys(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function Ht(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function br(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function rt(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ rt(t) : e;
}
function Ja(e) {
  return !ct(e, "__v_skip") && Object.isExtensible(e) && ic(e, "__v_skip", !0), e;
}
const Jt = (e) => dt(e) ? /* @__PURE__ */ bo(e) : e, Hs = (e) => dt(e) ? /* @__PURE__ */ ma(e) : e;
// @__NO_SIDE_EFFECTS__
function xt(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function I(e) {
  return Ec(e, !1);
}
// @__NO_SIDE_EFFECTS__
function Kd(e) {
  return Ec(e, !0);
}
function Ec(e, t) {
  return /* @__PURE__ */ xt(e) ? e : new Qd(e, t);
}
class Qd {
  constructor(t, s) {
    this.dep = new Za(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ rt(t), this._value = s ? t : Jt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ Ht(t) || /* @__PURE__ */ ys(t);
    t = n ? t : /* @__PURE__ */ rt(t), us(t, s) && (this._rawValue = t, this._value = n ? t : Jt(t), this.dep.trigger());
  }
}
function m(e) {
  return /* @__PURE__ */ xt(e) ? e.value : e;
}
const Jd = {
  get: (e, t, s) => t === "__v_raw" ? e : m(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const o = e[t];
    return /* @__PURE__ */ xt(o) && !/* @__PURE__ */ xt(s) ? (o.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function Oc(e) {
  return /* @__PURE__ */ ps(e) ? e : new Proxy(e, Jd);
}
// @__NO_SIDE_EFFECTS__
function Yd(e) {
  const t = Pe(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = ef(e, s);
  return t;
}
class Xd {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = Kt(s) ? s : String(s), this._raw = /* @__PURE__ */ rt(t);
    let o = !0, r = t;
    if (!Pe(t) || Kt(this._key) || !mr(this._key))
      do
        o = !/* @__PURE__ */ br(r) || /* @__PURE__ */ Ht(r);
      while (o && (r = r.__v_raw));
    this._shallow = o;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = m(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ xt(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ xt(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return Md(this._raw, this._key);
  }
}
function ef(e, t, s) {
  return new Xd(e, t, s);
}
class tf {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new Za(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = oo - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    vt !== this)
      return gc(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return bc(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function sf(e, t, s = !1) {
  let n, o;
  return Ge(e) ? n = e : (n = e.get, o = e.set), new tf(n, o, s);
}
const Io = {}, Go = /* @__PURE__ */ new WeakMap();
let nn;
function nf(e, t = !1, s = nn) {
  if (s) {
    let n = Go.get(s);
    n || Go.set(s, n = []), n.push(e);
  }
}
function of(e, t, s = pt) {
  const { immediate: n, deep: o, once: r, scheduler: a, augmentJob: i, call: l } = s, u = (R) => o ? R : /* @__PURE__ */ Ht(R) || o === !1 || o === 0 ? Is(R, 1) : Is(R);
  let d, f, b, h, O = !1, x = !1;
  if (/* @__PURE__ */ xt(e) ? (f = () => e.value, O = /* @__PURE__ */ Ht(e)) : /* @__PURE__ */ ps(e) ? (f = () => u(e), O = !0) : Pe(e) ? (x = !0, O = e.some((R) => /* @__PURE__ */ ps(R) || /* @__PURE__ */ Ht(R)), f = () => e.map((R) => {
    if (/* @__PURE__ */ xt(R))
      return R.value;
    if (/* @__PURE__ */ ps(R))
      return u(R);
    if (Ge(R))
      return l ? l(R, 2) : R();
  })) : Ge(e) ? t ? f = l ? () => l(e, 2) : e : f = () => {
    if (b) {
      gs();
      try {
        b();
      } finally {
        hs();
      }
    }
    const R = nn;
    nn = d;
    try {
      return l ? l(e, 3, [h]) : e(h);
    } finally {
      nn = R;
    }
  } : f = ms, t && o) {
    const R = f, J = o === !0 ? 1 / 0 : o;
    f = () => Is(R(), J);
  }
  const C = mc(), T = () => {
    d.stop(), C && C.active && Ba(C.effects, d);
  };
  if (r && t) {
    const R = t;
    t = (...J) => {
      try {
        return R(...J);
      } finally {
        T();
      }
    };
  }
  let A = x ? new Array(e.length).fill(Io) : Io;
  const z = (R) => {
    if (!(!(d.flags & 1) || !d.dirty && !R))
      if (t) {
        const J = d.run();
        if (R || o || O || (x ? J.some(($e, ne) => us($e, A[ne])) : us(J, A))) {
          const $e = nn;
          gs();
          try {
            b && b(), nn = d;
            const ne = [
              J,
              // pass undefined as the old value when it's changed for the first time
              A === Io ? void 0 : x && A[0] === Io ? [] : A,
              h
            ];
            A = J, l ? l(t, 3, ne) : (
              // @ts-expect-error
              t(...ne)
            );
          } finally {
            nn = $e, hs();
          }
        }
      } else
        d.run();
  };
  return i && i(z), d = new pc(f), d.scheduler = a ? () => a(z, !1) : z, h = (R) => nf(R, !1, d), b = d.onStop = () => {
    const R = Go.get(d);
    if (R) {
      if (l)
        l(R, 4);
      else
        for (const J of R) J();
      Go.delete(d);
    }
  }, t ? n ? z(!0) : A = d.run() : a ? a(z.bind(null, !0), !0) : d.run(), T.pause = d.pause.bind(d), T.resume = d.resume.bind(d), T.stop = T, T;
}
function Is(e, t = 1 / 0, s) {
  if (t <= 0 || !dt(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ xt(e))
    Is(e.value, t, s);
  else if (Pe(e))
    for (let n = 0; n < e.length; n++)
      Is(e[n], t, s);
  else if (Os(e) || Gs(e))
    e.forEach((n) => {
      Is(n, t, s);
    });
  else if (ac(e)) {
    for (const n in e)
      Is(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && Is(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function wo(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (o) {
    wr(o, t, s);
  }
}
function ns(e, t, s, n) {
  if (Ge(e)) {
    const o = wo(e, t, s, n);
    return o && oc(o) && o.catch((r) => {
      wr(r, t, s);
    }), o;
  }
  if (Pe(e)) {
    const o = [];
    for (let r = 0; r < e.length; r++)
      o.push(ns(e[r], t, s, n));
    return o;
  }
}
function wr(e, t, s, n = !0) {
  const o = t ? t.vnode : null, { errorHandler: r, throwUnhandledErrorInProduction: a } = t && t.appContext.config || pt;
  if (t) {
    let i = t.parent;
    const l = t.proxy, u = `https://vuejs.org/error-reference/#runtime-${s}`;
    for (; i; ) {
      const d = i.ec;
      if (d) {
        for (let f = 0; f < d.length; f++)
          if (d[f](e, l, u) === !1)
            return;
      }
      i = i.parent;
    }
    if (r) {
      gs(), wo(r, null, 10, [
        e,
        l,
        u
      ]), hs();
      return;
    }
  }
  rf(e, s, o, n, a);
}
function rf(e, t, s, n = !0, o = !1) {
  if (o)
    throw e;
  console.error(e);
}
const Ut = [];
let es = -1;
const ls = [];
let Vs = null, yn = 0;
const Tc = /* @__PURE__ */ Promise.resolve();
let qo = null;
function _o(e) {
  const t = qo || Tc;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function af(e) {
  let t = es + 1, s = Ut.length;
  for (; t < s; ) {
    const n = t + s >>> 1, o = Ut[n], r = ao(o);
    r < e || r === e && o.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function Ya(e) {
  if (!(e.flags & 1)) {
    const t = ao(e), s = Ut[Ut.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= ao(s) ? Ut.push(e) : Ut.splice(af(t), 0, e), e.flags |= 1, Pc();
  }
}
function Pc() {
  qo || (qo = Tc.then(zc));
}
function lf(e) {
  if (!Pe(e))
    Vs && e.id === -1 ? Vs.splice(yn + 1, 0, e) : e.flags & 1 || (ls.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      ls.push(e[t]);
  Pc();
}
function Mc(e, t, s, n = es + 1) {
  for (; n < Ut.length; n++) {
    const o = Ut[n];
    if (o && o.flags & 2) {
      if (e && o.id !== e.uid || t !== void 0 && !(o.id >= t))
        continue;
      Ut.splice(n, 1), n = e ? n - 1 : es, o.flags & 4 && (o.flags &= -2), o(), o.flags & 4 || (o.flags &= -2);
    }
  }
}
function Nc(e, t, s = 0) {
  if (ls.length) {
    let n = ls, o = 0;
    if (t) {
      n = [];
      for (let a = 0; a < ls.length; a++) {
        const i = ls[a];
        (i.i !== void 0 ? !i.i || i.i.uid < s : t.has(i)) ? ls[o++] = i : n.push(i);
      }
    }
    const r = [...new Set(n)].sort((a, i) => ao(a) - ao(i));
    if (ls.length = o, Vs) {
      for (let a = 0; a < r.length; a++)
        Vs.push(r[a]);
      return;
    }
    for (Vs = r, yn = 0; yn < Vs.length; yn++) {
      const a = Vs[yn];
      a.flags & 4 && (a.flags &= -2), a.flags & 8 || a(), a.flags &= -2;
    }
    Vs = null, yn = 0;
  }
}
let Lr = !1;
function cf(e, t) {
  if (Lr) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(ls);
  e(), Lr = !0;
  try {
    Mc(void 0, t), Nc(void 0, s, t);
  } finally {
    Lr = !1;
  }
}
const ao = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function zc(e) {
  try {
    for (es = 0; es < Ut.length; es++) {
      const t = Ut[es];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), wo(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; es < Ut.length; es++) {
      const t = Ut[es];
      t && (t.flags &= -2);
    }
    es = -1, Ut.length = 0, Nc(), qo = null, (Ut.length || ls.length) && zc();
  }
}
let Tt = null, Dc = null;
function Ho(e) {
  const t = Tt;
  return Tt = e, Dc = e && e.type.__scopeId || null, t;
}
function X(e, t = Tt, s) {
  if (!t || e._n)
    return e;
  const n = (...o) => {
    n._d && Jo(-1);
    const r = Ho(t), a = Es.length;
    let i;
    try {
      i = e(...o);
    } finally {
      for (let l = Es.length; l > a; l--) ni();
      Ho(r), n._d && Jo(1);
    }
    return i;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function je(e, t) {
  if (Tt === null)
    return e;
  const s = Cr(Tt), n = e.dirs || (e.dirs = []);
  for (let o = 0; o < t.length; o++) {
    let [r, a, i, l = pt] = t[o];
    r && (Ge(r) && (r = {
      mounted: r,
      updated: r
    }), r.deep && Is(a), n.push({
      dir: r,
      instance: s,
      value: a,
      oldValue: void 0,
      arg: i,
      modifiers: l
    }));
  }
  return e;
}
function Ys(e, t, s, n) {
  const o = e.dirs, r = t && t.dirs;
  for (let a = 0; a < o.length; a++) {
    const i = o[a];
    r && (i.oldValue = r[a].value);
    let l = i.dir[n];
    l && (gs(), ns(l, s, 8, [
      e.el,
      i,
      e,
      t
    ]), hs());
  }
}
function Vo(e, t) {
  if (zt) {
    let s = zt.provides;
    const n = zt.parent && zt.parent.provides;
    n === s && (s = zt.provides = Object.create(n)), s[e] = t;
  }
}
function Zt(e, t, s = !1) {
  const n = pu();
  if (n || cn) {
    let o = cn ? cn._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (o && e in o)
      return o[e];
    if (arguments.length > 1)
      return s && Ge(t) ? t.call(n && n.proxy) : t;
  }
}
function uf() {
  return !!(pu() || cn);
}
const df = /* @__PURE__ */ Symbol.for("v-scx"), ff = () => Zt(df);
function ss(e, t, s) {
  return jc(e, t, s);
}
function jc(e, t, s = pt) {
  const { immediate: n, deep: o, flush: r, once: a } = s, i = Pt({}, s), l = t && n || !t && r !== "post";
  let u;
  if (co) {
    if (r === "sync") {
      const h = ff();
      u = h.__watcherHandles || (h.__watcherHandles = []);
    } else if (!l) {
      const h = () => {
      };
      return h.stop = ms, h.resume = ms, h.pause = ms, h;
    }
  }
  const d = zt;
  i.call = (h, O, x) => ns(h, d, O, x);
  let f = !1;
  r === "post" ? i.scheduler = (h) => {
    h.i = d, jt(h, d && d.suspense);
  } : r !== "sync" && (f = !0, i.scheduler = (h, O) => {
    O ? h() : Ya(h);
  }), i.augmentJob = (h) => {
    t && (h.flags |= 4), f && (h.flags |= 2, d && (h.id = d.uid, h.i = d));
  };
  const b = of(e, t, i);
  return co && (u ? u.push(b) : l && b()), b;
}
function mf(e, t, s) {
  const n = this.proxy, o = yt(e) ? e.includes(".") ? Lc(n, e) : () => n[e] : e.bind(n, n);
  let r;
  Ge(t) ? r = t : (r = t.handler, s = t);
  const a = ko(this), i = jc(o, r.bind(n), s);
  return a(), i;
}
function Lc(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let o = 0; o < s.length && n; o++)
      n = n[s[o]];
    return n;
  };
}
const Ls = /* @__PURE__ */ new WeakMap(), Uc = /* @__PURE__ */ Symbol("_vte"), _r = (e) => e.__isTeleport, on = (e) => e && (e.disabled || e.disabled === ""), pf = (e) => e && (e.defer || e.defer === ""), xi = (e) => typeof SVGElement < "u" && e instanceof SVGElement, ki = (e) => typeof MathMLElement == "function" && e instanceof MathMLElement, pa = (e, t) => {
  const s = e && e.to;
  return yt(s) ? t ? t(s) : null : s;
}, vf = {
  name: "Teleport",
  __isTeleport: !0,
  process(e, t, s, n, o, r, a, i, l, u) {
    const {
      mc: d,
      pc: f,
      pbc: b,
      o: { insert: h, querySelector: O, createText: x, createComment: C, parentNode: T }
    } = u, A = on(t.props);
    let { dynamicChildren: z } = t;
    const R = (ne, j, re) => {
      ne.shapeFlag & 16 && d(
        ne.children,
        j,
        re,
        o,
        r,
        a,
        i,
        l
      );
    }, J = (ne = t) => {
      const j = on(ne.props), re = ne.target = pa(ne.props, O), ve = va(re, ne, x, h);
      re && (a !== "svg" && xi(re) ? a = "svg" : a !== "mathml" && ki(re) && (a = "mathml"), o && o.isCE && (o.ce._teleportTargets || (o.ce._teleportTargets = /* @__PURE__ */ new Set())).add(re), j || (R(ne, re, ve), Gn(ne, !1)));
    }, $e = (ne) => {
      const j = () => {
        if (Ls.get(ne) === j) {
          if (Ls.delete(ne), on(ne.props)) {
            const re = T(ne.el) || s;
            R(ne, re, ne.anchor), Gn(ne, !0);
          }
          J(ne);
        }
      };
      Ls.set(ne, j), jt(j, r);
    };
    if (e == null) {
      const ne = t.el = x(""), j = t.anchor = x("");
      if (h(ne, s, n), h(j, s, n), pf(t.props) || r && r.pendingBranch) {
        $e(t);
        return;
      }
      A && (R(t, s, j), Gn(t, !0)), J();
    } else {
      t.el = e.el;
      const ne = t.anchor = e.anchor, j = Ls.get(e);
      if (j) {
        j.flags |= 8, Ls.delete(e), $e(t);
        return;
      }
      t.targetStart = e.targetStart;
      const re = t.target = e.target, ve = t.targetAnchor = e.targetAnchor, Me = on(e.props), Ie = Me ? s : re, Oe = Me ? ne : ve;
      if (a === "svg" || xi(re) ? a = "svg" : (a === "mathml" || ki(re)) && (a = "mathml"), z ? (b(
        e.dynamicChildren,
        z,
        Ie,
        o,
        r,
        a,
        i
      ), si(e, t, !0)) : l || f(
        e,
        t,
        Ie,
        Oe,
        o,
        r,
        a,
        i,
        !1
      ), A)
        Me ? t.props && e.props && t.props.to !== e.props.to && (t.props.to = e.props.to) : Ro(
          t,
          s,
          ne,
          u,
          1
        );
      else if ((t.props && t.props.to) !== (e.props && e.props.to)) {
        const Ye = pa(t.props, O);
        Ye && (t.target = Ye, Ro(
          t,
          Ye,
          null,
          u,
          0
        ));
      } else Me && Ro(
        t,
        re,
        ve,
        u,
        1
      );
      Gn(t, A);
    }
  },
  remove(e, t, s, { um: n, o: { remove: o } }, r) {
    const {
      shapeFlag: a,
      children: i,
      anchor: l,
      targetStart: u,
      targetAnchor: d,
      target: f,
      props: b
    } = e, h = on(b), O = r || !h, x = Ls.get(e);
    if (x && (x.flags |= 8, Ls.delete(e)), f && (o(u), o(d)), r && o(l), !x && (h || f) && a & 16)
      for (let C = 0; C < i.length; C++) {
        const T = i[C];
        n(
          T,
          t,
          s,
          O,
          !!T.dynamicChildren
        );
      }
  },
  move: Ro,
  hydrate: gf
};
function Ro(e, t, s, { o: { insert: n }, m: o }, r = 2) {
  r === 0 && (e.targetStart && n(e.targetStart, t, s), n(e.targetAnchor, t, s), s = e.targetAnchor);
  const { el: a, anchor: i, shapeFlag: l, children: u, props: d } = e, f = r === 2;
  if (f && n(a, t, s), !Ls.has(e) && (!f || on(d)) && l & 16)
    for (let b = 0; b < u.length; b++)
      o(
        u[b],
        t,
        s,
        2
      );
  f && n(i, t, s);
}
function gf(e, t, s, n, o, r, {
  o: { nextSibling: a, parentNode: i, querySelector: l, insert: u, createText: d }
}, f) {
  function b(C, T) {
    let A = T;
    for (; A; ) {
      if (A && A.nodeType === 8) {
        if (A.data === "teleport start anchor")
          t.targetStart = A;
        else if (A.data === "teleport anchor") {
          t.targetAnchor = A, C._lpa = t.targetAnchor && a(t.targetAnchor);
          break;
        }
      }
      A = a(A);
    }
  }
  function h(C, T) {
    T.anchor = f(
      a(C),
      T,
      i(C),
      s,
      n,
      o,
      r
    );
  }
  const O = t.target = pa(
    t.props,
    l
  ), x = on(t.props);
  if (O) {
    const C = O._lpa || O.firstChild;
    t.shapeFlag & 16 && (x ? (h(e, t), b(O, C), t.targetAnchor || va(
      O,
      t,
      d,
      u,
      // if target is the same as the main view, insert anchors before current node
      // to avoid hydrating mismatch
      i(e) === O ? e : null
    )) : (t.anchor = a(e), b(O, C), t.targetAnchor || va(O, t, d, u), f(
      C && a(C),
      t,
      O,
      s,
      n,
      o,
      r
    ))), Gn(t, x);
  } else x && t.shapeFlag & 16 && (h(e, t), t.targetStart = e, t.targetAnchor = a(e));
  return t.anchor && a(t.anchor);
}
const Vc = vf;
function Gn(e, t) {
  const s = e.ctx;
  if (s && s.ut) {
    let n, o;
    for (t ? (n = e.el, o = e.anchor) : (n = e.targetStart, o = e.targetAnchor); n && n !== o; )
      n.nodeType === 1 && n.setAttribute("data-v-owner", s.uid), n = n.nextSibling;
    s.ut();
  }
}
function va(e, t, s, n, o = null) {
  const r = t.targetStart = s(""), a = t.targetAnchor = s("");
  return r[Uc] = a, e && (n(r, e, o), n(a, e, o)), a;
}
const Ur = /* @__PURE__ */ Symbol("_leaveCb");
function hf(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const s of e)
      if (s.type !== Yt) {
        t = s;
        break;
      }
  }
  return t;
}
function Fc(e) {
  if (!Xa(e))
    return _r(e.type) && e.children ? hf(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && Ge(s.default))
      return s.default();
  }
}
function Zo(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    Zo(
      _r(s.type) && Fc(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === de && Pe(e.children)) {
    const s = Xc(e.children, !1);
    s && Zo(s, t);
  }
}
function ga(e) {
  if (e.component)
    return ga(e.component.subTree);
  if (e.type === de) {
    const t = Pe(e.children) && Xc(e.children, !1);
    return t ? ga(t) : void 0;
  }
  if (e.type !== Yt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function Mt(e, t) {
  return Ge(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    Pt({ name: e.name }, t, { setup: e })
  ) : e;
}
function Bc(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function Si(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const Ko = /* @__PURE__ */ new WeakMap();
function eo(e, t, s, n, o = !1) {
  if (Pe(e)) {
    e.forEach(
      (x, C) => eo(
        x,
        t && (Pe(t) ? t[C] : t),
        s,
        n,
        o
      )
    );
    return;
  }
  if (_n(n) && !o) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && eo(e, t, s, n.component.subTree);
    return;
  }
  const r = n.shapeFlag & 4 ? Cr(n.component) : n.el, a = o ? null : r, { i, r: l } = e, u = t && t.r, d = i.refs === pt ? i.refs = {} : i.refs, f = i.setupState, b = /* @__PURE__ */ rt(f), h = f === pt ? nc : (x) => Si(d, x) ? !1 : ct(b, x), O = (x, C) => !(C && Si(d, C));
  if (u != null && u !== l) {
    if (Ci(t), yt(u))
      d[u] = null, h(u) && (f[u] = null);
    else if (/* @__PURE__ */ xt(u)) {
      const x = t;
      O(u, x.k) && (u.value = null), x.k && (d[x.k] = null);
    }
  }
  if (Ge(l))
    wo(l, i, 12, [a, d]);
  else {
    const x = yt(l), C = /* @__PURE__ */ xt(l);
    if (x || C) {
      const T = () => {
        if (e.f) {
          const A = x ? h(l) ? f[l] : d[l] : O() || !e.k ? l.value : d[e.k];
          if (o)
            Pe(A) && Ba(A, r);
          else if (Pe(A))
            A.includes(r) || A.push(r);
          else if (x)
            d[l] = [r], h(l) && (f[l] = d[l]);
          else {
            const z = [r];
            O(l, e.k) && (l.value = z), e.k && (d[e.k] = z);
          }
        } else x ? (d[l] = a, h(l) && (f[l] = a)) : C && (O(l, e.k) && (l.value = a), e.k && (d[e.k] = a));
      };
      if (a) {
        const A = () => {
          T(), Ko.delete(e);
        };
        A.id = -1, Ko.set(e, A), jt(A, s);
      } else
        Ci(e), T();
    }
  }
}
function Ci(e) {
  const t = Ko.get(e);
  t && (t.flags |= 8, Ko.delete(e));
}
hr().requestIdleCallback;
hr().cancelIdleCallback;
const _n = (e) => !!e.type.__asyncLoader, Xa = (e) => e.type.__isKeepAlive;
function yf(e, t) {
  Wc(e, "a", t);
}
function bf(e, t) {
  Wc(e, "da", t);
}
function Wc(e, t, s = zt) {
  const n = e.__wdc || (e.__wdc = () => {
    let o = s;
    for (; o; ) {
      if (o.isDeactivated)
        return;
      o = o.parent;
    }
    return e();
  });
  if (xr(t, n, s), s) {
    let o = s.parent;
    for (; o && o.parent; )
      Xa(o.parent.vnode) && wf(n, t, s, o), o = o.parent;
  }
}
function wf(e, t, s, n) {
  const o = xr(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  xo(() => {
    Ba(n[t], o);
  }, s);
}
function xr(e, t, s = zt, n = !1) {
  if (s) {
    const o = s[e] || (s[e] = []), r = t.__weh || (t.__weh = (...a) => {
      gs();
      const i = ko(s), l = ns(t, s, e, a);
      return i(), hs(), l;
    });
    return n ? o.unshift(r) : o.push(r), r;
  }
}
const Ms = (e) => (t, s = zt) => {
  (!co || e === "sp") && xr(e, (...n) => t(...n), s);
}, _f = Ms("bm"), Ns = Ms("m"), xf = Ms(
  "bu"
), kf = Ms("u"), Gc = Ms(
  "bum"
), xo = Ms("um"), Sf = Ms(
  "sp"
), Cf = Ms("rtg"), $f = Ms("rtc");
function If(e, t = zt) {
  xr("ec", e, t);
}
const Rf = "components", qc = /* @__PURE__ */ Symbol.for("v-ndc");
function $i(e) {
  return yt(e) ? Af(Rf, e, !1) || e : e || qc;
}
function Af(e, t, s = !0, n = !1) {
  const o = Tt || zt;
  if (o) {
    const r = o.type;
    {
      const i = fm(
        r,
        !1
      );
      if (i && (i === t || i === Vt(t) || i === vr(Vt(t))))
        return r;
    }
    const a = (
      // local registration
      // check instance[type] first which is resolved for options API
      Ii(o[e] || r[e], t) || // global registration
      Ii(o.appContext[e], t)
    );
    return !a && n ? r : a;
  }
}
function Ii(e, t) {
  return e && (e[t] || e[Vt(t)] || e[vr(Vt(t))]);
}
function Le(e, t, s, n) {
  let o;
  const r = s, a = Pe(e);
  if (a || yt(e)) {
    const i = a && /* @__PURE__ */ ps(e);
    let l = !1, u = !1;
    i && (l = !/* @__PURE__ */ Ht(e), u = /* @__PURE__ */ ys(e), e = yr(e)), o = new Array(e.length);
    for (let d = 0, f = e.length; d < f; d++)
      o[d] = t(
        l ? u ? Hs(Jt(e[d])) : Jt(e[d]) : e[d],
        d,
        void 0,
        r
      );
  } else if (typeof e == "number")
    if (!Number.isInteger(e) || e < 0)
      o = [];
    else {
      o = new Array(e);
      for (let i = 0; i < e; i++)
        o[i] = t(i + 1, i, void 0, r);
    }
  else if (dt(e))
    if (e[Symbol.iterator])
      o = Array.from(
        e,
        (i, l) => t(i, l, void 0, r)
      );
    else {
      const i = Object.keys(e);
      o = new Array(i.length);
      for (let l = 0, u = i.length; l < u; l++) {
        const d = i[l];
        o[l] = t(e[d], d, l, r);
      }
    }
  else
    o = [];
  return o;
}
function Hc(e, t, s, n, o, r) {
  if (s == null && (s = {}), Tt.ce || Tt.parent && _n(Tt.parent) && Tt.parent.ce) {
    const u = s, d = Object.keys(u).length > 0;
    return g(), ft(
      de,
      null,
      [V("slot", u, n)],
      d ? -2 : 64
    );
  }
  let a = e[t];
  a && a._c && (a._d = !1);
  const i = Es.length;
  g();
  let l;
  try {
    const u = a && Zc(a(s)), d = s.key || r || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    u && u.key;
    l = ft(
      de,
      {
        key: (d && !Kt(d) ? d : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!u && n ? "_fb" : "")
      },
      u || (n ? n() : []),
      u && e._ === 1 ? 64 : -2
    );
  } catch (u) {
    for (let d = Es.length; d > i; d--) ni();
    throw u;
  } finally {
    a && a._c && (a._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function Zc(e) {
  return e.some((t) => xn(t) ? !(t.type === Yt || t.type === de && !Zc(t.children)) : !0) ? e : null;
}
const ha = (e) => e ? vu(e) ? Cr(e) : ha(e.parent) : null, to = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ Pt(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => ha(e.parent),
    $root: (e) => ha(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => Qc(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      Ya(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = _o.bind(e.proxy)),
    $watch: (e) => mf.bind(e)
  })
), Vr = (e, t) => e !== pt && !e.__isScriptSetup && ct(e, t), Ef = {
  get({ _: e }, t) {
    if (t === "__v_skip")
      return !0;
    const { ctx: s, setupState: n, data: o, props: r, accessCache: a, type: i, appContext: l } = e;
    if (t[0] !== "$") {
      const b = a[t];
      if (b !== void 0)
        switch (b) {
          case 1:
            return n[t];
          case 2:
            return o[t];
          case 4:
            return s[t];
          case 3:
            return r[t];
        }
      else {
        if (Vr(n, t))
          return a[t] = 1, n[t];
        if (o !== pt && ct(o, t))
          return a[t] = 2, o[t];
        if (ct(r, t))
          return a[t] = 3, r[t];
        if (s !== pt && ct(s, t))
          return a[t] = 4, s[t];
        ya && (a[t] = 0);
      }
    }
    const u = to[t];
    let d, f;
    if (u)
      return t === "$attrs" && Nt(e.attrs, "get", ""), u(e);
    if (
      // css module (injected by vue-loader)
      (d = i.__cssModules) && (d = d[t])
    )
      return d;
    if (s !== pt && ct(s, t))
      return a[t] = 4, s[t];
    if (
      // global properties
      f = l.config.globalProperties, ct(f, t)
    )
      return f[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: o, ctx: r } = e;
    return Vr(o, t) ? (o[t] = s, !0) : n !== pt && ct(n, t) ? (n[t] = s, !0) : ct(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (r[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: o, props: r, type: a }
  }, i) {
    let l;
    return !!(s[i] || e !== pt && i[0] !== "$" && ct(e, i) || Vr(t, i) || ct(r, i) || ct(n, i) || ct(to, i) || ct(o.config.globalProperties, i) || (l = a.__cssModules) && l[i]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : ct(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function Ri(e) {
  return Pe(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let ya = !0;
function Of(e) {
  const t = Qc(e), s = e.proxy, n = e.ctx;
  ya = !1, t.beforeCreate && Ai(t.beforeCreate, e, "bc");
  const {
    // state
    data: o,
    computed: r,
    methods: a,
    watch: i,
    provide: l,
    inject: u,
    // lifecycle
    created: d,
    beforeMount: f,
    mounted: b,
    beforeUpdate: h,
    updated: O,
    activated: x,
    deactivated: C,
    beforeDestroy: T,
    beforeUnmount: A,
    destroyed: z,
    unmounted: R,
    render: J,
    renderTracked: $e,
    renderTriggered: ne,
    errorCaptured: j,
    serverPrefetch: re,
    // public API
    expose: ve,
    inheritAttrs: Me,
    // assets
    components: Ie,
    directives: Oe,
    filters: Ye
  } = t;
  if (u && Tf(u, n, null), a)
    for (const S in a) {
      const ue = a[S];
      Ge(ue) && (n[S] = ue.bind(s));
    }
  if (o) {
    const S = o.call(s, s);
    dt(S) && (e.data = /* @__PURE__ */ bo(S));
  }
  if (ya = !0, r)
    for (const S in r) {
      const ue = r[S], Ue = Ge(ue) ? ue.bind(s, s) : Ge(ue.get) ? ue.get.bind(s, s) : ms, ie = !Ge(ue) && Ge(ue.set) ? ue.set.bind(s) : ms, tt = ge({
        get: Ue,
        set: ie
      });
      Object.defineProperty(n, S, {
        enumerable: !0,
        configurable: !0,
        get: () => tt.value,
        set: (De) => tt.value = De
      });
    }
  if (i)
    for (const S in i)
      Kc(i[S], n, s, S);
  if (l) {
    const S = Ge(l) ? l.call(s) : l;
    Reflect.ownKeys(S).forEach((ue) => {
      Vo(ue, S[ue]);
    });
  }
  d && Ai(d, e, "c");
  function _(S, ue) {
    Pe(ue) ? ue.forEach((Ue) => S(Ue.bind(s))) : ue && S(ue.bind(s));
  }
  if (_(_f, f), _(Ns, b), _(xf, h), _(kf, O), _(yf, x), _(bf, C), _(If, j), _($f, $e), _(Cf, ne), _(Gc, A), _(xo, R), _(Sf, re), Pe(ve))
    if (ve.length) {
      const S = e.exposed || (e.exposed = {});
      ve.forEach((ue) => {
        Object.defineProperty(S, ue, {
          get: () => s[ue],
          set: (Ue) => s[ue] = Ue,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  J && e.render === ms && (e.render = J), Me != null && (e.inheritAttrs = Me), Ie && (e.components = Ie), Oe && (e.directives = Oe), re && Bc(e);
}
function Tf(e, t, s = ms) {
  Pe(e) && (e = ba(e));
  for (const n in e) {
    const o = e[n];
    let r;
    dt(o) ? "default" in o ? r = Zt(
      o.from || n,
      o.default,
      !0
    ) : r = Zt(o.from || n) : r = Zt(o), /* @__PURE__ */ xt(r) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => r.value,
      set: (a) => r.value = a
    }) : t[n] = r;
  }
}
function Ai(e, t, s) {
  ns(
    Pe(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function Kc(e, t, s, n) {
  let o = n.includes(".") ? Lc(s, n) : () => s[n];
  if (yt(e)) {
    const r = t[e];
    Ge(r) && ss(o, r);
  } else if (Ge(e))
    ss(o, e.bind(s));
  else if (dt(e))
    if (Pe(e))
      e.forEach((r) => Kc(r, t, s, n));
    else {
      const r = Ge(e.handler) ? e.handler.bind(s) : t[e.handler];
      Ge(r) && ss(o, r, e);
    }
}
function Qc(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: o,
    optionsCache: r,
    config: { optionMergeStrategies: a }
  } = e.appContext, i = r.get(t);
  let l;
  return i ? l = i : !o.length && !s && !n ? l = t : (l = {}, o.length && o.forEach(
    (u) => Qo(l, u, a, !0)
  ), Qo(l, t, a)), dt(t) && r.set(t, l), l;
}
function Qo(e, t, s, n = !1) {
  const { mixins: o, extends: r } = t;
  r && Qo(e, r, s, !0), o && o.forEach(
    (a) => Qo(e, a, s, !0)
  );
  for (const a in t)
    if (!(n && a === "expose")) {
      const i = Pf[a] || s && s[a];
      e[a] = i ? i(e[a], t[a]) : t[a];
    }
  return e;
}
const Pf = {
  data: Ei,
  props: Oi,
  emits: Oi,
  // objects
  methods: qn,
  computed: qn,
  // lifecycle
  beforeCreate: Dt,
  created: Dt,
  beforeMount: Dt,
  mounted: Dt,
  beforeUpdate: Dt,
  updated: Dt,
  beforeDestroy: Dt,
  beforeUnmount: Dt,
  destroyed: Dt,
  unmounted: Dt,
  activated: Dt,
  deactivated: Dt,
  errorCaptured: Dt,
  serverPrefetch: Dt,
  // assets
  components: qn,
  directives: qn,
  // watch
  watch: Nf,
  // provide / inject
  provide: Ei,
  inject: Mf
};
function Ei(e, t) {
  return t ? e ? function() {
    return Pt(
      Ge(e) ? e.call(this, this) : e,
      Ge(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function Mf(e, t) {
  return qn(ba(e), ba(t));
}
function ba(e) {
  if (Pe(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function Dt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function qn(e, t) {
  return e ? Pt(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function Oi(e, t) {
  return e ? Pe(e) && Pe(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : Pt(
    /* @__PURE__ */ Object.create(null),
    Ri(e),
    Ri(t ?? {})
  ) : t;
}
function Nf(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = Pt(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = Dt(e[n], t[n]);
  return s;
}
function Jc() {
  return {
    app: null,
    config: {
      isNativeTag: nc,
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
let zf = 0;
function Df(e, t) {
  return function(n, o = null) {
    Ge(n) || (n = Pt({}, n)), o != null && !dt(o) && (o = null);
    const r = Jc(), a = /* @__PURE__ */ new WeakSet(), i = [];
    let l = !1;
    const u = r.app = {
      _uid: zf++,
      _component: n,
      _props: o,
      _container: null,
      _context: r,
      _instance: null,
      version: pm,
      get config() {
        return r.config;
      },
      set config(d) {
      },
      use(d, ...f) {
        return a.has(d) || (d && Ge(d.install) ? (a.add(d), d.install(u, ...f)) : Ge(d) && (a.add(d), d(u, ...f))), u;
      },
      mixin(d) {
        return r.mixins.includes(d) || r.mixins.push(d), u;
      },
      component(d, f) {
        return f ? (r.components[d] = f, u) : r.components[d];
      },
      directive(d, f) {
        return f ? (r.directives[d] = f, u) : r.directives[d];
      },
      mount(d, f, b) {
        if (!l) {
          const h = u._ceVNode || V(n, o);
          return h.appContext = r, b === !0 ? b = "svg" : b === !1 && (b = void 0), e(h, d, b), l = !0, u._container = d, d.__vue_app__ = u, Cr(h.component);
        }
      },
      onUnmount(d) {
        i.push(d);
      },
      unmount() {
        l && (ns(
          i,
          u._instance,
          16
        ), e(null, u._container), delete u._container.__vue_app__);
      },
      provide(d, f) {
        return r.provides[d] = f, u;
      },
      runWithContext(d) {
        const f = cn;
        cn = u;
        try {
          return d();
        } finally {
          cn = f;
        }
      }
    };
    return u;
  };
}
let cn = null;
const jf = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${Vt(t)}Modifiers`] || e[`${Qs(t)}Modifiers`];
function Lf(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || pt;
  let o = s;
  const r = t.startsWith("update:"), a = r && jf(n, t.slice(7));
  a && (a.trim && (o = s.map((d) => yt(d) ? d.trim() : d)), a.number && (o = o.map(gr)));
  let i, l = n[i = Mr(t)] || // also try camelCase event handler (#2249)
  n[i = Mr(Vt(t))];
  !l && r && (l = n[i = Mr(Qs(t))]), l && ns(
    l,
    e,
    6,
    o
  );
  const u = n[i + "Once"];
  if (u) {
    if (!e.emitted)
      e.emitted = {};
    else if (e.emitted[i])
      return;
    e.emitted[i] = !0, ns(
      u,
      e,
      6,
      o
    );
  }
}
const Uf = /* @__PURE__ */ new WeakMap();
function Yc(e, t, s = !1) {
  const n = s ? Uf : t.emitsCache, o = n.get(e);
  if (o !== void 0)
    return o;
  const r = e.emits;
  let a = {}, i = !1;
  if (!Ge(e)) {
    const l = (u) => {
      const d = Yc(u, t, !0);
      d && (i = !0, Pt(a, d));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !r && !i ? (dt(e) && n.set(e, null), null) : (Pe(r) ? r.forEach((l) => a[l] = null) : Pt(a, r), dt(e) && n.set(e, a), a);
}
function kr(e, t) {
  return !e || !dr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), ct(e, t[0].toLowerCase() + t.slice(1)) || ct(e, Qs(t)) || ct(e, t));
}
function Ti(e) {
  const {
    type: t,
    vnode: s,
    proxy: n,
    withProxy: o,
    propsOptions: [r],
    slots: a,
    attrs: i,
    emit: l,
    render: u,
    renderCache: d,
    props: f,
    data: b,
    setupState: h,
    ctx: O,
    inheritAttrs: x
  } = e, C = Ho(e);
  let T, A;
  try {
    if (s.shapeFlag & 4) {
      const R = o || n, J = R;
      T = cs(
        u.call(
          J,
          R,
          d,
          f,
          h,
          b,
          O
        )
      ), A = i;
    } else {
      const R = t;
      T = cs(
        R.length > 1 ? R(
          f,
          { attrs: i, slots: a, emit: l }
        ) : R(
          f,
          null
        )
      ), A = t.props ? i : Vf(i);
    }
  } catch (R) {
    Es.length = 0, wr(R, e, 1), T = V(Yt);
  }
  let z = T;
  if (A && x !== !1) {
    const R = Object.keys(A), { shapeFlag: J } = z;
    R.length && J & 7 && (r && R.some(fr) && (A = Ff(
      A,
      r
    )), z = kn(z, A, !1, !0));
  }
  if (s.dirs && (z = kn(z, null, !1, !0), z.dirs = z.dirs ? z.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const R = _r(z.type) && Fc(z) || z;
    Zo(R, s.transition);
  }
  return T = z, Ho(C), T;
}
function Xc(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const o = e[n];
    if (xn(o)) {
      if (o.type !== Yt || o.children === "v-if") {
        if (s)
          return;
        s = o;
      }
    } else
      return;
  }
  return s;
}
const Vf = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || dr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, Ff = (e, t) => {
  const s = {};
  for (const n in e)
    (!fr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function Bf(e, t, s) {
  const { props: n, children: o, component: r } = e, { props: a, children: i, patchFlag: l } = t, u = r.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? Pi(n, a, u) : !!a;
    if (l & 8) {
      const d = t.dynamicProps;
      for (let f = 0; f < d.length; f++) {
        const b = d[f];
        if (eu(a, n, b) && !kr(u, b))
          return !0;
      }
    }
  } else
    return (o || i) && (!i || !i.$stable) ? !0 : n === a ? !1 : n ? a ? Pi(n, a, u) : !0 : !!a;
  return !1;
}
function Pi(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let o = 0; o < n.length; o++) {
    const r = n[o];
    if (!ct(e, r) || eu(t, e, r) && !kr(s, r))
      return !0;
  }
  return !1;
}
function eu(e, t, s) {
  const n = e[s], o = t[s];
  return s === "style" && dt(n) && dt(o) ? !Ts(n, o) : n !== o;
}
function Wf({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const o = t.subTree;
    if (o.suspense && o.suspense.activeBranch === e && (o.suspense.vnode.el = o.el = n, e = o), o === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const tu = {}, su = () => Object.create(tu), nu = (e) => Object.getPrototypeOf(e) === tu;
function Gf(e, t, s, n = !1) {
  const o = {}, r = su();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), ou(e, t, o, r);
  for (const a in e.propsOptions[0])
    a in o || (o[a] = void 0);
  s ? e.props = n ? o : /* @__PURE__ */ Ac(o) : e.type.props ? e.props = o : e.props = r, e.attrs = r;
}
function qf(e, t, s, n) {
  const {
    props: o,
    attrs: r,
    vnode: { patchFlag: a }
  } = e, i = /* @__PURE__ */ rt(o), [l] = e.propsOptions;
  let u = !1;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (n || a > 0) && !(a & 16)
  ) {
    if (a & 8) {
      const d = e.vnode.dynamicProps;
      for (let f = 0; f < d.length; f++) {
        let b = d[f];
        if (kr(e.emitsOptions, b))
          continue;
        const h = t[b];
        if (l)
          if (ct(r, b))
            h !== r[b] && (r[b] = h, u = !0);
          else {
            const O = Vt(b);
            o[O] = wa(
              l,
              i,
              O,
              h,
              e,
              !1
            );
          }
        else
          h !== r[b] && (r[b] = h, u = !0);
      }
    }
  } else {
    ou(e, t, o, r) && (u = !0);
    let d;
    for (const f in i)
      (!t || // for camelCase
      !ct(t, f) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((d = Qs(f)) === f || !ct(t, d))) && (l ? s && // for camelCase
      (s[f] !== void 0 || // for kebab-case
      s[d] !== void 0) && (o[f] = wa(
        l,
        i,
        f,
        void 0,
        e,
        !0
      )) : delete o[f]);
    if (r !== i)
      for (const f in r)
        (!t || !ct(t, f)) && (delete r[f], u = !0);
  }
  u && $s(e.attrs, "set", "");
}
function ou(e, t, s, n) {
  const [o, r] = e.propsOptions;
  let a = !1, i;
  if (t)
    for (let l in t) {
      if (Jn(l))
        continue;
      const u = t[l];
      let d;
      o && ct(o, d = Vt(l)) ? !r || !r.includes(d) ? s[d] = u : (i || (i = {}))[d] = u : kr(e.emitsOptions, l) || (!(l in n) || u !== n[l]) && (n[l] = u, a = !0);
    }
  if (r) {
    const l = /* @__PURE__ */ rt(s), u = i || pt;
    for (let d = 0; d < r.length; d++) {
      const f = r[d];
      s[f] = wa(
        o,
        l,
        f,
        u[f],
        e,
        !ct(u, f)
      );
    }
  }
  return a;
}
function wa(e, t, s, n, o, r) {
  const a = e[s];
  if (a != null) {
    const i = ct(a, "default");
    if (i && n === void 0) {
      const l = a.default;
      if (a.type !== Function && !a.skipFactory && Ge(l)) {
        const { propsDefaults: u } = o;
        if (s in u)
          n = u[s];
        else {
          const d = ko(o);
          n = u[s] = l.call(
            null,
            t
          ), d();
        }
      } else
        n = l;
      o.ce && o.ce._setProp(s, n);
    }
    a[
      0
      /* shouldCast */
    ] && (r && !i ? n = !1 : a[
      1
      /* shouldCastTrue */
    ] && (n === "" || n === Qs(s)) && (n = !0));
  }
  return n;
}
const Hf = /* @__PURE__ */ new WeakMap();
function ru(e, t, s = !1) {
  const n = s ? Hf : t.propsCache, o = n.get(e);
  if (o)
    return o;
  const r = e.props, a = {}, i = [];
  let l = !1;
  if (!Ge(e)) {
    const d = (f) => {
      l = !0;
      const [b, h] = ru(f, t, !0);
      Pt(a, b), h && i.push(...h);
    };
    !s && t.mixins.length && t.mixins.forEach(d), e.extends && d(e.extends), e.mixins && e.mixins.forEach(d);
  }
  if (!r && !l)
    return dt(e) && n.set(e, rn), rn;
  if (Pe(r))
    for (let d = 0; d < r.length; d++) {
      const f = Vt(r[d]);
      Mi(f) && (a[f] = pt);
    }
  else if (r)
    for (const d in r) {
      const f = Vt(d);
      if (Mi(f)) {
        const b = r[d], h = a[f] = Pe(b) || Ge(b) ? { type: b } : Pt({}, b), O = h.type;
        let x = !1, C = !0;
        if (Pe(O))
          for (let T = 0; T < O.length; ++T) {
            const A = O[T], z = Ge(A) && A.name;
            if (z === "Boolean") {
              x = !0;
              break;
            } else z === "String" && (C = !1);
          }
        else
          x = Ge(O) && O.name === "Boolean";
        h[
          0
          /* shouldCast */
        ] = x, h[
          1
          /* shouldCastTrue */
        ] = C, (x || ct(h, "default")) && i.push(f);
      }
    }
  const u = [a, i];
  return dt(e) && n.set(e, u), u;
}
function Mi(e) {
  return e[0] !== "$" && !Jn(e);
}
const ei = (e) => e === "_" || e === "_ctx" || e === "$stable", ti = (e) => Pe(e) ? e.map(cs) : [cs(e)], Zf = (e, t, s) => {
  if (t._n)
    return t;
  const n = X((...o) => ti(t(...o)), s);
  return n._c = !1, n;
}, au = (e, t, s) => {
  const n = e._ctx;
  for (const o in e) {
    if (ei(o)) continue;
    const r = e[o];
    if (Ge(r))
      t[o] = Zf(o, r, n);
    else if (r != null) {
      const a = ti(r);
      t[o] = () => a;
    }
  }
}, iu = (e, t) => {
  const s = ti(t);
  e.slots.default = () => s;
}, lu = (e, t, s) => {
  for (const n in t)
    (s || !ei(n)) && (e[n] = t[n]);
}, Kf = (e, t, s) => {
  const n = e.slots = su();
  if (e.vnode.shapeFlag & 32) {
    const o = t._;
    o ? (lu(n, t, s), s && ic(n, "_", o, !0)) : au(t, n);
  } else t && iu(e, t);
}, Qf = (e, t, s) => {
  const { vnode: n, slots: o } = e;
  let r = !0, a = pt;
  if (n.shapeFlag & 32) {
    const i = t._;
    i ? s && i === 1 ? r = !1 : lu(o, t, s) : (r = !t.$stable, au(t, o)), a = t;
  } else t && (iu(e, t), a = { default: 1 });
  if (r)
    for (const i in o)
      !ei(i) && a[i] == null && delete o[i];
}, jt = tm;
function Jf(e) {
  return Yf(e);
}
function Yf(e, t) {
  const s = hr();
  s.__VUE__ = !0;
  const {
    insert: n,
    remove: o,
    patchProp: r,
    createElement: a,
    createText: i,
    createComment: l,
    setText: u,
    setElementText: d,
    parentNode: f,
    nextSibling: b,
    setScopeId: h = ms,
    insertStaticContent: O
  } = e, x = (v, k, P, L = null, Z = null, Y = null, E = void 0, G = null, H = !!k.dynamicChildren) => {
    if (v === k)
      return;
    v && !Dn(v, k) && (L = U(v), De(v, Z, Y, !0), v = null), k.patchFlag === -2 && (H = !1, k.dynamicChildren = null), k.dynamicChildren && v && v.dynamicChildren && v.dynamicChildren.hasOnce && (k.dynamicChildren === rn && (k.dynamicChildren = []), k.dynamicChildren.hasOnce = !0);
    const { type: K, ref: ye, shapeFlag: le } = k;
    switch (K) {
      case Sr:
        C(v, k, P, L);
        break;
      case Yt:
        T(v, k, P, L);
        break;
      case Fo:
        v == null && A(k, P, L, E);
        break;
      case de:
        Ie(
          v,
          k,
          P,
          L,
          Z,
          Y,
          E,
          G,
          H
        );
        break;
      default:
        le & 1 ? J(
          v,
          k,
          P,
          L,
          Z,
          Y,
          E,
          G,
          H
        ) : le & 6 ? Oe(
          v,
          k,
          P,
          L,
          Z,
          Y,
          E,
          G,
          H
        ) : (le & 64 || le & 128) && K.process(
          v,
          k,
          P,
          L,
          Z,
          Y,
          E,
          G,
          H,
          q
        );
    }
    ye != null && Z ? eo(ye, v && v.ref, Y, k || v, !k) : ye == null && v && v.ref != null && eo(v.ref, null, Y, v, !0);
  }, C = (v, k, P, L) => {
    if (v == null)
      n(
        k.el = i(k.children),
        P,
        L
      );
    else {
      const Z = k.el = v.el;
      k.children !== v.children && u(Z, k.children);
    }
  }, T = (v, k, P, L) => {
    v == null ? n(
      k.el = l(k.children || ""),
      P,
      L
    ) : k.el = v.el;
  }, A = (v, k, P, L) => {
    [v.el, v.anchor] = O(
      v.children,
      k,
      P,
      L,
      v.el,
      v.anchor
    );
  }, z = ({ el: v, anchor: k }, P, L) => {
    let Z;
    for (; v && v !== k; )
      Z = b(v), n(v, P, L), v = Z;
    n(k, P, L);
  }, R = ({ el: v, anchor: k }) => {
    let P;
    for (; v && v !== k; )
      P = b(v), o(v), v = P;
    o(k);
  }, J = (v, k, P, L, Z, Y, E, G, H) => {
    if (k.type === "svg" ? E = "svg" : k.type === "math" && (E = "mathml"), v == null)
      $e(
        k,
        P,
        L,
        Z,
        Y,
        E,
        G,
        H
      );
    else {
      const K = v.el && v.el._isVueCE ? v.el : null;
      try {
        K && K._beginPatch(), re(
          v,
          k,
          Z,
          Y,
          E,
          G,
          H
        );
      } finally {
        K && K._endPatch();
      }
    }
  }, $e = (v, k, P, L, Z, Y, E, G) => {
    let H, K;
    const { props: ye, shapeFlag: le, transition: Re, dirs: Te } = v;
    if (H = v.el = a(
      v.type,
      Y,
      ye && ye.is,
      ye
    ), le & 8 ? d(H, v.children) : le & 16 && j(
      v.children,
      H,
      null,
      L,
      Z,
      Fr(v, Y),
      E,
      G
    ), Te && Ys(v, null, L, "created"), ne(H, v, v.scopeId, E, L), ye) {
      for (const st in ye)
        st !== "value" && !Jn(st) && r(H, st, null, ye[st], Y, L);
      "value" in ye && r(H, "value", null, ye.value, Y), (K = ye.onVnodeBeforeMount) && rs(K, L, v);
    }
    Te && Ys(v, null, L, "beforeMount");
    const qe = Xf(Z, Re);
    qe && Re.beforeEnter(H), n(H, k, P), ((K = ye && ye.onVnodeMounted) || qe || Te) && jt(() => {
      try {
        K && rs(K, L, v), qe && Re.enter(H), Te && Ys(v, null, L, "mounted");
      } finally {
      }
    }, Z);
  }, ne = (v, k, P, L, Z) => {
    if (P && h(v, P), L)
      for (let Y = 0; Y < L.length; Y++)
        h(v, L[Y]);
    if (Z) {
      let Y = Z.subTree;
      if (k === Y || uu(Y.type) && (Y.ssContent === k || Y.ssFallback === k)) {
        const E = Z.vnode;
        ne(
          v,
          E,
          E.scopeId,
          E.slotScopeIds,
          Z.parent
        );
      }
    }
  }, j = (v, k, P, L, Z, Y, E, G, H = 0) => {
    for (let K = H; K < v.length; K++) {
      const ye = v[K] = G ? Cs(v[K]) : cs(v[K]);
      x(
        null,
        ye,
        k,
        P,
        L,
        Z,
        Y,
        E,
        G
      );
    }
  }, re = (v, k, P, L, Z, Y, E) => {
    const G = k.el = v.el;
    let { patchFlag: H, dynamicChildren: K, dirs: ye } = k;
    H |= v.patchFlag & 16;
    const le = v.props || pt, Re = k.props || pt;
    let Te;
    if (P && Xs(P, !1), (Te = Re.onVnodeBeforeUpdate) && rs(Te, P, k, v), ye && Ys(k, v, P, "beforeUpdate"), P && Xs(P, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    K && (!v.dynamicChildren || v.dynamicChildren.length !== K.length) && (H = 0, E = !1, K = null), (le.innerHTML && Re.innerHTML == null || le.textContent && Re.textContent == null) && d(G, ""), K ? ve(
      v.dynamicChildren,
      K,
      G,
      P,
      L,
      Fr(k, Z),
      Y
    ) : E || ue(
      v,
      k,
      G,
      null,
      P,
      L,
      Fr(k, Z),
      Y,
      !1
    ), H > 0) {
      if (H & 16)
        Me(G, le, Re, P, Z);
      else if (H & 2 && le.class !== Re.class && r(G, "class", null, Re.class, Z), H & 4 && r(G, "style", le.style, Re.style, Z), H & 8) {
        const qe = k.dynamicProps;
        for (let st = 0; st < qe.length; st++) {
          const et = qe[st], te = le[et], pe = Re[et];
          (pe !== te || et === "value") && r(G, et, te, pe, Z, P);
        }
      }
      H & 1 && v.children !== k.children && d(G, k.children);
    } else !E && K == null && Me(G, le, Re, P, Z);
    ((Te = Re.onVnodeUpdated) || ye) && jt(() => {
      Te && rs(Te, P, k, v), ye && Ys(k, v, P, "updated");
    }, L);
  }, ve = (v, k, P, L, Z, Y, E) => {
    for (let G = 0; G < k.length; G++) {
      const H = v[G], K = k[G], ye = H.el || _a(H), le = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        ye && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (H.type === de || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !Dn(H, K) || // - In the case of a component, it could contain anything.
        H.shapeFlag & 198) ? f(ye) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          P
        )
      );
      x(
        H,
        K,
        le,
        null,
        L,
        Z,
        Y,
        E,
        !0
      );
    }
  }, Me = (v, k, P, L, Z) => {
    if (k !== P) {
      if (k !== pt)
        for (const Y in k)
          !Jn(Y) && !(Y in P) && r(
            v,
            Y,
            k[Y],
            null,
            Z,
            L
          );
      for (const Y in P) {
        if (Jn(Y)) continue;
        const E = P[Y], G = k[Y];
        E !== G && Y !== "value" && r(v, Y, G, E, Z, L);
      }
      "value" in P && r(v, "value", k.value, P.value, Z);
    }
  }, Ie = (v, k, P, L, Z, Y, E, G, H) => {
    const K = k.el = v ? v.el : i(""), ye = k.anchor = v ? v.anchor : i("");
    let { patchFlag: le, dynamicChildren: Re, slotScopeIds: Te } = k;
    Te && (G = G ? G.concat(Te) : Te), v == null ? (n(K, P, L), n(ye, P, L), j(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      k.children || [],
      P,
      ye,
      Z,
      Y,
      E,
      G,
      H
    )) : le > 0 && le & 64 && Re && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    v.dynamicChildren && v.dynamicChildren.length === Re.length ? (ve(
      v.dynamicChildren,
      Re,
      P,
      Z,
      Y,
      E,
      G
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (k.key != null || Z && k === Z.subTree) && si(
      v,
      k,
      !0
      /* shallow */
    )) : ue(
      v,
      k,
      P,
      ye,
      Z,
      Y,
      E,
      G,
      H
    );
  }, Oe = (v, k, P, L, Z, Y, E, G, H) => {
    k.slotScopeIds = G, v == null ? k.shapeFlag & 512 ? Z.ctx.activate(
      k,
      P,
      L,
      E,
      H
    ) : Ye(
      k,
      P,
      L,
      Z,
      Y,
      E,
      H
    ) : ae(v, k, H);
  }, Ye = (v, k, P, L, Z, Y, E) => {
    const G = v.component = im(
      v,
      L,
      Z
    );
    if (Xa(v) && (G.ctx.renderer = q), lm(G, !1, E), G.asyncDep) {
      if (Z && Z.registerDep(
        G,
        _,
        E,
        Y
      ), !v.el) {
        const H = G.subTree = V(Yt);
        T(null, H, k, P), v.placeholder = H.el;
      }
    } else
      _(
        G,
        v,
        k,
        P,
        Z,
        Y,
        E
      );
  }, ae = (v, k, P) => {
    const L = k.component = v.component;
    if (Bf(v, k, P))
      if (L.asyncDep && !L.asyncResolved) {
        k.el = v.el, k.placeholder = v.placeholder, S(L, k, P);
        return;
      } else
        L.next = k, L.update();
    else
      k.el = v.el, k.placeholder = v.placeholder, L.vnode = k;
  }, _ = (v, k, P, L, Z, Y, E) => {
    const G = () => {
      if (v.isMounted) {
        let { next: le, bu: Re, u: Te, parent: qe, vnode: st } = v;
        {
          const ze = cu(v);
          if (ze) {
            le && (le.el = st.el, S(v, le, E)), ze.asyncDep.then(() => {
              jt(() => {
                v.isUnmounted || K();
              }, Z);
            });
            return;
          }
        }
        let et = le, te;
        Xs(v, !1), le ? (le.el = st.el, S(v, le, E)) : le = st, Re && Uo(Re), (te = le.props && le.props.onVnodeBeforeUpdate) && rs(te, qe, le, st), Xs(v, !0);
        const pe = Ti(v), he = v.subTree;
        v.subTree = pe, x(
          he,
          pe,
          // parent may have changed if it's in a teleport
          f(he.el),
          // anchor may have changed if it's in a fragment
          U(he),
          v,
          Z,
          Y
        ), le.el = pe.el, et === null && Wf(v, pe.el), Te && jt(Te, Z), (te = le.props && le.props.onVnodeUpdated) && jt(
          () => rs(te, qe, le, st),
          Z
        );
      } else {
        let le;
        const { el: Re, props: Te } = k, { bm: qe, m: st, parent: et, root: te, type: pe } = v, he = _n(k);
        Xs(v, !1), qe && Uo(qe), !he && (le = Te && Te.onVnodeBeforeMount) && rs(le, et, k), Xs(v, !0);
        {
          te.ce && te.ce._hasShadowRoot() && te.ce._injectChildStyle(
            pe,
            v.parent ? v.parent.type : void 0
          );
          const ze = v.subTree = Ti(v);
          x(
            null,
            ze,
            P,
            L,
            v,
            Z,
            Y
          ), k.el = ze.el;
        }
        if (st && jt(st, Z), !he && (le = Te && Te.onVnodeMounted)) {
          const ze = k;
          jt(
            () => rs(le, et, ze),
            Z
          );
        }
        (k.shapeFlag & 256 || et && _n(et.vnode) && et.vnode.shapeFlag & 256) && v.a && jt(v.a, Z), v.isMounted = !0, k = P = L = null;
      }
    };
    v.scope.on();
    const H = v.effect = new pc(G);
    v.scope.off();
    const K = v.update = H.run.bind(H), ye = v.job = H.runIfDirty.bind(H);
    ye.i = v, ye.id = v.uid, H.scheduler = () => Ya(ye), Xs(v, !0), K();
  }, S = (v, k, P) => {
    k.component = v;
    const L = v.vnode.props;
    v.vnode = k, v.next = null, qf(v, k.props, L, P), Qf(v, k.children, P), gs(), Mc(v), hs();
  }, ue = (v, k, P, L, Z, Y, E, G, H = !1) => {
    const K = v && v.children, ye = v ? v.shapeFlag : 0, le = k.children, { patchFlag: Re, shapeFlag: Te } = k;
    if (Re > 0) {
      if (Re & 128) {
        ie(
          K,
          le,
          P,
          L,
          Z,
          Y,
          E,
          G,
          H
        );
        return;
      } else if (Re & 256) {
        Ue(
          K,
          le,
          P,
          L,
          Z,
          Y,
          E,
          G,
          H
        );
        return;
      }
    }
    Te & 8 ? (ye & 16 && F(K, Z, Y), le !== K && d(P, le)) : ye & 16 ? Te & 16 ? ie(
      K,
      le,
      P,
      L,
      Z,
      Y,
      E,
      G,
      H
    ) : F(K, Z, Y, !0) : (ye & 8 && d(P, ""), Te & 16 && j(
      le,
      P,
      L,
      Z,
      Y,
      E,
      G,
      H
    ));
  }, Ue = (v, k, P, L, Z, Y, E, G, H) => {
    v = v || rn, k = k || rn;
    const K = v.length, ye = k.length, le = Math.min(K, ye);
    let Re;
    for (Re = 0; Re < le; Re++) {
      const Te = k[Re] = H ? Cs(k[Re]) : cs(k[Re]);
      x(
        v[Re],
        Te,
        P,
        null,
        Z,
        Y,
        E,
        G,
        H
      );
    }
    K > ye ? F(
      v,
      Z,
      Y,
      !0,
      !1,
      le
    ) : j(
      k,
      P,
      L,
      Z,
      Y,
      E,
      G,
      H,
      le
    );
  }, ie = (v, k, P, L, Z, Y, E, G, H) => {
    let K = 0;
    const ye = k.length;
    let le = v.length - 1, Re = ye - 1;
    for (; K <= le && K <= Re; ) {
      const Te = v[K], qe = k[K] = H ? Cs(k[K]) : cs(k[K]);
      if (Dn(Te, qe))
        x(
          Te,
          qe,
          P,
          null,
          Z,
          Y,
          E,
          G,
          H
        );
      else
        break;
      K++;
    }
    for (; K <= le && K <= Re; ) {
      const Te = v[le], qe = k[Re] = H ? Cs(k[Re]) : cs(k[Re]);
      if (Dn(Te, qe))
        x(
          Te,
          qe,
          P,
          null,
          Z,
          Y,
          E,
          G,
          H
        );
      else
        break;
      le--, Re--;
    }
    if (K > le) {
      if (K <= Re) {
        const Te = Re + 1, qe = Te < ye ? k[Te].el : L;
        for (; K <= Re; )
          x(
            null,
            k[K] = H ? Cs(k[K]) : cs(k[K]),
            P,
            qe,
            Z,
            Y,
            E,
            G,
            H
          ), K++;
      }
    } else if (K > Re)
      for (; K <= le; )
        De(v[K], Z, Y, !0), K++;
    else {
      const Te = K, qe = K, st = /* @__PURE__ */ new Map();
      for (K = qe; K <= Re; K++) {
        const He = k[K] = H ? Cs(k[K]) : cs(k[K]);
        He.key != null && st.set(He.key, K);
      }
      let et, te = 0;
      const pe = Re - qe + 1;
      let he = !1, ze = 0;
      const Ke = new Array(pe);
      for (K = 0; K < pe; K++) Ke[K] = 0;
      for (K = Te; K <= le; K++) {
        const He = v[K];
        if (te >= pe) {
          De(He, Z, Y, !0);
          continue;
        }
        let Qe;
        if (He.key != null)
          Qe = st.get(He.key);
        else
          for (et = qe; et <= Re; et++)
            if (Ke[et - qe] === 0 && Dn(He, k[et])) {
              Qe = et;
              break;
            }
        Qe === void 0 ? De(He, Z, Y, !0) : (Ke[Qe - qe] = K + 1, Qe >= ze ? ze = Qe : he = !0, x(
          He,
          k[Qe],
          P,
          null,
          Z,
          Y,
          E,
          G,
          H
        ), te++);
      }
      const Ne = he ? em(Ke) : rn;
      for (et = Ne.length - 1, K = pe - 1; K >= 0; K--) {
        const He = qe + K, Qe = k[He], oe = k[He + 1], we = He + 1 < ye ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          oe.el || _a(oe)
        ) : L;
        Ke[K] === 0 ? x(
          null,
          Qe,
          P,
          we,
          Z,
          Y,
          E,
          G,
          H
        ) : he && (et < 0 || K !== Ne[et] ? tt(Qe, P, we, 2) : et--);
      }
    }
  }, tt = (v, k, P, L, Z = null) => {
    const { el: Y, type: E, transition: G, children: H, shapeFlag: K } = v;
    if (K & 6) {
      tt(v.component.subTree, k, P, L);
      return;
    }
    if (K & 128) {
      v.suspense.move(k, P, L);
      return;
    }
    if (K & 64) {
      E.move(v, k, P, q);
      return;
    }
    if (E === de) {
      n(Y, k, P);
      for (let le = 0; le < H.length; le++)
        tt(H[le], k, P, L);
      n(v.anchor, k, P);
      return;
    }
    if (E === Fo) {
      z(v, k, P);
      return;
    }
    if (L !== 2 && K & 1 && G)
      if (L === 0)
        G.persisted && !Y[Ur] ? n(Y, k, P) : (G.beforeEnter(Y), n(Y, k, P), jt(() => G.enter(Y), Z));
      else {
        const { leave: le, delayLeave: Re, afterLeave: Te } = G, qe = () => {
          v.ctx.isUnmounted ? o(Y) : n(Y, k, P);
        }, st = () => {
          const et = Y._isLeaving || !!Y[Ur];
          Y._isLeaving && Y[Ur](
            !0
            /* cancelled */
          ), G.persisted && !et ? qe() : le(Y, () => {
            qe(), Te && Te();
          });
        };
        Re ? Re(Y, qe, st) : st();
      }
    else
      n(Y, k, P);
  }, De = (v, k, P, L = !1, Z = !1) => {
    const {
      type: Y,
      props: E,
      ref: G,
      children: H,
      dynamicChildren: K,
      shapeFlag: ye,
      patchFlag: le,
      dirs: Re,
      cacheIndex: Te,
      memo: qe
    } = v;
    if ((le === -2 || K && K.hasOnce) && (Z = !1), G != null && (gs(), eo(G, null, P, v, !0), hs()), Te != null && (!v.ctx || v.ctx === k) && (k.renderCache[Te] = void 0), ye & 256) {
      k.ctx.deactivate(v);
      return;
    }
    const st = ye & 1 && Re, et = !_n(v);
    let te;
    if (et && (te = E && E.onVnodeBeforeUnmount) && rs(te, k, v), ye & 6)
      $(v.component, P, L);
    else {
      if (ye & 128) {
        v.suspense.unmount(P, L);
        return;
      }
      st && Ys(v, null, k, "beforeUnmount"), ye & 64 ? v.type.remove(
        v,
        k,
        P,
        q,
        L
      ) : K && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !K.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (Y !== de || le > 0 && le & 64) ? F(
        K,
        k,
        P,
        !1,
        !0
      ) : (Y === de && le & 384 || !Z && ye & 16) && F(H, k, P), L && bt(v);
    }
    const pe = qe != null && Te == null;
    (et && (te = E && E.onVnodeUnmounted) || st || pe) && jt(() => {
      te && rs(te, k, v), st && Ys(v, null, k, "unmounted"), pe && (v.el = null);
    }, P);
  }, bt = (v) => {
    const { type: k, el: P, anchor: L, transition: Z } = v, Y = k === de;
    if (Y && !Z) {
      ke(P, L);
      return;
    }
    if (k === Fo) {
      R(v), Z && !Z.persisted && Z.afterLeave && Z.afterLeave();
      return;
    }
    const E = Y ? ga(v) : v, G = () => {
      Y ? f(P) && ke(P, L) : o(P), Z && !Z.persisted && Z.afterLeave && Z.afterLeave();
    };
    if (E && E.shapeFlag & 1 && Z && !Z.persisted) {
      const { leave: H, delayLeave: K } = Z, ye = E.el, le = () => H(ye, G);
      K ? K(ye, G, le) : le();
    } else
      G();
  }, ke = (v, k) => {
    let P;
    for (; v !== k; )
      P = b(v), o(v), v = P;
    o(k);
  }, $ = (v, k, P) => {
    const { bum: L, scope: Z, job: Y, subTree: E, um: G, m: H, a: K } = v;
    Ni(H), Ni(K), L && Uo(L), Z.stop(), Y ? (Y.flags |= 8, De(E, v, k, P)) : v.vnode.el && E && (E.transition = v.vnode.transition, De(E, v, k, P)), G && jt(G, k), jt(() => {
      v.isUnmounted = !0;
    }, k);
  }, F = (v, k, P, L = !1, Z = !1, Y = 0) => {
    for (let E = Y; E < v.length; E++)
      De(v[E], k, P, L, Z);
  }, U = (v) => {
    if (v.shapeFlag & 6)
      return U(v.component.subTree);
    if (v.shapeFlag & 128)
      return v.suspense.next();
    const k = b(v.anchor || v.el), P = k && k[Uc];
    return P ? b(P) : k;
  }, B = (v, k, P) => {
    const L = v && k._vnode ? void 0 : v && v.component ? v.component.uid : am();
    cf(() => {
      v == null ? k._vnode && De(k._vnode, null, null, !0) : x(
        k._vnode || null,
        v,
        k,
        null,
        null,
        null,
        P
      ), k._vnode = v;
    }, L);
  }, q = {
    p: x,
    um: De,
    m: tt,
    r: bt,
    mt: Ye,
    mc: j,
    pc: ue,
    pbc: ve,
    n: U,
    o: e
  };
  return {
    render: B,
    hydrate: void 0,
    createApp: Df(B)
  };
}
function Fr({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function Xs({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function Xf(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function si(e, t, s = !1) {
  const n = e.children, o = t.children;
  if (Pe(n) && Pe(o))
    for (let r = 0; r < n.length; r++) {
      const a = n[r];
      let i = o[r];
      i.shapeFlag & 1 && !i.dynamicChildren && ((i.patchFlag <= 0 || i.patchFlag === 32) && (i = o[r] = Cs(o[r]), i.el = a.el), !s && i.patchFlag !== -2 && si(a, i)), i.type === Sr && (i.patchFlag === -1 && (i = o[r] = Cs(i)), i.el = a.el), i.type === Yt && !i.el && (i.el = a.el);
    }
}
function em(e) {
  const t = e.slice(), s = [0];
  let n, o, r, a, i;
  const l = e.length;
  for (n = 0; n < l; n++) {
    const u = e[n];
    if (u !== 0) {
      if (o = s[s.length - 1], e[o] < u) {
        t[n] = o, s.push(n);
        continue;
      }
      for (r = 0, a = s.length - 1; r < a; )
        i = r + a >> 1, e[s[i]] < u ? r = i + 1 : a = i;
      u < e[s[r]] && (r > 0 && (t[n] = s[r - 1]), s[r] = n);
    }
  }
  for (r = s.length, a = s[r - 1]; r-- > 0; )
    s[r] = a, a = t[a];
  return s;
}
function cu(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : cu(t);
}
function Ni(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function _a(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? _a(t.subTree) : null;
}
const uu = (e) => e.__isSuspense;
function tm(e, t) {
  t && t.pendingBranch ? Pe(e) ? t.effects.push(...e) : t.effects.push(e) : lf(e);
}
const de = /* @__PURE__ */ Symbol.for("v-fgt"), Sr = /* @__PURE__ */ Symbol.for("v-txt"), Yt = /* @__PURE__ */ Symbol.for("v-cmt"), Fo = /* @__PURE__ */ Symbol.for("v-stc"), Es = [];
let qt = null;
function g(e = !1) {
  Es.push(qt = e ? null : []);
}
function ni() {
  Es.pop(), qt = Es[Es.length - 1] || null;
}
let io = 1;
function Jo(e, t = !1) {
  io += e, e < 0 && qt && t && (qt.hasOnce = !0);
}
function du(e) {
  return e.dynamicChildren = io > 0 ? qt || rn : null, ni(), io > 0 && qt && qt.push(e), e;
}
function w(e, t, s, n, o, r) {
  return du(
    c(
      e,
      t,
      s,
      n,
      o,
      r,
      !0
    )
  );
}
function ft(e, t, s, n, o) {
  return du(
    V(
      e,
      t,
      s,
      n,
      o,
      !0
    )
  );
}
function xn(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function Dn(e, t) {
  return e.type === t.type && e.key === t.key;
}
const fu = ({ key: e }) => e ?? null, Bo = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? yt(e) || /* @__PURE__ */ xt(e) || Ge(e) ? { i: Tt, r: e, k: t, f: !!s } : e : null);
function c(e, t = null, s = null, n = 0, o = null, r = e === de ? 0 : 1, a = !1, i = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && fu(t),
    ref: t && Bo(t),
    scopeId: Dc,
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
    shapeFlag: r,
    patchFlag: n,
    dynamicProps: o,
    dynamicChildren: null,
    appContext: null,
    ctx: Tt
  };
  return i ? (Xo(l, s), r & 128 && e.normalize(l)) : s && (l.shapeFlag |= yt(s) ? 8 : 16), io > 0 && // avoid a block node from tracking itself
  !a && // has current parent block
  qt && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || r & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && qt.push(l), l;
}
const V = sm;
function sm(e, t = null, s = null, n = 0, o = null, r = !1) {
  if ((!e || e === qc) && (e = Yt), xn(e)) {
    const i = kn(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && Xo(i, s), io > 0 && !r && qt && (i.shapeFlag & 6 ? qt[qt.indexOf(e)] = i : qt.push(i)), i.patchFlag = -2, i;
  }
  if (mm(e) && (e = e.__vccOpts), t) {
    t = nm(t);
    let { class: i, style: l } = t;
    i && !yt(i) && (t.class = Ve(i)), dt(l) && (/* @__PURE__ */ br(l) && !Pe(l) && (l = Pt({}, l)), t.style = Pn(l));
  }
  const a = yt(e) ? 1 : uu(e) ? 128 : _r(e) ? 64 : dt(e) ? 4 : Ge(e) ? 2 : 0;
  return c(
    e,
    t,
    s,
    n,
    o,
    a,
    r,
    !0
  );
}
function nm(e) {
  return e ? /* @__PURE__ */ br(e) || nu(e) ? Pt({}, e) : e : null;
}
function kn(e, t, s = !1, n = !1) {
  const { props: o, ref: r, patchFlag: a, children: i, transition: l } = e, u = t ? om(o || {}, t) : o, d = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: u,
    key: u && fu(u),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && r ? Pe(r) ? r.concat(Bo(t)) : [r, Bo(t)] : Bo(t)
    ) : r,
    scopeId: e.scopeId,
    slotScopeIds: e.slotScopeIds,
    children: i,
    target: e.target,
    targetStart: e.targetStart,
    targetAnchor: e.targetAnchor,
    staticCount: e.staticCount,
    shapeFlag: e.shapeFlag,
    // if the vnode is cloned with extra props, we can no longer assume its
    // existing patch flag to be reliable and need to add the FULL_PROPS flag.
    // note: preserve flag for fragments since they use the flag for children
    // fast paths only.
    patchFlag: t && e.type !== de ? a === -1 ? 16 : a | 16 : a,
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
    ssContent: e.ssContent && kn(e.ssContent),
    ssFallback: e.ssFallback && kn(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && Zo(
    d,
    l.clone(d)
  ), d;
}
function D(e = " ", t = 0) {
  return V(Sr, null, e, t);
}
function Yo(e, t) {
  const s = V(Fo, null, e);
  return s.staticCount = t, s;
}
function Q(e = "", t = !1) {
  return t ? (g(), ft(Yt, null, e)) : V(Yt, null, e);
}
function cs(e) {
  return e == null || typeof e == "boolean" ? V(Yt) : Pe(e) ? V(
    de,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : xn(e) ? Cs(e) : V(Sr, null, String(e));
}
function Cs(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : kn(e);
}
function Xo(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (Pe(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const o = t.default;
      o && (o._c && (o._d = !1), Xo(e, o()), o._c && (o._d = !0));
      return;
    } else {
      s = 32;
      const o = t._;
      !o && !nu(t) ? t._ctx = Tt : o === 3 && Tt && (Tt.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (Ge(t)) {
    if (n & 65) {
      Xo(e, { default: t });
      return;
    }
    t = { default: t, _ctx: Tt }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [D(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function om(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const o in n)
      if (o === "class")
        t.class !== n.class && (t.class = Ve([t.class, n.class]));
      else if (o === "style")
        t.style = Pn([t.style, n.style]);
      else if (dr(o)) {
        const r = t[o], a = n[o];
        a && r !== a && !(Pe(r) && r.includes(a)) ? t[o] = r ? [].concat(r, a) : a : a == null && r == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !fr(o) && (t[o] = a);
      } else o !== "" && (t[o] = n[o]);
  }
  return t;
}
function rs(e, t, s, n = null) {
  ns(e, t, 7, [
    s,
    n
  ]);
}
const rm = Jc();
let mu = 0;
function am() {
  return mu;
}
function im(e, t, s) {
  const n = e.type, o = (t ? t.appContext : e.appContext) || rm, r = {
    uid: mu++,
    vnode: e,
    type: n,
    parent: t,
    appContext: o,
    root: null,
    // to be immediately set
    next: null,
    subTree: null,
    // will be set synchronously right after creation
    effect: null,
    update: null,
    // will be set synchronously right after creation
    job: null,
    scope: new dc(
      !0
      /* detached */
    ),
    render: null,
    proxy: null,
    exposed: null,
    exposeProxy: null,
    withProxy: null,
    provides: t ? t.provides : Object.create(o.provides),
    ids: t ? t.ids : ["", 0, 0],
    accessCache: null,
    renderCache: [],
    // local resolved assets
    components: null,
    directives: null,
    // resolved props and emits options
    propsOptions: ru(n, o),
    emitsOptions: Yc(n, o),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: pt,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: pt,
    data: pt,
    props: pt,
    attrs: pt,
    slots: pt,
    refs: pt,
    setupState: pt,
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
  return r.ctx = { _: r }, r.root = t ? t.root : r, r.emit = Lf.bind(null, r), e.ce && e.ce(r), r;
}
let zt = null;
const pu = () => zt || Tt;
let er, lo;
{
  const e = hr(), t = (s, n) => {
    let o;
    return (o = e[s]) || (o = e[s] = []), o.push(n), (r) => {
      o.length > 1 ? o.forEach((a) => a(r)) : o[0](r);
    };
  };
  er = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => zt = s
  ), lo = t(
    "__VUE_SSR_SETTERS__",
    (s) => co = s
  );
}
const ko = (e) => {
  const t = zt;
  return er(e), e.scope.on(), () => {
    e.scope.off(), er(t);
  };
}, zi = () => {
  zt && zt.scope.off(), er(null);
};
function vu(e) {
  return e.vnode.shapeFlag & 4;
}
let co = !1;
function lm(e, t = !1, s = !1) {
  t && lo(t);
  const { props: n, children: o } = e.vnode, r = vu(e);
  Gf(e, n, r, t), Kf(e, o, s || t);
  const a = r ? cm(e, t) : void 0;
  return t && lo(!1), a;
}
function cm(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Ef);
  const { setup: n } = s;
  if (n) {
    gs();
    const o = e.setupContext = n.length > 1 ? dm(e) : null, r = ko(e), a = wo(
      n,
      e,
      0,
      [
        e.props,
        o
      ]
    ), i = oc(a);
    if (hs(), r(), (i || e.sp) && !_n(e) && Bc(e), i) {
      if (a.then(zi, zi), t)
        return a.then((l) => {
          lo(!0);
          try {
            Di(e, l, t);
          } finally {
            lo(!1);
          }
        }).catch((l) => {
          wr(l, e, 0);
        });
      e.asyncDep = a;
    } else
      Di(e, a);
  } else
    gu(e);
}
function Di(e, t, s) {
  Ge(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : dt(t) && (e.setupState = Oc(t)), gu(e);
}
function gu(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || ms);
  {
    const o = ko(e);
    gs();
    try {
      Of(e);
    } finally {
      hs(), o();
    }
  }
}
const um = {
  get(e, t) {
    return Nt(e, "get", ""), e[t];
  }
};
function dm(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, um),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Cr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(Oc(Ja(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in to)
        return to[s](e);
    },
    has(t, s) {
      return s in t || s in to;
    }
  })) : e.proxy;
}
function fm(e, t = !0) {
  return Ge(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function mm(e) {
  return Ge(e) && "__vccOpts" in e;
}
const ge = (e, t) => /* @__PURE__ */ sf(e, t, co);
function uo(e, t, s) {
  try {
    Jo(-1);
    const n = arguments.length;
    return n === 2 ? dt(t) && !Pe(t) ? xn(t) ? V(e, null, [t]) : V(e, t) : V(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && xn(s) && (s = [s]), V(e, t, s));
  } finally {
    Jo(1);
  }
}
const pm = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let xa;
const ji = typeof window < "u" && window.trustedTypes;
if (ji)
  try {
    xa = /* @__PURE__ */ ji.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const hu = xa ? (e) => xa.createHTML(e) : (e) => e, vm = "http://www.w3.org/2000/svg", gm = "http://www.w3.org/1998/Math/MathML", Ss = typeof document < "u" ? document : null, Li = Ss && /* @__PURE__ */ Ss.createElement("template"), hm = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const o = t === "svg" ? Ss.createElementNS(vm, e) : t === "mathml" ? Ss.createElementNS(gm, e) : s ? Ss.createElement(e, { is: s }) : Ss.createElement(e);
    return e === "select" && n && n.multiple != null && o.setAttribute("multiple", n.multiple), o;
  },
  createText: (e) => Ss.createTextNode(e),
  createComment: (e) => Ss.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => Ss.querySelector(e),
  setScopeId(e, t) {
    e.setAttribute(t, "");
  },
  // __UNSAFE__
  // Reason: innerHTML.
  // Static content here can only come from compiled templates.
  // As long as the user only uses trusted templates, this is safe.
  insertStaticContent(e, t, s, n, o, r) {
    const a = s ? s.previousSibling : t.lastChild;
    if (o && (o === r || o.nextSibling))
      for (; t.insertBefore(o.cloneNode(!0), s), !(o === r || !(o = o.nextSibling)); )
        ;
    else {
      Li.innerHTML = hu(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const i = Li.content;
      if (n === "svg" || n === "mathml") {
        const l = i.firstChild;
        for (; l.firstChild; )
          i.appendChild(l.firstChild);
        i.removeChild(l);
      }
      t.insertBefore(i, s);
    }
    return [
      // first
      a ? a.nextSibling : t.firstChild,
      // last
      s ? s.previousSibling : t.lastChild
    ];
  }
}, ym = /* @__PURE__ */ Symbol("_vtc");
function bm(e, t, s) {
  const n = e[ym];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const Ui = /* @__PURE__ */ Symbol("_vod"), wm = /* @__PURE__ */ Symbol("_vsh"), _m = /* @__PURE__ */ Symbol(""), xm = /(?:^|;)\s*display\s*:/;
function km(e, t, s) {
  const n = e.style, o = yt(s);
  let r = !1;
  if (s && !o) {
    if (t)
      if (yt(t))
        for (const a of t.split(";")) {
          const i = a.slice(0, a.indexOf(":")).trim();
          s[i] == null && Hn(n, i, "");
        }
      else
        for (const a in t)
          s[a] == null && Hn(n, a, "");
    for (const a in s) {
      a === "display" && (r = !0);
      const i = s[a];
      i != null ? Cm(
        e,
        a,
        !yt(t) && t ? t[a] : void 0,
        i
      ) || Hn(n, a, i) : Hn(n, a, "");
    }
  } else if (o) {
    if (t !== s) {
      const a = n[_m];
      a && (s += ";" + a), n.cssText = s, r = xm.test(s);
    }
  } else t && e.removeAttribute("style");
  Ui in e && ((!o || t !== s) && (e[Ui] = r ? n.display : ""), e[wm] && (n.display = "none"));
}
const Ao = /\s*!important$/;
function Hn(e, t, s) {
  if (Pe(s))
    s.forEach((n) => Hn(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    Ao.test(s) ? e.setProperty(t, s.replace(Ao, ""), "important") : e.setProperty(t, s);
  else {
    const n = Sm(e, t);
    Ao.test(s) ? e.setProperty(
      Qs(n),
      s.replace(Ao, ""),
      "important"
    ) : e[n] = s;
  }
}
const Vi = ["Webkit", "Moz", "ms"], Br = {};
function Sm(e, t) {
  const s = Br[t];
  if (s)
    return s;
  let n = Vt(t);
  if (n !== "filter" && n in e)
    return Br[t] = n;
  n = vr(n);
  for (let o = 0; o < Vi.length; o++) {
    const r = Vi[o] + n;
    if (r in e)
      return Br[t] = r;
  }
  return t;
}
function Cm(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && yt(n) && s === n;
}
const Fi = "http://www.w3.org/1999/xlink";
function Bi(e, t, s, n, o, r = Rd(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(Fi, t.slice(6, t.length)) : e.setAttributeNS(Fi, t, s) : s == null || r && !lc(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    r ? "" : Kt(s) ? String(s) : s
  );
}
function Wi(e, t, s, n, o) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? hu(s) : s);
    return;
  }
  const r = e.tagName;
  if (t === "value" && r !== "PROGRESS" && // custom elements may use _value internally
  !r.includes("-")) {
    const i = r === "OPTION" ? e.getAttribute("value") || "" : e.value, l = s == null ? (
      // #11647: value should be set as empty string for null and undefined,
      // but <input type="checkbox"> should be set as 'on'.
      e.type === "checkbox" ? "on" : ""
    ) : String(s);
    (i !== l || !("_value" in e)) && (e.value = l), s == null && e.removeAttribute(t), e._value = s;
    return;
  }
  let a = !1;
  if (s === "" || s == null) {
    const i = typeof e[t];
    i === "boolean" ? s = lc(s) : s == null && i === "string" ? (s = "", a = !0) : i === "number" && (s = 0, a = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  a && e.removeAttribute(o || t);
}
function Ws(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function $m(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const Gi = /* @__PURE__ */ Symbol("_vei");
function Im(e, t, s, n, o = null) {
  const r = e[Gi] || (e[Gi] = {}), a = r[t];
  if (n && a)
    a.value = n;
  else {
    const [i, l] = Em(t);
    if (n) {
      const u = r[t] = Pm(
        n,
        o
      );
      Ws(e, i, u, l);
    } else a && ($m(e, i, a, l), r[t] = void 0);
  }
}
const Rm = /(Once|Passive|Capture)$/, Am = /^on:?(?:Once|Passive|Capture)$/;
function Em(e) {
  let t, s;
  for (; (s = e.match(Rm)) && !Am.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Qs(e.slice(2)), t];
}
let Wr = 0;
const Om = /* @__PURE__ */ Promise.resolve(), Tm = () => Wr || (Om.then(() => Wr = 0), Wr = Date.now());
function Pm(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const o = s.value;
    if (Pe(o)) {
      const r = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        r.call(n), n._stopped = !0;
      };
      const a = o.slice(), i = [n];
      for (let l = 0; l < a.length && !n._stopped; l++) {
        const u = a[l];
        u && ns(
          u,
          t,
          5,
          i
        );
      }
    } else
      ns(
        o,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = Tm(), s;
}
const qi = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, Mm = (e, t, s, n, o, r) => {
  const a = o === "svg";
  t === "class" ? bm(e, n, a) : t === "style" ? km(e, s, n) : dr(t) ? fr(t) || Im(e, t, s, n, r) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : Nm(e, t, n, a)) ? (Wi(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && Bi(e, t, n, a, r, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (zm(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !yt(n))) ? Wi(e, Vt(t), n, r, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), Bi(e, t, n, a));
};
function Nm(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && qi(t) && Ge(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const o = e.tagName;
    if (o === "IMG" || o === "VIDEO" || o === "CANVAS" || o === "SOURCE")
      return !1;
  }
  return qi(t) && yt(s) ? !1 : t in e;
}
function zm(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = Vt(t);
  return Array.isArray(s) ? s.some((o) => Vt(o) === n) : Object.keys(s).some((o) => Vt(o) === n);
}
const Sn = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return Pe(t) ? (s) => Uo(t, s) : t;
};
function Dm(e) {
  e.target.composing = !0;
}
function Hi(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const ds = /* @__PURE__ */ Symbol("_assign"), Eo = /* @__PURE__ */ Symbol("_initialValue");
function Gr(e, t, s) {
  return t && (e = e.trim()), s && (e = gr(e)), e;
}
const ut = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, o) {
    e.parentNode && (e.type === "text" ? e[Eo] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[Eo] = e.defaultValue.replace(/\r\n?/g, `
`))), e[ds] = Sn(o);
    const r = n || o.props && o.props.type === "number";
    Ws(e, t ? "change" : "input", (a) => {
      a.target.composing || e[ds](Gr(e.value, s, r));
    }), (s || r) && Ws(e, "change", () => {
      e.value = Gr(e.value, s, r);
    }), t || (Ws(e, "compositionstart", Dm), Ws(e, "compositionend", Hi), Ws(e, "change", Hi));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const o = t ?? "", r = e[Eo];
    delete e[Eo], r !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== r ? e[ds](Gr(e.value, s, n)) : e.value = o;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: o, number: r } }, a) {
    if (e[ds] = Sn(a), e.composing) return;
    const i = (r || e.type === "number") && !/^0\d/.test(e.value) ? gr(e.value) : e.value, l = t ?? "";
    if (i === l)
      return;
    const u = e.getRootNode();
    (u instanceof Document || u instanceof ShadowRoot) && u.activeElement === e && e.type !== "range" && (n && t === s || o && e.value.trim() === l) || (e.value = l);
  }
}, un = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[ds] = Sn(s), Ws(e, "change", () => {
      const n = e._modelValue, o = fo(e), r = e.checked, a = e[ds];
      if (Pe(n)) {
        const i = Wa(n, o), l = i !== -1;
        if (r && !l)
          a(n.concat(o));
        else if (!r && l) {
          const u = [...n];
          u.splice(i, 1), a(u);
        }
      } else if (Os(n)) {
        const i = new Set(n);
        r ? i.add(o) : i.delete(o), a(i);
      } else
        a(yu(e, r));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: Zi,
  beforeUpdate(e, t, s) {
    e[ds] = Sn(s), Zi(e, t, s);
  }
};
function Zi(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let o;
  if (Pe(t))
    o = Wa(t, n.props.value) > -1;
  else if (Os(t))
    o = t.has(n.props.value);
  else {
    if (t === s) return;
    o = Ts(t, yu(e, !0));
  }
  e.checked !== o && (e.checked = o);
}
const Qt = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, Ws(e, "change", () => {
      const o = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? gr(fo(l)) : fo(l)
      ), r = e.multiple, a = r ? Os(e._modelValue) ? new Set(o) : o : o[0], i = e._pendingValue = [
        r,
        r ? Pe(a) ? o.slice() : o : a
      ];
      try {
        e[ds](a);
      } finally {
        _o(() => {
          e._pendingValue === i && (e._pendingValue = void 0);
        });
      }
    }), e[ds] = Sn(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    Ki(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[ds] = Sn(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !jm(t, s[1], s[0])) && Ki(e, t);
  }
};
function jm(e, t, s) {
  if (!s || Pe(e)) return Ts(e, t);
  if (Os(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function Ki(e, t) {
  const s = e.multiple, n = Pe(t);
  if (!(s && !n && !Os(t))) {
    for (let o = 0, r = e.options.length; o < r; o++) {
      const a = e.options[o], i = fo(a);
      if (s)
        if (n) {
          const l = typeof i;
          l === "string" || l === "number" ? a.selected = t.some((u) => String(u) === String(i)) : a.selected = Wa(t, i) > -1;
        } else
          a.selected = t.has(i);
      else if (Ts(fo(a), t)) {
        e.selectedIndex !== o && (e.selectedIndex = o);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function fo(e) {
  return "_value" in e ? e._value : e.value;
}
function yu(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const Lm = ["ctrl", "shift", "alt", "meta"], Um = {
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
  exact: (e, t) => Lm.some((s) => e[`${s}Key`] && !t.includes(s))
}, mo = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((o, ...r) => {
    for (let a = 0; a < t.length; a++) {
      const i = Um[t[a]];
      if (i && i(o, t)) return;
    }
    return e(o, ...r);
  }));
}, Vm = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
}, fs = (e, t) => {
  const s = e._withKeys || (e._withKeys = {}), n = t.join(".");
  return s[n] || (s[n] = ((o) => {
    if (!("key" in o))
      return;
    const r = Qs(o.key);
    if (t.some(
      (a) => a === r || Vm[a] === r
    ))
      return e(o);
  }));
}, Fm = /* @__PURE__ */ Pt({ patchProp: Mm }, hm);
let Qi;
function Bm() {
  return Qi || (Qi = Jf(Fm));
}
const Wm = ((...e) => {
  const t = Bm().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const o = qm(n);
    if (!o) return;
    const r = t._component;
    !Ge(r) && !r.render && !r.template && (r.template = o.innerHTML), o.nodeType === 1 && (o.textContent = "");
    const a = s(o, !1, Gm(o));
    return o instanceof Element && (o.removeAttribute("v-cloak"), o.setAttribute("data-v-app", "")), a;
  }, t;
});
function Gm(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function qm(e) {
  return yt(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let bu;
const $r = (e) => bu = e, wu = (
  /* istanbul ignore next */
  Symbol()
);
function ka(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var so;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(so || (so = {}));
function Hm() {
  const e = fc(!0), t = e.run(() => /* @__PURE__ */ I({}));
  let s = [], n = [];
  const o = Ja({
    install(r) {
      $r(o), o._a = r, r.provide(wu, o), r.config.globalProperties.$pinia = o, n.forEach((a) => s.push(a)), n = [];
    },
    use(r) {
      return this._a ? s.push(r) : n.push(r), this;
    },
    _p: s,
    // it's actually undefined here
    // @ts-expect-error
    _a: null,
    _e: e,
    _s: /* @__PURE__ */ new Map(),
    state: t
  });
  return o;
}
const _u = () => {
};
function Ji(e, t, s, n = _u) {
  e.add(t);
  const o = () => {
    e.delete(t) && n();
  };
  return !s && mc() && Od(o), o;
}
function vn(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const Zm = (e) => e(), Yi = Symbol(), qr = Symbol();
function Sa(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], o = e[s];
    ka(o) && ka(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ xt(n) && !/* @__PURE__ */ ps(n) ? e[s] = Sa(o, n) : e[s] = n;
  }
  return e;
}
const Km = (
  /* istanbul ignore next */
  Symbol()
);
function Qm(e) {
  return !ka(e) || !Object.prototype.hasOwnProperty.call(e, Km);
}
const { assign: Us } = Object;
function Jm(e) {
  return !!(/* @__PURE__ */ xt(e) && e.effect);
}
function Ym(e, t, s, n) {
  const { state: o, actions: r, getters: a } = t, i = s.state.value[e];
  let l;
  function u() {
    i || (s.state.value[e] = o ? o() : {});
    const d = /* @__PURE__ */ Yd(s.state.value[e]);
    return Us(d, r, Object.keys(a || {}).reduce((f, b) => (f[b] = Ja(ge(() => {
      $r(s);
      const h = s._s.get(e);
      return a[b].call(h, h);
    })), f), {}));
  }
  return l = xu(e, u, t, s, n, !0), l;
}
function xu(e, t, s = {}, n, o, r) {
  let a;
  const i = Us({ actions: {} }, s), l = { deep: !0 };
  let u, d, f = /* @__PURE__ */ new Set(), b = /* @__PURE__ */ new Set(), h;
  const O = n.state.value[e];
  !r && !O && (n.state.value[e] = {});
  let x;
  function C(j) {
    let re;
    u = d = !1, typeof j == "function" ? (j(n.state.value[e]), re = {
      type: so.patchFunction,
      storeId: e,
      events: h
    }) : (Sa(n.state.value[e], j), re = {
      type: so.patchObject,
      payload: j,
      storeId: e,
      events: h
    });
    const ve = x = Symbol();
    _o().then(() => {
      x === ve && (u = !0);
    }), d = !0, vn(f, re, n.state.value[e]);
  }
  const T = r ? function() {
    const { state: re } = s, ve = re ? re() : {};
    this.$patch((Me) => {
      Us(Me, ve);
    });
  } : (
    /* istanbul ignore next */
    _u
  );
  function A() {
    a.stop(), f.clear(), b.clear(), n._s.delete(e);
  }
  const z = (j, re = "") => {
    if (Yi in j)
      return j[qr] = re, j;
    const ve = function() {
      $r(n);
      const Me = Array.from(arguments), Ie = /* @__PURE__ */ new Set(), Oe = /* @__PURE__ */ new Set();
      function Ye(S) {
        Ie.add(S);
      }
      function ae(S) {
        Oe.add(S);
      }
      vn(b, {
        args: Me,
        name: ve[qr],
        store: J,
        after: Ye,
        onError: ae
      });
      let _;
      try {
        _ = j.apply(this && this.$id === e ? this : J, Me);
      } catch (S) {
        throw vn(Oe, S), S;
      }
      return _ instanceof Promise ? _.then((S) => (vn(Ie, S), S)).catch((S) => (vn(Oe, S), Promise.reject(S))) : (vn(Ie, _), _);
    };
    return ve[Yi] = !0, ve[qr] = re, ve;
  }, R = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: Ji.bind(null, b),
    $patch: C,
    $reset: T,
    $subscribe(j, re = {}) {
      const ve = Ji(f, j, re.detached, () => Me()), Me = a.run(() => ss(() => n.state.value[e], (Ie) => {
        (re.flush === "sync" ? d : u) && j({
          storeId: e,
          type: so.direct,
          events: h
        }, Ie);
      }, Us({}, l, re)));
      return ve;
    },
    $dispose: A
  }, J = /* @__PURE__ */ bo(R);
  n._s.set(e, J);
  const ne = (n._a && n._a.runWithContext || Zm)(() => n._e.run(() => (a = fc()).run(() => t({ action: z }))));
  for (const j in ne) {
    const re = ne[j];
    if (/* @__PURE__ */ xt(re) && !Jm(re) || /* @__PURE__ */ ps(re))
      r || (O && Qm(re) && (/* @__PURE__ */ xt(re) ? re.value = O[j] : Sa(re, O[j])), n.state.value[e][j] = re);
    else if (typeof re == "function") {
      const ve = z(re, j);
      ne[j] = ve, i.actions[j] = re;
    }
  }
  return Us(J, ne), Us(/* @__PURE__ */ rt(J), ne), Object.defineProperty(J, "$state", {
    get: () => n.state.value[e],
    set: (j) => {
      C((re) => {
        Us(re, j);
      });
    }
  }), n._p.forEach((j) => {
    Us(J, a.run(() => j({
      store: J,
      app: n._a,
      pinia: n,
      options: i
    })));
  }), O && r && s.hydrate && s.hydrate(J.$state, O), u = !0, d = !0, J;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function Mn(e, t, s) {
  let n;
  const o = typeof t == "function";
  n = o ? s : t;
  function r(a, i) {
    const l = uf();
    return a = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    a || (l ? Zt(wu, null) : null), a && $r(a), a = bu, a._s.has(e) || (o ? xu(e, t, n, a) : Ym(e, n, a)), a._s.get(e);
  }
  return r.$id = e, r;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const bn = typeof document < "u";
function ku(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function Xm(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && ku(e.default);
}
const gt = Object.assign;
function Hr(e, t) {
  const s = {};
  for (const n in t) {
    const o = t[n];
    s[n] = os(o) ? o.map(e) : e(o);
  }
  return s;
}
const no = () => {
}, os = Array.isArray;
function Xi(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const Su = /#/g, ep = /&/g, tp = /\//g, sp = /=/g, np = /\?/g, Cu = /\+/g, op = /%5B/g, rp = /%5D/g, $u = /%5E/g, ap = /%60/g, Iu = /%7B/g, ip = /%7C/g, Ru = /%7D/g, lp = /%20/g;
function oi(e) {
  return e == null ? "" : encodeURI("" + e).replace(ip, "|").replace(op, "[").replace(rp, "]");
}
function cp(e) {
  return oi(e).replace(Iu, "{").replace(Ru, "}").replace($u, "^");
}
function Ca(e) {
  return oi(e).replace(Cu, "%2B").replace(lp, "+").replace(Su, "%23").replace(ep, "%26").replace(ap, "`").replace(Iu, "{").replace(Ru, "}").replace($u, "^");
}
function up(e) {
  return Ca(e).replace(sp, "%3D");
}
function dp(e) {
  return oi(e).replace(Su, "%23").replace(np, "%3F");
}
function fp(e) {
  return dp(e).replace(tp, "%2F");
}
function po(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const mp = /\/$/, pp = (e) => e.replace(mp, "");
function Zr(e, t, s = "/") {
  let n, o = {}, r = "", a = "";
  const i = t.indexOf("#");
  let l = t.indexOf("?");
  return l = i >= 0 && l > i ? -1 : l, l >= 0 && (n = t.slice(0, l), r = t.slice(l, i > 0 ? i : t.length), o = e(r.slice(1))), i >= 0 && (n = n || t.slice(0, i), a = t.slice(i, t.length)), n = yp(n ?? t, s), {
    fullPath: n + r + a,
    path: n,
    query: o,
    hash: po(a)
  };
}
function vp(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function gp(e, t, s) {
  const n = t.matched.length - 1, o = s.matched.length - 1;
  return n > -1 && n === o && Cn(t.matched[n], s.matched[o]) && Au(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function Cn(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function Au(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!hp(e[s], t[s])) return !1;
  return !0;
}
function hp(e, t) {
  return os(e) ? el(e, t) : os(t) ? el(t, e) : e?.valueOf() === t?.valueOf();
}
function el(e, t) {
  return os(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function yp(e, t) {
  if (e.startsWith("/")) return e;
  if (!e) return t;
  const s = t.split("/"), n = e.split("/"), o = n[n.length - 1];
  (o === ".." || o === ".") && n.push("");
  let r = s.length - 1, a, i;
  for (a = 0; a < n.length; a++)
    if (i = n[a], i !== ".")
      if (i === "..")
        r > 1 && r--;
      else break;
  return s.slice(0, r).join("/") + "/" + n.slice(a).join("/");
}
const zs = {
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
let $a = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), tl = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const Kr = "";
function bp(e) {
  if (!e) if (bn) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), pp(e);
}
const wp = /^[^#]+#/;
function _p(e, t) {
  return e.replace(wp, "#") + t;
}
function xp(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const kp = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function Sp(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), o = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!o)
      return;
    t = xp(o, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function sl(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Ia = /* @__PURE__ */ new Map();
function Cp(e, t) {
  Ia.set(e, t);
}
function $p(e) {
  const t = Ia.get(e);
  return Ia.delete(e), t;
}
function Ip(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function Eu(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let _t = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const Ou = Symbol("");
_t.MATCHER_NOT_FOUND + "", _t.NAVIGATION_GUARD_REDIRECT + "", _t.NAVIGATION_ABORTED + "", _t.NAVIGATION_CANCELLED + "", _t.NAVIGATION_DUPLICATED + "";
function $n(e, t) {
  return gt(/* @__PURE__ */ new Error(), {
    type: e,
    [Ou]: !0
  }, t);
}
function _s(e, t) {
  return e instanceof Error && Ou in e && (t == null || !!(e.type & t));
}
const Rp = [
  "params",
  "query",
  "hash"
];
function Ap(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of Rp) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function Ep(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const o = s[n].replace(Cu, " "), r = o.indexOf("="), a = po(r < 0 ? o : o.slice(0, r)), i = r < 0 ? null : po(o.slice(r + 1));
    if (a in t) {
      let l = t[a];
      os(l) || (l = t[a] = [l]), l.push(i);
    } else t[a] = i;
  }
  return t;
}
function nl(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = up(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (os(n) ? n.map((o) => o && Ca(o)) : [n && Ca(n)]).forEach((o) => {
      o !== void 0 && (t += (t.length ? "&" : "") + s, o != null && (t += "=" + o));
    });
  }
  return t;
}
function Op(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = os(n) ? n.map((o) => o == null ? null : "" + o) : n == null ? n : "" + n);
  }
  return t;
}
const Tp = Symbol(""), ol = Symbol(""), Ir = Symbol(""), ri = Symbol(""), Ra = Symbol("");
function jn() {
  let e = [];
  function t(n) {
    return e.push(n), () => {
      const o = e.indexOf(n);
      o > -1 && e.splice(o, 1);
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
function Fs(e, t, s, n, o, r = (a) => a()) {
  const a = n && (n.enterCallbacks[o] = n.enterCallbacks[o] || []);
  return () => new Promise((i, l) => {
    const u = (b) => {
      b === !1 ? l($n(_t.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : b instanceof Error ? l(b) : Ip(b) ? l($n(_t.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: b
      })) : (a && n.enterCallbacks[o] === a && typeof b == "function" && a.push(b), i());
    }, d = r(() => e.call(n && n.instances[o], t, s, u));
    let f = Promise.resolve(d);
    e.length < 3 && (f = f.then(u)), f.catch((b) => l(b));
  });
}
function Qr(e, t, s, n, o = (r) => r()) {
  const r = [];
  for (const a of e)
    for (const i in a.components) {
      let l = a.components[i];
      if (!(t !== "beforeRouteEnter" && !a.instances[i]))
        if (ku(l)) {
          const u = (l.__vccOpts || l)[t];
          u && r.push(Fs(u, s, n, a, i, o));
        } else {
          let u = l();
          r.push(() => u.then((d) => {
            if (!d) throw new Error(`Couldn't resolve component "${i}" at "${a.path}"`);
            const f = Xm(d) ? d.default : d;
            a.mods[i] = d, a.components[i] = f;
            const b = (f.__vccOpts || f)[t];
            return b && Fs(b, s, n, a, i, o)();
          }));
        }
    }
  return r;
}
function Pp(e, t) {
  const s = [], n = [], o = [], r = Math.max(t.matched.length, e.matched.length);
  for (let a = 0; a < r; a++) {
    const i = t.matched[a];
    i && (e.matched.find((u) => Cn(u, i)) ? n.push(i) : s.push(i));
    const l = e.matched[a];
    l && (t.matched.find((u) => Cn(u, l)) || o.push(l));
  }
  return [
    s,
    n,
    o
  ];
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
function Mp(e = "") {
  let t = [], s = [[Kr, {}]], n = 0;
  e = bp(e);
  function o(i, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([i, l]);
  }
  function r(i, l, { direction: u, delta: d }) {
    const f = {
      direction: u,
      delta: d,
      type: $a.pop
    };
    for (const b of t) b(i, l, f);
  }
  const a = {
    location: Kr,
    state: {},
    base: e,
    createHref: _p.bind(null, e),
    replace(i, l) {
      s.splice(n--, 1), o(i, l);
    },
    push(i, l) {
      o(i, l);
    },
    listen(i) {
      return t.push(i), () => {
        const l = t.indexOf(i);
        l > -1 && t.splice(l, 1);
      };
    },
    destroy() {
      t = [], s = [[Kr, {}]], n = 0;
    },
    go(i, l = !0) {
      const u = this.location, d = i < 0 ? tl.back : tl.forward;
      n = Math.max(0, Math.min(n + i, s.length - 1)), l && r(this.location, u, {
        direction: d,
        delta: i
      });
    }
  };
  return Object.defineProperty(a, "location", {
    enumerable: !0,
    get: () => s[n][0]
  }), Object.defineProperty(a, "state", {
    enumerable: !0,
    get: () => s[n][1]
  }), a;
}
let an = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var $t = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})($t || {});
const Np = {
  type: an.Static,
  value: ""
}, zp = /[a-zA-Z0-9_]/;
function Dp(e) {
  if (!e) return [[]];
  if (e === "/") return [[Np]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(h) {
    throw new Error(`ERR (${s})/"${u}": ${h}`);
  }
  let s = $t.Static, n = s;
  const o = [];
  let r;
  function a() {
    r && o.push(r), r = [];
  }
  let i = 0, l, u = "", d = "";
  function f() {
    u && (s === $t.Static ? r.push({
      type: an.Static,
      value: u
    }) : s === $t.Param || s === $t.ParamRegExp || s === $t.ParamRegExpEnd ? (r.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${u}) must be alone in its segment. eg: '/:ids+.`), r.push({
      type: an.Param,
      value: u,
      regexp: d,
      repeatable: l === "*" || l === "+",
      optional: l === "*" || l === "?"
    })) : t("Invalid state to consume buffer"), u = "");
  }
  function b() {
    u += l;
  }
  for (; i < e.length; ) {
    if (l = e[i++], l === "\\" && s !== $t.ParamRegExp) {
      n = s, s = $t.EscapeNext;
      continue;
    }
    switch (s) {
      case $t.Static:
        l === "/" ? (u && f(), a()) : l === ":" ? (f(), s = $t.Param) : b();
        break;
      case $t.EscapeNext:
        b(), s = n;
        break;
      case $t.Param:
        l === "(" ? s = $t.ParamRegExp : zp.test(l) ? b() : (f(), s = $t.Static, l !== "*" && l !== "?" && l !== "+" && i--);
        break;
      case $t.ParamRegExp:
        l === ")" ? d[d.length - 1] == "\\" ? d = d.slice(0, -1) + l : s = $t.ParamRegExpEnd : d += l;
        break;
      case $t.ParamRegExpEnd:
        f(), s = $t.Static, l !== "*" && l !== "?" && l !== "+" && i--, d = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === $t.ParamRegExp && t(`Unfinished custom RegExp for param "${u}"`), f(), a(), o;
}
const rl = "[^/]+?", jp = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var Lt = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(Lt || {});
const Lp = /[.+*?^${}()[\]/\\]/g;
function Up(e, t) {
  const s = gt({}, jp, t), n = [];
  let o = s.start ? "^" : "";
  const r = [];
  for (const u of e) {
    const d = u.length ? [] : [Lt.Root];
    s.strict && !u.length && (o += "/");
    for (let f = 0; f < u.length; f++) {
      const b = u[f];
      let h = Lt.Segment + (s.sensitive ? Lt.BonusCaseSensitive : 0);
      if (b.type === an.Static)
        f || (o += "/"), o += b.value.replace(Lp, "\\$&"), h += Lt.Static;
      else if (b.type === an.Param) {
        const { value: O, repeatable: x, optional: C, regexp: T } = b;
        r.push({
          name: O,
          repeatable: x,
          optional: C
        });
        const A = T || rl;
        if (A !== rl) {
          h += Lt.BonusCustomRegExp;
          try {
            `${A}`;
          } catch (R) {
            throw new Error(`Invalid custom RegExp for param "${O}" (${A}): ` + R.message);
          }
        }
        let z = x ? `((?:${A})(?:/(?:${A}))*)` : `(${A})`;
        f || (z = C && u.length < 2 ? `(?:/${z})` : "/" + z), C && (z += "?"), o += z, h += Lt.Dynamic, C && (h += Lt.BonusOptional), x && (h += Lt.BonusRepeatable), A === ".*" && (h += Lt.BonusWildcard);
      }
      d.push(h);
    }
    n.push(d);
  }
  if (s.strict && s.end) {
    const u = n.length - 1;
    n[u][n[u].length - 1] += Lt.BonusStrict;
  }
  s.strict || (o += "/?"), s.end ? o += "$" : s.strict && !o.endsWith("/") && (o += "(?:/|$)");
  const a = new RegExp(o, s.sensitive ? "" : "i");
  function i(u) {
    const d = u.match(a), f = {};
    if (!d) return null;
    for (let b = 1; b < d.length; b++) {
      const h = d[b] || "", O = r[b - 1];
      f[O.name] = h && O.repeatable ? h.split("/") : h;
    }
    return f;
  }
  function l(u) {
    let d = "", f = !1;
    for (const b of e) {
      (!f || !d.endsWith("/")) && (d += "/"), f = !1;
      for (const h of b) if (h.type === an.Static) d += h.value;
      else if (h.type === an.Param) {
        const { value: O, repeatable: x, optional: C } = h, T = O in u ? u[O] : "";
        if (os(T) && !x) throw new Error(`Provided param "${O}" is an array but it is not repeatable (* or + modifiers)`);
        const A = os(T) ? T.join("/") : T;
        if (!A) if (C)
          b.length < 2 && (d.endsWith("/") ? d = d.slice(0, -1) : f = !0);
        else throw new Error(`Missing required param "${O}"`);
        d += A;
      }
    }
    return d || "/";
  }
  return {
    re: a,
    score: n,
    keys: r,
    parse: i,
    stringify: l
  };
}
function Vp(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === Lt.Static + Lt.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === Lt.Static + Lt.Segment ? 1 : -1 : 0;
}
function Tu(e, t) {
  let s = 0;
  const n = e.score, o = t.score;
  for (; s < n.length && s < o.length; ) {
    const r = Vp(n[s], o[s]);
    if (r) return r;
    s++;
  }
  if (Math.abs(o.length - n.length) === 1) {
    if (al(n)) return 1;
    if (al(o)) return -1;
  }
  return o.length - n.length;
}
function al(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const Fp = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function Bp(e, t, s) {
  const n = Up(Dp(e.path), s), o = gt(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !o.record.aliasOf == !t.record.aliasOf && t.children.push(o), o;
}
function Wp(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = Xi(Fp, t);
  function o(f) {
    return n.get(f);
  }
  function r(f, b, h) {
    const O = !h, x = ll(f);
    x.aliasOf = h && h.record;
    const C = Xi(t, f), T = [x];
    if ("alias" in f) {
      const R = typeof f.alias == "string" ? [f.alias] : f.alias;
      for (const J of R) T.push(ll(gt({}, x, {
        components: h ? h.record.components : x.components,
        path: J,
        aliasOf: h ? h.record : x
      })));
    }
    let A, z;
    for (const R of T) {
      const { path: J } = R;
      if (b && J[0] !== "/") {
        const $e = b.record.path, ne = $e[$e.length - 1] === "/" ? "" : "/";
        R.path = b.record.path + (J && ne + J);
      }
      if (A = Bp(R, b, C), h ? h.alias.push(A) : (z = z || A, z !== A && z.alias.push(A), O && f.name && !cl(A) && a(f.name)), Pu(A) && l(A), x.children) {
        const $e = x.children;
        for (let ne = 0; ne < $e.length; ne++) r($e[ne], A, h && h.children[ne]);
      }
      h = h || A;
    }
    return z ? () => {
      a(z);
    } : no;
  }
  function a(f) {
    if (Eu(f)) {
      const b = n.get(f);
      b && (n.delete(f), s.splice(s.indexOf(b), 1), b.children.forEach(a), b.alias.forEach(a));
    } else {
      const b = s.indexOf(f);
      b > -1 && (s.splice(b, 1), f.record.name && n.delete(f.record.name), f.children.forEach(a), f.alias.forEach(a));
    }
  }
  function i() {
    return s;
  }
  function l(f) {
    const b = Hp(f, s);
    s.splice(b, 0, f), f.record.name && !cl(f) && n.set(f.record.name, f);
  }
  function u(f, b) {
    let h, O = {}, x, C;
    if ("name" in f && f.name) {
      if (h = n.get(f.name), !h) throw $n(_t.MATCHER_NOT_FOUND, { location: f });
      C = h.record.name, O = gt(il(b.params, h.keys.filter((z) => !z.optional).concat(h.parent ? h.parent.keys.filter((z) => z.optional) : []).map((z) => z.name)), f.params && il(f.params, h.keys.map((z) => z.name))), x = h.stringify(O);
    } else if (f.path != null)
      x = f.path, h = s.find((z) => z.re.test(x)), h && (O = h.parse(x), C = h.record.name);
    else {
      if (h = b.name ? n.get(b.name) : s.find((z) => z.re.test(b.path)), !h) throw $n(_t.MATCHER_NOT_FOUND, {
        location: f,
        currentLocation: b
      });
      C = h.record.name, O = gt({}, b.params, f.params), x = h.stringify(O);
    }
    const T = [];
    let A = h;
    for (; A; )
      T.unshift(A.record), A = A.parent;
    return {
      name: C,
      path: x,
      params: O,
      matched: T,
      meta: qp(T)
    };
  }
  e.forEach((f) => r(f));
  function d() {
    s.length = 0, n.clear();
  }
  return {
    addRoute: r,
    resolve: u,
    removeRoute: a,
    clearRoutes: d,
    getRoutes: i,
    getRecordMatcher: o
  };
}
function il(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function ll(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: Gp(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function Gp(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function cl(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function qp(e) {
  return e.reduce((t, s) => gt(t, s.meta), {});
}
function Hp(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const r = s + n >> 1;
    Tu(e, t[r]) < 0 ? n = r : s = r + 1;
  }
  const o = Zp(e);
  return o && (n = t.lastIndexOf(o, n - 1)), n;
}
function Zp(e) {
  let t = e;
  for (; t = t.parent; ) if (Pu(t) && Tu(e, t) === 0) return t;
}
function Pu({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function ul(e) {
  const t = Zt(Ir), s = Zt(ri), n = ge(() => {
    const l = m(e.to);
    return t.resolve(l);
  }), o = ge(() => {
    const { matched: l } = n.value, { length: u } = l, d = l[u - 1], f = s.matched;
    if (!d || !f.length) return -1;
    const b = f.findIndex(Cn.bind(null, d));
    if (b > -1) return b;
    const h = dl(l[u - 2]);
    return u > 1 && dl(d) === h && f[f.length - 1].path !== h ? f.findIndex(Cn.bind(null, l[u - 2])) : b;
  }), r = ge(() => o.value > -1 && Yp(s.params, n.value.params)), a = ge(() => o.value > -1 && o.value === s.matched.length - 1 && Au(s.params, n.value.params));
  function i(l = {}) {
    if (Jp(l)) {
      const u = t[m(e.replace) ? "replace" : "push"](m(e.to)).catch(no);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => u), u;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: ge(() => n.value.href),
    isActive: r,
    isExactActive: a,
    navigate: i
  };
}
function Kp(e) {
  return e.length === 1 ? e[0] : e;
}
const Qp = /* @__PURE__ */ Mt({
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
  useLink: ul,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ bo(ul(e)), { options: n } = Zt(Ir), o = ge(() => ({
      [fl(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [fl(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const r = t.default && Kp(t.default(s));
      return e.custom ? r : uo("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: o.value
      }, r);
    };
  }
}), Aa = Qp;
function Jp(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function Yp(e, t) {
  for (const s in t) {
    const n = t[s], o = e[s];
    if (typeof n == "string") {
      if (n !== o) return !1;
    } else if (!os(o) || o.length !== n.length || n.some((r, a) => r.valueOf() !== o[a].valueOf())) return !1;
  }
  return !0;
}
function dl(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const fl = (e, t, s) => e ?? t ?? s, Xp = /* @__PURE__ */ Mt({
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
    const n = Zt(Ra), o = ge(() => e.route || n.value), r = Zt(ol, 0), a = ge(() => {
      let u = m(r);
      const { matched: d } = o.value;
      let f;
      for (; (f = d[u]) && !f.components; ) u++;
      return u;
    }), i = ge(() => o.value.matched[a.value]);
    Vo(ol, ge(() => a.value + 1)), Vo(Tp, i), Vo(Ra, o);
    const l = /* @__PURE__ */ I();
    return ss(() => [
      l.value,
      i.value,
      e.name
    ], ([u, d, f], [b, h, O]) => {
      d && (d.instances[f] = u, h && h !== d && u && u === b && (d.leaveGuards.size || (d.leaveGuards = h.leaveGuards), d.updateGuards.size || (d.updateGuards = h.updateGuards))), u && d && (!h || !Cn(d, h) || !b) && (d.enterCallbacks[f] || []).forEach((x) => x(u));
    }, { flush: "post" }), () => {
      const u = o.value, d = e.name, f = i.value, b = f && f.components[d];
      if (!b) return ml(s.default, {
        Component: b,
        route: u
      });
      const h = f.props[d], O = h ? h === !0 ? u.params : typeof h == "function" ? h(u) : h : null, C = uo(b, gt({}, O, t, {
        onVnodeUnmounted: (T) => {
          T.component.isUnmounted && (f.instances[d] = null);
        },
        ref: l
      }));
      return ml(s.default, {
        Component: C,
        route: u
      }) || C;
    };
  }
});
function ml(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const Mu = Xp;
function ev(e) {
  const t = Wp(e.routes, e), s = e.parseQuery || Ep, n = e.stringifyQuery || nl, o = e.history, r = jn(), a = jn(), i = jn(), l = /* @__PURE__ */ Kd(zs);
  let u = zs;
  bn && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const d = Hr.bind(null, (U) => "" + U), f = Hr.bind(null, fp), b = Hr.bind(null, po);
  function h(U, B) {
    let q, me;
    return Eu(U) ? (q = t.getRecordMatcher(U), me = B) : me = U, t.addRoute(me, q);
  }
  function O(U) {
    const B = t.getRecordMatcher(U);
    B && t.removeRoute(B);
  }
  function x() {
    return t.getRoutes().map((U) => U.record);
  }
  function C(U) {
    return !!t.getRecordMatcher(U);
  }
  function T(U, B) {
    if (B = gt({}, B || l.value), typeof U == "string") {
      const L = Zr(s, U, B.path), Z = t.resolve({ path: L.path }, B), Y = o.createHref(L.fullPath);
      return gt(L, Z, {
        params: b(Z.params),
        hash: po(L.hash),
        redirectedFrom: void 0,
        href: Y
      });
    }
    let q;
    if (U.path != null)
      q = gt({}, U, { path: Zr(s, U.path, B.path).path });
    else {
      const L = gt({}, U.params);
      for (const Z in L) L[Z] == null && delete L[Z];
      q = gt({}, U, { params: f(L) }), B.params = f(B.params);
    }
    const me = t.resolve(q, B), v = U.hash || "";
    me.params = d(b(me.params));
    const k = vp(n, gt({}, U, {
      hash: cp(v),
      path: me.path
    })), P = o.createHref(k);
    return gt({
      fullPath: k,
      hash: v,
      query: n === nl ? Op(U.query) : U.query || {}
    }, me, {
      redirectedFrom: void 0,
      href: P
    });
  }
  function A(U) {
    return typeof U == "string" ? Zr(s, U, l.value.path) : gt({}, U);
  }
  function z(U, B) {
    if (u !== U) return $n(_t.NAVIGATION_CANCELLED, {
      from: B,
      to: U
    });
  }
  function R(U) {
    return ne(U);
  }
  function J(U) {
    return R(gt(A(U), { replace: !0 }));
  }
  function $e(U, B) {
    const q = U.matched[U.matched.length - 1];
    if (q && q.redirect) {
      const { redirect: me } = q;
      let v = typeof me == "function" ? me(U, B) : me;
      return typeof v == "string" && (v = v.includes("?") || v.includes("#") ? v = A(v) : { path: v }, v.params = {}), gt({
        query: U.query,
        hash: U.hash,
        params: v.path != null ? {} : U.params
      }, v);
    }
  }
  function ne(U, B) {
    const q = u = T(U), me = l.value, v = U.state, k = U.force, P = U.replace === !0, L = $e(q, me);
    if (L) return ne(gt(A(L), {
      state: typeof L == "object" ? gt({}, v, L.state) : v,
      force: k,
      replace: P
    }), B || q);
    const Z = q;
    Z.redirectedFrom = B;
    let Y;
    return !k && gp(n, me, q) && (Y = $n(_t.NAVIGATION_DUPLICATED, {
      to: Z,
      from: me
    }), tt(me, me, !0, !1)), (Y ? Promise.resolve(Y) : ve(Z, me)).catch((E) => _s(E) ? _s(E, _t.NAVIGATION_GUARD_REDIRECT) ? E : ie(E) : ue(E, Z, me)).then((E) => {
      if (E) {
        if (_s(E, _t.NAVIGATION_GUARD_REDIRECT))
          return ne(gt({ replace: P }, A(E.to), {
            state: typeof E.to == "object" ? gt({}, v, E.to.state) : v,
            force: k
          }), B || Z);
      } else E = Ie(Z, me, !0, P, v);
      return Me(Z, me, E), E;
    });
  }
  function j(U, B) {
    const q = z(U, B);
    return q ? Promise.reject(q) : Promise.resolve();
  }
  function re(U) {
    const B = ke.values().next().value;
    return B && typeof B.runWithContext == "function" ? B.runWithContext(U) : U();
  }
  function ve(U, B) {
    let q;
    const [me, v, k] = Pp(U, B);
    q = Qr(me.reverse(), "beforeRouteLeave", U, B);
    for (const L of me) L.leaveGuards.forEach((Z) => {
      q.push(Fs(Z, U, B));
    });
    const P = j.bind(null, U, B);
    return q.push(P), F(q).then(() => {
      q = [];
      for (const L of r.list()) q.push(Fs(L, U, B));
      return q.push(P), F(q);
    }).then(() => {
      q = Qr(v, "beforeRouteUpdate", U, B);
      for (const L of v) L.updateGuards.forEach((Z) => {
        q.push(Fs(Z, U, B));
      });
      return q.push(P), F(q);
    }).then(() => {
      q = [];
      for (const L of k) if (L.beforeEnter) if (os(L.beforeEnter)) for (const Z of L.beforeEnter) q.push(Fs(Z, U, B));
      else q.push(Fs(L.beforeEnter, U, B));
      return q.push(P), F(q);
    }).then(() => (U.matched.forEach((L) => L.enterCallbacks = {}), q = Qr(k, "beforeRouteEnter", U, B, re), q.push(P), F(q))).then(() => {
      q = [];
      for (const L of a.list()) q.push(Fs(L, U, B));
      return q.push(P), F(q);
    }).catch((L) => _s(L, _t.NAVIGATION_CANCELLED) ? L : Promise.reject(L));
  }
  function Me(U, B, q) {
    i.list().forEach((me) => re(() => me(U, B, q)));
  }
  function Ie(U, B, q, me, v) {
    const k = z(U, B);
    if (k) return k;
    const P = B === zs, L = bn ? history.state : {};
    q && (me || P ? o.replace(U.fullPath, gt({ scroll: P && L && L.scroll }, v)) : o.push(U.fullPath, v)), l.value = U, tt(U, B, q, P), ie();
  }
  let Oe;
  function Ye() {
    Oe || (Oe = o.listen((U, B, q) => {
      if (!$.listening) return;
      const me = T(U), v = $e(me, $.currentRoute.value);
      if (v) {
        ne(gt(v, {
          replace: !0,
          force: !0
        }), me).catch(no);
        return;
      }
      u = me;
      const k = l.value;
      bn && Cp(sl(k.fullPath, q.delta), kp()), ve(me, k).catch((P) => _s(P, _t.NAVIGATION_ABORTED | _t.NAVIGATION_CANCELLED) ? P : _s(P, _t.NAVIGATION_GUARD_REDIRECT) ? (ne(gt(A(P.to), { force: !0 }), me).then((L) => {
        _s(L, _t.NAVIGATION_ABORTED | _t.NAVIGATION_DUPLICATED) && !q.delta && q.type === $a.pop && o.go(-1, !1);
      }).catch(no), Promise.reject()) : (q.delta && o.go(-q.delta, !1), ue(P, me, k))).then((P) => {
        P = P || Ie(me, k, !1), P && (q.delta && !_s(P, _t.NAVIGATION_CANCELLED) ? o.go(-q.delta, !1) : q.type === $a.pop && _s(P, _t.NAVIGATION_ABORTED | _t.NAVIGATION_DUPLICATED) && o.go(-1, !1)), Me(me, k, P);
      }).catch(no);
    }));
  }
  let ae = jn(), _ = jn(), S;
  function ue(U, B, q) {
    ie(U);
    const me = _.list();
    return me.length ? me.forEach((v) => v(U, B, q)) : console.error(U), Promise.reject(U);
  }
  function Ue() {
    return S && l.value !== zs ? Promise.resolve() : new Promise((U, B) => {
      ae.add([U, B]);
    });
  }
  function ie(U) {
    return S || (S = !U, Ye(), ae.list().forEach(([B, q]) => U ? q(U) : B()), ae.reset()), U;
  }
  function tt(U, B, q, me) {
    const { scrollBehavior: v } = e;
    if (!bn || !v) return Promise.resolve();
    const k = !q && $p(sl(U.fullPath, 0)) || (me || !q) && history.state && history.state.scroll || null;
    return _o().then(() => v(U, B, k)).then((P) => P && Sp(P)).catch((P) => ue(P, U, B));
  }
  const De = (U) => o.go(U);
  let bt;
  const ke = /* @__PURE__ */ new Set(), $ = {
    currentRoute: l,
    listening: !0,
    addRoute: h,
    removeRoute: O,
    clearRoutes: t.clearRoutes,
    hasRoute: C,
    getRoutes: x,
    resolve: T,
    options: e,
    push: R,
    replace: J,
    go: De,
    back: () => De(-1),
    forward: () => De(1),
    beforeEach: r.add,
    beforeResolve: a.add,
    afterEach: i.add,
    onError: _.add,
    isReady: Ue,
    install(U) {
      U.component("RouterLink", Aa), U.component("RouterView", Mu), U.config.globalProperties.$router = $, Object.defineProperty(U.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => m(l)
      }), bn && !bt && l.value === zs && (bt = !0, R(o.location).catch((me) => {
      }));
      const B = {};
      for (const me in zs) Object.defineProperty(B, me, {
        get: () => l.value[me],
        enumerable: !0
      });
      U.provide(Ir, $), U.provide(ri, /* @__PURE__ */ Ac(B)), U.provide(Ra, l);
      const q = U.unmount;
      ke.add(U), U.unmount = function() {
        ke.delete(U), ke.size < 1 && (u = zs, Oe && Oe(), Oe = null, l.value = zs, bt = !1, S = !1), q();
      };
    }
  };
  function F(U) {
    return U.reduce((B, q) => B.then(() => re(q)), Promise.resolve());
  }
  return $;
}
function ai() {
  return Zt(Ir);
}
function Nu(e) {
  return Zt(ri);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const en = {
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
const pl = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Jr(e) {
  return e != null;
}
function tv(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (b) => s[b] ?? b, o = e.size ?? e.width ?? en.width, r = e.size ?? e.height ?? en.height, a = e.aliases?.filter((b) => typeof b == "string" && b.trim() !== "").map((b) => `lucide-${b}`) ?? [], i = [...e.name ? [`lucide-${e.name}`] : [], ...a], l = t.className?.split(" ").filter(Boolean) ?? [], u = t.includeDefaultClasses === !1 ? pl(...l) : pl("lucide", ...i, ...l), d = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? en["stroke-width"]) * Number(e.size ?? e.width ?? en.width) / Number(t.size ?? t.width ?? en.width) : t.strokeWidth ?? en["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(en).reduce((b, [h, O]) => (b[n(h)] = O, b), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && Jr(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && Jr(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && Jr(t.height) && {
        [n("height")]: t.height
      },
      [n("stroke-width")]: d,
      ...u && {
        [n("class")]: u
      },
      [n("viewBox")]: `0 0 ${o} ${r}`,
      ...t.hasA11yProp === !1 ? {
        [n("aria-hidden")]: "true"
      } : {},
      ..."attributes" in t && t.attributes
    },
    e.node.map((b) => {
      const [h, O, x] = b, C = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...O } : O;
      return x ? [h, C, x] : [h, C];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const sv = (e) => {
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
const Oo = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const nv = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ov = /* @__PURE__ */ Symbol("lucide-icons");
function rv() {
  return Zt(ov, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const av = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && nv(e),
    node: t ?? s ?? [],
    size: 24,
    aliases: []
  },
  absoluteStrokeWidth: o,
  "absolute-stroke-width": r,
  nonScalingStroke: a,
  "non-scaling-stroke": i,
  strokeWidth: l,
  "stroke-width": u,
  size: d,
  width: f = d,
  height: b = d,
  color: h,
  ...O
}, { slots: x }) => {
  const {
    size: C,
    color: T,
    strokeWidth: A = 2,
    absoluteStrokeWidth: z = !1,
    nonScalingStroke: R = !1,
    class: J = ""
  } = rv(), $e = Oo(o) || Oo(r) || o === !0 || r === !0 || z === !0, ne = Oo(a) || Oo(i) || a === !0 || i === !0 || R === !0;
  delete O.class;
  const j = x.default?.(), [, re, ve = []] = tv(n, {
    color: h ?? T,
    width: f ?? d ?? C,
    height: b ?? d ?? C,
    strokeWidth: l ?? u ?? A,
    absoluteStrokeWidth: $e,
    nonScalingStroke: ne,
    className: J,
    hasA11yProp: j != null && j.length > 0 || sv(O),
    attributes: O
  });
  return uo("svg", re, [
    ...ve.map(([Me, Ie]) => uo(Me, Ie)),
    ...j ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function St(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: o }) => uo(
    av,
    {
      ...n,
      icon: s
    },
    o.default ? { default: o.default } : void 0
  );
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const iv = {
  name: "check",
  size: 24,
  node: [["path", { d: "M20 6 9 17l-5-5", key: "1gmf2c" }]]
}, lv = St(iv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const cv = {
  name: "chevron-down",
  size: 24,
  node: [["path", { d: "m6 9 6 6 6-6", key: "qrunsl" }]]
}, uv = St(cv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const dv = {
  name: "database",
  size: 24,
  node: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]
}, fv = St(dv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const mv = {
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
}, zu = St(mv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const pv = {
  name: "image-off",
  size: 24,
  node: [
    ["line", { x1: "2", x2: "22", y1: "2", y2: "22", key: "a6p6uj" }],
    ["path", { d: "M10.41 10.41a2 2 0 1 1-2.83-2.83", key: "1bzlo9" }],
    ["line", { x1: "13.5", x2: "6", y1: "13.5", y2: "21", key: "1q0aeu" }],
    ["line", { x1: "18", x2: "21", y1: "12", y2: "15", key: "5mozeu" }],
    [
      "path",
      {
        d: "M3.59 3.59A1.99 1.99 0 0 0 3 5v14a2 2 0 0 0 2 2h14c.55 0 1.052-.22 1.41-.59",
        key: "mmje98"
      }
    ],
    ["path", { d: "M21 15V5a2 2 0 0 0-2-2H9", key: "43el77" }]
  ]
}, vv = St(pv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const gv = {
  name: "image-plus",
  size: 24,
  node: [
    ["path", { d: "M16 5h6", key: "1vod17" }],
    ["path", { d: "M19 2v6", key: "4bpg5p" }],
    ["path", { d: "M21 11.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7.5", key: "1ue2ih" }],
    ["path", { d: "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21", key: "1xmnt7" }],
    ["circle", { cx: "9", cy: "9", r: "2", key: "af1f0g" }]
  ]
}, hv = St(gv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const yv = {
  name: "import",
  size: 24,
  node: [
    ["path", { d: "M12 3v12", key: "1x0j5s" }],
    ["path", { d: "m8 11 4 4 4-4", key: "1dohi6" }],
    [
      "path",
      {
        d: "M8 5H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-4",
        key: "1ywtjm"
      }
    ]
  ]
}, bv = St(yv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const wv = {
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
}, Du = St(wv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const _v = {
  name: "list-plus",
  size: 24,
  node: [
    ["path", { d: "M16 5H3", key: "m91uny" }],
    ["path", { d: "M11 12H3", key: "51ecnj" }],
    ["path", { d: "M16 19H3", key: "zzsher" }],
    ["path", { d: "M18 9v6", key: "1twb98" }],
    ["path", { d: "M21 12h-6", key: "bt1uis" }]
  ]
}, xv = St(_v);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const kv = {
  name: "menu",
  size: 24,
  node: [
    ["path", { d: "M4 5h16", key: "1tepv9" }],
    ["path", { d: "M4 12h16", key: "1lakjw" }],
    ["path", { d: "M4 19h16", key: "1djgab" }]
  ]
}, Sv = St(kv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Cv = {
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
}, $v = St(Cv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Iv = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, Rr = St(Iv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Rv = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, Av = St(Rv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ev = {
  name: "rotate-ccw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }]
  ]
}, Ov = St(Ev);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Tv = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, Ea = St(Tv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Pv = {
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
}, Mv = St(Pv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Nv = {
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
}, zv = St(Nv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Dv = {
  name: "star",
  size: 24,
  node: [
    [
      "path",
      {
        d: "M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z",
        key: "r04s7s"
      }
    ]
  ]
}, tr = St(Dv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const jv = {
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
}, Lv = St(jv);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Uv = {
  name: "x",
  size: 24,
  node: [
    ["path", { d: "M18 6 6 18", key: "1bl5f8" }],
    ["path", { d: "m6 6 12 12", key: "d8bk6v" }]
  ]
}, sr = St(Uv), ju = "comfymodal", Lu = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], Yr = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function Zs(e) {
  return typeof e == "string" && Lu.indexOf(e) !== -1;
}
function To(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function Uu(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), o = n[0], r = o.indexOf("=");
  if (r === -1 || To(o.slice(0, r)) !== ju) return t;
  const a = To(o.slice(r + 1));
  if (!Zs(a)) return t;
  let i = null;
  for (let l = 1; l < n.length; l++) {
    const u = n[l], d = u.indexOf("=");
    if (d === -1 || To(u.slice(0, d)) !== "focus") continue;
    const f = To(u.slice(d + 1));
    i = f === null || f === "" ? null : f;
    break;
  }
  return { matched: !0, page: a, focus: i };
}
function Vu(e) {
  if (!Zs(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + ju + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function vl(e, t) {
  if (!t || !Zs(t.page)) return "none";
  if (!e || !Zs(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function Vv(e, t) {
  if (e && Zs(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = Uu(t);
  return s.matched && Zs(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
var at;
(function(e) {
  e.assertEqual = (o) => {
  };
  function t(o) {
  }
  e.assertIs = t;
  function s(o) {
    throw new Error();
  }
  e.assertNever = s, e.arrayToEnum = (o) => {
    const r = {};
    for (const a of o)
      r[a] = a;
    return r;
  }, e.getValidEnumValues = (o) => {
    const r = e.objectKeys(o).filter((i) => typeof o[o[i]] != "number"), a = {};
    for (const i of r)
      a[i] = o[i];
    return e.objectValues(a);
  }, e.objectValues = (o) => e.objectKeys(o).map(function(r) {
    return o[r];
  }), e.objectKeys = typeof Object.keys == "function" ? (o) => Object.keys(o) : (o) => {
    const r = [];
    for (const a in o)
      Object.prototype.hasOwnProperty.call(o, a) && r.push(a);
    return r;
  }, e.find = (o, r) => {
    for (const a of o)
      if (r(a))
        return a;
  }, e.isInteger = typeof Number.isInteger == "function" ? (o) => Number.isInteger(o) : (o) => typeof o == "number" && Number.isFinite(o) && Math.floor(o) === o;
  function n(o, r = " | ") {
    return o.map((a) => typeof a == "string" ? `'${a}'` : a).join(r);
  }
  e.joinValues = n, e.jsonStringifyReplacer = (o, r) => typeof r == "bigint" ? r.toString() : r;
})(at || (at = {}));
var gl;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(gl || (gl = {}));
const Ce = at.arrayToEnum([
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
]), Bs = (e) => {
  switch (typeof e) {
    case "undefined":
      return Ce.undefined;
    case "string":
      return Ce.string;
    case "number":
      return Number.isNaN(e) ? Ce.nan : Ce.number;
    case "boolean":
      return Ce.boolean;
    case "function":
      return Ce.function;
    case "bigint":
      return Ce.bigint;
    case "symbol":
      return Ce.symbol;
    case "object":
      return Array.isArray(e) ? Ce.array : e === null ? Ce.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? Ce.promise : typeof Map < "u" && e instanceof Map ? Ce.map : typeof Set < "u" && e instanceof Set ? Ce.set : typeof Date < "u" && e instanceof Date ? Ce.date : Ce.object;
    default:
      return Ce.unknown;
  }
}, fe = at.arrayToEnum([
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
class Ps extends Error {
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
    const s = t || function(r) {
      return r.message;
    }, n = { _errors: [] }, o = (r) => {
      for (const a of r.issues)
        if (a.code === "invalid_union")
          a.unionErrors.map(o);
        else if (a.code === "invalid_return_type")
          o(a.returnTypeError);
        else if (a.code === "invalid_arguments")
          o(a.argumentsError);
        else if (a.path.length === 0)
          n._errors.push(s(a));
        else {
          let i = n, l = 0;
          for (; l < a.path.length; ) {
            const u = a.path[l];
            l === a.path.length - 1 ? (i[u] = i[u] || { _errors: [] }, i[u]._errors.push(s(a))) : i[u] = i[u] || { _errors: [] }, i = i[u], l++;
          }
        }
    };
    return o(this), n;
  }
  static assert(t) {
    if (!(t instanceof Ps))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, at.jsonStringifyReplacer, 2);
  }
  get isEmpty() {
    return this.issues.length === 0;
  }
  flatten(t = (s) => s.message) {
    const s = {}, n = [];
    for (const o of this.issues)
      if (o.path.length > 0) {
        const r = o.path[0];
        s[r] = s[r] || [], s[r].push(t(o));
      } else
        n.push(t(o));
    return { formErrors: n, fieldErrors: s };
  }
  get formErrors() {
    return this.flatten();
  }
}
Ps.create = (e) => new Ps(e);
const Oa = (e, t) => {
  let s;
  switch (e.code) {
    case fe.invalid_type:
      e.received === Ce.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case fe.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, at.jsonStringifyReplacer)}`;
      break;
    case fe.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${at.joinValues(e.keys, ", ")}`;
      break;
    case fe.invalid_union:
      s = "Invalid input";
      break;
    case fe.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${at.joinValues(e.options)}`;
      break;
    case fe.invalid_enum_value:
      s = `Invalid enum value. Expected ${at.joinValues(e.options)}, received '${e.received}'`;
      break;
    case fe.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case fe.invalid_return_type:
      s = "Invalid function return type";
      break;
    case fe.invalid_date:
      s = "Invalid date";
      break;
    case fe.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : at.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case fe.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case fe.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case fe.custom:
      s = "Invalid input";
      break;
    case fe.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case fe.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case fe.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, at.assertNever(e);
  }
  return { message: s };
};
let Fv = Oa;
function Bv() {
  return Fv;
}
const Wv = (e) => {
  const { data: t, path: s, errorMaps: n, issueData: o } = e, r = [...s, ...o.path || []], a = {
    ...o,
    path: r
  };
  if (o.message !== void 0)
    return {
      ...o,
      path: r,
      message: o.message
    };
  let i = "";
  const l = n.filter((u) => !!u).slice().reverse();
  for (const u of l)
    i = u(a, { data: t, defaultError: i }).message;
  return {
    ...o,
    path: r,
    message: i
  };
};
function be(e, t) {
  const s = Bv(), n = Wv({
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
      s === Oa ? void 0 : Oa
      // then global default map
    ].filter((o) => !!o)
  });
  e.common.issues.push(n);
}
class Ft {
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
    for (const o of s) {
      if (o.status === "aborted")
        return We;
      o.status === "dirty" && t.dirty(), n.push(o.value);
    }
    return { status: t.value, value: n };
  }
  static async mergeObjectAsync(t, s) {
    const n = [];
    for (const o of s) {
      const r = await o.key, a = await o.value;
      n.push({
        key: r,
        value: a
      });
    }
    return Ft.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const o of s) {
      const { key: r, value: a } = o;
      if (r.status === "aborted" || a.status === "aborted")
        return We;
      r.status === "dirty" && t.dirty(), a.status === "dirty" && t.dirty(), r.value !== "__proto__" && (typeof a.value < "u" || o.alwaysSet) && (n[r.value] = a.value);
    }
    return { status: t.value, value: n };
  }
}
const We = Object.freeze({
  status: "aborted"
}), Zn = (e) => ({ status: "dirty", value: e }), Xt = (e) => ({ status: "valid", value: e }), hl = (e) => e.status === "aborted", yl = (e) => e.status === "dirty", In = (e) => e.status === "valid", nr = (e) => typeof Promise < "u" && e instanceof Promise;
var Ee;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(Ee || (Ee = {}));
class bs {
  constructor(t, s, n, o) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = o;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const bl = (e, t) => {
  if (In(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new Ps(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function Je(e) {
  if (!e)
    return {};
  const { errorMap: t, invalid_type_error: s, required_error: n, description: o } = e;
  if (t && (s || n))
    throw new Error(`Can't use "invalid_type_error" or "required_error" in conjunction with custom error map.`);
  return t ? { errorMap: t, description: o } : { errorMap: (a, i) => {
    const { message: l } = e;
    return a.code === "invalid_enum_value" ? { message: l ?? i.defaultError } : typeof i.data > "u" ? { message: l ?? n ?? i.defaultError } : a.code !== "invalid_type" ? { message: i.defaultError } : { message: l ?? s ?? i.defaultError };
  }, description: o };
}
class nt {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return Bs(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: Bs(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new Ft(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: Bs(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (nr(s))
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
      parsedType: Bs(t)
    }, o = this._parseSync({ data: t, path: n.path, parent: n });
    return bl(n, o);
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
      parsedType: Bs(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return In(n) ? {
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
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => In(n) ? {
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
      parsedType: Bs(t)
    }, o = this._parse({ data: t, path: n.path, parent: n }), r = await (nr(o) ? o : Promise.resolve(o));
    return bl(n, r);
  }
  refine(t, s) {
    const n = (o) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(o) : s;
    return this._refinement((o, r) => {
      const a = t(o), i = () => r.addIssue({
        code: fe.custom,
        ...n(o)
      });
      return typeof Promise < "u" && a instanceof Promise ? a.then((l) => l ? !0 : (i(), !1)) : a ? !0 : (i(), !1);
    });
  }
  refinement(t, s) {
    return this._refinement((n, o) => t(n) ? !0 : (o.addIssue(typeof s == "function" ? s(n, o) : s), !1));
  }
  _refinement(t) {
    return new En({
      schema: this,
      typeName: Fe.ZodEffects,
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
    return qs.create(this, this._def);
  }
  nullable() {
    return On.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return vs.create(this);
  }
  promise() {
    return lr.create(this, this._def);
  }
  or(t) {
    return rr.create([this, t], this._def);
  }
  and(t) {
    return ar.create(this, t, this._def);
  }
  transform(t) {
    return new En({
      ...Je(this._def),
      schema: this,
      typeName: Fe.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Ma({
      ...Je(this._def),
      innerType: this,
      defaultValue: s,
      typeName: Fe.ZodDefault
    });
  }
  brand() {
    return new mg({
      typeName: Fe.ZodBranded,
      type: this,
      ...Je(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new Na({
      ...Je(this._def),
      innerType: this,
      catchValue: s,
      typeName: Fe.ZodCatch
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
    return ii.create(this, t);
  }
  readonly() {
    return za.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const Gv = /^c[^\s-]{8,}$/i, qv = /^[0-9a-z]+$/, Hv = /^[0-9A-HJKMNP-TV-Z]{26}$/i, Zv = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, Kv = /^[a-z0-9_-]{21}$/i, Qv = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, Jv = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Yv = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, Xv = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let Xr;
const eg = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, tg = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, sg = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, ng = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, og = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, rg = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, Fu = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", ag = new RegExp(`^${Fu}$`);
function Bu(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function ig(e) {
  return new RegExp(`^${Bu(e)}$`);
}
function lg(e) {
  let t = `${Fu}T${Bu(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function cg(e, t) {
  return !!((t === "v4" || !t) && eg.test(e) || (t === "v6" || !t) && sg.test(e));
}
function ug(e, t) {
  if (!Qv.test(e))
    return !1;
  try {
    const [s] = e.split(".");
    if (!s)
      return !1;
    const n = s.replace(/-/g, "+").replace(/_/g, "/").padEnd(s.length + (4 - s.length % 4) % 4, "="), o = JSON.parse(atob(n));
    return !(typeof o != "object" || o === null || "typ" in o && o?.typ !== "JWT" || !o.alg || t && o.alg !== t);
  } catch {
    return !1;
  }
}
function dg(e, t) {
  return !!((t === "v4" || !t) && tg.test(e) || (t === "v6" || !t) && ng.test(e));
}
class Rs extends nt {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== Ce.string) {
      const r = this._getOrReturnCtx(t);
      return be(r, {
        code: fe.invalid_type,
        expected: Ce.string,
        received: r.parsedType
      }), We;
    }
    const n = new Ft();
    let o;
    for (const r of this._def.checks)
      if (r.kind === "min")
        t.data.length < r.value && (o = this._getOrReturnCtx(t, o), be(o, {
          code: fe.too_small,
          minimum: r.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: r.message
        }), n.dirty());
      else if (r.kind === "max")
        t.data.length > r.value && (o = this._getOrReturnCtx(t, o), be(o, {
          code: fe.too_big,
          maximum: r.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: r.message
        }), n.dirty());
      else if (r.kind === "length") {
        const a = t.data.length > r.value, i = t.data.length < r.value;
        (a || i) && (o = this._getOrReturnCtx(t, o), a ? be(o, {
          code: fe.too_big,
          maximum: r.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: r.message
        }) : i && be(o, {
          code: fe.too_small,
          minimum: r.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: r.message
        }), n.dirty());
      } else if (r.kind === "email")
        Yv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "email",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "emoji")
        Xr || (Xr = new RegExp(Xv, "u")), Xr.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "emoji",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "uuid")
        Zv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "uuid",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "nanoid")
        Kv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "nanoid",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "cuid")
        Gv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "cuid",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "cuid2")
        qv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "cuid2",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "ulid")
        Hv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
          validation: "ulid",
          code: fe.invalid_string,
          message: r.message
        }), n.dirty());
      else if (r.kind === "url")
        try {
          new URL(t.data);
        } catch {
          o = this._getOrReturnCtx(t, o), be(o, {
            validation: "url",
            code: fe.invalid_string,
            message: r.message
          }), n.dirty();
        }
      else r.kind === "regex" ? (r.regex.lastIndex = 0, r.regex.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "regex",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty())) : r.kind === "trim" ? t.data = t.data.trim() : r.kind === "includes" ? t.data.includes(r.value, r.position) || (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.invalid_string,
        validation: { includes: r.value, position: r.position },
        message: r.message
      }), n.dirty()) : r.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : r.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : r.kind === "startsWith" ? t.data.startsWith(r.value) || (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.invalid_string,
        validation: { startsWith: r.value },
        message: r.message
      }), n.dirty()) : r.kind === "endsWith" ? t.data.endsWith(r.value) || (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.invalid_string,
        validation: { endsWith: r.value },
        message: r.message
      }), n.dirty()) : r.kind === "datetime" ? lg(r).test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.invalid_string,
        validation: "datetime",
        message: r.message
      }), n.dirty()) : r.kind === "date" ? ag.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.invalid_string,
        validation: "date",
        message: r.message
      }), n.dirty()) : r.kind === "time" ? ig(r).test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.invalid_string,
        validation: "time",
        message: r.message
      }), n.dirty()) : r.kind === "duration" ? Jv.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "duration",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty()) : r.kind === "ip" ? cg(t.data, r.version) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "ip",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty()) : r.kind === "jwt" ? ug(t.data, r.alg) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "jwt",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty()) : r.kind === "cidr" ? dg(t.data, r.version) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "cidr",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty()) : r.kind === "base64" ? og.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "base64",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty()) : r.kind === "base64url" ? rg.test(t.data) || (o = this._getOrReturnCtx(t, o), be(o, {
        validation: "base64url",
        code: fe.invalid_string,
        message: r.message
      }), n.dirty()) : at.assertNever(r);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((o) => t.test(o), {
      validation: s,
      code: fe.invalid_string,
      ...Ee.errToObj(n)
    });
  }
  _addCheck(t) {
    return new Rs({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...Ee.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...Ee.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...Ee.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...Ee.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...Ee.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...Ee.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...Ee.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...Ee.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...Ee.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...Ee.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...Ee.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...Ee.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...Ee.errToObj(t) });
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
      ...Ee.errToObj(t?.message)
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
      ...Ee.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...Ee.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...Ee.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...Ee.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...Ee.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...Ee.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...Ee.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...Ee.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...Ee.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, Ee.errToObj(t));
  }
  trim() {
    return new Rs({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new Rs({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new Rs({
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
Rs.create = (e) => new Rs({
  checks: [],
  typeName: Fe.ZodString,
  coerce: e?.coerce ?? !1,
  ...Je(e)
});
function fg(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, o = s > n ? s : n, r = Number.parseInt(e.toFixed(o).replace(".", "")), a = Number.parseInt(t.toFixed(o).replace(".", ""));
  return r % a / 10 ** o;
}
class Rn extends nt {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== Ce.number) {
      const r = this._getOrReturnCtx(t);
      return be(r, {
        code: fe.invalid_type,
        expected: Ce.number,
        received: r.parsedType
      }), We;
    }
    let n;
    const o = new Ft();
    for (const r of this._def.checks)
      r.kind === "int" ? at.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.invalid_type,
        expected: "integer",
        received: "float",
        message: r.message
      }), o.dirty()) : r.kind === "min" ? (r.inclusive ? t.data < r.value : t.data <= r.value) && (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.too_small,
        minimum: r.value,
        type: "number",
        inclusive: r.inclusive,
        exact: !1,
        message: r.message
      }), o.dirty()) : r.kind === "max" ? (r.inclusive ? t.data > r.value : t.data >= r.value) && (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.too_big,
        maximum: r.value,
        type: "number",
        inclusive: r.inclusive,
        exact: !1,
        message: r.message
      }), o.dirty()) : r.kind === "multipleOf" ? fg(t.data, r.value) !== 0 && (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.not_multiple_of,
        multipleOf: r.value,
        message: r.message
      }), o.dirty()) : r.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.not_finite,
        message: r.message
      }), o.dirty()) : at.assertNever(r);
    return { status: o.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, Ee.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, Ee.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, Ee.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, Ee.toString(s));
  }
  setLimit(t, s, n, o) {
    return new Rn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: Ee.toString(o)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Rn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: Ee.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: Ee.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: Ee.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: Ee.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: Ee.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: Ee.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: Ee.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: Ee.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: Ee.toString(t)
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && at.isInteger(t.value));
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
Rn.create = (e) => new Rn({
  checks: [],
  typeName: Fe.ZodNumber,
  coerce: e?.coerce || !1,
  ...Je(e)
});
class vo extends nt {
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
    if (this._getType(t) !== Ce.bigint)
      return this._getInvalidInput(t);
    let n;
    const o = new Ft();
    for (const r of this._def.checks)
      r.kind === "min" ? (r.inclusive ? t.data < r.value : t.data <= r.value) && (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.too_small,
        type: "bigint",
        minimum: r.value,
        inclusive: r.inclusive,
        message: r.message
      }), o.dirty()) : r.kind === "max" ? (r.inclusive ? t.data > r.value : t.data >= r.value) && (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.too_big,
        type: "bigint",
        maximum: r.value,
        inclusive: r.inclusive,
        message: r.message
      }), o.dirty()) : r.kind === "multipleOf" ? t.data % r.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), be(n, {
        code: fe.not_multiple_of,
        multipleOf: r.value,
        message: r.message
      }), o.dirty()) : at.assertNever(r);
    return { status: o.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return be(s, {
      code: fe.invalid_type,
      expected: Ce.bigint,
      received: s.parsedType
    }), We;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, Ee.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, Ee.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, Ee.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, Ee.toString(s));
  }
  setLimit(t, s, n, o) {
    return new vo({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: Ee.toString(o)
        }
      ]
    });
  }
  _addCheck(t) {
    return new vo({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: Ee.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: Ee.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: Ee.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: Ee.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: Ee.toString(s)
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
vo.create = (e) => new vo({
  checks: [],
  typeName: Fe.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...Je(e)
});
class Ta extends nt {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== Ce.boolean) {
      const n = this._getOrReturnCtx(t);
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.boolean,
        received: n.parsedType
      }), We;
    }
    return Xt(t.data);
  }
}
Ta.create = (e) => new Ta({
  typeName: Fe.ZodBoolean,
  coerce: e?.coerce || !1,
  ...Je(e)
});
class or extends nt {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== Ce.date) {
      const r = this._getOrReturnCtx(t);
      return be(r, {
        code: fe.invalid_type,
        expected: Ce.date,
        received: r.parsedType
      }), We;
    }
    if (Number.isNaN(t.data.getTime())) {
      const r = this._getOrReturnCtx(t);
      return be(r, {
        code: fe.invalid_date
      }), We;
    }
    const n = new Ft();
    let o;
    for (const r of this._def.checks)
      r.kind === "min" ? t.data.getTime() < r.value && (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.too_small,
        message: r.message,
        inclusive: !0,
        exact: !1,
        minimum: r.value,
        type: "date"
      }), n.dirty()) : r.kind === "max" ? t.data.getTime() > r.value && (o = this._getOrReturnCtx(t, o), be(o, {
        code: fe.too_big,
        message: r.message,
        inclusive: !0,
        exact: !1,
        maximum: r.value,
        type: "date"
      }), n.dirty()) : at.assertNever(r);
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
      message: Ee.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: Ee.toString(s)
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
  typeName: Fe.ZodDate,
  ...Je(e)
});
class wl extends nt {
  _parse(t) {
    if (this._getType(t) !== Ce.symbol) {
      const n = this._getOrReturnCtx(t);
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.symbol,
        received: n.parsedType
      }), We;
    }
    return Xt(t.data);
  }
}
wl.create = (e) => new wl({
  typeName: Fe.ZodSymbol,
  ...Je(e)
});
class _l extends nt {
  _parse(t) {
    if (this._getType(t) !== Ce.undefined) {
      const n = this._getOrReturnCtx(t);
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.undefined,
        received: n.parsedType
      }), We;
    }
    return Xt(t.data);
  }
}
_l.create = (e) => new _l({
  typeName: Fe.ZodUndefined,
  ...Je(e)
});
class xl extends nt {
  _parse(t) {
    if (this._getType(t) !== Ce.null) {
      const n = this._getOrReturnCtx(t);
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.null,
        received: n.parsedType
      }), We;
    }
    return Xt(t.data);
  }
}
xl.create = (e) => new xl({
  typeName: Fe.ZodNull,
  ...Je(e)
});
class kl extends nt {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return Xt(t.data);
  }
}
kl.create = (e) => new kl({
  typeName: Fe.ZodAny,
  ...Je(e)
});
class Sl extends nt {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return Xt(t.data);
  }
}
Sl.create = (e) => new Sl({
  typeName: Fe.ZodUnknown,
  ...Je(e)
});
class Ks extends nt {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return be(s, {
      code: fe.invalid_type,
      expected: Ce.never,
      received: s.parsedType
    }), We;
  }
}
Ks.create = (e) => new Ks({
  typeName: Fe.ZodNever,
  ...Je(e)
});
class Cl extends nt {
  _parse(t) {
    if (this._getType(t) !== Ce.undefined) {
      const n = this._getOrReturnCtx(t);
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.void,
        received: n.parsedType
      }), We;
    }
    return Xt(t.data);
  }
}
Cl.create = (e) => new Cl({
  typeName: Fe.ZodVoid,
  ...Je(e)
});
class vs extends nt {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), o = this._def;
    if (s.parsedType !== Ce.array)
      return be(s, {
        code: fe.invalid_type,
        expected: Ce.array,
        received: s.parsedType
      }), We;
    if (o.exactLength !== null) {
      const a = s.data.length > o.exactLength.value, i = s.data.length < o.exactLength.value;
      (a || i) && (be(s, {
        code: a ? fe.too_big : fe.too_small,
        minimum: i ? o.exactLength.value : void 0,
        maximum: a ? o.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: o.exactLength.message
      }), n.dirty());
    }
    if (o.minLength !== null && s.data.length < o.minLength.value && (be(s, {
      code: fe.too_small,
      minimum: o.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: o.minLength.message
    }), n.dirty()), o.maxLength !== null && s.data.length > o.maxLength.value && (be(s, {
      code: fe.too_big,
      maximum: o.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: o.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((a, i) => o.type._parseAsync(new bs(s, a, s.path, i)))).then((a) => Ft.mergeArray(n, a));
    const r = [...s.data].map((a, i) => o.type._parseSync(new bs(s, a, s.path, i)));
    return Ft.mergeArray(n, r);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new vs({
      ...this._def,
      minLength: { value: t, message: Ee.toString(s) }
    });
  }
  max(t, s) {
    return new vs({
      ...this._def,
      maxLength: { value: t, message: Ee.toString(s) }
    });
  }
  length(t, s) {
    return new vs({
      ...this._def,
      exactLength: { value: t, message: Ee.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
vs.create = (e, t) => new vs({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: Fe.ZodArray,
  ...Je(t)
});
function wn(e) {
  if (e instanceof kt) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = qs.create(wn(n));
    }
    return new kt({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof vs ? new vs({
    ...e._def,
    type: wn(e.element)
  }) : e instanceof qs ? qs.create(wn(e.unwrap())) : e instanceof On ? On.create(wn(e.unwrap())) : e instanceof dn ? dn.create(e.items.map((t) => wn(t))) : e;
}
class kt extends nt {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = at.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== Ce.object) {
      const u = this._getOrReturnCtx(t);
      return be(u, {
        code: fe.invalid_type,
        expected: Ce.object,
        received: u.parsedType
      }), We;
    }
    const { status: n, ctx: o } = this._processInputParams(t), { shape: r, keys: a } = this._getCached(), i = [];
    if (!(this._def.catchall instanceof Ks && this._def.unknownKeys === "strip"))
      for (const u in o.data)
        a.includes(u) || i.push(u);
    const l = [];
    for (const u of a) {
      const d = r[u], f = o.data[u];
      l.push({
        key: { status: "valid", value: u },
        value: d._parse(new bs(o, f, o.path, u)),
        alwaysSet: u in o.data
      });
    }
    if (this._def.catchall instanceof Ks) {
      const u = this._def.unknownKeys;
      if (u === "passthrough")
        for (const d of i)
          l.push({
            key: { status: "valid", value: d },
            value: { status: "valid", value: o.data[d] }
          });
      else if (u === "strict")
        i.length > 0 && (be(o, {
          code: fe.unrecognized_keys,
          keys: i
        }), n.dirty());
      else if (u !== "strip") throw new Error("Internal ZodObject error: invalid unknownKeys value.");
    } else {
      const u = this._def.catchall;
      for (const d of i) {
        const f = o.data[d];
        l.push({
          key: { status: "valid", value: d },
          value: u._parse(
            new bs(o, f, o.path, d)
            //, ctx.child(key), value, getParsedType(value)
          ),
          alwaysSet: d in o.data
        });
      }
    }
    return o.common.async ? Promise.resolve().then(async () => {
      const u = [];
      for (const d of l) {
        const f = await d.key, b = await d.value;
        u.push({
          key: f,
          value: b,
          alwaysSet: d.alwaysSet
        });
      }
      return u;
    }).then((u) => Ft.mergeObjectSync(n, u)) : Ft.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return Ee.errToObj, new kt({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const o = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: Ee.errToObj(t).message ?? o
          } : {
            message: o
          };
        }
      } : {}
    });
  }
  strip() {
    return new kt({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new kt({
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
    return new kt({
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
    return new kt({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: Fe.ZodObject
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
    return new kt({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of at.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new kt({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of at.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new kt({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return wn(this);
  }
  partial(t) {
    const s = {};
    for (const n of at.objectKeys(this.shape)) {
      const o = this.shape[n];
      t && !t[n] ? s[n] = o : s[n] = o.optional();
    }
    return new kt({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of at.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let r = this.shape[n];
        for (; r instanceof qs; )
          r = r._def.innerType;
        s[n] = r;
      }
    return new kt({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return Wu(at.objectKeys(this.shape));
  }
}
kt.create = (e, t) => new kt({
  shape: () => e,
  unknownKeys: "strip",
  catchall: Ks.create(),
  typeName: Fe.ZodObject,
  ...Je(t)
});
kt.strictCreate = (e, t) => new kt({
  shape: () => e,
  unknownKeys: "strict",
  catchall: Ks.create(),
  typeName: Fe.ZodObject,
  ...Je(t)
});
kt.lazycreate = (e, t) => new kt({
  shape: e,
  unknownKeys: "strip",
  catchall: Ks.create(),
  typeName: Fe.ZodObject,
  ...Je(t)
});
class rr extends nt {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function o(r) {
      for (const i of r)
        if (i.result.status === "valid")
          return i.result;
      for (const i of r)
        if (i.result.status === "dirty")
          return s.common.issues.push(...i.ctx.common.issues), i.result;
      const a = r.map((i) => new Ps(i.ctx.common.issues));
      return be(s, {
        code: fe.invalid_union,
        unionErrors: a
      }), We;
    }
    if (s.common.async)
      return Promise.all(n.map(async (r) => {
        const a = {
          ...s,
          common: {
            ...s.common,
            issues: []
          },
          parent: null
        };
        return {
          result: await r._parseAsync({
            data: s.data,
            path: s.path,
            parent: a
          }),
          ctx: a
        };
      })).then(o);
    {
      let r;
      const a = [];
      for (const l of n) {
        const u = {
          ...s,
          common: {
            ...s.common,
            issues: []
          },
          parent: null
        }, d = l._parseSync({
          data: s.data,
          path: s.path,
          parent: u
        });
        if (d.status === "valid")
          return d;
        d.status === "dirty" && !r && (r = { result: d, ctx: u }), u.common.issues.length && a.push(u.common.issues);
      }
      if (r)
        return s.common.issues.push(...r.ctx.common.issues), r.result;
      const i = a.map((l) => new Ps(l));
      return be(s, {
        code: fe.invalid_union,
        unionErrors: i
      }), We;
    }
  }
  get options() {
    return this._def.options;
  }
}
rr.create = (e, t) => new rr({
  options: e,
  typeName: Fe.ZodUnion,
  ...Je(t)
});
function Pa(e, t) {
  const s = Bs(e), n = Bs(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === Ce.object && n === Ce.object) {
    const o = at.objectKeys(t), r = at.objectKeys(e).filter((i) => o.indexOf(i) !== -1), a = { ...e, ...t };
    for (const i of r) {
      const l = Pa(e[i], t[i]);
      if (!l.valid)
        return { valid: !1 };
      a[i] = l.data;
    }
    return { valid: !0, data: a };
  } else if (s === Ce.array && n === Ce.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const o = [];
    for (let r = 0; r < e.length; r++) {
      const a = e[r], i = t[r], l = Pa(a, i);
      if (!l.valid)
        return { valid: !1 };
      o.push(l.data);
    }
    return { valid: !0, data: o };
  } else return s === Ce.date && n === Ce.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class ar extends nt {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), o = (r, a) => {
      if (hl(r) || hl(a))
        return We;
      const i = Pa(r.value, a.value);
      return i.valid ? ((yl(r) || yl(a)) && s.dirty(), { status: s.value, value: i.data }) : (be(n, {
        code: fe.invalid_intersection_types
      }), We);
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
    ]).then(([r, a]) => o(r, a)) : o(this._def.left._parseSync({
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
  typeName: Fe.ZodIntersection,
  ...Je(s)
});
class dn extends nt {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Ce.array)
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.array,
        received: n.parsedType
      }), We;
    if (n.data.length < this._def.items.length)
      return be(n, {
        code: fe.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), We;
    !this._def.rest && n.data.length > this._def.items.length && (be(n, {
      code: fe.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const r = [...n.data].map((a, i) => {
      const l = this._def.items[i] || this._def.rest;
      return l ? l._parse(new bs(n, a, n.path, i)) : null;
    }).filter((a) => !!a);
    return n.common.async ? Promise.all(r).then((a) => Ft.mergeArray(s, a)) : Ft.mergeArray(s, r);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new dn({
      ...this._def,
      rest: t
    });
  }
}
dn.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new dn({
    items: e,
    typeName: Fe.ZodTuple,
    rest: null,
    ...Je(t)
  });
};
class ir extends nt {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Ce.object)
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.object,
        received: n.parsedType
      }), We;
    const o = [], r = this._def.keyType, a = this._def.valueType;
    for (const i in n.data)
      o.push({
        key: r._parse(new bs(n, i, n.path, i)),
        value: a._parse(new bs(n, n.data[i], n.path, i)),
        alwaysSet: i in n.data
      });
    return n.common.async ? Ft.mergeObjectAsync(s, o) : Ft.mergeObjectSync(s, o);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof nt ? new ir({
      keyType: t,
      valueType: s,
      typeName: Fe.ZodRecord,
      ...Je(n)
    }) : new ir({
      keyType: Rs.create(),
      valueType: t,
      typeName: Fe.ZodRecord,
      ...Je(s)
    });
  }
}
class $l extends nt {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Ce.map)
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.map,
        received: n.parsedType
      }), We;
    const o = this._def.keyType, r = this._def.valueType, a = [...n.data.entries()].map(([i, l], u) => ({
      key: o._parse(new bs(n, i, n.path, [u, "key"])),
      value: r._parse(new bs(n, l, n.path, [u, "value"]))
    }));
    if (n.common.async) {
      const i = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of a) {
          const u = await l.key, d = await l.value;
          if (u.status === "aborted" || d.status === "aborted")
            return We;
          (u.status === "dirty" || d.status === "dirty") && s.dirty(), i.set(u.value, d.value);
        }
        return { status: s.value, value: i };
      });
    } else {
      const i = /* @__PURE__ */ new Map();
      for (const l of a) {
        const u = l.key, d = l.value;
        if (u.status === "aborted" || d.status === "aborted")
          return We;
        (u.status === "dirty" || d.status === "dirty") && s.dirty(), i.set(u.value, d.value);
      }
      return { status: s.value, value: i };
    }
  }
}
$l.create = (e, t, s) => new $l({
  valueType: t,
  keyType: e,
  typeName: Fe.ZodMap,
  ...Je(s)
});
class go extends nt {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== Ce.set)
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.set,
        received: n.parsedType
      }), We;
    const o = this._def;
    o.minSize !== null && n.data.size < o.minSize.value && (be(n, {
      code: fe.too_small,
      minimum: o.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: o.minSize.message
    }), s.dirty()), o.maxSize !== null && n.data.size > o.maxSize.value && (be(n, {
      code: fe.too_big,
      maximum: o.maxSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: o.maxSize.message
    }), s.dirty());
    const r = this._def.valueType;
    function a(l) {
      const u = /* @__PURE__ */ new Set();
      for (const d of l) {
        if (d.status === "aborted")
          return We;
        d.status === "dirty" && s.dirty(), u.add(d.value);
      }
      return { status: s.value, value: u };
    }
    const i = [...n.data.values()].map((l, u) => r._parse(new bs(n, l, n.path, u)));
    return n.common.async ? Promise.all(i).then((l) => a(l)) : a(i);
  }
  min(t, s) {
    return new go({
      ...this._def,
      minSize: { value: t, message: Ee.toString(s) }
    });
  }
  max(t, s) {
    return new go({
      ...this._def,
      maxSize: { value: t, message: Ee.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
go.create = (e, t) => new go({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: Fe.ZodSet,
  ...Je(t)
});
class Il extends nt {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
Il.create = (e, t) => new Il({
  getter: e,
  typeName: Fe.ZodLazy,
  ...Je(t)
});
class Rl extends nt {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return be(s, {
        received: s.data,
        code: fe.invalid_literal,
        expected: this._def.value
      }), We;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Rl.create = (e, t) => new Rl({
  value: e,
  typeName: Fe.ZodLiteral,
  ...Je(t)
});
function Wu(e, t) {
  return new An({
    values: e,
    typeName: Fe.ZodEnum,
    ...Je(t)
  });
}
class An extends nt {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return be(s, {
        expected: at.joinValues(n),
        received: s.parsedType,
        code: fe.invalid_type
      }), We;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return be(s, {
        received: s.data,
        code: fe.invalid_enum_value,
        options: n
      }), We;
    }
    return Xt(t.data);
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
    return An.create(t, {
      ...this._def,
      ...s
    });
  }
  exclude(t, s = this._def) {
    return An.create(this.options.filter((n) => !t.includes(n)), {
      ...this._def,
      ...s
    });
  }
}
An.create = Wu;
class Al extends nt {
  _parse(t) {
    const s = at.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== Ce.string && n.parsedType !== Ce.number) {
      const o = at.objectValues(s);
      return be(n, {
        expected: at.joinValues(o),
        received: n.parsedType,
        code: fe.invalid_type
      }), We;
    }
    if (this._cache || (this._cache = new Set(at.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const o = at.objectValues(s);
      return be(n, {
        received: n.data,
        code: fe.invalid_enum_value,
        options: o
      }), We;
    }
    return Xt(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
Al.create = (e, t) => new Al({
  values: e,
  typeName: Fe.ZodNativeEnum,
  ...Je(t)
});
class lr extends nt {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== Ce.promise && s.common.async === !1)
      return be(s, {
        code: fe.invalid_type,
        expected: Ce.promise,
        received: s.parsedType
      }), We;
    const n = s.parsedType === Ce.promise ? s.data : Promise.resolve(s.data);
    return Xt(n.then((o) => this._def.type.parseAsync(o, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
lr.create = (e, t) => new lr({
  type: e,
  typeName: Fe.ZodPromise,
  ...Je(t)
});
class En extends nt {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === Fe.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), o = this._def.effect || null, r = {
      addIssue: (a) => {
        be(n, a), a.fatal ? s.abort() : s.dirty();
      },
      get path() {
        return n.path;
      }
    };
    if (r.addIssue = r.addIssue.bind(r), o.type === "preprocess") {
      const a = o.transform(n.data, r);
      if (n.common.async)
        return Promise.resolve(a).then(async (i) => {
          if (s.value === "aborted")
            return We;
          const l = await this._def.schema._parseAsync({
            data: i,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? We : l.status === "dirty" || s.value === "dirty" ? Zn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return We;
        const i = this._def.schema._parseSync({
          data: a,
          path: n.path,
          parent: n
        });
        return i.status === "aborted" ? We : i.status === "dirty" || s.value === "dirty" ? Zn(i.value) : i;
      }
    }
    if (o.type === "refinement") {
      const a = (i) => {
        const l = o.refinement(i, r);
        if (n.common.async)
          return Promise.resolve(l);
        if (l instanceof Promise)
          throw new Error("Async refinement encountered during synchronous parse operation. Use .parseAsync instead.");
        return i;
      };
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return i.status === "aborted" ? We : (i.status === "dirty" && s.dirty(), a(i.value), { status: s.value, value: i.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => i.status === "aborted" ? We : (i.status === "dirty" && s.dirty(), a(i.value).then(() => ({ status: s.value, value: i.value }))));
    }
    if (o.type === "transform")
      if (n.common.async === !1) {
        const a = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!In(a))
          return We;
        const i = o.transform(a.value, r);
        if (i instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: i };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => In(a) ? Promise.resolve(o.transform(a.value, r)).then((i) => ({
          status: s.value,
          value: i
        })) : We);
    at.assertNever(o);
  }
}
En.create = (e, t, s) => new En({
  schema: e,
  typeName: Fe.ZodEffects,
  effect: t,
  ...Je(s)
});
En.createWithPreprocess = (e, t, s) => new En({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: Fe.ZodEffects,
  ...Je(s)
});
class qs extends nt {
  _parse(t) {
    return this._getType(t) === Ce.undefined ? Xt(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
qs.create = (e, t) => new qs({
  innerType: e,
  typeName: Fe.ZodOptional,
  ...Je(t)
});
class On extends nt {
  _parse(t) {
    return this._getType(t) === Ce.null ? Xt(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
On.create = (e, t) => new On({
  innerType: e,
  typeName: Fe.ZodNullable,
  ...Je(t)
});
class Ma extends nt {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === Ce.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
Ma.create = (e, t) => new Ma({
  innerType: e,
  typeName: Fe.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...Je(t)
});
class Na extends nt {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = {
      ...s,
      common: {
        ...s.common,
        issues: []
      }
    }, o = this._def.innerType._parse({
      data: n.data,
      path: n.path,
      parent: {
        ...n
      }
    });
    return nr(o) ? o.then((r) => ({
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new Ps(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new Ps(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
Na.create = (e, t) => new Na({
  innerType: e,
  typeName: Fe.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...Je(t)
});
class El extends nt {
  _parse(t) {
    if (this._getType(t) !== Ce.nan) {
      const n = this._getOrReturnCtx(t);
      return be(n, {
        code: fe.invalid_type,
        expected: Ce.nan,
        received: n.parsedType
      }), We;
    }
    return { status: "valid", value: t.data };
  }
}
El.create = (e) => new El({
  typeName: Fe.ZodNaN,
  ...Je(e)
});
class mg extends nt {
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
class ii extends nt {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const r = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return r.status === "aborted" ? We : r.status === "dirty" ? (s.dirty(), Zn(r.value)) : this._def.out._parseAsync({
          data: r.value,
          path: n.path,
          parent: n
        });
      })();
    {
      const o = this._def.in._parseSync({
        data: n.data,
        path: n.path,
        parent: n
      });
      return o.status === "aborted" ? We : o.status === "dirty" ? (s.dirty(), {
        status: "dirty",
        value: o.value
      }) : this._def.out._parseSync({
        data: o.value,
        path: n.path,
        parent: n
      });
    }
  }
  static create(t, s) {
    return new ii({
      in: t,
      out: s,
      typeName: Fe.ZodPipeline
    });
  }
}
class za extends nt {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (o) => (In(o) && (o.value = Object.freeze(o.value)), o);
    return nr(s) ? s.then((o) => n(o)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
za.create = (e, t) => new za({
  innerType: e,
  typeName: Fe.ZodReadonly,
  ...Je(t)
});
var Fe;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(Fe || (Fe = {}));
const Rt = Rs.create, ea = Rn.create, Po = Ta.create;
Ks.create;
const Gu = vs.create, li = kt.create;
rr.create;
ar.create;
dn.create;
const pg = ir.create, Da = An.create;
lr.create;
qs.create;
On.create;
const vg = "comfymodal.studio.vue.";
function gg() {
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
function hg() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return gg();
}
function As(e, t, s, n) {
  const o = vg + e, r = hg();
  return {
    key: o,
    read() {
      let a = null;
      try {
        a = r.getItem(o);
      } catch {
        return t;
      }
      if (a === null) return t;
      let i;
      try {
        i = JSON.parse(a);
      } catch {
        return t;
      }
      if (!s) return i ?? t;
      const l = s.safeParse(i);
      return l.success ? l.data : t;
    },
    write(a) {
      try {
        r.setItem(o, JSON.stringify(a));
      } catch {
      }
    },
    remove() {
      try {
        r.removeItem(o);
      } catch {
      }
    }
  };
}
const yg = "/comfymodal";
class bg extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function wg(e, t) {
  if (typeof e == "string" && e.trim() !== "") return e;
  if (e && typeof e == "object") {
    const s = e;
    for (const o of ["message", "error"]) {
      const r = s[o];
      if (typeof r == "string" && r.trim() !== "") return r;
    }
    const n = s.detail;
    if (typeof n == "string" && n.trim() !== "") return n;
    if (n && typeof n == "object") {
      const o = n;
      for (const r of ["message", "code"]) {
        const a = o[r];
        if (typeof a == "string" && a.trim() !== "") return a;
      }
    }
  }
  return t;
}
function _g(e, t) {
  if (t === void 0)
    return e ? { signal: e, cleanup: () => {
    } } : { signal: void 0, cleanup: () => {
    } };
  const s = new AbortController(), n = setTimeout(
    () => s.abort(new DOMException("Request timed out", "TimeoutError")),
    t
  ), o = () => s.abort(e?.reason);
  return e && (e.aborted ? s.abort(e.reason) : e.addEventListener("abort", o, { once: !0 })), {
    signal: s.signal,
    cleanup: () => {
      clearTimeout(n), e?.removeEventListener("abort", o);
    }
  };
}
async function ce(e, t = {}, s = fetch) {
  const {
    method: n = "GET",
    body: o,
    signal: r,
    timeoutMs: a,
    headers: i = {}
  } = t, { signal: l, cleanup: u } = _g(r, a);
  try {
    if (l && l.aborted) throw l.reason;
    const d = await s(yg + e, {
      method: n,
      headers: {
        "Content-Type": "application/json",
        ...i
      },
      body: o === void 0 ? void 0 : JSON.stringify(o),
      signal: l
    }), f = await d.text();
    let b = null;
    if (f !== "")
      try {
        b = JSON.parse(f);
      } catch {
        b = f;
      }
    if (!d.ok)
      throw new bg(
        d.status,
        wg(b, `Request failed with status ${d.status}`),
        b
      );
    return b;
  } finally {
    u();
  }
}
const xg = li({ value: Rt(), label: Rt() }).passthrough(), kg = li({
  gpu: Rt().default(""),
  default_gpu: Rt().default(""),
  available_gpus: Gu(xg).default([]),
  persisted_gpu: Rt().default(""),
  output_format: Rt().default("original"),
  quality: ea().default(75),
  webp_lossless_compression: Rt().default("balanced"),
  auto_save_local: Po().default(!1),
  save_folder: Rt().default(""),
  save_metadata_sidecar: Po().default(!0),
  preview_default: Da(["off", "on"]).default("off"),
  preview_codec: Rt().default("webp"),
  preview_quality: ea().default(70),
  data_saver_default: Da(["off", "on"]).default("off"),
  data_saver_codec: Rt().default("webp"),
  data_saver_quality: ea().default(70),
  execution_mode: Rt().default("v2"),
  execution_mode_source: Rt().default(""),
  execution_mode_locked: Po().default(!1),
  engine_migration_notice: Rt().nullable().default(null),
  skip_plan_validation: Po().default(!1),
  golden_gpu_order: pg(Rt()).default({})
}).passthrough(), Sg = li({ status: Rt().optional(), level: Rt().default("off"), effective: Rt().default("off") }).passthrough();
async function Mo() {
  return kg.parse(await ce("/config"));
}
async function Cg(e) {
  return ce("/config", { method: "POST", body: e });
}
async function Ol() {
  return Sg.parse(await ce("/profile/level"));
}
async function $g(e) {
  return ce("/profile/level", { method: "POST", body: { level: e } });
}
async function Ig() {
  return ce("/studio/golden/profiles");
}
async function Rg(e, t) {
  return ce("/studio/golden/gpu-order", { method: "POST", body: { profile: e, order: t } });
}
async function Ag(e) {
  return ce("/studio/golden/deploy", { method: "POST", body: { profile: e } });
}
async function Tl(e) {
  return ce(`/studio/golden/deploy?profile=${encodeURIComponent(e)}`);
}
const Ln = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function Pl(e) {
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
    localStorage.setItem(Ln.outputFormat, s.output_format), localStorage.setItem(Ln.quality, String(s.quality)), localStorage.setItem(Ln.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(Ln.saveFolder, s.save_folder), localStorage.setItem(Ln.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const qu = "comfymodal-studio";
function Ar(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(qu), s = (n) => {
    const o = n.data?.kind;
    (o === "settings" || o === "workspace" || o === "history" || o === "workflows") && e(o);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function mt(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(qu);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
function Tn() {
  let e = 0, t = null;
  return {
    run: (n) => {
      e += 1;
      const o = e, r = t;
      r && (r.superseded = !0, r.controller.abort());
      const a = new AbortController(), i = { controller: a, superseded: !1 };
      let l;
      const u = new Promise((b) => {
        l = () => b({ stale: !0 });
      }), d = () => l();
      a.signal.addEventListener("abort", d, { once: !0 }), t = i;
      const f = () => {
        a.signal.removeEventListener("abort", d), t === i && (t = null);
      };
      return (async () => {
        try {
          return await Promise.race([
            n(a.signal).then((b) => o !== e || i.superseded || a.signal.aborted ? { stale: !0 } : { stale: !1, value: b }),
            u
          ]);
        } catch (b) {
          if (i.superseded || o !== e || a.signal.aborted)
            return { stale: !0 };
          throw b;
        } finally {
          f();
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
function Eg(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function Og(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const o = setTimeout(() => {
      t.removeEventListener("abort", r), s();
    }, e), r = () => {
      clearTimeout(o), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", r, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function Kn(e) {
  const { intervalMs: t, signal: s, run: n, done: o, onAttempt: r } = e;
  let a = 0;
  for (; ; ) {
    Eg(s), a += 1, r && r(a);
    const i = await n(s, a);
    if (o(i)) return i;
    await Og(t, s);
  }
}
const Tg = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function ta(e) {
  return Tg.has(e);
}
let Ml = 0;
function Pg() {
  return Ml += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${Ml}`;
}
const Gt = /* @__PURE__ */ Mn("studio-operations", () => {
  const e = /* @__PURE__ */ I(/* @__PURE__ */ new Map()), t = ge(() => [...e.value.values()]), s = ge(
    () => t.value.filter((b) => b.status === "pending" || b.status === "running")
  );
  function n(b) {
    return e.value.get(b);
  }
  function o(b) {
    const h = Date.now(), O = Pg(), x = b.status === "pending" ? "pending" : "running";
    return e.value.set(O, {
      id: O,
      kind: b.kind,
      label: b.label,
      status: x,
      progress: b.progress,
      message: b.message,
      startedAt: h,
      finishedAt: void 0,
      workspaceId: b.workspaceId
    }), O;
  }
  function r(b, h) {
    const O = e.value.get(b);
    if (!O) return;
    const { status: x, ...C } = h, T = { ...O, ...C };
    !ta(O.status) && x !== void 0 && !ta(x) && (T.status = x), e.value.set(b, T);
  }
  function a(b, h, O) {
    const x = e.value.get(b);
    !x || ta(x.status) || e.value.set(b, {
      ...x,
      status: h,
      message: O === void 0 ? x.message : O,
      finishedAt: Date.now()
    });
  }
  function i(b, h) {
    a(b, "completed", h);
  }
  function l(b, h) {
    a(b, "failed", h);
  }
  function u(b, h) {
    a(b, "canceled", h);
  }
  function d(b) {
    e.value.delete(b);
  }
  function f() {
    e.value.clear();
  }
  return {
    byId: e,
    all: t,
    active: s,
    get: n,
    start: o,
    patch: r,
    finish: i,
    fail: l,
    cancel: u,
    remove: d,
    clear: f
  };
}), Mg = Da(["comfortable", "compact"]), sa = As(
  "shell.density",
  "comfortable",
  Mg
), Ng = [
  "comfymodal_gpu",
  "comfymodal_output_format",
  "comfymodal_quality",
  "comfymodal_webp_lossless_compression",
  "comfymodal_auto_save_local",
  "comfymodal_save_folder",
  "comfymodal_save_metadata_sidecar",
  "comfymodal_preview_default",
  "comfymodal_preview_codec",
  "comfymodal_preview_quality",
  "comfymodal_data_saver_default",
  "comfymodal_data_saver_codec",
  "comfymodal_data_saver_quality",
  "comfymodal-studio-history-columns",
  "comfymodal_heavy_tracing",
  "comfymodal.studio.golden.profile.v1",
  "comfymodal-studio-panel-width",
  "comfymodal.studio.playground.carousel-cleared.v1",
  "comfymodal_remote_inventory_refresh_interval_s",
  "comfymodal_skip_plan_validation"
], Hu = [
  "generation",
  "outputs",
  "accounts",
  "interface",
  "advanced"
];
function zg(e) {
  try {
    return localStorage.getItem(e);
  } catch {
    return null;
  }
}
function Un(e, t) {
  try {
    localStorage.setItem(e, t);
  } catch {
  }
}
function Vn(e) {
  for (const t of e)
    try {
      localStorage.removeItem(t);
    } catch {
    }
}
const So = /* @__PURE__ */ Mn("studio-settings", () => {
  const e = /* @__PURE__ */ I("generation"), t = /* @__PURE__ */ I(sa.read()), s = /* @__PURE__ */ I(null), n = /* @__PURE__ */ I("off"), o = /* @__PURE__ */ I("off"), r = /* @__PURE__ */ I(!1), a = /* @__PURE__ */ I(!1), i = /* @__PURE__ */ I(null), l = /* @__PURE__ */ I(!1), u = /* @__PURE__ */ I([]), d = /* @__PURE__ */ I(null), f = /* @__PURE__ */ I(null), b = /* @__PURE__ */ I(!1);
  let h = !1, O = null;
  const x = As("golden.profile", "", Rt()), C = As(
    "golden.favorites",
    [],
    Gu(Rt())
  ), T = As("history.columns", "6"), A = As("inventory.interval", "300"), z = /* @__PURE__ */ I(x.read()), R = /* @__PURE__ */ I(C.read()), J = /* @__PURE__ */ I(T.read()), $e = /* @__PURE__ */ I(A.read()), ne = ge(() => s.value?.gpu ?? ""), j = ge(() => {
    const B = s.value?.golden_gpu_order;
    return B && typeof B == "object" ? B : {};
  });
  async function re() {
    r.value = !0, i.value = null;
    try {
      const [B, q] = await Promise.all([Mo(), Ol()]);
      s.value = B, n.value = q.level, o.value = q.effective || q.level, Pl(B), l.value = !0;
    } catch (B) {
      throw i.value = B instanceof Error ? B.message : "Could not load Settings", B;
    } finally {
      r.value = !1, h && (h = !1, re());
    }
  }
  async function ve(B) {
    a.value = !0, i.value = null;
    try {
      await Cg(B);
      const q = await Mo();
      s.value = q, Pl(q), mt("settings");
    } catch (q) {
      try {
        s.value = await Mo();
      } catch {
      }
      throw i.value = q instanceof Error ? q.message : "Could not save Settings", q;
    } finally {
      a.value = !1;
    }
  }
  async function Me(B) {
    const q = n.value;
    n.value = B, Un("comfymodal_heavy_tracing", B);
    try {
      await $g(B);
      const me = await Ol();
      o.value = me.effective || me.level, mt("settings");
    } catch (me) {
      throw n.value = q, Un("comfymodal_heavy_tracing", q), me;
    }
  }
  async function Ie(B) {
    const q = zg("comfymodal_skip_plan_validation");
    Un("comfymodal_skip_plan_validation", B ? "1" : "0");
    try {
      await ve({ skip_plan_validation: B });
    } catch (me) {
      if (q === null)
        try {
          localStorage.removeItem("comfymodal_skip_plan_validation");
        } catch {
        }
      else
        Un("comfymodal_skip_plan_validation", q);
      throw me;
    }
  }
  async function Oe() {
    d.value = null;
    try {
      const B = await Ig();
      if (!B || B.status !== "ok" || !Array.isArray(B.profiles))
        throw new Error(
          B && B.message || "invalid catalog response"
        );
      const q = new Set(
        B.profiles.filter((k) => k && typeof k.name == "string").map((k) => k.name)
      );
      u.value = B.profiles.filter((k) => k && q.has(k.name));
      const me = s.value?.golden_profile, v = typeof me == "string" ? me : "";
      if (q.has(v))
        z.value = v;
      else if (!q.has(z.value)) {
        const k = typeof B.defaultProfile == "string" && q.has(B.defaultProfile) ? B.defaultProfile : "";
        z.value = k;
      }
      x.write(z.value), z.value && (f.value = await Tl(
        z.value
      ));
    } catch (B) {
      throw d.value = B instanceof Error ? B.message : "Could not load Golden profiles", B;
    }
  }
  function Ye(B) {
    z.value = B, x.write(B);
  }
  function ae(B) {
    const q = R.value.includes(B) ? R.value.filter((me) => me !== B) : [...R.value, B];
    R.value = q, C.write(q);
  }
  async function _(B, q) {
    await Rg(B, q);
    const me = await Mo();
    s.value = me, mt("settings");
  }
  async function S(B) {
    const q = Gt(), me = q.start({ kind: "deploy", label: `Deploy Golden ${B}` });
    b.value = !0;
    try {
      await Ag(B), await Kn({
        intervalMs: 2e3,
        run: async () => {
          const v = await Tl(B), k = String(v?.state ?? "unknown");
          return q.patch(me, { message: `Golden deploy: ${k}` }), v;
        },
        done: (v) => v?.state === "done" || v?.state === "failed"
      }).then((v) => {
        if (v?.state === "failed")
          throw new Error(String(v.output || v.message || "Golden deploy failed"));
        f.value = v;
      }), q.finish(me, "Golden deploy finished"), await Oe();
    } catch (v) {
      throw q.fail(
        me,
        v instanceof Error ? v.message : "Golden deploy failed"
      ), v;
    } finally {
      b.value = !1;
    }
    return me;
  }
  function ue(B) {
    J.value = B, T.write(B);
  }
  function Ue(B) {
    $e.value = B, A.write(B);
  }
  async function ie(B) {
    if (B === "generation") {
      Vn(["comfymodal_gpu", "comfymodal_preview_default", "comfymodal_preview_codec", "comfymodal_preview_quality", "comfymodal_data_saver_default", "comfymodal_data_saver_codec", "comfymodal_data_saver_quality"]);
      const q = s.value?.default_gpu || "rtx-pro-6000";
      await ve({ gpu: q, golden_profile: null }), Ye("");
    } else B === "outputs" ? (Vn(["comfymodal_output_format", "comfymodal_quality", "comfymodal_webp_lossless_compression", "comfymodal_auto_save_local", "comfymodal_save_folder", "comfymodal_save_metadata_sidecar"]), await ve({
      output_format: "original",
      quality: 75,
      webp_lossless_compression: "balanced",
      auto_save_local: !1,
      save_metadata_sidecar: !0
    })) : B === "interface" ? (Vn(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1", "comfymodal_remote_inventory_refresh_interval_s", "comfymodal-studio-history-columns"]), ue("6"), Ue("300")) : B === "advanced" && (Vn(["comfymodal_heavy_tracing", "comfymodal_skip_plan_validation"]), await Me("off").catch(() => {
    }), await ve({ skip_plan_validation: !1 }).catch(() => {
    }));
    mt("settings");
  }
  async function tt() {
    Vn(Ng), Ye(""), R.value = [], C.write([]), ue("6"), Ue("300");
    const B = s.value?.default_gpu || "rtx-pro-6000";
    await ve({ gpu: B, golden_profile: null }).catch(() => {
    }), await Me("off").catch(() => {
    }), await ve({ skip_plan_validation: !1 }).catch(() => {
    }), await re().catch(() => {
    });
  }
  async function De() {
    O || (O = Ar((B) => {
      if (B === "settings") {
        if (r.value) {
          h = !0;
          return;
        }
        re();
      }
    })), l.value || await re(), Un("comfymodal_heavy_tracing", n.value);
  }
  function bt(B) {
    Hu.includes(B) && (e.value = B);
  }
  function ke(B) {
    t.value = B, sa.write(B);
  }
  function $() {
    e.value = "generation", t.value = "comfortable", sa.write("comfortable");
  }
  const F = Tn();
  async function U(B) {
    const q = await F.run(B);
    return q.stale ? null : q.value;
  }
  return {
    activeSection: e,
    density: t,
    config: s,
    profileLevel: n,
    effectiveProfileLevel: o,
    loading: r,
    saving: a,
    error: i,
    bootstrapped: l,
    goldenProfiles: u,
    goldenError: d,
    goldenDeployState: f,
    goldenDeploying: b,
    selectedGoldenProfile: z,
    favoriteGoldenProfiles: R,
    columnsPreference: J,
    refreshIntervalPreference: $e,
    gpu: ne,
    goldenGpuOrder: j,
    outputPreferences: ge(() => s.value ? {
      output_format: s.value.output_format,
      quality: s.value.quality,
      webp_lossless_compression: s.value.webp_lossless_compression,
      auto_save_local: s.value.auto_save_local,
      save_folder: s.value.save_folder,
      save_metadata_sidecar: s.value.save_metadata_sidecar,
      data_saver_default: s.value.data_saver_default,
      data_saver_codec: s.value.data_saver_codec,
      data_saver_quality: s.value.data_saver_quality
    } : null),
    load: re,
    initialize: De,
    save: ve,
    setProfile: Me,
    setSkipPlanValidation: Ie,
    loadGolden: Oe,
    selectGoldenProfile: Ye,
    toggleGoldenFavorite: ae,
    setGoldenGpuOrder: _,
    deployGoldenProfile: S,
    setHistoryColumns: ue,
    setInventoryInterval: Ue,
    resetSection: ie,
    resetAll: tt,
    loadSubresource: U,
    setSection: bt,
    setDensity: ke,
    reset: $
  };
});
function na(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const o = String(n.id ?? "");
    return { id: o, label: String(n.label ?? o), isActive: o !== "" && o === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function Zu(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function Dg(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function jg() {
  return ce("/workspaces");
}
async function Lg(e) {
  return ce("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function Nl() {
  return Zu(await ce("/deploy/status"));
}
async function Ug() {
  return ce("/deploy", { method: "POST" });
}
async function Vg() {
  return ce("/deploy/log");
}
async function Fg(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return ce(`/studio/inventory/refresh${t}`);
}
async function Bg(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return ce(`/studio/models${s}`);
}
async function Wg(e = !1) {
  return ce("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function Gg() {
  return ce("/studio/custom-nodes");
}
async function qg(e, t) {
  return ce(`/studio/models/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function Hg() {
  return ce("/studio/custom-nodes/refresh", { method: "POST" });
}
async function Zg(e) {
  return ce("/workspaces", { method: "POST", body: e });
}
async function Kg(e) {
  return ce("/workspaces/swap", { method: "POST", body: e });
}
async function Qg(e) {
  return ce(`/workspaces/swap/${encodeURIComponent(e)}`);
}
function Jg(e, t) {
  return { workspace_id: e, confirm: !0, selected_keys: t.slice() };
}
function zl(e) {
  const t = String(e && e.phase || "");
  if (t === "downloading_models") {
    const s = String(e && e.download_message || ""), n = Number(e && e.download_completed || 0), o = Number(e && e.download_total || 0) + Number(e && e.download_skipped || 0);
    return s || `Preparing downloads… ${n}/${o}`;
  }
  return t === "syncing_custom_nodes" ? String(e && e.sync_message || "Syncing custom nodes to Modal…") : t === "deploying" ? String(e && e.deploy_message || "Deploying workspace…") : t ? `Phase: ${t.replace(/_/g, " ")}` : "";
}
async function Yg() {
  return ce("/studio/custom-nodes/sync-status");
}
async function Xg() {
  return ce("/studio/custom-nodes/sync", { method: "POST" });
}
async function eh() {
  return ce("/studio/custom-nodes/sync/rebuild-dependencies", { method: "POST" });
}
async function th(e) {
  return ce(`/studio/custom-nodes/sync/status/${encodeURIComponent(e)}`);
}
async function sh(e) {
  return ce("/model/install", { method: "POST", body: e });
}
function nh(e) {
  const s = String(e || "").split("?")[0].split("#")[0].split("/").filter(Boolean).pop() || "";
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}
async function oh(e) {
  return ce(`/download/status/${encodeURIComponent(e || "")}`);
}
async function rh(e) {
  return ce("/studio/models/install-request", { method: "POST", body: e });
}
async function ah(e) {
  return ce("/studio/custom-nodes/install-request", { method: "POST", body: e });
}
async function ih() {
  return ce("/manifest/repair/scan", { method: "POST" });
}
async function lh(e) {
  return ce("/manifest/repair/apply", { method: "POST", body: { updates: e } });
}
async function ch(e, t) {
  return ce("/manifest/repair/delete-placeholder", { method: "POST", body: { folder: e, filename: t } });
}
async function uh() {
  return ce("/auth/status");
}
async function Dl(e) {
  return ce(e === "civitai" ? "/civitai-token" : "/hf-token");
}
async function dh(e, t) {
  return ce(e === "civitai" ? "/civitai-token" : "/hf-token", { method: "POST", body: { token: t } });
}
function jl(e) {
  return !!(e && typeof e == "object" && typeof e.token == "string" && e.token !== "");
}
async function fh() {
  return ce("/health?mode=deploy");
}
const Er = /* @__PURE__ */ Mn("studio-infrastructure", () => {
  const e = /* @__PURE__ */ I("unknown"), t = /* @__PURE__ */ I(null), s = /* @__PURE__ */ I(null), n = /* @__PURE__ */ I([]), o = /* @__PURE__ */ I(null), r = /* @__PURE__ */ I(Zu(null)), a = /* @__PURE__ */ I(null), i = /* @__PURE__ */ I([]), l = /* @__PURE__ */ I([]), u = /* @__PURE__ */ I([]), d = /* @__PURE__ */ I(null), f = /* @__PURE__ */ I(!1), b = /* @__PURE__ */ I(null), h = /* @__PURE__ */ I(!1), O = /* @__PURE__ */ I(null), x = /* @__PURE__ */ I(null), C = /* @__PURE__ */ I(!1), T = /* @__PURE__ */ I(null), A = /* @__PURE__ */ I(!1), z = /* @__PURE__ */ I(!1), R = /* @__PURE__ */ I(null), J = /* @__PURE__ */ I(null), $e = /* @__PURE__ */ I(null), ne = Tn(), j = /* @__PURE__ */ I(null), re = /* @__PURE__ */ I(null), ve = /* @__PURE__ */ I(null);
  let Me = !1, Ie = null;
  const Oe = ge(() => n.value.find((te) => te.isActive) ?? null);
  function Ye(te, pe) {
    e.value = te, t.value = pe ?? null;
  }
  function ae(te) {
    s.value = te;
  }
  function _() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  function S(te) {
    O.value = te;
  }
  async function ue() {
    const te = na(await jg());
    n.value = te.rows, o.value = te.activeId;
  }
  async function Ue() {
    r.value = await Nl(), e.value = r.value.state, t.value = r.value.message || null;
  }
  async function ie() {
    const te = await ne.run(async (ze) => {
      const [Ke, Ne] = await Promise.all([Bg(), Gg()]);
      return ze.aborted ? null : { modelResult: Ke, nodeResult: Ne };
    });
    if (te.stale || !te.value) return;
    const pe = te.value.modelResult.models;
    i.value = (Array.isArray(pe) ? pe : []).filter(
      (ze) => !!ze && typeof ze == "object"
    );
    const he = te.value.nodeResult.custom_nodes;
    u.value = (Array.isArray(he) ? he : []).filter(
      (ze) => !!ze && typeof ze == "object"
    );
  }
  async function tt() {
    f.value = !0, b.value = null;
    try {
      await Promise.all([ue(), Ue(), ie()]), s.value = "server inventory loaded";
    } catch (te) {
      throw b.value = te instanceof Error ? te.message : "Could not load infrastructure", te;
    } finally {
      f.value = !1, Me && (Me = !1, tt());
    }
  }
  async function De() {
    Ie || (Ie = Ar((te) => {
      if (te === "workspace") {
        if (f.value) {
          Me = !0;
          return;
        }
        tt();
      }
    })), n.value.length || await tt();
  }
  async function bt(te) {
    h.value = !0;
    try {
      const pe = await Zg(te), he = na(pe);
      n.value = he.rows, o.value = he.activeId, mt("workspace");
    } finally {
      h.value = !1;
    }
  }
  async function ke(te) {
    if (re.value || ve.value)
      throw new Error("Cannot change workspace while an operation is active");
    h.value = !0;
    const pe = n.value;
    try {
      const he = await Lg(te);
      if (!he || he.status !== "ok")
        throw new Error(String(he?.message || "Activation failed"));
      const ze = na(he);
      n.value = ze.rows, o.value = ze.activeId, S(`Active workspace is now ${ze.rows.find((Ke) => Ke.isActive)?.label || te}.`), await Ue(), mt("workspace");
    } catch (he) {
      throw n.value = pe, he;
    } finally {
      h.value = !1;
    }
  }
  async function $(te, pe) {
    const he = Gt();
    if (re.value || ve.value)
      throw new Error("Another operation is already active");
    h.value = !0, C.value = !1, x.value = null;
    const ze = o.value ?? void 0, Ke = he.start({
      kind: "workspace-swap",
      label: "Swap workspace",
      workspaceId: ze
    });
    ve.value = Ke;
    const Ne = new AbortController(), He = window.setTimeout(() => Ne.abort(), 1800 * 1e3);
    try {
      const Qe = await Kg({ workspace_id: te, ...pe || {} }), oe = String(Qe.status || "");
      if (oe === "busy") throw new Error(String(Qe.message || "Deploy already running — try again later."));
      if (oe === "error") throw new Error(String(Qe.message || "Workspace swap failed."));
      if (oe === "confirm_required") {
        C.value = !0, he.patch(Ke, { status: "pending", message: "Confirmation required" });
        return;
      }
      if (oe === "repair_required")
        throw he.fail(Ke, String(Qe.message || "manifest repair required")), await P(), new Error(String(Qe.message || "manifest repair required"));
      if (oe === "review_required") {
        const we = (Array.isArray(Qe.to_install) ? Qe.to_install : []).map((it) => {
          const lt = it;
          return {
            key: `${String(lt.save_path || lt.folder || "")}/${String(lt.filename || "")}`,
            filename: String(lt.filename || ""),
            folder: String(lt.folder || lt.save_path || "")
          };
        });
        x.value = {
          workspaceLabel: String(Qe.workspace_label || te),
          toInstall: we,
          installCount: Number(Qe.install_count || we.length),
          presentCount: Number(Qe.present_count || 0),
          removeCount: Array.isArray(Qe.to_remove) ? Qe.to_remove.length : 0
        }, he.patch(Ke, { status: "pending", message: "Review required" });
        return;
      }
      if (oe === "started" && Qe.swap_id) {
        await q(String(Qe.swap_id), Ke, Ne.signal, ze);
        return;
      }
      throw new Error(String(Qe.message || "Unexpected swap response."));
    } catch (Qe) {
      if (C.value || x.value) throw Qe;
      const oe = Qe instanceof Error ? Qe.message : "Workspace swap failed";
      throw he.fail(Ke, oe), S(oe), Qe;
    } finally {
      window.clearTimeout(He), !C.value && !x.value && (ve.value = null), h.value = !1;
    }
  }
  async function F(te) {
    C.value = !1, ve.value = null, await $(te, { confirm_prompt_interrupt: !0 });
  }
  async function U(te, pe) {
    const he = ve.value;
    x.value = null, ve.value = null, he && Gt().cancel(he, "Superseded by review confirmation"), await $(te, Jg(te, pe));
  }
  async function B() {
    const te = ve.value;
    C.value = !1, x.value = null, ve.value = null, h.value = !1, te && Gt().cancel(te, "Swap cancelled."), S("Swap cancelled.");
  }
  async function q(te, pe, he, ze) {
    const Ke = Gt();
    try {
      await Kn({
        intervalMs: 1e3,
        signal: he,
        run: async () => {
          const Ne = await Qg(te);
          return Ke.patch(pe, { message: zl(Ne) || "Working…" }), S(zl(Ne) || "Working…"), Ne;
        },
        done: (Ne) => String(Ne.status || "") !== "running"
      }).then((Ne) => {
        const He = String(Ne.status || "");
        if (He === "ok") {
          const Qe = String(Ne.workspace_label || "workspace");
          Ke.finish(pe, `Swap done — ${Qe}. Deploy started.`), S(`Done — ${Qe}. Deploy started.`);
        } else throw He === "repair_required" ? (Ke.fail(pe, String(Ne.message || "manifest repair required")), P(), new Error(String(Ne.message || "manifest repair required"))) : He === "not_found" ? new Error("Swap status unavailable.") : new Error(
          String(Ne.message || Ne.error || Ne.deploy_message || "Workspace swap failed")
        );
      }), ze && o.value, await ue(), await Ue(), mt("workspace");
    } catch (Ne) {
      if (!C.value && !x.value) {
        const He = Ne instanceof Error ? Ne.message : "Workspace swap failed";
        try {
          Ke.fail(pe, He);
        } catch {
        }
        S(He);
      }
      throw Ne;
    } finally {
      ve.value = null;
    }
  }
  async function me() {
    const te = Gt();
    if (re.value) return re.value;
    if (ve.value) throw new Error("Cannot deploy while a swap is active");
    const pe = o.value ?? void 0, he = te.start({
      kind: "deploy",
      label: "Deploy workspace",
      workspaceId: pe
    });
    re.value = he;
    const ze = new AbortController();
    j.value = ze;
    const Ke = window.setTimeout(() => ze.abort(new DOMException("Deployment polling timed out", "TimeoutError")), 600 * 1e3);
    try {
      await Ug(), te.patch(he, { status: "running", message: "Deployment started" });
      const Ne = await Kn({
        intervalMs: 3e3,
        signal: ze.signal,
        run: async () => {
          const He = await Nl();
          return r.value = He, e.value = He.state, t.value = He.message || null, te.patch(he, { message: He.message || `Deployment: ${He.state}` }), He;
        },
        done: (He) => He.state === "ready" || He.state === "deployed_unwarmed" || He.state !== "deploying" && He.state !== "starting" && He.state !== "unknown"
      });
      if (!Dg(Ne.state)) throw new Error(Ne.message || `Deployment ended in ${Ne.state}`);
      if (pe && o.value !== pe) throw new Error("Deployment target workspace changed");
      te.finish(he, Ne.message || "Deployment completed");
    } catch (Ne) {
      const He = Ne instanceof Error ? Ne.message : "Deployment failed";
      throw te.fail(he, He), Ne;
    } finally {
      window.clearTimeout(Ke), j.value = null, re.value = null;
    }
    return he;
  }
  async function v() {
    const [te, pe, he] = await Promise.all([
      uh().catch(() => null),
      Dl("hf").catch(() => null),
      Dl("civitai").catch(() => null)
    ]);
    T.value = !!(te && te.connected === !0), A.value = jl(pe), z.value = jl(he);
  }
  async function k(te, pe) {
    const he = await dh(te, pe);
    if (!he || he.status !== "ok")
      throw new Error(String(he?.message || he?.error || "Save failed."));
    return await v(), pe ? "Saved." : "Cleared.";
  }
  async function P() {
    J.value = null;
    const te = await ih();
    R.value = te;
  }
  async function L(te) {
    J.value = null;
    const pe = await lh(te);
    J.value = String(pe.message || "Repairs applied."), R.value = pe;
  }
  async function Z(te, pe) {
    await ch(te, pe), await P();
  }
  async function Y() {
    d.value = await Yg();
  }
  async function E() {
    const te = Gt(), pe = te.start({ kind: "node-sync", label: "Push custom-node plugins" });
    try {
      await Xg(), te.finish(pe, "Plugins pushed"), await Y(), mt("workspace");
    } catch (he) {
      throw te.fail(pe, he instanceof Error ? he.message : "Push failed"), he;
    }
  }
  async function G() {
    const te = Gt(), pe = te.start({ kind: "node-sync", label: "Rebuild custom-node dependencies" });
    try {
      const he = await eh(), ze = String(he.sync_id || he.syncId || "");
      ze && await Kn({
        intervalMs: 3e3,
        run: async () => {
          const Ke = await th(ze);
          return te.patch(pe, { message: String(Ke.message || "Rebuilding…") }), Ke;
        },
        done: (Ke) => String(Ke.status || "") !== "running"
      }), te.finish(pe, "Dependencies rebuilt"), await Y(), mt("workspace");
    } catch (he) {
      throw te.fail(pe, he instanceof Error ? he.message : "Rebuild failed"), he;
    }
  }
  async function H(te) {
    const pe = Gt(), he = pe.start({ kind: "model-download", label: `Download ${String(te.filename || te.url || "model")}` });
    try {
      const ze = await sh(te), Ke = String(ze.download_id || ze.downloadId || "");
      if (!Ke) {
        pe.finish(he, "Install request accepted"), await ie();
        return;
      }
      await Kn({
        intervalMs: 2e3,
        run: async () => {
          const Ne = await oh(Ke);
          return pe.patch(he, {
            progress: typeof Ne.progress == "number" ? Ne.progress : void 0,
            message: String(Ne.message || "Downloading…")
          }), Ne;
        },
        done: (Ne) => String(Ne.status || "") !== "running"
      }).then((Ne) => {
        if (String(Ne.status || "") === "error")
          throw new Error(String(Ne.message || "Download failed"));
      }), pe.finish(he, "Download complete"), await ie(), mt("workspace");
    } catch (ze) {
      throw pe.fail(he, ze instanceof Error ? ze.message : "Download failed"), ze;
    }
  }
  async function K(te) {
    await rh(te), await ie();
  }
  async function ye(te) {
    await ah(te), await ie();
  }
  async function le(te, pe) {
    await qg(te, pe), await ie();
  }
  async function Re() {
    await Fg(0), await ie(), s.value = "inventory refreshed", mt("workspace");
  }
  async function Te(te = !0) {
    const pe = await Wg(te);
    i.value = Array.isArray(pe.models) ? pe.models.filter((he) => !!he && typeof he == "object") : i.value, await ie();
  }
  async function qe() {
    const te = await Hg();
    u.value = Array.isArray(te.custom_nodes) ? te.custom_nodes.filter((pe) => !!pe && typeof pe == "object") : u.value, await ie();
  }
  async function st() {
    a.value = await Vg();
  }
  async function et() {
    $e.value = await fh();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: o,
    activeWorkspace: Oe,
    deployStatus: r,
    deployLog: a,
    models: i,
    modelTypes: l,
    customNodes: u,
    customNodeSync: d,
    loading: f,
    error: b,
    busy: h,
    progress: O,
    swapReview: x,
    swapConfirmRequired: C,
    authConnected: T,
    hfConfigured: A,
    civitaiConfigured: z,
    repairIssues: R,
    repairMessage: J,
    health: $e,
    deploymentOperationId: re,
    swapOperationId: ve,
    setDeploy: Ye,
    setSyncSummary: ae,
    reset: _,
    load: tt,
    initialize: De,
    loadWorkspaces: ue,
    loadDeployment: Ue,
    loadInventory: ie,
    saveWorkspace: bt,
    selectWorkspace: ke,
    startSwap: $,
    confirmSwapInterrupt: F,
    confirmSwapReview: U,
    cancelSwapDialog: B,
    deploy: me,
    loadCredentials: v,
    saveCredential: k,
    scanRepair: P,
    applyRepair: L,
    deletePlaceholder: Z,
    loadSyncStatus: Y,
    pushPlugins: E,
    rebuildDependencies: G,
    installModel: H,
    installModelRequest: K,
    installCustomNode: ye,
    updateModelNotes: le,
    refreshRemoteInventoryNow: Re,
    rescanModelsNow: Te,
    refreshCustomNodesNow: qe,
    loadLog: st,
    loadHealth: et
  };
});
function ci(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return Object.prototype.hasOwnProperty.call(t, "workflow") ? t.workflow : Object.prototype.hasOwnProperty.call(t, "version") ? t.version : Object.prototype.hasOwnProperty.call(t, "mapping") ? t.mapping : e;
}
async function mh(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.tag && t.set("tag", e.tag), e.folder && t.set("folder", e.folder), e.favorite && t.set("favorite", "1");
  const s = t.toString() ? `?${t}` : "";
  return ce(`/studio/workflows${s}`);
}
async function ph(e) {
  return ce(`/studio/workflows/${encodeURIComponent(e)}`).then((t) => ({ ...t, workflow: ci(t) }));
}
async function vh(e) {
  return ce(`/studio/workflows/${encodeURIComponent(e)}/versions`);
}
async function gh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}`).then((t) => ci(t));
}
async function hh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`).then((t) => ci(t));
}
async function yh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/candidates`);
}
async function bh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/dependencies`);
}
async function wh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`);
}
async function Ll(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/portability`);
}
async function _h() {
  return ce("/studio/workflows/folders");
}
async function xh() {
  return ce("/studio/workflows/tags");
}
async function Ul(e, t) {
  return ce(`/studio/workflows/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function kh(e) {
  return ce("/studio/workflows", { method: "POST", body: e });
}
async function Sh(e) {
  return ce("/studio/workflows/import", { method: "POST", body: e });
}
async function Ch(e) {
  return ce(`/studio/workflows/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function $h(e) {
  return ce("/studio/workflows/folders", { method: "POST", body: { path: e } });
}
async function Ih(e, t) {
  return ce(`/studio/workflows/${encodeURIComponent(e)}/versions`, { method: "POST", body: t });
}
async function Rh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/state`);
}
async function Ah(e, t) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`, { method: "POST", body: t });
}
async function Eh(e, t) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/revision`, { method: "POST", body: t });
}
async function Oh(e, t) {
  return ce(`/studio/workflows/${encodeURIComponent(e)}/dependencies/nonessential`, { method: "POST", body: { keys: t } });
}
async function Th(e, t) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`, { method: "PATCH", body: t });
}
async function Ph(e, t) {
  return ce(`/studio/method-compat?workflow_id=${encodeURIComponent(e)}&version_id=${encodeURIComponent(t)}`);
}
async function Mh(e) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`);
}
async function Nh(e, t) {
  return ce(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`, { method: "POST", body: t });
}
async function zh(e, t) {
  return ce(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function Dh(e) {
  return ce(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function jh(e, t = {}) {
  return ce(`/studio/workflows/presets/${encodeURIComponent(e)}/duplicate`, { method: "POST", body: t });
}
async function Lh(e, t) {
  return ce(`/studio/workflows/presets/${encodeURIComponent(e)}/copy-to-version`, { method: "POST", body: { workflow_version_id: t } });
}
async function Uh(e, t) {
  return ce(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`);
}
async function Vh(e) {
  return ce("/studio/guidance-mappings", { method: "POST", body: { mapping: e } });
}
async function Fh(e, t) {
  return ce(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`, { method: "DELETE" });
}
async function Bh(e) {
  const t = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(e)}/export`);
  if (!t.ok) return { ok: !1, message: `Export failed with status ${t.status}` };
  const s = await t.blob(), n = t.headers.get("Content-Disposition") || "", o = /filename="?([^";]+)"?/.exec(n);
  return { ok: !0, blob: s, filename: o ? o[1].trim() : "manifest.json" };
}
async function Vl(e, t = !0) {
  return ce(`/studio/workflows/import-manifest?dry_run=${t ? "1" : "0"}`, { method: "POST", body: e });
}
function ui(e) {
  const t = String(e || "t2i").toLowerCase();
  return t === "txt2img" ? "t2i" : t;
}
const ks = ["feature-type", "required-bindings", "exposed-controls", "details"], Wh = {
  prompt: { key: "prompt", label: "Prompt", hint: "CLIPTextEncode · text" },
  seed: { key: "seed", label: "Seed", hint: "KSampler · seed" },
  step_count: { key: "step_count", label: "Step count", hint: "KSampler · steps" },
  cfg_scale: { key: "cfg_scale", label: "CFG scale", hint: "KSampler · cfg" },
  sampler: { key: "sampler", label: "Sampler", hint: "KSampler · sampler_name" },
  width: { key: "width", label: "Width", hint: "EmptyLatentImage · width" },
  height: { key: "height", label: "Height", hint: "EmptyLatentImage · height" },
  model_unet: { key: "model_unet", label: "Model", hint: "UNETLoader · unet_name" },
  vae: { key: "vae", label: "VAE", hint: "VAELoader · vae_name" },
  clip: { key: "clip", label: "CLIP", hint: "CLIPLoader · clip_name" },
  source_image: { key: "source_image", label: "Source image", hint: "LoadImage · image" },
  mask: { key: "mask", label: "Mask", hint: "Bind the exact input this workflow reads" },
  output: { key: "output", label: "Output", hint: "SaveImage · images" }
}, Fl = {
  t2i: ["prompt", "seed", "model_unet", "vae", "clip"],
  i2i: ["prompt", "seed", "model_unet", "vae", "clip", "source_image"],
  inpaint: ["prompt", "seed", "model_unet", "vae", "clip", "source_image", "mask"],
  sketch: ["prompt", "seed", "model_unet", "vae", "clip", "source_image"],
  outpaint: ["prompt", "seed", "model_unet", "vae", "clip", "source_image"]
}, Bl = {
  t2i: ["step_count", "cfg_scale", "sampler", "width", "height"],
  i2i: ["step_count", "cfg_scale", "sampler", "width", "height", "mask"],
  inpaint: ["step_count", "cfg_scale", "sampler", "width", "height"],
  sketch: ["step_count", "cfg_scale", "sampler", "width", "height", "mask"],
  outpaint: ["step_count", "cfg_scale", "sampler", "width", "height", "mask"]
};
function tn(e) {
  return Wh[e] ?? { key: e, label: e, hint: "" };
}
function Wl(e) {
  return Fl[ui(e)] ?? Fl.t2i;
}
function Gh(e) {
  return Bl[ui(e)] ?? Bl.t2i;
}
const qh = {
  prompt: [{ nodeType: "CLIPTextEncode", widget: "text" }],
  seed: [{ nodeType: "KSampler", widget: "seed" }],
  step_count: [{ nodeType: "KSampler", widget: "steps" }],
  cfg_scale: [{ nodeType: "KSampler", widget: "cfg" }],
  sampler: [{ nodeType: "KSampler", widget: "sampler_name" }],
  width: [{ nodeType: "EmptyLatentImage", widget: "width" }],
  height: [{ nodeType: "EmptyLatentImage", widget: "height" }],
  model_unet: [{ nodeType: "UNETLoader", widget: "unet_name" }, { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" }],
  vae: [{ nodeType: "VAELoader", widget: "vae_name" }, { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" }],
  clip: [{ nodeType: "CLIPLoader", widget: "clip_name" }, { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" }],
  source_image: [{ nodeType: "LoadImage", widget: "image" }],
  mask: [],
  output: [{ nodeType: "SaveImage" }, { nodeType: "PreviewImage" }]
};
function Hh(e) {
  return qh[e] ?? [];
}
function Qn(e) {
  return {
    v: 1,
    workflowId: e.workflowId || "",
    versionId: e.versionId || "",
    step: e.step && ks.includes(e.step) ? e.step : "feature-type",
    featureType: e.featureType || "t2i",
    bindings: e.bindings || {},
    outputBinding: e.outputBinding || null,
    controls: Array.isArray(e.controls) ? e.controls.slice(0, 64) : [],
    details: e.details || {}
  };
}
function Zh(e, t, s) {
  if (!e || e.length > 12e3) return null;
  try {
    const n = JSON.parse(e);
    return n.v !== 1 || n.workflowId !== t || n.versionId !== s ? null : Qn(n);
  } catch {
    return null;
  }
}
async function fn(e, t) {
  try {
    const s = await fetch(e, t);
    let n = "";
    try {
      n = await s.text();
    } catch {
      n = "";
    }
    let o = null;
    if (n)
      try {
        o = JSON.parse(n);
      } catch {
        o = { message: n };
      }
    return { ok: s.ok, status: s.status, data: o };
  } catch {
    return null;
  }
}
async function Kh(e) {
  return fn("/customnode/install/git_url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: e })
  });
}
async function Qh(e) {
  return fn("/manager/queue/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(e || {})
  });
}
async function Jh() {
  return fn("/manager/queue/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
}
async function Yh() {
  const e = await fn("/externalmodel/getlist?mode=default");
  return e && e.ok ? e : fn("/externalmodel/getlist?mode=cache");
}
async function Xh() {
  return fn("/customnode/getlist?mode=default&skip_update=true");
}
async function ey() {
  return fn("/customnode/getmappings?mode=default");
}
function ja(e) {
  return String(e || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}
function Or(e) {
  return String(e || "").split("/").filter(Boolean).pop() || "";
}
function ty(e) {
  try {
    return new RegExp(e);
  } catch {
    return null;
  }
}
function sy(e, t) {
  const s = {}, n = {}, o = {}, r = [], a = (l, u, d) => {
    const f = String(u ?? "").toLowerCase();
    f && !l[f] && (l[f] = d);
  }, i = (l, u) => {
    const d = {
      key: String(l),
      name: String(u.title || u.name || l),
      cnrId: String(u.cnr_id || u.id || l),
      repository: String(u.repository || ""),
      version: String(u.version || "unknown"),
      selected_version: String(u.selected_version || "latest"),
      channel: String(u.channel || "default"),
      mode: String(u.mode || "default"),
      install_type: String(u.install_type || ""),
      files: Array.isArray(u.files) ? u.files : []
    };
    s[String(l).toLowerCase()] = d;
    const f = String(u.repository || "");
    return f && (a(s, ja(f), d), a(s, Or(f).toLowerCase(), d)), d;
  };
  for (const [l, u] of Object.entries(e || {}))
    u && typeof u == "object" && i(l, u);
  if (t && typeof t == "object")
    for (const [l, u] of Object.entries(t)) {
      const d = Array.isArray(u) ? u[0] : u.classes, f = Array.isArray(u) ? u[1] : {}, b = s[String(l).toLowerCase()] || s[ja(l)];
      if (b) {
        if (Array.isArray(f.preemptions))
          for (const h of f.preemptions) a(o, h, b);
        if (typeof f.nodename_pattern == "string") {
          const h = ty(f.nodename_pattern);
          h && r.push({ re: h, record: b });
        }
      }
      for (const h of Array.isArray(d) ? d : [])
        b && a(n, h, b);
    }
  return { packs: s, byClass: n, preemptions: o, patterns: r };
}
function ny(e, t) {
  if (!t || !e) return null;
  for (const o of [e.cnr_id, e.aux_id]) {
    if (!o) continue;
    const r = String(o), a = t.packs[r.toLowerCase()] || t.packs[ja(r)] || t.packs[Or(r).toLowerCase()];
    if (a) return a;
  }
  const s = Array.isArray(e.classes) ? e.classes : e.classes ? [e.classes] : [], n = s.map((o) => String(o ?? "").toLowerCase()).filter(Boolean);
  for (const o of n)
    if (t.preemptions[o]) return t.preemptions[o];
  for (const o of n)
    if (t.byClass[o]) return t.byClass[o];
  for (const o of s) {
    const r = String(o ?? "");
    if (r) {
      for (const a of t.patterns || [])
        if (a.re.test(r)) return a.record;
    }
  }
  return null;
}
function Gl(e, t) {
  const s = ny(e, t);
  if (s)
    return { kind: "cnr", pack: s, url: "", name: s.name || String(e.name || "") };
  const n = String(e.repository_url || "");
  return n ? { kind: "git", pack: null, url: n, name: String(e.name || "") } : { kind: "none", pack: null, url: "", name: String(e.name || "") };
}
function oy(e) {
  const t = Array.isArray(e.files) ? e.files.slice() : [];
  return {
    id: e.cnrId || e.repository || t[0] || "",
    version: e.version || "unknown",
    selected_version: e.selected_version || "latest",
    channel: e.channel || "default",
    mode: e.mode || "default",
    repository: e.repository || t[0] || "",
    files: t,
    ui_id: String(e.key || e.cnrId || ""),
    install_type: e.install_type || "",
    skip_post_install: !1
  };
}
async function ry(e) {
  if (!e || e.kind === "none")
    return { ok: !1, message: "No Manager install target identified for this pack." };
  try {
    if (e.kind === "cnr") {
      const o = await Qh(oy(e.pack));
      if (!o) return { ok: !1, message: "Could not reach ComfyUI-Manager." };
      if (o.status === 403)
        return { ok: !1, message: "Manager refused the CNR install (403). Raise Manager's security level, then retry." };
      if (!o.ok) {
        const a = o.data, i = a && (a.message || a.error) || `HTTP ${o.status}`;
        return { ok: !1, message: `Install failed: ${String(i)}` };
      }
      const r = await Jh();
      return !r || !r.ok ? { ok: !1, message: "Install queued, but Manager did not start it. Open ComfyUI-Manager and press Start." } : { ok: !0, message: "Install queued through ComfyUI-Manager — restart ComfyUI to load it." };
    }
    const t = await Kh(e.url);
    if (!t) return { ok: !1, message: "Could not reach ComfyUI-Manager." };
    if (t.status === 403)
      return { ok: !1, message: "Manager refused the install (403). Set allow_git_url_install=true, use a loopback session, then restart ComfyUI." };
    if (t.ok) return { ok: !0, message: "Installed — restart ComfyUI to load it." };
    const s = t.data, n = s && (s.message || s.error) || `HTTP ${t.status}`;
    return { ok: !1, message: `Install failed: ${String(n)}` };
  } catch (t) {
    return { ok: !1, message: `Install failed: ${t?.message || "request failed"}` };
  }
}
const Ku = {
  checkpoint: "checkpoints",
  checkpoints: "checkpoints",
  unclip: "checkpoints",
  lora: "loras",
  loras: "loras",
  lycoris: "loras",
  vae: "vae",
  clip: "text_encoders",
  text_encoder: "text_encoders",
  text_encoders: "text_encoders",
  unet: "diffusion_models",
  diffusion_model: "diffusion_models",
  diffusion_models: "diffusion_models",
  t2i_adapter: "controlnet",
  "t2i-adapter": "controlnet",
  "t2i-style": "controlnet",
  controlnet: "controlnet",
  clip_vision: "clip_vision",
  gligen: "gligen",
  upscale: "upscale_models"
};
function La(e) {
  const t = String(e ?? "").trim().toLowerCase();
  return t && Ku[t] || "";
}
function Qu(e, t) {
  const s = String(e ?? "").trim();
  return s && s.toLowerCase() !== "default" ? s : La(t) || "";
}
function ay(e) {
  const t = String(e || "").trim();
  if (!t || t.toLowerCase() === "default") return "";
  const s = t.split("/")[0] || "";
  return Ku[s.toLowerCase()] || s;
}
function iy(e, t) {
  if (!e || !t || typeof t != "object") return !0;
  const s = La(e) || String(e).toLowerCase(), n = La(t.type) || ay(t.savePath);
  return !s || !n ? !0 : s === n;
}
function ly(e) {
  const t = {};
  for (const s of Array.isArray(e) ? e : []) {
    if (!s || typeof s != "object") continue;
    const n = s;
    if (!n.filename) continue;
    const o = {
      url: String(n.url || ""),
      reference: String(n.reference || ""),
      savePath: Qu(n.save_path, n.type),
      type: String(n.type || ""),
      name: String(n.name || ""),
      installed: n.installed
    }, r = String(n.filename);
    t[r] || (t[r] = o);
    const a = Or(r);
    a && a !== r && !t[a] && (t[a] = o);
  }
  return t;
}
function cy(e, t) {
  if (!t || !e || !e.filename) return null;
  const s = String(e.filename), n = [s], o = Or(s);
  o && o !== s && n.push(o);
  for (const r of n) {
    const a = t[r];
    if (a && iy(e.role, a)) return a;
  }
  return null;
}
const Fn = "comfymodal.studio.wizard.draft.v1", di = /* @__PURE__ */ Mn("studio-workflows", () => {
  const e = /* @__PURE__ */ I([]), t = /* @__PURE__ */ I(null), s = /* @__PURE__ */ I(null), n = /* @__PURE__ */ I([]), o = /* @__PURE__ */ I(null), r = /* @__PURE__ */ I(null), a = /* @__PURE__ */ I(null), i = /* @__PURE__ */ I(null), l = /* @__PURE__ */ I(null), u = /* @__PURE__ */ I(null), d = /* @__PURE__ */ I([]), f = /* @__PURE__ */ I(null), b = /* @__PURE__ */ I(null), h = /* @__PURE__ */ I(""), O = /* @__PURE__ */ I(""), x = /* @__PURE__ */ I(!1), C = /* @__PURE__ */ I(""), T = /* @__PURE__ */ I(!1), A = /* @__PURE__ */ I(null), z = /* @__PURE__ */ I(!1), R = /* @__PURE__ */ I(null), J = /* @__PURE__ */ I(!1), $e = /* @__PURE__ */ I(null), ne = /* @__PURE__ */ I(null), j = /* @__PURE__ */ I(null), re = /* @__PURE__ */ I(null), ve = Tn(), Me = /* @__PURE__ */ I(null), Ie = /* @__PURE__ */ I(null), Oe = /* @__PURE__ */ I(""), Ye = /* @__PURE__ */ I({}), ae = /* @__PURE__ */ I({});
  let _ = null;
  function S(N) {
    t.value = N;
  }
  function ue() {
    t.value = null, s.value = null, n.value = [], o.value = null;
  }
  async function Ue() {
    T.value = !0, A.value = null;
    try {
      const [N, se, Ae] = await Promise.all([
        mh({ search: C.value, tag: h.value || void 0, folder: O.value || void 0, favorite: x.value || void 0 }),
        _h().catch(() => null),
        xh().catch(() => null)
      ]);
      e.value = N.workflows ?? [], f.value = se, b.value = Ae;
    } catch (N) {
      throw A.value = N instanceof Error ? N.message : "Could not load workflows", N;
    } finally {
      T.value = !1;
    }
  }
  async function ie() {
    _ || (_ = Ar((N) => {
      N === "workflows" && !T.value && Ue();
    })), e.value.length || await Ue();
  }
  async function tt(N) {
    t.value = N;
    const se = await ve.run(async (Et) => {
      const [Ot, wt] = await Promise.all([ph(N), vh(N)]);
      return Et.aborted ? null : { workflowResponse: Ot, versionsResponse: wt };
    });
    if (se.stale || !se.value) return;
    s.value = se.value.workflowResponse.workflow ?? null, n.value = se.value.versionsResponse.versions ?? [];
    const Ae = s.value?.latest_version_id, Be = n.value.find((Et) => Et.workflow_version_id === Ae) ?? n.value.at(-1) ?? null;
    Be && await De(Be.workflow_version_id);
  }
  async function De(N) {
    const se = await ve.run(async (Be) => {
      const [Et, Ot, wt, Bt, Pr, W, p] = await Promise.all([
        gh(N),
        hh(N),
        bh(N),
        wh(N),
        Ll(N),
        Mh(N),
        Rh(N)
      ]);
      return Be.aborted ? null : { versionResponse: Et, mappingResponse: Ot, dependencyResponse: wt, compatibilityResponse: Bt, portabilityResponse: Pr, presetsResponse: W, stateResponse: p };
    });
    if (se.stale || !se.value) return;
    o.value = se.value.versionResponse, r.value = se.value.mappingResponse, a.value = null, i.value = se.value.dependencyResponse, l.value = se.value.compatibilityResponse, u.value = se.value.portabilityResponse, ne.value = se.value.stateResponse;
    const Ae = se.value.presetsResponse;
    d.value = Ae.presets ?? [], Te(se.value.dependencyResponse), Re(se.value.dependencyResponse), s.value && N && (j.value = await Ph(s.value.workflow_id, N).catch(() => null));
  }
  async function bt() {
    o.value && (a.value = await yh(o.value.workflow_version_id));
  }
  function ke() {
    const N = s.value?.workflow_id ?? "", se = o.value?.workflow_version_id ?? "";
    try {
      R.value = Zh(sessionStorage.getItem(Fn), N, se) ?? Qn({ workflowId: N, versionId: se, featureType: ui(s.value?.workflow_type) });
    } catch {
      R.value = Qn({ workflowId: N, versionId: se });
    }
    z.value = !0;
  }
  function $() {
    try {
      const N = typeof performance < "u" && typeof performance.getEntriesByType == "function" ? performance.getEntriesByType("navigation") : [], se = N && N[0] && N[0].type;
      if (se) return se === "reload" || se === "back_forward";
      const Ae = performance.navigation;
      return !!Ae && Ae.type !== 0;
    } catch {
      return !1;
    }
  }
  async function F() {
    if (z.value || !$()) return !1;
    let N = null;
    try {
      N = sessionStorage.getItem(Fn);
    } catch {
      return !1;
    }
    if (!N) return !1;
    let se = null;
    try {
      const Ae = JSON.parse(N);
      if (Ae.v !== 1 || !Ae.workflowId || !Ae.versionId) return !1;
      se = Qn(Ae);
    } catch {
      return !1;
    }
    try {
      await tt(se.workflowId);
    } catch {
      return !1;
    }
    return o.value?.workflow_version_id !== se.versionId ? !1 : (R.value = se, z.value = !0, !0);
  }
  function U(N) {
    if (R.value) {
      R.value = Qn({ ...R.value, ...N });
      try {
        sessionStorage.setItem(Fn, JSON.stringify(R.value));
      } catch {
      }
    }
  }
  function B(N) {
    U({ step: N });
  }
  function q() {
    z.value = !1, R.value = null;
    try {
      sessionStorage.removeItem(Fn);
    } catch {
    }
  }
  async function me(N) {
    t.value && (await Ul(t.value, N), await Ue(), await tt(t.value), mt("workflows"));
  }
  async function v(N, se) {
    await Ul(N, { favorite: se }), await Ue(), mt("workflows");
  }
  async function k(N) {
    await kh(N), await Ue(), mt("workflows");
  }
  async function P(N) {
    const se = Gt(), Ae = se.start({ kind: "workflow-import", label: "Import workflow" });
    try {
      await Sh(N), se.finish(Ae, "Workflow imported"), await Ue(), mt("workflows");
    } catch (Be) {
      throw se.fail(Ae, Be instanceof Error ? Be.message : "Import failed"), Be;
    }
  }
  async function L() {
    t.value && (await Ch(t.value), ue(), await Ue(), mt("workflows"));
  }
  async function Z(N) {
    await $h(N), await Ue();
  }
  async function Y(N) {
    t.value && (await Ih(t.value, N), await tt(t.value), mt("workflows"));
  }
  async function E(N) {
    const se = o.value?.workflow_version_id;
    if (!se) throw new Error("No version selected");
    const Ae = r.value;
    !!Ae && typeof Ae.mapping_id == "string" ? await Eh(se, N) : await Ah(se, N), await De(se), mt("workflows");
  }
  async function G(N) {
    t.value && (await Oh(t.value, N), o.value && await De(o.value.workflow_version_id));
  }
  async function H() {
    if (Ie.value) return Ie.value;
    try {
      const se = (await Yh())?.data ?? {}, Ae = Array.isArray(se.models) ? se.models : Array.isArray(se) ? se : [];
      Ie.value = ly(Ae);
    } catch {
      Ie.value = null;
    }
    return Ie.value;
  }
  function K(N) {
    return Ie.value ? cy(
      { filename: N.filename, role: N.role ?? N.folder },
      Ie.value
    ) : null;
  }
  function ye(N) {
    return Gl(N, Me.value);
  }
  function le(N) {
    const Ae = (Array.isArray(N.source_urls) ? N.source_urls.map(String).filter(Boolean) : [])[0] ?? "";
    if (Ae)
      return { url: Ae, savePath: String(N.folder || ""), viaManager: !1 };
    const Be = K(N);
    return Be && Be.url ? {
      url: Be.url,
      savePath: Qu(Be.savePath, Be.type) || String(N.folder || ""),
      viaManager: !0
    } : { url: "", savePath: String(N.folder || ""), viaManager: !1 };
  }
  function Re(N) {
    if (!N || typeof N != "object") return;
    const se = s.value?.name;
    if (!se) return;
    const Ae = N.models;
    if (!Array.isArray(Ae)) return;
    const Be = { ...Ye.value };
    for (const Et of Ae) {
      const Ot = String(Et?.filename || "");
      if (!Ot) continue;
      const wt = Be[Ot] ?? [];
      wt.includes(se) || wt.push(se), Be[Ot] = wt;
    }
    Ye.value = Be;
  }
  async function Te(N) {
    if (!N || typeof N != "object") return;
    const se = N;
    if (se.status !== "ok") return;
    const Ae = Array.isArray(se.models) ? se.models : [], Be = Array.isArray(se.custom_nodes) ? se.custom_nodes : [], Et = Ae.some((wt) => {
      const Bt = wt ?? {};
      return Bt.state !== "installed" && !(Array.isArray(Bt.source_urls) && Bt.source_urls.length > 0);
    }), Ot = Be.some((wt) => {
      const Bt = wt ?? {};
      return Bt.state === "missing" && !Bt.repository_url;
    });
    Et && H().catch(() => null), Ot && qe().catch(() => null);
  }
  async function qe() {
    if (Me.value) return Me.value;
    try {
      const [N, se] = await Promise.all([
        Xh(),
        ey()
      ]), Ae = (N?.data ?? {}).node_packs, Be = se?.data ?? {};
      Me.value = sy(
        Ae ?? {},
        Be
      );
    } catch {
      Me.value = null;
    }
    return Me.value;
  }
  async function st(N) {
    const se = String(N.name || N.cnr_id || "node"), Ae = await qe(), Be = Gl(N, Ae);
    ae.value = { ...ae.value, [se]: "Installing…" };
    const Et = await ry(Be);
    ae.value = { ...ae.value, [se]: Et.message }, Et.ok && await Er().loadInventory().catch(() => {
    });
  }
  async function et(N) {
    o.value && (await Th(o.value.workflow_version_id, N), await De(o.value.workflow_version_id));
  }
  async function te() {
    o.value && (u.value = await Ll(o.value.workflow_version_id));
  }
  async function pe() {
    if (!o.value) return;
    const N = await Bh(o.value.workflow_version_id);
    if (!N.ok || !N.blob) throw new Error(N.message || "Export failed");
    const se = URL.createObjectURL(N.blob);
    try {
      const Ae = document.createElement("a");
      Ae.href = se, Ae.download = N.filename || "manifest.json", document.body.appendChild(Ae), Ae.click(), Ae.remove();
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(se), 1e3);
    }
  }
  async function he(N) {
    const se = await Vl(N, !0);
    return re.value = se, se;
  }
  async function ze(N) {
    await Vl(N, !1), re.value = null, await Ue(), mt("workflows");
  }
  function Ke(N) {
    const se = {};
    for (const [Ae, Be] of Object.entries(N))
      Be instanceof Blob || typeof Be == "string" && (Be.startsWith("blob:") || Be.startsWith("data:image/")) || Ae === "sourceImage" || Ae === "referenceImages" || Ae === "mask" || Ae === "sketch" || Ae === "generatedImages" || Ae === "compareImages" || (se[Ae] = Be);
    return se;
  }
  async function Ne(N) {
    o.value && (await Nh(o.value.workflow_version_id, {
      ...N,
      studio_state: Ke(N.studio_state)
    }), await De(o.value.workflow_version_id));
  }
  async function He(N, se) {
    const Ae = se.studio_state && typeof se.studio_state == "object" ? { ...se, studio_state: Ke(se.studio_state) } : se;
    await zh(N, Ae), o.value && await De(o.value.workflow_version_id);
  }
  async function Qe(N) {
    await Dh(N), o.value && await De(o.value.workflow_version_id);
  }
  async function oe(N, se) {
    await jh(N, se ? { name: se } : {}), o.value && await De(o.value.workflow_version_id);
  }
  async function we(N, se) {
    await Lh(N, se), mt("workflows");
  }
  async function it(N, se) {
    return Uh(N, se);
  }
  async function lt(N) {
    await Vh(N);
  }
  async function At(N, se) {
    await Fh(N, se);
  }
  async function Ze() {
    const N = R.value;
    if (!N) throw new Error("No wizard draft");
    const se = N.bindings || {};
    if (!Object.values(se).filter(
      (Be) => Be && typeof Be == "object" && Be.confirmed === !0
    ).length) throw new Error("Confirm at least one graph binding first");
    if (!N.outputBinding) throw new Error("Capture the output binding first");
    J.value = !0, $e.value = null;
    try {
      await E({
        feature_type: N.featureType,
        bindings: N.bindings,
        output_binding: N.outputBinding,
        controls: N.controls,
        details: N.details
      });
      try {
        sessionStorage.removeItem(Fn);
      } catch {
      }
      R.value = null, z.value = !1;
    } catch (Be) {
      throw $e.value = Be instanceof Error ? Be.message : "Mapping save failed", Be;
    } finally {
      J.value = !1;
    }
  }
  return {
    workflows: e,
    selectedId: t,
    selectedWorkflow: s,
    versions: n,
    selectedVersion: o,
    mapping: r,
    mappingCandidates: a,
    dependencies: i,
    compatibility: l,
    portability: u,
    presets: d,
    folders: f,
    tags: b,
    tagFilter: h,
    folderFilter: O,
    favoritesOnly: x,
    versionState: ne,
    methodCompat: j,
    manifestPreview: re,
    query: C,
    loading: T,
    error: A,
    wizardOpen: z,
    wizardDraft: R,
    wizardSaving: J,
    wizardError: $e,
    select: S,
    clear: ue,
    loadList: Ue,
    initialize: ie,
    selectWorkflow: tt,
    selectVersion: De,
    loadMappingCandidates: bt,
    openWizard: ke,
    updateWizard: U,
    setWizardStep: B,
    closeWizard: q,
    updateMetadata: me,
    maybeResumeWizard: F,
    toggleFavorite: v,
    createNewWorkflow: k,
    importNewWorkflow: P,
    deleteSelectedWorkflow: L,
    createFolder: Z,
    captureVersion: Y,
    saveMapping: E,
    markNonessential: G,
    saveCompatibility: et,
    recheckPortability: te,
    loadManagerIndex: qe,
    loadManagerModels: H,
    resolveModelMatch: K,
    resolveNodePlan: ye,
    modelInstallTarget: le,
    libraryQuery: Oe,
    modelUsage: Ye,
    installDependencyNode: st,
    dependencyInstallMessage: ae,
    exportManifest: pe,
    previewManifestImport: he,
    commitManifestImport: ze,
    sanitizePresetState: Ke,
    createPreset: Ne,
    savePreset: He,
    removePreset: Qe,
    duplicateCurrentPreset: oe,
    copyPresetForward: we,
    loadGuidance: it,
    saveGuidance: lt,
    removeGuidance: At,
    saveWizardMapping: Ze
  };
});
function Ju(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var o = e.length;
    for (t = 0; t < o; t++) e[t] && (s = Ju(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function Yu() {
  for (var e, t, s = 0, n = "", o = arguments.length; s < o; s++) (e = arguments[s]) && (t = Ju(e)) && (n && (n += " "), n += t);
  return n;
}
const uy = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, dy = (e, t) => ({
  classGroupId: e,
  validator: t
}), Xu = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), cr = "-", ql = [], fy = "arbitrary..", my = (e) => {
  const t = vy(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (a) => {
      if (a.startsWith("[") && a.endsWith("]"))
        return py(a);
      const i = a.split(cr), l = i[0] === "" && i.length > 1 ? 1 : 0;
      return ed(i, l, t);
    },
    getConflictingClassGroupIds: (a, i) => {
      if (i) {
        const l = n[a], u = s[a];
        return l ? u ? uy(u, l) : l : u || ql;
      }
      return s[a] || ql;
    }
  };
}, ed = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const o = e[t], r = s.nextPart.get(o);
  if (r) {
    const u = ed(e, t + 1, r);
    if (u) return u;
  }
  const a = s.validators;
  if (a === null)
    return;
  const i = t === 0 ? e.join(cr) : e.slice(t).join(cr), l = a.length;
  for (let u = 0; u < l; u++) {
    const d = a[u];
    if (d.validator(i))
      return d.classGroupId;
  }
}, py = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? fy + n : void 0;
})(), vy = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return gy(s, t);
}, gy = (e, t) => {
  const s = Xu();
  for (const n in e) {
    const o = e[n];
    fi(o, s, n, t);
  }
  return s;
}, fi = (e, t, s, n) => {
  const o = e.length;
  for (let r = 0; r < o; r++) {
    const a = e[r];
    hy(a, t, s, n);
  }
}, hy = (e, t, s, n) => {
  if (typeof e == "string") {
    yy(e, t, s);
    return;
  }
  if (typeof e == "function") {
    by(e, t, s, n);
    return;
  }
  wy(e, t, s, n);
}, yy = (e, t, s) => {
  const n = e === "" ? t : td(t, e);
  n.classGroupId = s;
}, by = (e, t, s, n) => {
  if (_y(e)) {
    fi(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(dy(s, e));
}, wy = (e, t, s, n) => {
  const o = Object.entries(e), r = o.length;
  for (let a = 0; a < r; a++) {
    const [i, l] = o[a];
    fi(l, td(t, i), s, n);
  }
}, td = (e, t) => {
  let s = e;
  const n = t.split(cr), o = n.length;
  for (let r = 0; r < o; r++) {
    const a = n[r];
    let i = s.nextPart.get(a);
    i || (i = Xu(), s.nextPart.set(a, i)), s = i;
  }
  return s;
}, _y = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, xy = (e) => {
  if (e < 1)
    return {
      get: () => {
      },
      set: () => {
      }
    };
  let t = 0, s = /* @__PURE__ */ Object.create(null), n = /* @__PURE__ */ Object.create(null);
  const o = (r, a) => {
    s[r] = a, t++, t > e && (t = 0, n = s, s = /* @__PURE__ */ Object.create(null));
  };
  return {
    get(r) {
      let a = s[r];
      if (a !== void 0)
        return a;
      if ((a = n[r]) !== void 0)
        return o(r, a), a;
    },
    set(r, a) {
      r in s ? s[r] = a : o(r, a);
    }
  };
}, Ua = "!", Hl = ":", ky = [], Zl = (e, t, s, n, o) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: o
}), Sy = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (o) => {
    const r = [];
    let a = 0, i = 0, l = 0, u;
    const d = o.length;
    for (let x = 0; x < d; x++) {
      const C = o[x];
      if (a === 0 && i === 0) {
        if (C === Hl) {
          r.push(o.slice(l, x)), l = x + 1;
          continue;
        }
        if (C === "/") {
          u = x;
          continue;
        }
      }
      C === "[" ? a++ : C === "]" ? a-- : C === "(" ? i++ : C === ")" && i--;
    }
    const f = r.length === 0 ? o : o.slice(l);
    let b = f, h = !1;
    f.endsWith(Ua) ? (b = f.slice(0, -1), h = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      f.startsWith(Ua) && (b = f.slice(1), h = !0)
    );
    const O = u && u > l ? u - l : void 0;
    return Zl(r, h, b, O);
  };
  if (t) {
    const o = t + Hl, r = n;
    n = (a) => a.startsWith(o) ? r(a.slice(o.length)) : Zl(ky, !1, a, void 0, !0);
  }
  if (s) {
    const o = n;
    n = (r) => s({
      className: r,
      parseClassName: o
    });
  }
  return n;
}, Cy = (e) => {
  const t = /* @__PURE__ */ new Map();
  return e.orderSensitiveModifiers.forEach((s, n) => {
    t.set(s, 1e6 + n);
  }), (s) => {
    const n = [];
    let o = [];
    for (let r = 0; r < s.length; r++) {
      const a = s[r], i = a[0] === "[", l = t.has(a);
      i || l ? (o.length > 0 && (o.sort(), n.push(...o), o = []), n.push(a)) : o.push(a);
    }
    return o.length > 0 && (o.sort(), n.push(...o)), n;
  };
}, $y = (e) => ({
  cache: xy(e.cacheSize),
  parseClassName: Sy(e),
  sortModifiers: Cy(e),
  postfixLookupClassGroupIds: Iy(e),
  ...my(e)
}), Iy = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, Ry = /\s+/, Ay = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: o,
    sortModifiers: r,
    postfixLookupClassGroupIds: a
  } = t, i = [], l = e.trim().split(Ry);
  let u = "";
  for (let d = l.length - 1; d >= 0; d -= 1) {
    const f = l[d], {
      isExternal: b,
      modifiers: h,
      hasImportantModifier: O,
      baseClassName: x,
      maybePostfixModifierPosition: C
    } = s(f);
    if (b) {
      u = f + (u.length > 0 ? " " + u : u);
      continue;
    }
    let T = !!C, A;
    if (T) {
      const ne = x.substring(0, C);
      A = n(ne);
      const j = A && a[A] ? n(x) : void 0;
      j && j !== A && (A = j, T = !1);
    } else
      A = n(x);
    if (!A) {
      if (!T) {
        u = f + (u.length > 0 ? " " + u : u);
        continue;
      }
      if (A = n(x), !A) {
        u = f + (u.length > 0 ? " " + u : u);
        continue;
      }
      T = !1;
    }
    const z = h.length === 0 ? "" : h.length === 1 ? h[0] : r(h).join(":"), R = O ? z + Ua : z, J = R + A;
    if (i.indexOf(J) > -1)
      continue;
    i.push(J);
    const $e = o(A, T);
    for (let ne = 0; ne < $e.length; ++ne) {
      const j = $e[ne];
      i.push(R + j);
    }
    u = f + (u.length > 0 ? " " + u : u);
  }
  return u;
}, Ey = (...e) => {
  let t = 0, s, n, o = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = sd(s)) && (o && (o += " "), o += n);
  return o;
}, sd = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = sd(e[n])) && (s && (s += " "), s += t);
  return s;
}, Oy = (e, ...t) => {
  let s, n, o, r;
  const a = (l) => {
    const u = t.reduce((d, f) => f(d), e());
    return s = $y(u), n = s.cache.get, o = s.cache.set, r = i, i(l);
  }, i = (l) => {
    const u = n(l);
    if (u)
      return u;
    const d = Ay(l, s);
    return o(l, d), d;
  };
  return r = a, (...l) => r(Ey(...l));
}, Ty = [], Ct = (e) => {
  const t = (s) => s[e] || Ty;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, nd = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, od = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Py = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, My = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, Ny = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, zy = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Dy = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, jy = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, Ds = (e) => Py.test(e), Xe = (e) => !!e && !Number.isNaN(Number(e)), as = (e) => !!e && Number.isInteger(Number(e)), oa = (e) => e.endsWith("%") && Xe(e.slice(0, -1)), xs = (e) => My.test(e), rd = () => !0, Ly = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  Ny.test(e) && !zy.test(e)
), mi = () => !1, Uy = (e) => Dy.test(e), Vy = (e) => jy.test(e), Fy = (e) => !xe(e) && !Se(e), By = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), Wy = (e) => Js(e, ld, mi), xe = (e) => nd.test(e), sn = (e) => Js(e, cd, Ly), Kl = (e) => Js(e, Yy, Xe), Gy = (e) => Js(e, dd, rd), qy = (e) => Js(e, ud, mi), Ql = (e) => Js(e, ad, mi), Hy = (e) => Js(e, id, Vy), No = (e) => Js(e, fd, Uy), Se = (e) => od.test(e), Bn = (e) => mn(e, cd), Zy = (e) => mn(e, ud), Jl = (e) => mn(e, ad), Ky = (e) => mn(e, ld), Qy = (e) => mn(e, id), zo = (e) => mn(e, fd, !0), Jy = (e) => mn(e, dd, !0), Js = (e, t, s) => {
  const n = nd.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, mn = (e, t, s = !1) => {
  const n = od.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, ad = (e) => e === "position" || e === "percentage", id = (e) => e === "image" || e === "url", ld = (e) => e === "length" || e === "size" || e === "bg-size", cd = (e) => e === "length", Yy = (e) => e === "number", ud = (e) => e === "family-name", dd = (e) => e === "number" || e === "weight", fd = (e) => e === "shadow", Xy = () => {
  const e = Ct("color"), t = Ct("font"), s = Ct("text"), n = Ct("font-weight"), o = Ct("tracking"), r = Ct("leading"), a = Ct("breakpoint"), i = Ct("container"), l = Ct("spacing"), u = Ct("radius"), d = Ct("shadow"), f = Ct("inset-shadow"), b = Ct("text-shadow"), h = Ct("drop-shadow"), O = Ct("blur"), x = Ct("perspective"), C = Ct("aspect"), T = Ct("ease"), A = Ct("animate"), z = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], R = () => [
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
  ], J = () => [...R(), Se, xe], $e = () => ["auto", "hidden", "clip", "visible", "scroll"], ne = () => ["auto", "contain", "none"], j = () => [Se, xe, l], re = () => [Ds, "full", "auto", ...j()], ve = () => [as, "none", "subgrid", Se, xe], Me = () => ["auto", {
    span: ["full", as, Se, xe]
  }, as, Se, xe], Ie = () => [as, "auto", Se, xe], Oe = () => ["auto", "min", "max", "fr", Se, xe], Ye = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], ae = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], _ = () => ["auto", ...j()], S = () => [Ds, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...j()], ue = () => [i, Ds, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...j()], Ue = () => [Ds, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...j()], ie = () => [e, Se, xe], tt = () => [...R(), Jl, Ql, {
    position: [Se, xe]
  }], De = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], bt = () => ["auto", "cover", "contain", Ky, Wy, {
    size: [Se, xe]
  }], ke = () => [oa, Bn, sn], $ = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    u,
    Se,
    xe
  ], F = () => ["", Xe, Bn, sn], U = () => ["solid", "dashed", "dotted", "double"], B = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], q = () => [Xe, oa, Jl, Ql], me = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    O,
    Se,
    xe
  ], v = () => ["none", Xe, Se, xe], k = () => ["none", Xe, Se, xe], P = () => [Xe, Se, xe], L = () => [Ds, "full", ...j()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [xs],
      breakpoint: [xs],
      color: [rd],
      container: [xs],
      "drop-shadow": [xs],
      ease: ["in", "out", "in-out"],
      font: [Fy],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [xs],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [xs],
      shadow: [xs],
      spacing: ["px", Xe],
      text: [xs],
      "text-shadow": [xs],
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
        aspect: ["auto", "square", Ds, xe, Se, C]
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
        "@container": ["", "normal", "size", Se, xe]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [By],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [Xe, "auto", xe, Se, i]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": z()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": z()
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
        overflow: $e()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": $e()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": $e()
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
        inset: re()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": re()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": re()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": re(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: re()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": re(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: re()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": re()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": re()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: re()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: re()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: re()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: re()
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
        z: [as, "auto", Se, xe]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [Ds, "full", "auto", i, ...j()]
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
        flex: [Xe, Ds, "auto", "initial", "none", xe]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", Xe, Se, xe]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", Xe, Se, xe]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [as, "first", "last", "none", Se, xe]
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
        col: Me()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": Ie()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": Ie()
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
        row: Me()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": Ie()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": Ie()
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
        "auto-cols": Oe()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": Oe()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: j()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": j()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": j()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...Ye(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...ae(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...ae()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...Ye()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...ae(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...ae(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": Ye()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...ae(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...ae()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: j()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: j()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: j()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: j()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: j()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: j()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: j()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: j()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: j()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: j()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: j()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: _()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: _()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: _()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: _()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: _()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: _()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: _()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: _()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: _()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: _()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: _()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": j()
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
        "space-y": j()
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
        size: S()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ...ue()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...ue()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...ue()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...Ue()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...Ue()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...Ue()]
      }],
      /**
       * Width
       * @see https://tailwindcss.com/docs/width
       */
      w: [{
        w: [i, "screen", ...S()]
      }],
      /**
       * Min-Width
       * @see https://tailwindcss.com/docs/min-width
       */
      "min-w": [{
        "min-w": [
          i,
          "screen",
          /** Deprecated. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          "none",
          ...S()
        ]
      }],
      /**
       * Max-Width
       * @see https://tailwindcss.com/docs/max-width
       */
      "max-w": [{
        "max-w": [
          i,
          "screen",
          "none",
          /** Deprecated since Tailwind CSS v4.0.0. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          "prose",
          /** Deprecated since Tailwind CSS v4.0.0. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          {
            screen: [a]
          },
          ...S()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...S()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...S()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...S()]
      }],
      // ------------------
      // --- Typography ---
      // ------------------
      /**
       * Font Size
       * @see https://tailwindcss.com/docs/font-size
       */
      "font-size": [{
        text: ["base", s, Bn, sn]
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
        font: [n, Jy, Gy]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", oa, xe]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [Zy, qy, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [xe]
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
        tracking: [o, Se, xe]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [Xe, "none", Se, Kl]
      }],
      /**
       * Line Height
       * @see https://tailwindcss.com/docs/line-height
       */
      leading: [{
        leading: [
          "none",
          /** Deprecated since Tailwind CSS v4.0.0. @see https://github.com/tailwindlabs/tailwindcss.com/issues/2027#issuecomment-2620152757 */
          r,
          ...j()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", Se, xe]
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
        list: ["disc", "decimal", "none", Se, xe]
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
        placeholder: ie()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: ie()
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
        decoration: [...U(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [Xe, "from-font", "auto", Se, sn]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: ie()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [Xe, "auto", Se, xe]
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
        indent: j()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [as, Se, xe]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", Se, xe]
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
        content: ["none", Se, xe]
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
        bg: tt()
      }],
      /**
       * Background Repeat
       * @see https://tailwindcss.com/docs/background-repeat
       */
      "bg-repeat": [{
        bg: De()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: bt()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, as, Se, xe],
          radial: ["", Se, xe],
          conic: ["", as, Se, xe]
        }, Qy, Hy]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: ie()
      }],
      /**
       * Gradient Color Stops From Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from-pos": [{
        from: ke()
      }],
      /**
       * Gradient Color Stops Via Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via-pos": [{
        via: ke()
      }],
      /**
       * Gradient Color Stops To Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to-pos": [{
        to: ke()
      }],
      /**
       * Gradient Color Stops From
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from": [{
        from: ie()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: ie()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: ie()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: $()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": $()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": $()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": $()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": $()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": $()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": $()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": $()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": $()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": $()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": $()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": $()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": $()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": $()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": $()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: F()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": F()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": F()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": F()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": F()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": F()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": F()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": F()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": F()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": F()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": F()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": F()
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
        "divide-y": F()
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
        border: [...U(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...U(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: ie()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": ie()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": ie()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": ie()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": ie()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": ie()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": ie()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": ie()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": ie()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": ie()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": ie()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: ie()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [...U(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [Xe, Se, xe]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", Xe, Bn, sn]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: ie()
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
          d,
          zo,
          No
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: ie()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", f, zo, No]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": ie()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: F()
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
        ring: ie()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [Xe, sn]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": ie()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": F()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": ie()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", b, zo, No]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": ie()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [Xe, Se, xe]
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
        "mask-linear": [Xe]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": q()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": q()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": ie()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": ie()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": q()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": q()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": ie()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": ie()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": q()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": q()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": ie()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": ie()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": q()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": q()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": ie()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": ie()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": q()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": q()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": ie()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": ie()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": q()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": q()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": ie()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": ie()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": q()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": q()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": ie()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": ie()
      }],
      "mask-image-radial": [{
        "mask-radial": [Se, xe]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": q()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": q()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": ie()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": ie()
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
        "mask-radial-at": R()
      }],
      "mask-image-conic-pos": [{
        "mask-conic": [Xe]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": q()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": q()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": ie()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": ie()
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
        mask: tt()
      }],
      /**
       * Mask Repeat
       * @see https://tailwindcss.com/docs/mask-repeat
       */
      "mask-repeat": [{
        mask: De()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: bt()
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
        mask: ["none", Se, xe]
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
          Se,
          xe
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: me()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [Xe, Se, xe]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [Xe, Se, xe]
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
          zo,
          No
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": ie()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", Xe, Se, xe]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [Xe, Se, xe]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", Xe, Se, xe]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [Xe, Se, xe]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", Xe, Se, xe]
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
          Se,
          xe
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": me()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [Xe, Se, xe]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [Xe, Se, xe]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", Xe, Se, xe]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [Xe, Se, xe]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", Xe, Se, xe]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [Xe, Se, xe]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [Xe, Se, xe]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", Xe, Se, xe]
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
        "border-spacing": j()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": j()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": j()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", Se, xe]
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
        duration: [Xe, "initial", Se, xe]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", T, Se, xe]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [Xe, Se, xe]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", A, Se, xe]
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
        perspective: [x, Se, xe]
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
        rotate: v()
      }],
      /**
       * Rotate X
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-x": [{
        "rotate-x": v()
      }],
      /**
       * Rotate Y
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-y": [{
        "rotate-y": v()
      }],
      /**
       * Rotate Z
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-z": [{
        "rotate-z": v()
      }],
      /**
       * Scale
       * @see https://tailwindcss.com/docs/scale
       */
      scale: [{
        scale: k()
      }],
      /**
       * Scale X
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-x": [{
        "scale-x": k()
      }],
      /**
       * Scale Y
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-y": [{
        "scale-y": k()
      }],
      /**
       * Scale Z
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-z": [{
        "scale-z": k()
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
        skew: P()
      }],
      /**
       * Skew X
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-x": [{
        "skew-x": P()
      }],
      /**
       * Skew Y
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-y": [{
        "skew-y": P()
      }],
      /**
       * Transform
       * @see https://tailwindcss.com/docs/transform
       */
      transform: [{
        transform: [Se, xe, "", "none", "gpu", "cpu"]
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
        translate: L()
      }],
      /**
       * Translate X
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-x": [{
        "translate-x": L()
      }],
      /**
       * Translate Y
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-y": [{
        "translate-y": L()
      }],
      /**
       * Translate Z
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-z": [{
        "translate-z": L()
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
        zoom: [as, Se, xe]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: ie()
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
        caret: ie()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", Se, xe]
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
        "scrollbar-thumb": ie()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": ie()
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
        "scroll-m": j()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": j()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": j()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": j()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": j()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": j()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": j()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": j()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": j()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": j()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": j()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": j()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": j()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": j()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": j()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": j()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": j()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": j()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": j()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": j()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": j()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": j()
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
        "will-change": ["auto", "scroll", "contents", "transform", Se, xe]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...ie()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [Xe, Bn, sn, Kl]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...ie()]
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
}, eb = /* @__PURE__ */ Oy(Xy);
function pi(...e) {
  return eb(Yu(e));
}
const tb = { class: "cmst:flex cmst:h-14 cmst:items-center cmst:gap-3 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:pl-3 cmst:pr-14" }, sb = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:text-cmst-muted" }, nb = { class: "cmst:flex-1 cmst:min-w-0" }, ob = ["onKeydown"], rb = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:px-4 cmst:py-3" }, ab = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-1 cmst:flex-col cmst:gap-0.5 cmst:overflow-y-auto cmst:px-3 cmst:pb-4"
}, ib = {
  key: 0,
  class: "cmst-drawer-hint"
}, lb = {
  key: 1,
  class: "cmst-drawer-hint"
}, cb = {
  key: 2,
  class: "cmst-drawer-hint"
}, ub = /* @__PURE__ */ Mt({
  __name: "StudioApp",
  setup(e) {
    const t = Nu(), s = So(), n = Er(), o = di(), r = /* @__PURE__ */ I(!1), a = /* @__PURE__ */ I(null), i = /* @__PURE__ */ I(null);
    Ns(() => {
      s.initialize(), n.initialize();
      try {
        document.body.setAttribute("data-cmv-vue-ready", "1");
      } catch {
      }
      i.value?.focus();
    });
    const l = {
      playground: zu,
      history: Av,
      workflows: Du,
      backend: Mv,
      settings: zv
    }, u = ["playground", "history"], d = ["workflows", "backend", "settings"], f = ge(() => String(t.name ?? "playground")), b = ge(
      () => Yr[f.value ?? "playground"] ?? "Studio"
    ), h = ge(() => o.wizardOpen);
    function O() {
      r.value = !0;
    }
    function x() {
      r.value = !1;
    }
    ss(
      () => t.fullPath,
      () => {
        r.value = !1;
      }
    ), ss(r, (T) => {
      T && _o(() => {
        a.value?.focus();
      });
    });
    function C() {
      window.dispatchEvent(new CustomEvent("comfymodal:close-vue-studio")), window.__comfymodalCloseVueStudio?.();
    }
    return (T, A) => (g(), w("div", {
      "data-testid": "vue-studio-root",
      class: Ve(["cmst:relative cmst:flex cmst:flex-col cmst:bg-cmst-bg cmst:text-cmst-fg", h.value ? "cmst:min-h-0" : "cmst:min-h-[60vh]"])
    }, [
      c("header", tb, [
        c("button", {
          type: "button",
          "aria-label": "Open navigation",
          "data-testid": "vue-nav-drawer-open",
          class: "cmst:shrink-0 cmst:rounded-md cmst:p-2 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg",
          onClick: O
        }, [
          V(m(Sv), {
            class: "cmst:size-4",
            "aria-hidden": "true"
          })
        ]),
        A[0] || (A[0] = c("span", { class: "cmst:shrink-0 cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg" }, " Modal Studio ", -1)),
        A[1] || (A[1] = c("span", {
          "aria-hidden": "true",
          class: "cmst:shrink-0 cmst:text-cmst-muted"
        }, "/", -1)),
        c("span", sb, M(b.value), 1),
        c("button", {
          ref_key: "closeBtn",
          ref: i,
          type: "button",
          "data-testid": "vue-studio-close",
          "aria-label": "Close Studio",
          class: "cmst:shrink-0 cmst:rounded-md cmst:p-1.5 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg",
          onClick: C
        }, [
          V(m(sr), {
            class: "cmst:size-4",
            "aria-hidden": "true"
          })
        ], 512)
      ]),
      c("main", nb, [
        V(m(Mu))
      ]),
      r.value ? (g(), w(de, { key: 0 }, [
        c("button", {
          type: "button",
          "aria-label": "Close navigation",
          class: "cmst-drawer-backdrop",
          "data-testid": "vue-nav-drawer-backdrop",
          onClick: x
        }),
        c("div", {
          ref_key: "drawerPanel",
          ref: a,
          class: "cmst-drawer",
          role: "dialog",
          "aria-modal": "true",
          "aria-label": "Studio navigation",
          "data-testid": "vue-nav-drawer",
          tabindex: "-1",
          onKeydown: fs(mo(x, ["stop"]), ["esc"])
        }, [
          c("div", rb, [
            A[2] || (A[2] = c("span", { class: "cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg" }, " Modal Studio ", -1)),
            c("button", {
              type: "button",
              "aria-label": "Close navigation",
              class: "cmst-close-btn",
              onClick: x
            }, [
              V(m(sr), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })
            ])
          ]),
          c("nav", ab, [
            (g(), w(de, null, Le(u, (z) => V(m(Aa), {
              key: z,
              to: { name: z },
              class: "cmst-drawer-row",
              "data-active": f.value === z,
              "data-testid": `vue-nav-${z}`,
              "aria-current": f.value === z ? "page" : void 0
            }, {
              default: X(() => [
                (g(), ft($i(l[z]), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                })),
                D(" " + M(m(Yr)[z]), 1)
              ]),
              _: 2
            }, 1032, ["to", "data-active", "data-testid", "aria-current"])), 64)),
            A[3] || (A[3] = c("p", { class: "cmst-micro cmst:px-3 cmst:pb-1 cmst:pt-4" }, "Studio", -1)),
            (g(), w(de, null, Le(d, (z) => V(m(Aa), {
              key: z,
              to: { name: z },
              class: Ve(["cmst-drawer-row", m(pi)(f.value === z && "cmst:text-cmst-fg")]),
              "data-active": f.value === z,
              "data-testid": `vue-nav-${z}`,
              "aria-current": f.value === z ? "page" : void 0
            }, {
              default: X(() => [
                (g(), ft($i(l[z]), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                })),
                D(" " + M(m(Yr)[z]) + " ", 1),
                z === "workflows" ? (g(), w("span", ib, "Library + setup")) : z === "backend" ? (g(), w("span", lb, "Deployment + models")) : z === "settings" ? (g(), w("span", cb, "Preferences")) : Q("", !0)
              ]),
              _: 2
            }, 1032, ["to", "data-active", "data-testid", "aria-current", "class"])), 64))
          ])
        ], 40, ob)
      ], 64)) : Q("", !0)
    ], 2));
  }
}), db = "/", md = { page: "playground", focus: null };
function Do(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function ra(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), o = Zs(n) ? n : md.page;
  let r = null;
  if (s)
    for (const a of s.split("&")) {
      const i = a.indexOf("=");
      if (i !== -1 && decodeURIComponent(a.slice(0, i)) === "focus") {
        try {
          const l = decodeURIComponent(a.slice(i + 1));
          r = l === "" ? null : l;
        } catch {
          r = null;
        }
        break;
      }
    }
  return { page: o, focus: r };
}
function aa(e) {
  const t = Uu(e.location.hash);
  return !t.matched || !Zs(t.page) ? null : { page: t.page, focus: t.focus };
}
function ia(e, t, s) {
  const n = Vu(t);
  if (!n) return;
  const o = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", o) : e.history.replaceState({}, "", o);
}
function fb(e, t) {
  let s = Vv(t, e.location.hash), n = Do(s), o = {};
  const r = n, a = /* @__PURE__ */ new Set();
  let i = !1;
  const l = () => {
    const d = n;
    s = aa(e) ?? { ...md }, n = Do(s), a.forEach((b) => b(n, d));
  }, u = (d, f) => d === null && f === r;
  return {
    get base() {
      return db;
    },
    get location() {
      return n;
    },
    get state() {
      return o;
    },
    createHref: (d) => {
      const f = Vu(ra(d));
      return f === "" ? "#" + d : f;
    },
    replace: (d, f) => {
      const b = aa(e), h = ra(d), O = Do(h);
      s = h, f !== void 0 && (o = f), n = O, !u(b, O) && vl(b, h) !== "none" && ia(e, h, "replace");
    },
    push: (d, f) => {
      const b = aa(e), h = ra(d), O = Do(h);
      if (s = h, f !== void 0 && (o = f), n = O, u(b, O)) return;
      const x = vl(b, h);
      x === "push" ? ia(e, h, "push") : x === "replace" && ia(e, h, "replace");
    },
    go: (d) => {
      e.history.go(d);
    },
    listen: (d) => {
      const f = (b, h) => {
        d(b, h, { type: "pop", direction: "unknown", delta: 0 });
      };
      return a.add(f), i || (e.addEventListener("popstate", l), i = !0), () => {
        a.delete(f), a.size === 0 && i && (e.removeEventListener("popstate", l), i = !1);
      };
    },
    destroy: () => {
      a.clear(), i && (e.removeEventListener("popstate", l), i = !1);
    }
  };
}
const Yl = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, Xl = Yu, mb = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return Xl(e, s?.class, s?.className);
  const { variants: o, defaultVariants: r } = t, a = Object.keys(o).map((u) => {
    const d = s?.[u], f = r?.[u];
    if (d === null) return null;
    const b = Yl(d) || Yl(f);
    return o[u][b];
  }), i = s && Object.entries(s).reduce((u, d) => {
    let [f, b] = d;
    return b === void 0 || (u[f] = b), u;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((u, d) => {
    let { class: f, className: b, ...h } = d;
    return Object.entries(h).every((O) => {
      let [x, C] = O;
      return Array.isArray(C) ? C.includes({
        ...r,
        ...i
      }[x]) : {
        ...r,
        ...i
      }[x] === C;
    }) ? [
      ...u,
      f,
      b
    ] : u;
  }, []);
  return Xl(e, a, l, s?.class, s?.className);
}, pb = mb(
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
), vb = ["type", "disabled"], ee = /* @__PURE__ */ Mt({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (g(), w("button", {
      type: e.type,
      disabled: e.disabled,
      class: Ve(m(pb)({ variant: e.variant, size: e.size }))
    }, [
      Hc(t.$slots, "default")
    ], 10, vb));
  }
});
function Tr(e) {
  return pi(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-6 cmst:sm:p-8",
    e
  );
}
const gb = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-danger",
  role: "alert"
}, hb = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, yb = {
  key: 1,
  class: "cmst-type-meta",
  "data-testid": "vue-backend-progress",
  role: "status"
}, bb = {
  class: "cmst-seg",
  role: "tablist",
  "aria-label": "Backend sections"
}, wb = ["data-active", "aria-selected", "data-testid", "onClick"], _b = {
  role: "listbox",
  "aria-label": "Workspaces",
  class: "cmst:min-w-0"
}, xb = ["aria-selected", "data-testid", "onClick"], kb = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, Sb = { class: "cmst-type-object cmst:truncate" }, Cb = { class: "cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate" }, $b = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, Ib = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1.5" }, Rb = {
  key: 0,
  "aria-label": "Workspace form",
  class: "cmst:mt-3 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3",
  "data-testid": "vue-workspace-form"
}, Ab = { class: "cmst-type-section" }, Eb = { class: "cmst:mt-3 cmst:flex cmst:max-w-md cmst:flex-col cmst:gap-2.5" }, Ob = { class: "cmst-field-label" }, Tb = { class: "cmst-field-label" }, Pb = { class: "cmst-field-label" }, Mb = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, Nb = { class: "cmst:mt-3 cmst:flex cmst:gap-1.5" }, zb = {
  key: 1,
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3",
  "data-testid": "vue-swap-confirm"
}, Db = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, jb = {
  key: 2,
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3",
  "data-testid": "vue-swap-review"
}, Lb = { class: "cmst:text-[13px]" }, Ub = ["value"], Vb = { class: "cmst-type-meta" }, Fb = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, Bb = {
  "aria-label": "Accounts and tokens",
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4"
}, Wb = { class: "cmst:mt-1 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-[13px]" }, Gb = { "data-testid": "vue-auth-status" }, qb = { class: "cmst:mt-1" }, Hb = { class: "cmst-setting-row" }, Zb = { class: "cmst:min-w-0" }, Kb = { class: "cmst:text-[13px] cmst:font-medium" }, Qb = { "data-testid": "vue-cred-hf-state" }, Jb = { class: "cmst:flex cmst:gap-1.5" }, Yb = { class: "cmst-setting-row" }, Xb = { class: "cmst:min-w-0" }, ew = { class: "cmst:text-[13px] cmst:font-medium" }, tw = { "data-testid": "vue-cred-civitai-state" }, sw = { class: "cmst:flex cmst:gap-1.5" }, nw = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted",
  role: "status"
}, ow = {
  "aria-label": "Manifest repair",
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4"
}, rw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, aw = {
  key: 0,
  class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-repair-rows"
}, iw = { class: "cmst:truncate cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text" }, lw = { class: "cmst:text-cmst-muted" }, cw = { class: "cmst:mt-1.5 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1.5" }, uw = ["onUpdate:modelValue", "aria-label"], dw = ["onUpdate:modelValue", "aria-label"], fw = {
  class: "cmst:flex cmst:items-center cmst:gap-1 cmst:text-xs cmst:text-cmst-muted",
  title: "Remove from workspace on next swap"
}, mw = ["onUpdate:modelValue"], pw = {
  key: 1,
  class: "cmst:mt-2 cmst:flex cmst:gap-1.5"
}, vw = {
  key: 2,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, gw = {
  key: 3,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted",
  role: "status"
}, hw = { "aria-label": "Deployment readiness" }, yw = { class: "cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3" }, bw = { class: "cmst:min-w-0" }, ww = { class: "cmst:mt-1.5 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-[13px]" }, _w = { "data-testid": "vue-deploy-state" }, xw = {
  key: 0,
  class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted"
}, kw = {
  key: 1,
  class: "cmst:mt-2 cmst:w-56 cmst:max-w-full"
}, Sw = ["aria-valuenow"], Cw = { class: "cmst:flex cmst:flex-wrap cmst:gap-1.5" }, $w = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, Iw = {
  key: 1,
  class: "cmst:mt-2"
}, Rw = {
  "aria-label": "Custom-node sync",
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4"
}, Aw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Ew = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, Ow = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-1.5" }, Tw = {
  key: 4,
  "aria-label": "Models"
}, Pw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Mw = { class: "cmst-type-meta cmst:mt-0.5" }, Nw = { class: "cmst:flex cmst:gap-1.5" }, zw = {
  class: "cmst:mt-2 cmst:max-h-64 cmst:overflow-auto",
  "data-testid": "vue-models-list"
}, Dw = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, jw = { class: "cmst-type-meta cmst:truncate" }, Lw = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, Uw = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-1.5" }, Vw = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "vue-model-install-message",
  role: "status"
}, Fw = {
  key: 5,
  "aria-label": "Custom nodes"
}, Bw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Ww = { class: "cmst-type-meta cmst:mt-0.5" }, Gw = { class: "cmst:flex cmst:gap-1.5" }, qw = {
  class: "cmst:mt-2 cmst:max-h-64 cmst:overflow-auto",
  "data-testid": "vue-nodes-list"
}, Hw = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, Zw = { class: "cmst-type-meta cmst:truncate" }, Kw = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, Qw = /* @__PURE__ */ Mt({
  __name: "BackendView",
  setup(e) {
    const t = Er(), s = /* @__PURE__ */ I("workspaces"), n = /* @__PURE__ */ I(""), o = /* @__PURE__ */ I(!1), r = /* @__PURE__ */ I(""), a = /* @__PURE__ */ I(""), i = /* @__PURE__ */ I(""), l = /* @__PURE__ */ I(""), u = /* @__PURE__ */ I(""), d = /* @__PURE__ */ I([]), f = /* @__PURE__ */ I(""), b = /* @__PURE__ */ I(""), h = /* @__PURE__ */ I(""), O = /* @__PURE__ */ I(""), x = /* @__PURE__ */ I(""), C = /* @__PURE__ */ I(""), T = /* @__PURE__ */ I("diffusion_models"), A = /* @__PURE__ */ I(""), z = /* @__PURE__ */ I(!1), R = /* @__PURE__ */ I({}), J = /* @__PURE__ */ I({}), $e = /* @__PURE__ */ I({}), ne = ge(() => {
      const ke = t.repairIssues, $ = Array.isArray(ke) ? ke : ke && typeof ke == "object" ? ke.issues : null;
      return Array.isArray($) ? $.filter((F) => !!F && typeof F == "object").map((F) => ({
        folder: String(F.folder || ""),
        filename: String(F.filename || ""),
        kind: String(F.source_kind || "unknown")
      })) : [];
    });
    function j(ke) {
      return `${ke.folder}/${ke.filename}`;
    }
    async function re(ke) {
      const $ = ne.value.map((F) => {
        const U = j(F);
        return ke ? { folder: F.folder, filename: F.filename, skip: !0 } : {
          folder: F.folder,
          filename: F.filename,
          url: (R.value[U] ?? "").trim(),
          source_kind: J.value[U] || F.kind,
          ...$e.value[U] ? { remove: !0 } : {}
        };
      }).filter((F) => ke || String(F.url || "") || F.remove);
      await t.applyRepair($).catch(() => {
      });
    }
    async function ve(ke) {
      await t.deletePlaceholder(ke.folder, ke.filename).catch(() => {
      });
    }
    const Me = ["workspaces", "deployment", "models", "nodes"];
    Ns(async () => {
      await t.initialize().catch(() => {
      }), await Promise.all([
        t.loadCredentials().catch(() => {
        }),
        t.loadSyncStatus().catch(() => {
        })
      ]);
    });
    function Ie(ke) {
      const $ = ke.toLowerCase();
      return $ === "ready" || $ === "deployed" || $ === "deployed_unwarmed" || $ === "complete" || $ === "completed" || $ === "success" ? "cmst:bg-cmst-ok" : $ === "failed" || $ === "error" ? "cmst:bg-cmst-danger" : $ === "deploying" || $ === "running" || $ === "pending" || $ === "syncing" || $ === "warming" || $ === "unknown" ? "cmst:bg-cmst-warn" : "cmst:bg-cmst-muted";
    }
    const Oe = ge(() => {
      const ke = t.deployStatus?.progress;
      return typeof ke != "number" || Number.isNaN(ke) ? null : Math.min(100, Math.max(0, Math.round(ke <= 1 ? ke * 100 : ke)));
    }), Ye = ge(() => {
      const ke = x.value.trim().toLowerCase();
      return ke ? t.customNodes.filter(
        ($) => String($.title || $.id || $.name || "").toLowerCase().includes(ke)
      ) : t.customNodes;
    });
    async function ae() {
      n.value && await t.selectWorkspace(n.value).catch(() => {
      });
    }
    function _() {
      u.value = "", r.value = "", a.value = "", i.value = "", l.value = "", o.value = !0;
    }
    function S() {
      const ke = t.workspaces.find(($) => $.id === n.value);
      ke && (u.value = ke.id, r.value = ke.label, a.value = "", i.value = "", l.value = "", o.value = !0);
    }
    async function ue() {
      if (l.value = "", !r.value.trim()) {
        l.value = "Workspace label required.";
        return;
      }
      if (!u.value && (!a.value.trim() || !i.value.trim())) {
        l.value = "Token ID and Token Secret are required.";
        return;
      }
      try {
        await t.saveWorkspace(
          u.value ? { workspace_id: u.value, label: r.value.trim(), token_id: a.value.trim(), token_secret: i.value.trim(), set_active: !1 } : { label: r.value.trim(), token_id: a.value.trim(), token_secret: i.value.trim(), set_active: !1 }
        ), o.value = !1;
      } catch (ke) {
        l.value = ke instanceof Error ? ke.message : "Save failed.";
      }
    }
    async function Ue() {
      n.value && await t.startSwap(n.value).catch(() => {
      });
    }
    async function ie() {
      await t.confirmSwapReview(n.value, d.value).catch(() => {
      });
    }
    async function tt() {
      await t.deploy().catch(() => {
      });
    }
    async function De(ke) {
      h.value = "";
      try {
        const $ = await t.saveCredential(ke, ke === "hf" ? f.value : b.value);
        h.value = $, f.value = "", b.value = "";
      } catch ($) {
        h.value = $ instanceof Error ? $.message : "Save failed.";
      }
    }
    async function bt() {
      if (C.value.trim()) {
        A.value = "Installing…";
        try {
          const ke = C.value.trim();
          await t.installModel({ url: ke, filename: nh(ke), save_path: T.value }), A.value = "Install request accepted.";
        } catch (ke) {
          A.value = ke instanceof Error ? ke.message : "Install failed.";
        }
        C.value = "";
      }
    }
    return (ke, $) => (g(), w("section", {
      class: Ve(m(Tr)("cmst:mx-auto cmst:w-full cmst:max-w-6xl")),
      "data-testid": "vue-page-backend"
    }, [
      m(t).error ? (g(), w("div", gb, M(m(t).error), 1)) : Q("", !0),
      c("div", hb, [
        $[29] || ($[29] = c("div", null, [
          c("h1", { class: "cmst-type-view" }, "Manage Modal")
        ], -1)),
        V(ee, {
          variant: "ghost",
          size: "icon",
          "aria-label": "Reload infrastructure",
          disabled: m(t).loading,
          onClick: $[0] || ($[0] = (F) => m(t).load())
        }, {
          default: X(() => [
            V(m(Rr), {
              class: Ve(["cmst:size-4", m(t).loading ? "cmst:animate-spin" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ]),
          _: 1
        }, 8, ["disabled"])
      ]),
      m(t).progress ? (g(), w("p", yb, M(m(t).progress), 1)) : Q("", !0),
      c("div", bb, [
        (g(), w(de, null, Le(Me, (F) => c("button", {
          key: F,
          type: "button",
          role: "tab",
          class: "cmst-seg-btn cmst:capitalize",
          "data-active": s.value === F,
          "aria-selected": s.value === F,
          "data-testid": `vue-backend-tab-${F}`,
          onClick: (U) => s.value = F
        }, M(F), 9, wb)), 64))
      ]),
      s.value === "workspaces" ? (g(), w(de, { key: 2 }, [
        c("div", _b, [
          (g(!0), w(de, null, Le(m(t).workspaces, (F) => (g(), w("button", {
            key: F.id,
            type: "button",
            role: "option",
            class: "cmst-object-row",
            "aria-selected": n.value === F.id,
            "data-testid": `vue-workspace-${F.id}`,
            onClick: (U) => n.value = F.id
          }, [
            c("span", kb, [
              c("span", {
                class: Ve(["cmst-status-dot", F.isActive ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
                "aria-hidden": "true"
              }, null, 2),
              c("strong", Sb, M(F.label), 1)
            ]),
            c("span", Cb, M(F.isActive ? "Active" : "Idle") + " · last deploy: " + M(F.lastDeployStatus), 1)
          ], 8, xb))), 128)),
          m(t).workspaces.length ? Q("", !0) : (g(), w("p", $b, " No workspaces returned by the server. "))
        ]),
        c("div", Ib, [
          V(ee, {
            size: "sm",
            variant: "secondary",
            disabled: !n.value || m(t).busy,
            "data-testid": "vue-workspace-activate",
            onClick: ae
          }, {
            default: X(() => [...$[30] || ($[30] = [
              D("Set Active", -1)
            ])]),
            _: 1
          }, 8, ["disabled"]),
          V(ee, {
            size: "sm",
            variant: "outline",
            disabled: m(t).busy,
            onClick: _
          }, {
            default: X(() => [...$[31] || ($[31] = [
              D("Add workspace", -1)
            ])]),
            _: 1
          }, 8, ["disabled"]),
          V(ee, {
            size: "sm",
            variant: "ghost",
            disabled: !n.value || m(t).busy,
            onClick: S
          }, {
            default: X(() => [...$[32] || ($[32] = [
              D("Edit", -1)
            ])]),
            _: 1
          }, 8, ["disabled"]),
          V(ee, {
            size: "sm",
            variant: "ghost",
            disabled: !n.value || m(t).busy,
            "data-testid": "vue-workspace-swap",
            onClick: Ue
          }, {
            default: X(() => [...$[33] || ($[33] = [
              D("Swap", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ]),
        o.value ? (g(), w("section", Rb, [
          c("h3", Ab, M(u.value ? "Edit workspace" : "Add workspace"), 1),
          c("div", Eb, [
            c("label", Ob, [
              $[34] || ($[34] = D("Label", -1)),
              je(c("input", {
                "onUpdate:modelValue": $[1] || ($[1] = (F) => r.value = F),
                class: "cmst-field"
              }, null, 512), [
                [ut, r.value]
              ])
            ]),
            c("label", Tb, [
              $[35] || ($[35] = D("Token ID", -1)),
              je(c("input", {
                "onUpdate:modelValue": $[2] || ($[2] = (F) => a.value = F),
                class: "cmst-field cmst:font-mono",
                placeholder: "ak-…"
              }, null, 512), [
                [ut, a.value]
              ])
            ]),
            c("label", Pb, [
              $[36] || ($[36] = D("Token Secret", -1)),
              je(c("input", {
                "onUpdate:modelValue": $[3] || ($[3] = (F) => i.value = F),
                type: "password",
                class: "cmst-field cmst:font-mono",
                placeholder: "as-…"
              }, null, 512), [
                [ut, i.value]
              ])
            ])
          ]),
          l.value ? (g(), w("p", Mb, M(l.value), 1)) : Q("", !0),
          c("div", Nb, [
            V(ee, {
              size: "sm",
              "data-testid": "vue-workspace-save",
              onClick: ue
            }, {
              default: X(() => [...$[37] || ($[37] = [
                D("Save workspace", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              size: "sm",
              variant: "ghost",
              onClick: $[4] || ($[4] = (F) => o.value = !1)
            }, {
              default: X(() => [...$[38] || ($[38] = [
                D("Cancel", -1)
              ])]),
              _: 1
            })
          ])
        ])) : Q("", !0),
        m(t).swapConfirmRequired ? (g(), w("div", zb, [
          $[41] || ($[41] = c("p", { class: "cmst:text-[13px]" }, "A prompt is still running. Switch workspaces anyway?", -1)),
          c("div", Db, [
            V(ee, {
              size: "sm",
              "data-testid": "vue-swap-confirm-yes",
              onClick: $[5] || ($[5] = (F) => m(t).confirmSwapInterrupt(n.value))
            }, {
              default: X(() => [...$[39] || ($[39] = [
                D("Interrupt and switch", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              size: "sm",
              variant: "ghost",
              onClick: $[6] || ($[6] = (F) => m(t).cancelSwapDialog())
            }, {
              default: X(() => [...$[40] || ($[40] = [
                D("Cancel", -1)
              ])]),
              _: 1
            })
          ])
        ])) : Q("", !0),
        m(t).swapReview ? (g(), w("div", jb, [
          c("p", Lb, "Select models to download to " + M(m(t).swapReview.workspaceLabel) + ":", 1),
          (g(!0), w(de, null, Le(m(t).swapReview.toInstall, (F) => (g(), w("label", {
            key: F.key,
            class: "cmst:mt-1 cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:text-[13px]"
          }, [
            je(c("input", {
              "onUpdate:modelValue": $[7] || ($[7] = (U) => d.value = U),
              type: "checkbox",
              value: F.key
            }, null, 8, Ub), [
              [un, d.value]
            ]),
            c("span", Vb, M(F.filename) + " · " + M(F.folder), 1)
          ]))), 128)),
          c("div", Fb, [
            V(ee, {
              size: "sm",
              "data-testid": "vue-swap-review-go",
              onClick: ie
            }, {
              default: X(() => [...$[42] || ($[42] = [
                D("Start swap", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              size: "sm",
              variant: "ghost",
              onClick: $[8] || ($[8] = (F) => m(t).cancelSwapDialog())
            }, {
              default: X(() => [...$[43] || ($[43] = [
                D("Cancel", -1)
              ])]),
              _: 1
            })
          ])
        ])) : Q("", !0),
        c("section", Bb, [
          $[49] || ($[49] = c("h3", { class: "cmst-type-section" }, "Accounts & tokens", -1)),
          c("p", Wb, [
            c("span", {
              class: Ve(["cmst-status-dot", m(t).authConnected ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
              "aria-hidden": "true"
            }, null, 2),
            $[44] || ($[44] = D(" Modal connection: ", -1)),
            c("strong", Gb, M(m(t).authConnected === null ? "unknown" : m(t).authConnected ? "connected" : "not configured"), 1)
          ]),
          c("div", qb, [
            c("div", Hb, [
              c("div", Zb, [
                c("p", Kb, [
                  $[45] || ($[45] = D("HuggingFace · ", -1)),
                  c("span", Qb, M(m(t).hfConfigured ? "configured" : "not configured"), 1)
                ])
              ]),
              c("div", Jb, [
                je(c("input", {
                  "onUpdate:modelValue": $[9] || ($[9] = (F) => f.value = F),
                  type: "password",
                  placeholder: "hf_...",
                  "aria-label": "HuggingFace token",
                  class: "cmst-field cmst:w-44",
                  "data-testid": "vue-cred-hf-input"
                }, null, 512), [
                  [ut, f.value]
                ]),
                V(ee, {
                  size: "sm",
                  variant: "secondary",
                  "data-testid": "vue-cred-hf-save",
                  onClick: $[10] || ($[10] = (F) => De("hf"))
                }, {
                  default: X(() => [...$[46] || ($[46] = [
                    D("Save", -1)
                  ])]),
                  _: 1
                })
              ])
            ]),
            c("div", Yb, [
              c("div", Xb, [
                c("p", ew, [
                  $[47] || ($[47] = D("Civitai · ", -1)),
                  c("span", tw, M(m(t).civitaiConfigured ? "configured" : "not configured"), 1)
                ])
              ]),
              c("div", sw, [
                je(c("input", {
                  "onUpdate:modelValue": $[11] || ($[11] = (F) => b.value = F),
                  type: "password",
                  placeholder: "Civitai API key",
                  "aria-label": "Civitai token",
                  class: "cmst-field cmst:w-44",
                  "data-testid": "vue-cred-civitai-input"
                }, null, 512), [
                  [ut, b.value]
                ]),
                V(ee, {
                  size: "sm",
                  variant: "secondary",
                  "data-testid": "vue-cred-civitai-save",
                  onClick: $[12] || ($[12] = (F) => De("civitai"))
                }, {
                  default: X(() => [...$[48] || ($[48] = [
                    D("Save", -1)
                  ])]),
                  _: 1
                })
              ])
            ])
          ]),
          h.value ? (g(), w("p", nw, M(h.value), 1)) : Q("", !0)
        ]),
        c("section", ow, [
          c("div", rw, [
            $[51] || ($[51] = c("h3", { class: "cmst-type-section" }, "Manifest repair", -1)),
            V(ee, {
              size: "sm",
              variant: "ghost",
              "data-testid": "vue-repair-scan",
              onClick: $[13] || ($[13] = (F) => m(t).scanRepair())
            }, {
              default: X(() => [...$[50] || ($[50] = [
                D("Scan issues", -1)
              ])]),
              _: 1
            })
          ]),
          ne.value.length ? (g(), w("ul", aw, [
            (g(!0), w(de, null, Le(ne.value, (F) => (g(), w("li", {
              key: `${F.folder}/${F.filename}`,
              class: "cmst:rounded-md cmst:bg-cmst-surface cmst:p-3"
            }, [
              c("p", iw, [
                D(M(F.filename) + " ", 1),
                c("span", lw, "(" + M(F.folder) + ")", 1)
              ]),
              c("div", cw, [
                je(c("input", {
                  "onUpdate:modelValue": (U) => R.value[`${F.folder}/${F.filename}`] = U,
                  class: "cmst-field cmst:min-w-0 cmst:flex-1 cmst:font-mono cmst:text-xs",
                  placeholder: "https://huggingface.co/…",
                  "aria-label": `Source URL for ${F.filename}`
                }, null, 8, uw), [
                  [ut, R.value[`${F.folder}/${F.filename}`]]
                ]),
                je(c("select", {
                  "onUpdate:modelValue": (U) => J.value[`${F.folder}/${F.filename}`] = U,
                  class: "cmst-field cmst:text-xs",
                  "aria-label": `Source kind for ${F.filename}`
                }, [...$[52] || ($[52] = [
                  c("option", { value: "unknown" }, "unknown", -1),
                  c("option", { value: "huggingface" }, "huggingface", -1),
                  c("option", { value: "civitai" }, "civitai", -1),
                  c("option", { value: "direct" }, "direct", -1)
                ])], 8, dw), [
                  [Qt, J.value[`${F.folder}/${F.filename}`]]
                ]),
                c("label", fw, [
                  je(c("input", {
                    "onUpdate:modelValue": (U) => $e.value[`${F.folder}/${F.filename}`] = U,
                    type: "checkbox"
                  }, null, 8, mw), [
                    [un, $e.value[`${F.folder}/${F.filename}`]]
                  ]),
                  $[53] || ($[53] = D(" Remove ", -1))
                ]),
                V(ee, {
                  size: "sm",
                  variant: "ghost",
                  class: "cmst:text-cmst-danger",
                  onClick: (U) => ve(F)
                }, {
                  default: X(() => [...$[54] || ($[54] = [
                    D("Delete", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"])
              ])
            ]))), 128))
          ])) : Q("", !0),
          ne.value.length ? (g(), w("div", pw, [
            V(ee, {
              size: "sm",
              "data-testid": "vue-repair-apply",
              onClick: $[14] || ($[14] = (F) => re(!1))
            }, {
              default: X(() => [...$[55] || ($[55] = [
                D("Save valid", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              size: "sm",
              variant: "ghost",
              "data-testid": "vue-repair-skip",
              onClick: $[15] || ($[15] = (F) => re(!0))
            }, {
              default: X(() => [...$[56] || ($[56] = [
                D("Skip all", -1)
              ])]),
              _: 1
            })
          ])) : Q("", !0),
          m(t).repairIssues && !ne.value.length ? (g(), w("pre", vw, M(JSON.stringify(m(t).repairIssues, null, 2)), 1)) : Q("", !0),
          m(t).repairMessage ? (g(), w("p", gw, M(m(t).repairMessage), 1)) : Q("", !0)
        ])
      ], 64)) : Q("", !0),
      s.value === "deployment" ? (g(), w(de, { key: 3 }, [
        c("section", hw, [
          c("div", yw, [
            c("div", bw, [
              $[57] || ($[57] = c("h3", { class: "cmst-type-section" }, "Deployment readiness", -1)),
              c("p", ww, [
                c("span", {
                  class: Ve(["cmst-status-dot", Ie(m(t).deployStatus.state)]),
                  "aria-hidden": "true"
                }, null, 2),
                c("strong", _w, M(m(t).deployStatus.state), 1)
              ]),
              m(t).deployMessage ? (g(), w("p", xw, M(m(t).deployMessage), 1)) : Q("", !0),
              Oe.value !== null ? (g(), w("div", kw, [
                c("div", {
                  class: "cmst-progress-track",
                  role: "progressbar",
                  "aria-valuenow": Oe.value,
                  "aria-valuemin": "0",
                  "aria-valuemax": "100"
                }, [
                  c("div", {
                    class: "cmst-progress-fill",
                    style: Pn({ width: `${Oe.value}%` })
                  }, null, 4)
                ], 8, Sw)
              ])) : Q("", !0)
            ]),
            c("div", Cw, [
              V(ee, {
                size: "sm",
                disabled: m(t).loading || !!m(t).deploymentOperationId,
                "data-testid": "vue-deploy",
                onClick: tt
              }, {
                default: X(() => [...$[58] || ($[58] = [
                  D("Deploy", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              V(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-deploy-refresh",
                onClick: $[16] || ($[16] = (F) => m(t).loadDeployment())
              }, {
                default: X(() => [...$[59] || ($[59] = [
                  D("Refresh status", -1)
                ])]),
                _: 1
              }),
              V(ee, {
                size: "sm",
                variant: "ghost",
                onClick: $[17] || ($[17] = (F) => z.value = !z.value)
              }, {
                default: X(() => [
                  D(M(z.value ? "Hide" : "Show") + " log", 1)
                ]),
                _: 1
              })
            ])
          ]),
          z.value ? (g(), w("pre", $w, M(m(t).deployLog ?? "Loading…"), 1)) : Q("", !0),
          z.value && !m(t).deployLog ? (g(), w("div", Iw, [
            V(ee, {
              size: "sm",
              variant: "ghost",
              onClick: $[18] || ($[18] = (F) => m(t).loadLog())
            }, {
              default: X(() => [...$[60] || ($[60] = [
                D("Load deployment log", -1)
              ])]),
              _: 1
            })
          ])) : Q("", !0)
        ]),
        c("section", Rw, [
          c("div", Aw, [
            $[62] || ($[62] = c("h3", { class: "cmst-type-section" }, "Custom-node sync", -1)),
            V(ee, {
              size: "sm",
              variant: "ghost",
              onClick: $[19] || ($[19] = (F) => m(t).loadSyncStatus())
            }, {
              default: X(() => [...$[61] || ($[61] = [
                D("Refresh status", -1)
              ])]),
              _: 1
            })
          ]),
          m(t).customNodeSync ? (g(), w("pre", Ew, M(JSON.stringify(m(t).customNodeSync, null, 2)), 1)) : Q("", !0),
          c("div", Ow, [
            V(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": "vue-node-push",
              onClick: $[20] || ($[20] = (F) => m(t).pushPlugins())
            }, {
              default: X(() => [...$[63] || ($[63] = [
                D("Push plugins (fast)", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": "vue-node-rebuild",
              onClick: $[21] || ($[21] = (F) => m(t).rebuildDependencies())
            }, {
              default: X(() => [...$[64] || ($[64] = [
                D("Rebuild dependencies (slow)", -1)
              ])]),
              _: 1
            })
          ])
        ])
      ], 64)) : Q("", !0),
      s.value === "models" ? (g(), w("section", Tw, [
        c("div", Pw, [
          c("div", null, [
            $[65] || ($[65] = c("h3", { class: "cmst-type-section" }, "Models", -1)),
            c("p", Mw, M(m(t).models.length) + " installed", 1)
          ]),
          c("div", Nw, [
            je(c("input", {
              "onUpdate:modelValue": $[22] || ($[22] = (F) => O.value = F),
              class: "cmst-field cmst:w-48",
              placeholder: "Search models",
              "aria-label": "Search models",
              onKeyup: $[23] || ($[23] = fs((F) => m(t).loadInventory(), ["enter"]))
            }, null, 544), [
              [ut, O.value]
            ]),
            V(ee, {
              size: "sm",
              variant: "outline",
              onClick: $[24] || ($[24] = (F) => m(t).rescanModelsNow(!0))
            }, {
              default: X(() => [...$[66] || ($[66] = [
                D("Rescan", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        c("div", zw, [
          (g(!0), w(de, null, Le(m(t).models, (F, U) => (g(), w("div", {
            key: U,
            class: "cmst-data-row"
          }, [
            $[67] || ($[67] = c("span", {
              class: "cmst-status-dot cmst:bg-cmst-muted",
              "aria-hidden": "true"
            }, null, -1)),
            c("span", Dw, M(String(F.filename || F.name || F.id || `model ${U}`)), 1),
            c("span", jw, M(String(F.folder || F.type || "")), 1)
          ]))), 128)),
          m(t).models.length ? Q("", !0) : (g(), w("p", Lw, "No models installed."))
        ]),
        c("div", Uw, [
          je(c("input", {
            "onUpdate:modelValue": $[25] || ($[25] = (F) => C.value = F),
            class: "cmst-field cmst:min-w-0 cmst:flex-1",
            placeholder: "Paste a direct model link",
            "aria-label": "Model URL",
            "data-testid": "vue-model-url"
          }, null, 512), [
            [ut, C.value]
          ]),
          je(c("select", {
            "onUpdate:modelValue": $[26] || ($[26] = (F) => T.value = F),
            class: "cmst-field",
            "aria-label": "Model folder"
          }, [...$[68] || ($[68] = [
            Yo('<option value="diffusion_models">diffusion_models</option><option value="vae">vae</option><option value="clip">clip</option><option value="loras">loras</option><option value="upscale_models">upscale_models</option>', 5)
          ])], 512), [
            [Qt, T.value]
          ]),
          V(ee, {
            size: "sm",
            "data-testid": "vue-model-install",
            onClick: bt
          }, {
            default: X(() => [...$[69] || ($[69] = [
              D("Install", -1)
            ])]),
            _: 1
          })
        ]),
        A.value ? (g(), w("p", Vw, M(A.value), 1)) : Q("", !0)
      ])) : Q("", !0),
      s.value === "nodes" ? (g(), w("section", Fw, [
        c("div", Bw, [
          c("div", null, [
            $[70] || ($[70] = c("h3", { class: "cmst-type-section" }, "Custom nodes", -1)),
            c("p", Ww, M(Ye.value.length) + " registered", 1)
          ]),
          c("div", Gw, [
            je(c("input", {
              "onUpdate:modelValue": $[27] || ($[27] = (F) => x.value = F),
              class: "cmst-field cmst:w-48",
              placeholder: "Search nodes",
              "aria-label": "Search nodes"
            }, null, 512), [
              [ut, x.value]
            ]),
            V(ee, {
              size: "sm",
              variant: "outline",
              onClick: $[28] || ($[28] = (F) => m(t).refreshCustomNodesNow())
            }, {
              default: X(() => [...$[71] || ($[71] = [
                D("Refresh registry", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        c("div", qw, [
          (g(!0), w(de, null, Le(Ye.value, (F, U) => (g(), w("div", {
            key: U,
            class: "cmst-data-row"
          }, [
            $[72] || ($[72] = c("span", {
              class: "cmst-status-dot cmst:bg-cmst-muted",
              "aria-hidden": "true"
            }, null, -1)),
            c("span", Hw, M(String(F.title || F.id || F.name || `node ${U}`)), 1),
            c("span", Zw, M(String(F.version || F.id || "")), 1)
          ]))), 128)),
          Ye.value.length ? Q("", !0) : (g(), w("p", Kw, "No custom nodes match."))
        ])
      ])) : Q("", !0)
    ], 2));
  }
});
function pd(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return t.item ?? t.generation ?? t.experiment ?? e;
}
function ht(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function Jw(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = ht(s, "asset_id", "assetId"), o = () => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: ht(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: ht(s, "logical_key", "logicalKey"),
    thumbUrl: ht(s, "thumb_url", "thumbnail_url") || o(),
    previewUrl: ht(s, "preview_url", "data_saver_url") || o(),
    dataSaverUrl: ht(s, "data_saver_url", "preview_url") || o(),
    originalUrl: ht(s, "original_url") || o(),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: ht(s, "filename", "name"),
    exportState: ht(s, "export_state", "exportState") || "not_exported"
  };
}
function Yw(e, t) {
  const s = e && typeof e == "object" ? e : {};
  return {
    index: t,
    status: ht(s, "status", "outcome") || "unknown",
    error: ht(s, "error", "message") || null,
    ...s
  };
}
function ho(e) {
  return e.dataSaverUrl || e.thumbUrl || e.originalUrl;
}
function vd(e) {
  return e.originalAvailable && e.originalUrl ? e.originalUrl : e.dataSaverUrl || e.originalUrl || e.thumbUrl;
}
function gd(e) {
  return e.originalUrl || e.dataSaverUrl || e.thumbUrl;
}
function Xw(e, t) {
  const s = e.featured_output_index;
  if (typeof s == "number" && t[s]) return s;
  const n = e.featured_output;
  if (n && typeof n == "object") {
    const o = n.index;
    if (typeof o == "number" && t[o]) return o;
  }
  return 0;
}
function ur(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((u, d) => Jw(u, d)), o = Xw(t, n), r = Array.isArray(t.cells) ? t.cells : [], a = Array.isArray(t.cover) ? t.cover : [], i = Array.isArray(t.attempts) ? t.attempts : [], l = Array.isArray(t.errors) ? t.errors : [];
  return {
    id: ht(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: ht(t, "status", "outcome") || "unknown",
    workflow: ht(t, "workflow", "workflow_name"),
    workflowVersion: ht(t, "workflow_version", "workflowVersion", "version_id"),
    preset: ht(t, "preset", "preset_name"),
    prompt: ht(t, "prompt", "positive_prompt"),
    startedAt: ht(t, "started_at", "created_at") || null,
    completedAt: ht(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: ht(t, "note"),
    outputs: n,
    featuredOutput: n[o] ?? n[0] ?? null,
    featuredOutputIndex: o,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    replayReason: ht(t, "replay_reason", "replayReason"),
    attempts: i.map((u, d) => Yw(u, d)),
    errors: l.filter((u) => !!u && typeof u == "object").map((u) => ({ code: ht(u, "code") || "error", message: ht(u, "message") || "Unknown error" })),
    params: t.params && typeof t.params == "object" ? t.params : {},
    timing: t.timing && typeof t.timing == "object" ? t.timing : {},
    cells: r.map((u) => ur(u)),
    cover: a.map((u) => u ? ur(u) : null),
    axisLabels: {
      x: ht(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "x"),
      y: ht(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "y")
    },
    counts: {
      cells: typeof t.true_cell_count == "number" ? t.true_cell_count : r.length,
      results: typeof t.result_count == "number" ? t.result_count : 0,
      failed: typeof t.failed_count == "number" ? t.failed_count : 0,
      interrupted: typeof t.interrupted_count == "number" ? t.interrupted_count : 0
    },
    raw: t
  };
}
async function e_(e = {}) {
  const t = new URLSearchParams(), s = { limit: 24, ...e };
  s.sort !== void 0 && (s.order = s.sort, delete s.sort), s.favorite_only !== void 0 && (s.favorite = s.favorite_only, delete s.favorite_only);
  for (const [n, o] of Object.entries(s))
    o !== void 0 && String(o) !== "" && t.set(n, String(o));
  return ce(`/history-v2/feed?${t}`);
}
async function t_(e) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}`).then(pd);
}
async function s_(e) {
  return ce(`/history-v2/experiments/${encodeURIComponent(e)}`).then(pd);
}
async function n_(e, t) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function o_(e, t) {
  return ce(`/history-v2/experiments/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function r_(e, t) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function a_(e, t) {
  return ce(`/history-v2/experiments/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function i_(e, t) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}/featured`, { method: "PATCH", body: { output_index: t } });
}
async function l_(e, t = {}) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}/original`, { method: "POST", body: t });
}
async function c_(e) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}/original/retry`, { method: "POST" });
}
async function u_(e) {
  return ce(`/history-v2/generations/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function d_(e) {
  return ce(`/history-v2/experiments/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function f_(e) {
  return ce(`/history-v2/experiments/${encodeURIComponent(e)}/cancel`, { method: "POST" });
}
async function m_(e, t) {
  return ce(`/history-v2/experiments/${encodeURIComponent(e)}/cells/${encodeURIComponent(t)}/retry`, { method: "POST" });
}
async function p_(e, t) {
  return ce("/history-v2/bulk-delete", { method: "POST", body: { generation_ids: e, experiment_ids: t } });
}
async function v_(e) {
  return ce(`/history-v2/assets/${encodeURIComponent(e)}/export`, { method: "POST" });
}
async function g_(e) {
  return ce(`/history-v2/assets/${encodeURIComponent(e)}/open`, { method: "POST" });
}
async function h_(e) {
  return ce(`/history-v2/assets/${encodeURIComponent(e)}/reveal`, { method: "POST" });
}
function y_(e) {
  const t = e.split(";")[0].trim().toLowerCase();
  return t === "image/png" ? "png" : t === "image/jpeg" ? "jpg" : t === "image/webp" ? "webp" : t === "image/gif" ? "gif" : t === "image/bmp" ? "bmp" : "png";
}
function b_(e, t, s) {
  return `${[e.workflow || "generation", e.id, `output-${t.index}`].map((o) => o.replace(/[^a-zA-Z0-9-_]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48)).filter(Boolean).join("-") || "history-output"}.${s}`;
}
async function w_(e, t, s = "original") {
  const n = s === "original" ? t.originalUrl : s === "dataSaver" ? t.dataSaverUrl : t.thumbUrl, o = await fetch(n);
  if (!o.ok) throw new Error(`Download failed with status ${o.status}`);
  const r = await o.blob(), a = b_(e, t, y_(r.type)), i = URL.createObjectURL(r);
  try {
    const l = document.createElement("a");
    l.href = i, l.download = a, document.body.appendChild(l), l.click(), l.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(i), 1e3);
  }
}
async function __(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return ce(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const gn = As("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1, kind: "mixed", status: "" }), Nn = /* @__PURE__ */ Mn("studio-history", () => {
  const e = /* @__PURE__ */ I([]), t = /* @__PURE__ */ I(null), s = /* @__PURE__ */ I(null), n = /* @__PURE__ */ I(gn.read().query), o = /* @__PURE__ */ I(gn.read().sort), r = /* @__PURE__ */ I(gn.read().favoriteOnly), a = /* @__PURE__ */ I(gn.read().kind), i = /* @__PURE__ */ I(gn.read().status), l = /* @__PURE__ */ I(null), u = /* @__PURE__ */ I(!1), d = /* @__PURE__ */ I(!1), f = /* @__PURE__ */ I(null), b = /* @__PURE__ */ I(null), h = /* @__PURE__ */ I(null), O = /* @__PURE__ */ I(null), x = /* @__PURE__ */ I(/* @__PURE__ */ new Set()), C = /* @__PURE__ */ I(!1), T = /* @__PURE__ */ I(null), A = Tn(), z = Tn();
  let R = !1, J = null;
  const $e = ge(() => e.value.find((E) => E.id === t.value) ?? null), ne = ge(() => e.value.find((E) => E.id === s.value) ?? $e.value), j = ge(() => ({
    a: e.value.find((E) => E.id === h.value) ?? null,
    b: e.value.find((E) => E.id === O.value) ?? null
  })), re = ge(() => [...x.value]);
  function ve() {
    gn.write({ query: n.value, sort: o.value, favoriteOnly: r.value, kind: a.value, status: i.value });
  }
  function Me(E) {
    s.value = E, E && (t.value = E);
  }
  function Ie(E) {
    n.value = E, ve();
  }
  function Oe(E) {
    o.value = E, ve();
  }
  function Ye(E) {
    r.value = E, ve();
  }
  function ae(E) {
    a.value = E, ve();
  }
  function _(E) {
    i.value = E, ve();
  }
  function S(E) {
    const G = e.value.findIndex((H) => H.id === E.id && H.kind === E.kind);
    G >= 0 ? e.value[G] = E : e.value.unshift(E);
  }
  function ue(E, G) {
    e.value = e.value.filter((H) => !(H.id === G && H.kind === E)), t.value === G && (t.value = null), s.value === G && (s.value = null), h.value === G && (h.value = null), O.value === G && (O.value = null), x.value.delete(`${E}:${G}`);
  }
  async function Ue(E = !1) {
    d.value = !0, f.value = null;
    try {
      const G = await A.run(async (ye) => {
        const le = await e_({
          search: n.value,
          order: o.value,
          favorite: r.value ? !0 : void 0,
          kind: a.value === "mixed" ? void 0 : a.value,
          status: i.value || void 0,
          cursor: E ? l.value ?? void 0 : void 0
        });
        return ye.aborted ? null : le;
      });
      if (G.stale || !G.value) return;
      const H = G.value, K = (H.items ?? H.records ?? []).map(ur);
      e.value = E ? e.value.concat(K) : K, l.value = H.next_cursor ?? null, u.value = H.has_more === !0 || !!l.value;
    } catch (G) {
      throw f.value = G instanceof Error ? G.message : "Could not load History V2", G;
    } finally {
      d.value = !1, R && (R = !1, Ue());
    }
  }
  async function ie(E, G = "generation") {
    b.value = null;
    try {
      const H = await z.run(async (K) => {
        const ye = G === "experiment" ? await s_(E) : await t_(E);
        return K.aborted ? null : ye;
      });
      if (H.stale || !H.value) return;
      S(ur(H.value)), t.value = E;
    } catch (H) {
      throw b.value = H instanceof Error ? H.message : "Could not load History detail", H;
    }
  }
  async function tt(E) {
    if (Me(E), !E) return;
    const G = e.value.find((H) => H.id === E);
    await ie(E, G?.kind ?? "generation");
  }
  async function De(E, G) {
    const H = E.favorite;
    E.favorite = G;
    try {
      E.kind === "experiment" ? await o_(E.id, G) : await n_(E.id, G), mt("history");
    } catch (K) {
      throw E.favorite = H, K;
    }
  }
  async function bt(E, G) {
    const H = E.note;
    E.note = G;
    try {
      E.kind === "experiment" ? await a_(E.id, G) : await r_(E.id, G), mt("history");
    } catch (K) {
      throw E.note = H, K;
    }
  }
  async function ke(E, G) {
    await i_(E.id, G), await ie(E.id, E.kind), mt("history");
  }
  async function $(E) {
    await __(E), ue(E.kind, E.id), mt("history");
  }
  function F(E) {
    const G = `${E.kind}:${E.id}`, H = new Set(x.value);
    H.has(G) ? H.delete(G) : H.add(G), x.value = H;
  }
  function U() {
    x.value = /* @__PURE__ */ new Set();
  }
  async function B() {
    const E = [], G = [];
    for (const H of x.value) {
      const K = H.indexOf(":"), ye = H.slice(0, K), le = H.slice(K + 1);
      ye === "experiment" ? G.push(le) : E.push(le);
    }
    if (!(!E.length && !G.length)) {
      await p_(E, G);
      for (const H of E) ue("generation", H);
      for (const H of G) ue("experiment", H);
      U(), mt("history");
    }
  }
  async function q(E, G) {
    let H;
    return G === "original" ? H = await l_(E.id) : G === "retry" ? H = await c_(E.id) : H = await u_(E.id), T.value = `${G} accepted for ${E.id}`, mt("history"), H;
  }
  async function me(E, G, H) {
    let K;
    return G === "resume" ? K = await d_(E.id) : H ? K = await m_(E.id, H) : K = await f_(E.id), await ie(E.id, "experiment"), mt("history"), K;
  }
  async function v(E) {
    const G = await v_(E.assetId);
    return E.exportState = "exported", G;
  }
  function k(E, G) {
    E === "a" ? h.value = G : O.value = G;
  }
  function P() {
    const E = h.value;
    h.value = O.value, O.value = E;
  }
  function L() {
    h.value = null, O.value = null;
  }
  async function Z() {
    J || (J = Ar((E) => {
      if (E === "history") {
        if (d.value) {
          R = !0;
          return;
        }
        Ue();
      }
    })), e.value.length || await Ue();
  }
  function Y() {
    e.value = [], t.value = null, s.value = null, l.value = null, h.value = null, O.value = null, x.value = /* @__PURE__ */ new Set();
  }
  return {
    records: e,
    selected: $e,
    selectedId: t,
    focused: ne,
    focusId: s,
    query: n,
    sort: o,
    favoriteOnly: r,
    kindFilter: a,
    statusFilter: i,
    cursor: l,
    hasMore: u,
    loading: d,
    error: f,
    detailError: b,
    compareA: h,
    compareB: O,
    compareRecords: j,
    selection: re,
    viewerOpen: C,
    actionMessage: T,
    setFocus: Me,
    setQuery: Ie,
    setSort: Oe,
    setFavoriteOnly: Ye,
    setKindFilter: ae,
    setStatusFilter: _,
    loadFeed: Ue,
    loadDetail: ie,
    applyRouteFocus: tt,
    setFavorite: De,
    setNote: bt,
    setFeatured: ke,
    remove: $,
    toggleSelection: F,
    clearSelection: U,
    removeSelected: B,
    runReplayAction: q,
    runExperimentAction: me,
    exportAsset: v,
    openHistoryAsset: g_,
    revealHistoryAsset: h_,
    downloadHistoryAsset: w_,
    selectCompare: k,
    swapCompare: P,
    clearCompare: L,
    selectFeedAsset: ho,
    selectDetailAsset: vd,
    selectCompareAsset: gd,
    initialize: Z,
    clear: Y
  };
}), x_ = { class: "cmst-media-well cmst:relative" }, k_ = ["aria-label", "data-testid"], S_ = ["src", "alt"], C_ = {
  key: 1,
  class: "cmst:flex cmst:aspect-square cmst:w-full cmst:flex-col cmst:items-center cmst:justify-center cmst:gap-1.5 cmst:text-cmst-muted",
  "aria-hidden": "true"
}, $_ = { class: "cmst:text-xs" }, I_ = ["aria-pressed", "aria-label", "data-testid"], R_ = ["aria-pressed", "aria-label", "data-testid"], A_ = ["aria-label"], E_ = { class: "cmst-type-object cmst:block cmst:truncate" }, O_ = { class: "cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate" }, T_ = /* @__PURE__ */ Mt({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = e, n = t, o = Nn(), r = ge(() => `${s.record.kind}:${s.record.id}`), a = ge(() => o.selection.includes(r.value)), i = ge(() => {
      const h = s.record.featuredOutput;
      return !h || typeof h.width != "number" || typeof h.height != "number" ? null : `${h.width}×${h.height}`;
    }), l = ge(() => {
      const h = s.record.prompt?.trim();
      return h && !/^[{[]/.test(h) ? h.length > 80 ? `${h.slice(0, 80)}…` : h : s.record.workflow ? s.record.workflow : s.record.kind === "experiment" ? "Experiment" : "Generation";
    });
    function u(h) {
      if (!h) return null;
      const O = Date.parse(h);
      if (Number.isNaN(O)) return null;
      const x = Math.max(0, Math.round((Date.now() - O) / 6e4));
      if (x < 1) return "just now";
      if (x < 60) return `${x}m ago`;
      const C = Math.round(x / 60);
      if (C < 24) return `${C}h ago`;
      const T = Math.round(C / 24);
      return T < 30 ? `${T}d ago` : new Date(O).toLocaleDateString();
    }
    const d = ge(() => u(s.record.completedAt ?? s.record.startedAt));
    async function f(h) {
      h.stopPropagation(), await o.setFavorite(s.record, !s.record.favorite).catch(() => {
      });
    }
    function b(h) {
      h.stopPropagation(), o.toggleSelection(s.record);
    }
    return (h, O) => (g(), w("div", {
      class: Ve(["cmst:group cmst:overflow-hidden cmst:rounded cmst:bg-cmst-matte", a.value ? "cmst:ring-2 cmst:ring-cmst-primary cmst:ring-inset" : ""])
    }, [
      c("div", x_, [
        c("button", {
          type: "button",
          class: "cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:p-0 cmst:text-left",
          "aria-label": `Open ${e.record.workflow || e.record.id}`,
          "data-testid": `vue-history-card-${e.record.id}`,
          onClick: O[0] || (O[0] = (x) => n("select", e.record)),
          onKeydown: O[1] || (O[1] = fs((x) => n("select", e.record), ["enter"]))
        }, [
          e.record.featuredOutput ? (g(), w("img", {
            key: 0,
            src: m(ho)(e.record.featuredOutput),
            alt: e.record.workflow || e.record.id,
            class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
            loading: "lazy"
          }, null, 8, S_)) : (g(), w("span", C_, [
            V(m(vv), { class: "cmst:size-[18px]" }),
            c("span", $_, M(e.record.status === "failed" ? "Failed" : "No preview"), 1)
          ]))
        ], 40, k_),
        c("div", {
          class: Ve(["cmst-hover-actions cmst:absolute cmst:right-1.5 cmst:top-1.5 cmst:flex cmst:gap-1", e.record.favorite || a.value ? "cmst-hover-actions-pinned" : ""])
        }, [
          c("button", {
            type: "button",
            class: "cmst-icon-btn cmst:bg-cmst-raised/90",
            "aria-pressed": e.record.favorite ? "true" : "false",
            "aria-label": e.record.favorite ? `Remove ${e.record.id} from favorites` : `Add ${e.record.id} to favorites`,
            "data-testid": `vue-history-favorite-${e.record.id}`,
            onClick: O[2] || (O[2] = (x) => f(x))
          }, [
            V(m(tr), {
              class: Ve(["cmst:size-3.5", e.record.favorite ? "cmst:fill-cmst-primary cmst:text-cmst-primary" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ], 8, I_),
          c("button", {
            type: "button",
            class: "cmst-icon-btn cmst:bg-cmst-raised/90",
            "aria-pressed": a.value ? "true" : "false",
            "aria-label": a.value ? `Deselect ${e.record.id}` : `Select ${e.record.id}`,
            "data-testid": `vue-history-select-${e.record.id}`,
            onClick: O[3] || (O[3] = (x) => b(x))
          }, [
            V(m(lv), {
              class: Ve(["cmst:size-3.5", a.value ? "cmst:text-cmst-primary" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ], 8, R_)
        ], 2)
      ]),
      c("button", {
        type: "button",
        class: "cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:px-2.5 cmst:py-2 cmst:text-left",
        "aria-label": `Open ${e.record.workflow || e.record.id}`,
        onClick: O[4] || (O[4] = (x) => n("select", e.record))
      }, [
        c("span", E_, M(l.value), 1),
        c("span", O_, [
          D(M(e.record.status), 1),
          i.value ? (g(), w(de, { key: 0 }, [
            D(" · " + M(i.value), 1)
          ], 64)) : Q("", !0),
          d.value ? (g(), w(de, { key: 1 }, [
            D(" · " + M(d.value), 1)
          ], 64)) : Q("", !0)
        ])
      ], 8, A_)
    ], 2));
  }
}), P_ = /* @__PURE__ */ Mt({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = e, n = t, o = So(), r = ge(() => {
      const a = Number.parseInt(String(o.columnsPreference ?? "4"), 10);
      return Number.isNaN(a) ? 4 : Math.min(8, Math.max(2, a));
    });
    return (a, i) => (g(), w("div", {
      class: "cmst:grid cmst:gap-0.5",
      style: Pn({ gridTemplateColumns: `repeat(${r.value}, minmax(0, 1fr))` }),
      "data-testid": "vue-history-grid"
    }, [
      (g(!0), w(de, null, Le(s.records, (l) => (g(), ft(T_, {
        key: `${l.kind}:${l.id}`,
        record: l,
        onSelect: i[0] || (i[0] = (u) => n("select", u))
      }, null, 8, ["record"]))), 128))
    ], 4));
  }
}), M_ = ["aria-label", "onKeydown"], N_ = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, z_ = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, D_ = { class: "cmst:text-lg cmst:font-semibold" }, j_ = { class: "cmst:text-xs cmst:opacity-70" }, L_ = {
  key: 0,
  class: "cmst:mt-2 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, U_ = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70",
  role: "status"
}, V_ = ["src", "alt", "data-testid"], F_ = {
  key: 3,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, B_ = {
  key: 4,
  class: "cmst:mt-3 cmst:text-sm cmst:text-red-300"
}, W_ = {
  key: 5,
  class: "cmst:mt-3 cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-viewer-params"
}, G_ = { class: "cmst:mt-1" }, q_ = { class: "cmst:opacity-70" }, H_ = {
  key: 6,
  class: "cmst:mt-3 cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-viewer-attempts"
}, Z_ = { class: "cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, K_ = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Q_ = { class: "cmst:mt-2 cmst:flex cmst:items-center cmst:gap-2" }, J_ = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-xs" }, Y_ = ["data-testid"], X_ = {
  key: 0,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, e1 = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, t1 = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:opacity-70"
}, s1 = { class: "cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1" }, n1 = {
  key: 1,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, o1 = { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, r1 = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, a1 = ["data-testid"], i1 = ["data-testid", "aria-label", "onClick", "onKeydown"], l1 = ["data-testid"], c1 = {
  key: 0,
  class: "cmst:opacity-70"
}, u1 = { class: "cmst:mt-4 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, d1 = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, f1 = { key: 0 }, m1 = {
  key: 1,
  class: "cmst:flex cmst:items-center cmst:gap-2"
}, p1 = { class: "cmst:text-xs" }, v1 = /* @__PURE__ */ Mt({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = e, n = t, o = Nn(), r = /* @__PURE__ */ I(s.record?.note ?? ""), a = /* @__PURE__ */ I(!1), i = /* @__PURE__ */ I(null), l = /* @__PURE__ */ I(null), u = /* @__PURE__ */ I(null), d = /* @__PURE__ */ I(null), f = (x) => x ? Object.entries(x.params).map(([C, T]) => [C, String(T ?? "")]) : [], b = (x) => x && x.charAt(0).toUpperCase() + x.slice(1);
    Ns(() => {
      u.value = document.activeElement, r.value = s.record?.note ?? "", l.value?.focus();
    }), xo(() => {
      u.value?.focus?.();
    });
    async function h(x, C) {
      i.value = x;
      try {
        await C();
      } catch {
      } finally {
        i.value = null;
      }
    }
    function O() {
      n("close");
    }
    return (x, C) => e.record ? (g(), w("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-state": "open",
      "data-testid": "vue-history-viewer",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": `${e.record.kind} detail`,
      tabindex: "-1",
      onKeydown: fs(mo(O, ["stop"]), ["esc"])
    }, [
      c("div", N_, [
        c("div", z_, [
          c("div", null, [
            c("h2", D_, M(e.record.workflow || e.record.id), 1),
            c("p", j_, M(b(e.record.status)) + " · " + M(e.record.kind) + " · " + M(e.record.id), 1)
          ]),
          V(ee, {
            ref_key: "closeBtn",
            ref: l,
            variant: "outline",
            size: "sm",
            "data-testid": "vue-viewer-close",
            onClick: O
          }, {
            default: X(() => [...C[13] || (C[13] = [
              D("Close", -1)
            ])]),
            _: 1
          }, 512)
        ]),
        m(o).detailError ? (g(), w("div", L_, M(m(o).detailError), 1)) : Q("", !0),
        m(o).actionMessage ? (g(), w("p", U_, M(m(o).actionMessage), 1)) : Q("", !0),
        e.record.featuredOutput ? (g(), w("img", {
          key: 2,
          src: m(vd)(e.record.featuredOutput),
          alt: e.record.workflow || e.record.id,
          class: "cmst:mx-auto cmst:mt-4 cmst:max-h-[50vh] cmst:max-w-full cmst:object-contain",
          "data-testid": `vue-viewer-image-${e.record.id}`
        }, null, 8, V_)) : (g(), w("p", F_, "No projected image asset.")),
        e.record.errors.length ? (g(), w("div", B_, [
          (g(!0), w(de, null, Le(e.record.errors, (T, A) => (g(), w("p", { key: A }, M(T.code) + ": " + M(T.message), 1))), 128))
        ])) : Q("", !0),
        f(e.record).length ? (g(), w("div", W_, [
          C[14] || (C[14] = c("h3", { class: "cmst:font-semibold" }, "Parameters", -1)),
          c("dl", G_, [
            (g(!0), w(de, null, Le(f(e.record), ([T, A]) => (g(), w("div", {
              key: T,
              class: "cmst:flex cmst:gap-2"
            }, [
              c("dt", q_, M(T), 1),
              c("dd", null, M(A), 1)
            ]))), 128))
          ])
        ])) : Q("", !0),
        e.record.attempts.length ? (g(), w("div", H_, [
          C[15] || (C[15] = c("h3", { class: "cmst:font-semibold" }, "Attempts", -1)),
          (g(!0), w(de, null, Le(e.record.attempts, (T) => (g(), w("p", {
            key: T.index
          }, "Attempt " + M(T.index) + ": " + M(T.status), 1))), 128))
        ])) : Q("", !0),
        c("div", Z_, [
          c("div", K_, [
            C[18] || (C[18] = c("h3", { class: "cmst:font-semibold" }, "Annotations", -1)),
            c("div", Q_, [
              V(ee, {
                size: "sm",
                variant: "outline",
                "aria-pressed": e.record.favorite ? "true" : "false",
                "data-testid": `vue-viewer-favorite-${e.record.id}`,
                onClick: C[0] || (C[0] = (T) => h("favorite", () => m(o).setFavorite(e.record, !e.record.favorite)))
              }, {
                default: X(() => [
                  D(M(e.record.favorite ? "★ Favorited" : "☆ Favorite"), 1)
                ]),
                _: 1
              }, 8, ["aria-pressed", "data-testid"])
            ]),
            c("label", J_, [
              C[16] || (C[16] = D(" Note ", -1)),
              je(c("textarea", {
                "onUpdate:modelValue": C[1] || (C[1] = (T) => r.value = T),
                rows: "2",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-sm",
                "data-testid": `vue-viewer-note-${e.record.id}`
              }, null, 8, Y_), [
                [ut, r.value]
              ])
            ]),
            V(ee, {
              class: "cmst:mt-2",
              size: "sm",
              variant: "secondary",
              "data-testid": `vue-viewer-note-save-${e.record.id}`,
              onClick: C[2] || (C[2] = (T) => h("note", () => m(o).setNote(e.record, r.value)))
            }, {
              default: X(() => [...C[17] || (C[17] = [
                D("Save note", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          e.record.kind === "generation" ? (g(), w("div", X_, [
            C[27] || (C[27] = c("h3", { class: "cmst:font-semibold" }, "Replay", -1)),
            c("div", e1, [
              V(ee, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || i.value !== null,
                "data-testid": `vue-viewer-original-${e.record.id}`,
                onClick: C[3] || (C[3] = (T) => h("original", () => m(o).runReplayAction(e.record, "original")))
              }, {
                default: X(() => [...C[19] || (C[19] = [
                  D("Generate Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              V(ee, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || i.value !== null,
                "data-testid": `vue-viewer-retry-${e.record.id}`,
                onClick: C[4] || (C[4] = (T) => h("retry", () => m(o).runReplayAction(e.record, "retry")))
              }, {
                default: X(() => [...C[20] || (C[20] = [
                  D("Retry Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              V(ee, {
                size: "sm",
                variant: "outline",
                disabled: i.value !== null,
                "data-testid": `vue-viewer-resume-${e.record.id}`,
                onClick: C[5] || (C[5] = (T) => h("resume", () => m(o).runReplayAction(e.record, "resume")))
              }, {
                default: X(() => [...C[21] || (C[21] = [
                  D("Resume", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"])
            ]),
            e.record.replayCapable ? Q("", !0) : (g(), w("p", t1, M(e.record.replayReason || "Not replay-capable."), 1)),
            C[28] || (C[28] = c("h3", { class: "cmst:mt-3 cmst:font-semibold" }, "Outputs", -1)),
            (g(!0), w(de, null, Le(e.record.outputs, (T) => (g(), w("div", {
              key: T.index,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs"
            }, [
              c("p", null, M(T.filename || `output ${T.index}`) + " · " + M(T.exportState), 1),
              c("div", s1, [
                V(ee, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-download-${T.assetId}`,
                  onClick: (A) => h(`download-${T.index}`, () => m(o).downloadHistoryAsset(e.record, T, "original"))
                }, {
                  default: X(() => [...C[22] || (C[22] = [
                    D("Download", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                V(ee, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-export-${T.assetId}`,
                  onClick: (A) => h(`export-${T.index}`, () => m(o).exportAsset(T))
                }, {
                  default: X(() => [...C[23] || (C[23] = [
                    D("Export", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                V(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (A) => h(`open-${T.index}`, () => m(o).openHistoryAsset(T.assetId))
                }, {
                  default: X(() => [...C[24] || (C[24] = [
                    D("Open", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                V(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (A) => h(`reveal-${T.index}`, () => m(o).revealHistoryAsset(T.assetId))
                }, {
                  default: X(() => [...C[25] || (C[25] = [
                    D("Reveal", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                V(ee, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-featured-${T.index}`,
                  onClick: (A) => h("featured", () => m(o).setFeatured(e.record, T.index))
                }, {
                  default: X(() => [...C[26] || (C[26] = [
                    D("Feature", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"])
              ])
            ]))), 128))
          ])) : (g(), w("div", n1, [
            C[32] || (C[32] = c("h3", { class: "cmst:font-semibold" }, "Experiment", -1)),
            c("p", o1, "Cells: " + M(e.record.counts.cells) + " · Results: " + M(e.record.counts.results) + " · Failed: " + M(e.record.counts.failed), 1),
            c("div", r1, [
              V(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-resume-${e.record.id}`,
                onClick: C[6] || (C[6] = (T) => h("exp-resume", () => m(o).runExperimentAction(e.record, "resume")))
              }, {
                default: X(() => [...C[29] || (C[29] = [
                  D("Resume", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"]),
              V(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-cancel-${e.record.id}`,
                onClick: C[7] || (C[7] = (T) => h("exp-cancel", () => m(o).runExperimentAction(e.record, "cancel")))
              }, {
                default: X(() => [...C[30] || (C[30] = [
                  D("Cancel", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"])
            ]),
            (g(!0), w(de, null, Le(e.record.cells, (T) => (g(), w("div", {
              key: T.id,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs",
              "data-testid": `vue-cell-${T.id}`
            }, [
              c("button", {
                type: "button",
                class: "cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:text-left",
                "data-testid": `vue-cell-open-${T.id}`,
                "aria-label": `Open cell ${T.id}`,
                onClick: (A) => d.value = d.value === T.id ? null : T.id,
                onKeydown: fs(mo((A) => d.value = d.value === T.id ? null : T.id, ["prevent"]), ["enter"])
              }, [
                c("p", null, M(T.id) + " · " + M(T.status), 1)
              ], 40, i1),
              d.value === T.id ? (g(), w("div", {
                key: 0,
                "data-testid": `vue-cell-detail-${T.id}`,
                tabindex: "0"
              }, [
                c("p", null, M(T.featuredOutput ? "Preview available" : "No preview projected") + " · " + M(T.status), 1),
                T.prompt ? (g(), w("p", c1, M(T.prompt), 1)) : Q("", !0)
              ], 8, l1)) : Q("", !0),
              T.status === "failed" ? (g(), ft(ee, {
                key: 1,
                class: "cmst:mt-1",
                size: "sm",
                variant: "ghost",
                "data-testid": `vue-cell-retry-${T.id}`,
                onClick: (A) => h(`cell-${T.id}`, () => m(o).runExperimentAction(e.record, "cancel", T.id))
              }, {
                default: X(() => [...C[31] || (C[31] = [
                  D("Retry cell", -1)
                ])]),
                _: 1
              }, 8, ["data-testid", "onClick"])) : Q("", !0)
            ], 8, a1))), 128))
          ]))
        ]),
        c("div", u1, [
          c("div", d1, [
            V(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-a-${e.record.id}`,
              onClick: C[8] || (C[8] = (T) => m(o).selectCompare("a", e.record.id))
            }, {
              default: X(() => [...C[33] || (C[33] = [
                D("Compare A", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            V(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-b-${e.record.id}`,
              onClick: C[9] || (C[9] = (T) => m(o).selectCompare("b", e.record.id))
            }, {
              default: X(() => [...C[34] || (C[34] = [
                D("Compare B", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          a.value ? (g(), w("div", m1, [
            c("span", p1, "Delete this " + M(e.record.kind) + "?", 1),
            V(ee, {
              size: "sm",
              "data-testid": `vue-delete-confirm-${e.record.id}`,
              onClick: C[11] || (C[11] = (T) => h("delete", () => m(o).remove(e.record).then(O)))
            }, {
              default: X(() => [...C[36] || (C[36] = [
                D("Confirm delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            V(ee, {
              size: "sm",
              variant: "ghost",
              onClick: C[12] || (C[12] = (T) => a.value = !1)
            }, {
              default: X(() => [...C[37] || (C[37] = [
                D("Cancel", -1)
              ])]),
              _: 1
            })
          ])) : (g(), w("div", f1, [
            V(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-delete-${e.record.id}`,
              onClick: C[10] || (C[10] = (T) => a.value = !0)
            }, {
              default: X(() => [...C[35] || (C[35] = [
                D("Delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]))
        ])
      ])
    ], 40, M_)) : Q("", !0);
  }
}), hd = /* @__PURE__ */ Mt({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (g(), w("div", {
      class: Ve(
        m(pi)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg"
        )
      )
    }, [
      Hc(t.$slots, "default")
    ], 2));
  }
});
function g1() {
  if (typeof document > "u")
    throw new Error(
      "[studio] portal target unavailable: no document (the Vue Studio only runs in the ComfyUI browser host)"
    );
  const e = document.querySelector("[data-studio-portals]");
  if (!e)
    throw new Error(
      "[studio] missing [data-studio-portals]: the ComfyUI host must create the Studio-contained portal target before mounting the Vue app"
    );
  return e;
}
const h1 = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, y1 = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70",
  "data-testid": "vue-picker-empty"
}, b1 = {
  key: 1,
  class: "cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:sm:grid-cols-3"
}, w1 = ["data-testid", "aria-label", "onClick"], _1 = ["src", "alt"], x1 = { class: "cmst:mt-1 cmst:block cmst:truncate cmst:text-xs" }, k1 = { class: "cmst:mt-3 cmst:flex cmst:justify-center" }, yd = /* @__PURE__ */ Mt({
  __name: "HistoryPicker",
  emits: ["select", "cancel"],
  setup(e, { emit: t }) {
    const s = Nn(), n = /* @__PURE__ */ I(""), o = /* @__PURE__ */ I(null);
    Ns(async () => {
      o.value = g1(), await s.initialize();
    });
    const r = t;
    let a;
    function i(u) {
      window.clearTimeout(a), a = window.setTimeout(() => {
        s.setQuery(u), s.loadFeed();
      }, 250);
    }
    function l(u) {
      r("select", u);
    }
    return (u, d) => o.value ? (g(), ft(Vc, {
      key: 0,
      to: o.value
    }, [
      c("div", {
        class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
        "data-state": "open",
        "data-testid": "vue-history-picker",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": "Pick a History generation",
        tabindex: "-1",
        onKeydown: d[4] || (d[4] = fs(mo((f) => r("cancel"), ["stop"]), ["esc"]))
      }, [
        V(hd, { class: "cmst:w-[min(48rem,94vw)] cmst:max-h-[86vh] cmst:overflow-auto cmst:p-4" }, {
          default: X(() => [
            c("div", h1, [
              d[6] || (d[6] = c("h2", { class: "cmst:text-base cmst:font-semibold" }, "Pick from History", -1)),
              V(ee, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-picker-cancel",
                onClick: d[0] || (d[0] = (f) => r("cancel"))
              }, {
                default: X(() => [...d[5] || (d[5] = [
                  D("Cancel", -1)
                ])]),
                _: 1
              })
            ]),
            je(c("input", {
              "onUpdate:modelValue": d[1] || (d[1] = (f) => n.value = f),
              class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              placeholder: "Search generations",
              "aria-label": "Search generations",
              onInput: d[2] || (d[2] = (f) => i(f.target.value))
            }, null, 544), [
              [ut, n.value]
            ]),
            m(s).records.length ? (g(), w("div", b1, [
              (g(!0), w(de, null, Le(m(s).records, (f) => (g(), w("button", {
                key: `${f.kind}:${f.id}`,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-picker-option-${f.id}`,
                "aria-label": `Select ${f.workflow || f.id}`,
                onClick: (b) => l(f)
              }, [
                f.featuredOutput ? (g(), w("img", {
                  key: 0,
                  src: m(ho)(f.featuredOutput),
                  alt: f.workflow || f.id,
                  class: "cmst:aspect-square cmst:w-full cmst:object-cover cmst:rounded",
                  loading: "lazy"
                }, null, 8, _1)) : Q("", !0),
                c("span", x1, M(f.workflow || f.id), 1)
              ], 8, w1))), 128))
            ])) : (g(), w("div", y1, "No generations match.")),
            c("div", k1, [
              m(s).hasMore ? (g(), ft(ee, {
                key: 0,
                variant: "outline",
                size: "sm",
                onClick: d[3] || (d[3] = (f) => m(s).loadFeed(!0))
              }, {
                default: X(() => [...d[7] || (d[7] = [
                  D("Load more", -1)
                ])]),
                _: 1
              })) : Q("", !0)
            ])
          ]),
          _: 1
        })
      ], 32)
    ], 8, ["to"])) : Q("", !0);
  }
}), S1 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, C1 = { class: "cmst:flex cmst:gap-1.5" }, $1 = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, I1 = { class: "cmst-media-well cmst:flex cmst:aspect-[4/3] cmst:items-center cmst:justify-center" }, R1 = ["src", "alt", "data-testid"], A1 = {
  key: 1,
  class: "cmst:px-3 cmst:text-center cmst:text-xs cmst:text-cmst-muted"
}, E1 = { class: "cmst-type-meta cmst:mt-1 cmst:truncate" }, O1 = /* @__PURE__ */ Mt({
  __name: "CompareViewer",
  setup(e) {
    const t = Nn(), s = ge(() => t.compareRecords);
    function n(a) {
      return t.records.find((i) => i.id === a) ?? null;
    }
    function o(a) {
      const i = n(a)?.featuredOutput;
      return i ? gd(i) : null;
    }
    function r(a) {
      const i = a === "a" ? t.compareA : t.compareB, l = n(i);
      return l ? `${a.toUpperCase()} · ${l.workflow || l.id}` : `Slot ${a.toUpperCase()} empty or deleted.`;
    }
    return (a, i) => s.value.a || s.value.b ? (g(), ft(hd, {
      key: 0,
      class: "cmst:p-4",
      "data-testid": "vue-compare"
    }, {
      default: X(() => [
        c("div", S1, [
          i[4] || (i[4] = c("div", { class: "cmst:min-w-0" }, [
            c("h3", { class: "cmst-type-section" }, "Compare"),
            c("p", { class: "cmst-type-meta cmst:mt-0.5" }, "transient — never persisted")
          ], -1)),
          c("div", C1, [
            V(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-swap",
              onClick: i[0] || (i[0] = (l) => m(t).swapCompare())
            }, {
              default: X(() => [...i[2] || (i[2] = [
                D("Switch A/B", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-clear",
              onClick: i[1] || (i[1] = (l) => m(t).clearCompare())
            }, {
              default: X(() => [...i[3] || (i[3] = [
                D("Clear", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        c("div", $1, [
          (g(), w(de, null, Le(["a", "b"], (l) => c("figure", {
            key: l,
            class: "cmst:min-w-0"
          }, [
            c("div", I1, [
              o(l === "a" ? m(t).compareA : m(t).compareB) ? (g(), w("img", {
                key: 0,
                src: o(l === "a" ? m(t).compareA : m(t).compareB),
                alt: `Compare ${l.toUpperCase()}`,
                class: "cmst:max-h-full cmst:max-w-full cmst:object-contain",
                "data-testid": `vue-compare-${l}`
              }, null, 8, R1)) : (g(), w("span", A1, "Slot " + M(l.toUpperCase()) + " empty or deleted.", 1))
            ]),
            c("figcaption", E1, M(r(l)), 1)
          ])), 64))
        ])
      ]),
      _: 1
    })) : Q("", !0);
  }
}), T1 = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, P1 = { class: "cmst-type-meta cmst:mt-0.5" }, M1 = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, N1 = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-xs cmst:text-cmst-muted" }, z1 = {
  class: "cmst-type-meta",
  "aria-hidden": "true"
}, D1 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, j1 = { class: "cmst:relative" }, L1 = ["value"], U1 = ["value"], V1 = { class: "cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px] cmst:text-cmst-muted" }, F1 = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-danger",
  role: "alert"
}, B1 = {
  key: 1,
  class: "cmst:py-6 cmst:text-[13px] cmst:text-cmst-muted"
}, W1 = {
  key: 2,
  class: "cmst:py-6 cmst:text-[13px] cmst:text-cmst-muted",
  "data-testid": "vue-history-empty"
}, G1 = {
  key: 0,
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2"
}, q1 = { class: "cmst-type-meta" }, H1 = { class: "cmst:flex cmst:justify-center" }, Z1 = /* @__PURE__ */ Mt({
  __name: "HistoryView",
  setup(e) {
    const t = Nn(), s = So(), n = Nu(), o = ai(), r = /* @__PURE__ */ I(t.query), a = /* @__PURE__ */ I(!1), i = ge({
      get: () => {
        const O = Number.parseInt(String(s.columnsPreference ?? "4"), 10);
        return Number.isNaN(O) ? 4 : Math.min(8, Math.max(2, O));
      },
      set: (O) => s.setHistoryColumns(String(O))
    });
    function l() {
      const O = n.query.focus;
      return typeof O == "string" && O !== "" ? O : null;
    }
    Ns(async () => {
      await t.initialize(), await t.applyRouteFocus(l());
    }), ss(
      () => n.query.focus,
      (O) => {
        t.applyRouteFocus(typeof O == "string" ? O : null);
      }
    );
    let u;
    ss(r, (O) => {
      window.clearTimeout(u), u = window.setTimeout(() => {
        t.setQuery(O), t.loadFeed();
      }, 250);
    });
    async function d(O) {
      t.setFocus(O.id), await o.replace({ name: "history", query: { focus: O.id } }), await t.loadDetail(O.id, O.kind), t.viewerOpen = !0;
    }
    async function f() {
      t.viewerOpen = !1, await o.replace({ name: "history" });
    }
    function b(O) {
      a.value = !1, d(O);
    }
    function h() {
      t.setQuery(""), r.value = "", t.setStatusFilter(""), t.setKindFilter("mixed"), t.loadFeed();
    }
    return (O, x) => (g(), w("section", {
      class: Ve(m(Tr)()),
      "data-testid": "vue-page-history"
    }, [
      c("div", T1, [
        c("div", null, [
          x[15] || (x[15] = c("h1", { class: "cmst-type-view" }, "History", -1)),
          c("p", P1, M(m(t).records.length) + " records · " + M(m(t).selection.length) + " selected ", 1)
        ]),
        c("div", M1, [
          c("label", N1, [
            x[16] || (x[16] = c("span", { "aria-hidden": "true" }, "Tiles", -1)),
            je(c("input", {
              "onUpdate:modelValue": x[0] || (x[0] = (C) => i.value = C),
              type: "range",
              min: "2",
              max: "8",
              step: "1",
              "aria-label": "Thumbnail columns",
              "data-testid": "vue-history-thumb-size",
              class: "cmst:accent-cmst-primary"
            }, null, 512), [
              [
                ut,
                i.value,
                void 0,
                { number: !0 }
              ]
            ]),
            c("span", z1, M(i.value), 1)
          ]),
          V(ee, {
            variant: "secondary",
            size: "sm",
            "data-testid": "vue-history-picker-open",
            onClick: x[1] || (x[1] = (C) => a.value = !0)
          }, {
            default: X(() => [...x[17] || (x[17] = [
              D("Pick generation", -1)
            ])]),
            _: 1
          }),
          V(ee, {
            variant: "ghost",
            size: "icon",
            "aria-label": "Refresh history",
            disabled: m(t).loading,
            onClick: x[2] || (x[2] = (C) => m(t).loadFeed())
          }, {
            default: X(() => [
              V(m(Rr), {
                class: Ve(["cmst:size-4", m(t).loading ? "cmst:animate-spin" : ""]),
                "aria-hidden": "true"
              }, null, 8, ["class"])
            ]),
            _: 1
          }, 8, ["disabled"])
        ])
      ]),
      c("div", D1, [
        c("div", j1, [
          V(m(Ea), {
            class: "cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted",
            "aria-hidden": "true"
          }),
          je(c("input", {
            "onUpdate:modelValue": x[3] || (x[3] = (C) => r.value = C),
            class: "cmst-field cmst:w-52 cmst:pl-8",
            placeholder: "Search history",
            "aria-label": "Search history",
            "data-testid": "vue-history-search"
          }, null, 512), [
            [ut, r.value]
          ])
        ]),
        c("select", {
          value: m(t).kindFilter,
          class: "cmst-field",
          "aria-label": "Record kind",
          onChange: x[4] || (x[4] = (C) => {
            m(t).setKindFilter(C.target.value), m(t).loadFeed();
          })
        }, [...x[18] || (x[18] = [
          c("option", { value: "mixed" }, "All kinds", -1),
          c("option", { value: "generation" }, "Generations", -1),
          c("option", { value: "experiment" }, "Experiments", -1)
        ])], 40, L1),
        c("select", {
          value: m(t).statusFilter,
          class: "cmst-field",
          "aria-label": "Status filter",
          onChange: x[5] || (x[5] = (C) => {
            m(t).setStatusFilter(C.target.value), m(t).loadFeed();
          })
        }, [...x[19] || (x[19] = [
          Yo('<option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="running">Running</option><option value="canceled">Canceled</option>', 5)
        ])], 40, U1),
        je(c("select", {
          "onUpdate:modelValue": x[6] || (x[6] = (C) => m(t).sort = C),
          class: "cmst-field",
          "aria-label": "Sort order",
          onChange: x[7] || (x[7] = (C) => {
            m(t).setSort(m(t).sort), m(t).loadFeed();
          })
        }, [...x[20] || (x[20] = [
          c("option", { value: "newest" }, "Newest", -1),
          c("option", { value: "oldest" }, "Oldest", -1),
          c("option", { value: "fastest" }, "Fastest", -1),
          c("option", { value: "slowest" }, "Slowest", -1)
        ])], 544), [
          [Qt, m(t).sort]
        ]),
        c("label", V1, [
          je(c("input", {
            "onUpdate:modelValue": x[8] || (x[8] = (C) => m(t).favoriteOnly = C),
            type: "checkbox",
            onChange: x[9] || (x[9] = (C) => {
              m(t).setFavoriteOnly(m(t).favoriteOnly), m(t).loadFeed();
            })
          }, null, 544), [
            [un, m(t).favoriteOnly]
          ]),
          x[21] || (x[21] = D(" Favorites ", -1))
        ])
      ]),
      m(t).error ? (g(), w("div", F1, [
        D(M(m(t).error) + " ", 1),
        V(ee, {
          class: "cmst:ml-2",
          size: "sm",
          variant: "ghost",
          onClick: x[10] || (x[10] = (C) => m(t).loadFeed())
        }, {
          default: X(() => [...x[22] || (x[22] = [
            D("Retry", -1)
          ])]),
          _: 1
        })
      ])) : Q("", !0),
      m(t).loading && !m(t).records.length ? (g(), w("p", B1, " Loading history… ")) : m(t).records.length ? (g(), w(de, { key: 3 }, [
        m(t).selection.length ? (g(), w("div", G1, [
          c("span", q1, M(m(t).selection.length) + " selected", 1),
          V(ee, {
            size: "sm",
            variant: "outline",
            "data-testid": "vue-history-bulk-delete",
            onClick: x[11] || (x[11] = (C) => m(t).removeSelected())
          }, {
            default: X(() => [
              D("Delete selected (" + M(m(t).selection.length) + ")", 1)
            ]),
            _: 1
          }),
          V(ee, {
            size: "sm",
            variant: "ghost",
            onClick: x[12] || (x[12] = (C) => m(t).clearSelection())
          }, {
            default: X(() => [...x[25] || (x[25] = [
              D("Clear selection", -1)
            ])]),
            _: 1
          })
        ])) : Q("", !0),
        V(P_, {
          records: m(t).records,
          onSelect: d
        }, null, 8, ["records"]),
        c("div", H1, [
          m(t).hasMore ? (g(), ft(ee, {
            key: 0,
            variant: "outline",
            onClick: x[13] || (x[13] = (C) => m(t).loadFeed(!0))
          }, {
            default: X(() => [...x[26] || (x[26] = [
              D("Load more", -1)
            ])]),
            _: 1
          })) : Q("", !0)
        ])
      ], 64)) : (g(), w("div", W1, [
        x[24] || (x[24] = D(" No records match this query. ", -1)),
        V(ee, {
          class: "cmst:ml-2",
          size: "sm",
          variant: "ghost",
          onClick: h
        }, {
          default: X(() => [...x[23] || (x[23] = [
            D("Clear filters", -1)
          ])]),
          _: 1
        })
      ])),
      V(O1),
      m(t).viewerOpen ? (g(), ft(v1, {
        key: 4,
        record: m(t).selected,
        onClose: f
      }, null, 8, ["record"])) : Q("", !0),
      a.value ? (g(), ft(yd, {
        key: 5,
        onSelect: b,
        onCancel: x[14] || (x[14] = (C) => a.value = !1)
      })) : Q("", !0)
    ], 2));
  }
});
async function K1(e, t = "", s) {
  let n = `/studio/workflows/${encodeURIComponent(e)}/run-context`;
  return t && (n += `?version_id=${encodeURIComponent(t)}`), ce(n, {}, s);
}
async function Q1(e, t) {
  return ce("/studio/run", { method: "POST", body: e }, t);
}
async function J1(e, t) {
  return ce("/studio/run_batch", { method: "POST", body: e }, t);
}
async function Y1(e, t) {
  return ce(
    "/studio/experiment-v2",
    { method: "POST", body: e },
    t
  );
}
async function X1(e, t) {
  return ce(
    `/studio/experiments/${encodeURIComponent(e)}/stop-now`,
    { method: "POST", body: {} },
    t
  );
}
async function ex(e, t = fetch) {
  const s = new FormData();
  s.append("image", e, e.name || "studio-image.png"), s.append("overwrite", "false");
  let n;
  try {
    n = await t("/upload/image", { method: "POST", body: s });
  } catch {
    return { ok: !1, message: "Image upload request failed" };
  }
  if (!n.ok) return { ok: !1, message: `Upload failed with status ${n.status}` };
  try {
    const o = await n.json(), r = o.files, a = typeof o.name == "string" ? o.name : Array.isArray(r) && typeof r[0] == "string" ? r[0] : void 0;
    return a ? { ok: !0, filename: a } : { ok: !1, message: "Upload returned no filename" };
  } catch {
    return { ok: !1, message: "Upload returned an unreadable response" };
  }
}
function Wn(e) {
  try {
    if (typeof crypto < "u" && typeof crypto.randomUUID == "function")
      return crypto.randomUUID();
  } catch {
  }
  return `${e}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
const ec = {
  generate: ["text", "references", "layout", "sketch", "guidance"],
  edit: ["text", "references", "select", "expand", "sketch"],
  post: ["adjust", "color", "detail", "effects", "crop", "heal", "upscale"]
}, Va = ["upscale"], tx = new Set(
  [
    "image",
    "images",
    "imageurl",
    "imagedata",
    "source",
    "source_image",
    "sourceimage",
    "mask",
    "references",
    "reference",
    "sketch"
  ].map((e) => e.toLowerCase())
), sx = /* @__PURE__ */ new Set(["model_unet", "model", "unet", "clip", "vae", "model_clip", "model_vae"]);
function js(e) {
  try {
    if (typeof structuredClone == "function") return structuredClone(e);
  } catch {
  }
  return JSON.parse(JSON.stringify(e));
}
function nx(e) {
  const t = {};
  for (const [s, n] of Object.entries(e))
    tx.has(s.toLowerCase()) || (t[s] = n);
  return t;
}
function ox(e, t) {
  return e === "source_image" || e === "mask" ? !0 : t?.control_kind === "image";
}
function rx(e, t) {
  return sx.has(e) ? !0 : !t || typeof t != "object" ? !1 : t.control_kind === "file" || t.control_kind === "model";
}
function la(e, t) {
  const s = {};
  for (const [n, o] of Object.entries(e))
    !o || typeof o != "object" || (o.default !== void 0 ? s[n] = o.default : Array.isArray(o.enum_options) && o.enum_options.length && (s[n] = o.enum_options[0]));
  return s;
}
function ax(e, t) {
  const s = [];
  for (const [n, o] of Object.entries(e)) {
    const r = t[n];
    if (!r) {
      s.push({ field: n, message: `unknown control '${n}'` });
      continue;
    }
    !ox(n, r) && !rx(n, r) && Array.isArray(r.enum_options) && r.enum_options.length && o !== void 0 && o !== null && !r.enum_options.some((a) => a === o) && s.push({ field: n, message: "must be one of the available options" }), typeof o == "number" && (typeof r.minimum == "number" && o < r.minimum && s.push({ field: n, message: `must be >= ${r.minimum}` }), typeof r.maximum == "number" && o > r.maximum && s.push({ field: n, message: `must be <= ${r.maximum}` })), r.required && (o == null || typeof o == "string" && o.trim() === "") && s.push({ field: n, message: "required" });
  }
  for (const [n, o] of Object.entries(t))
    o?.required && !Object.prototype.hasOwnProperty.call(e, n) && s.push({ field: n, message: `missing required control '${n}'` });
  return s;
}
const tc = (e, t) => As(
  `playground.draft.${e}.${t}`,
  {}
), ca = As(
  "playground.selection.v1",
  { workflowId: "", versionId: "" }
), sc = As(
  "playground.current-generation.v1",
  { key: "", generationId: "" }
), ix = /* @__PURE__ */ Mn("studio-playground", () => {
  const e = /* @__PURE__ */ I("txt2img"), t = /* @__PURE__ */ I(!1), s = /* @__PURE__ */ I(!1), n = /* @__PURE__ */ I("generate"), o = /* @__PURE__ */ I("text"), r = /* @__PURE__ */ I(ca.read().workflowId), a = /* @__PURE__ */ I(ca.read().versionId), i = /* @__PURE__ */ I(null), l = /* @__PURE__ */ I({}), u = /* @__PURE__ */ I({}), d = /* @__PURE__ */ I("idle"), f = /* @__PURE__ */ I(""), b = /* @__PURE__ */ I([]), h = /* @__PURE__ */ I(!1), O = /* @__PURE__ */ I(0), x = /* @__PURE__ */ I(""), C = /* @__PURE__ */ I(0), T = /* @__PURE__ */ I(!1), A = /* @__PURE__ */ I(""), z = /* @__PURE__ */ I([]), R = /* @__PURE__ */ I({}), J = /* @__PURE__ */ I({}), $e = /* @__PURE__ */ I(null), ne = /* @__PURE__ */ I(!1), j = /* @__PURE__ */ I({
    status: "idle",
    message: "",
    runId: "",
    experimentId: ""
  }), re = /* @__PURE__ */ I(null), ve = /* @__PURE__ */ I(null), Me = /* @__PURE__ */ I(""), Ie = /* @__PURE__ */ I([]), Oe = /* @__PURE__ */ I({}), Ye = Tn(), ae = ge(() => `${r.value}::${a.value}`), _ = ge(() => ax(u.value, l.value)), S = ge(() => {
    if (d.value === "loading") return "Loading workflow…";
    if (d.value === "error") return f.value || "Workflow unavailable";
    if (!r.value) return "Select a workflow to begin";
    if (!h.value)
      return b.value[0] || "This workflow is not runnable yet";
    const oe = _.value.find((we) => we.message === "required" || we.message.startsWith("missing"));
    return oe ? `Fill in ${oe.field} to generate` : Va.includes(o.value) ? "This tool arrives in a later phase — execution is disabled" : ue.value ? "A run is already in flight" : null;
  }), ue = ge(() => j.value.status === "submitting" || j.value.status === "running"), Ue = ge(() => Ie.value.length), ie = ge(
    () => Object.entries(Oe.value).filter(([, oe]) => oe.enabled && oe.values.length > 0)
  );
  function tt() {
    ca.write({ workflowId: r.value, versionId: a.value });
  }
  function De() {
    if (!(!r.value || !a.value))
      try {
        tc(r.value, a.value).write({ ...u.value });
      } catch {
      }
  }
  function bt(oe) {
    e.value = oe;
  }
  function ke(oe) {
    t.value = oe, oe && (s.value = !1);
  }
  function $(oe) {
    s.value = oe, oe && (t.value = !1);
  }
  function F(oe, we) {
    n.value = oe, o.value = we;
  }
  function U(oe, we) {
    u.value = { ...u.value, [oe]: we }, ne.value = !0, De();
  }
  function B() {
    u.value = la(l.value), z.value = [], R.value = {}, J.value = {}, ne.value = !1, q(), De();
  }
  function q() {
    x.value = "", C.value += 1, T.value = !1, A.value = "";
  }
  function me(oe, we) {
    x.value = we, u.value = { ...u.value, source_image: oe }, ne.value = !0, De();
  }
  function v() {
    const oe = { ...u.value };
    delete oe.source_image, delete oe.mask, u.value = oe, q(), De();
  }
  function k(oe) {
    return x.value = oe, C.value += 1, T.value = !0, A.value = "", C.value;
  }
  function P(oe, we, it) {
    return oe !== C.value || we !== x.value ? !1 : (T.value = !1, u.value = { ...u.value, source_image: it }, ne.value = !0, De(), !0);
  }
  function L(oe, we, it) {
    oe !== C.value || we !== x.value || (T.value = !1, A.value = it);
  }
  async function Z(oe) {
    const we = ae.value, it = k(we), lt = await ex(oe);
    return !lt.ok || !lt.filename ? (L(it, we, lt.message || "Upload failed"), !1) : P(it, we, lt.filename);
  }
  function Y(oe) {
    z.value = [...z.value, { id: Wn("ref"), filename: oe }], ne.value = !0;
  }
  function E(oe) {
    z.value = z.value.filter((we) => we.id !== oe), ne.value = !0;
  }
  function G(oe) {
    J.value = { ...J.value, ...oe }, ne.value = !0;
  }
  function H() {
    J.value = {}, ne.value = !0;
  }
  function K(oe, we) {
    const it = oe && typeof oe.controls == "object" ? oe.controls : {}, lt = nx(it);
    u.value = { ...la(l.value), ...lt }, z.value = [], J.value = {}, q(), Ne(null), $e.value = we, ne.value = !1, De();
  }
  async function ye(oe, we = "", it) {
    const lt = O.value += 1;
    r.value = oe, a.value = we, i.value = null, l.value = {}, u.value = {}, b.value = [], f.value = "", h.value = !1, q(), z.value = [], d.value = "loading", tt();
    const At = await Ye.run(async (wt) => {
      const Bt = await K1(oe, we, it);
      return wt.aborted ? null : Bt;
    });
    if (At.stale || !At.value) return { ok: !1, error: "superseded" };
    if (lt !== O.value) return { ok: !1, error: "superseded" };
    const Ze = At.value;
    if (!Ze || Ze.status !== "ok")
      return d.value = "error", f.value = "Could not load workflow", { ok: !1, error: f.value };
    const N = Ze.control_schema ?? {}, se = Ze.version?.workflow_version_id;
    typeof se == "string" && se && (a.value = se, tt()), i.value = Ze, l.value = N;
    const Ae = Array.isArray(
      Ze.version?.reasons
    ) ? Ze.version.reasons : [];
    Ze.version?.runnable !== !0 && !Ae.length && Ae.push("This workflow is not runnable yet"), Ze.mapping || Ae.push("missing mapping"), b.value = Ae, h.value = Ae.length === 0, d.value = "ready";
    let Be = {};
    try {
      Be = tc(r.value, a.value).read();
    } catch {
      Be = {};
    }
    const Ot = { ...la(N) };
    for (const [wt, Bt] of Object.entries(Be))
      Object.prototype.hasOwnProperty.call(N, wt) && (Ot[wt] = Bt);
    u.value = Ot, f.value = "";
    try {
      const wt = sc.read();
      re.value = wt.key === ae.value && wt.generationId ? wt.generationId : null;
    } catch {
      re.value = null;
    }
    return { ok: !0 };
  }
  function le(oe) {
    return {
      workflow_id: r.value,
      workflow_version_id: a.value,
      featureId: e.value,
      workflow_type: String(
        i.value?.workflow?.workflow_type ?? "t2i"
      ),
      controls: js({ ...u.value }),
      modal_options: oe ? js({ ...oe }) : void 0,
      profile_name: null,
      request_id: Wn("req"),
      metadata: {
        source: "studio_playground_vue",
        workflow_id: r.value,
        workflow_version_id: a.value
      },
      trace: {}
    };
  }
  function Re(oe, we) {
    if (we.method && (oe.studio_method = we.method), we.references && (oe.studio_references = we.references), we.guidance && (oe.guidance = we.guidance), we.style) {
      oe.studio_style = we.style;
      const it = we.style.composed;
      typeof it == "string" && (oe.controls = { ...oe.controls, prompt: it });
    }
  }
  async function Te(oe = {}) {
    const we = S.value;
    if (we) return { ok: !1, error: we };
    const it = le(oe.modalOptions);
    Re(it, {
      method: oe.method,
      references: oe.references ?? (z.value.length ? { items: js(z.value.map((Ze) => Ze.filename)), methods: R.value } : void 0),
      guidance: oe.guidance,
      style: oe.style
    }), ve.value = js(it), Me.value = String(it.controls.source_image ?? "");
    const lt = Gt(), At = lt.start({
      kind: "generation",
      label: "Generation",
      status: "running",
      message: "Submitting…"
    });
    j.value = { status: "submitting", message: "Submitting…", runId: "", experimentId: "" };
    try {
      const Ze = await Q1(it, oe.fetchImpl), N = String(Ze.runId ?? Ze.run_id ?? Ze.id ?? "");
      return Ne(N || null), j.value = {
        status: "running",
        message: "Running…",
        runId: N,
        experimentId: "",
        detail: Ze
      }, lt.patch(At, { message: "Running…" }), Ze.status === "ok" || Ze.direct_run ? (j.value = { status: "succeeded", message: "Run completed", runId: N, experimentId: "", detail: Ze }, lt.finish(At, "Run completed"), N && oe.onDone?.({ id: N }), { ok: !0 }) : (j.value = { status: "running", message: "Running…", runId: N, experimentId: "", detail: Ze }, { ok: !0 });
    } catch (Ze) {
      const N = Ze instanceof Error ? Ze.message : "Submission failed";
      return j.value = { status: "failed", message: N, runId: "", experimentId: "" }, lt.fail(At, N), { ok: !1, error: N };
    }
  }
  function qe(oe) {
    return r.value ? (Ie.value = [
      ...Ie.value,
      {
        id: Wn("q"),
        label: oe || `Variant ${Ie.value.length + 1}`,
        workflowId: r.value,
        workflowVersionId: a.value,
        controlValues: js({ ...u.value })
      }
    ], { ok: !0 }) : { ok: !1, error: "Select a workflow first" };
  }
  function st(oe) {
    Ie.value = Ie.value.filter((we) => we.id !== oe);
  }
  function et() {
    Ie.value = [];
  }
  async function te(oe = {}) {
    if (!Ie.value.length) return { ok: !1, error: "Queue is empty" };
    if (ue.value) return { ok: !1, error: "A run is already in flight" };
    const we = Ie.value.filter(
      (Ze) => Ze.workflowId === Ie.value[0].workflowId
    ), it = Ie.value.filter((Ze) => Ze.workflowId !== Ie.value[0].workflowId);
    if (Ie.value = it, we.length === 1) {
      const Ze = we[0];
      return u.value = { ...Ze.controlValues }, Te({ modalOptions: oe.modalOptions, fetchImpl: oe.fetchImpl });
    }
    const lt = Gt(), At = lt.start({
      kind: "generation",
      label: `Batch (${we.length})`,
      status: "running",
      message: `Batch running: 0 of ${we.length} complete`
    });
    j.value = {
      status: "running",
      message: `Batch running: 0 of ${we.length} complete`,
      runId: "",
      experimentId: ""
    };
    try {
      const Ze = we.map((N) => ({
        request_id: Wn("variant"),
        controls: js(N.controlValues)
      }));
      return await J1(
        {
          profile: null,
          workflow_id: we[0].workflowId,
          workflow_version_id: we[0].workflowVersionId,
          request_id: Wn("batch"),
          modal_options: oe.modalOptions ? js({ ...oe.modalOptions }) : null,
          variants: Ze
        },
        oe.fetchImpl
      ), j.value = { status: "succeeded", message: "Batch submitted", runId: "", experimentId: "" }, lt.finish(At, "Batch submitted"), { ok: !0 };
    } catch (Ze) {
      const N = Ze instanceof Error ? Ze.message : "Batch failed";
      return j.value = { status: "failed", message: N, runId: "", experimentId: "" }, lt.fail(At, N), { ok: !1, error: N };
    }
  }
  function pe(oe, we) {
    const it = Oe.value[oe] ?? { enabled: !1, values: [] };
    Oe.value = { ...Oe.value, [oe]: { ...it, ...we } };
  }
  function he() {
    Oe.value = {};
  }
  async function ze(oe = {}) {
    if (ie.value.length === 0) return { ok: !1, error: "Enable at least one sweep axis" };
    const we = S.value;
    if (we && we !== "A run is already in flight") return { ok: !1, error: we };
    const it = le(oe.modalOptions), lt = js({
      ...it,
      axes: Object.fromEntries(ie.value.map(([N, se]) => [N, se.values]))
    });
    ve.value = lt;
    const At = Gt(), Ze = At.start({ kind: "experiment", label: "Experiment", status: "running" });
    j.value = { status: "submitting", message: "Submitting experiment…", runId: "", experimentId: "" };
    try {
      const N = await Y1(lt, oe.fetchImpl), se = String(N.experiment_id ?? N.experimentId ?? N.id ?? "");
      return Ne(se || null), j.value = { status: "running", message: "Experiment running…", runId: "", experimentId: se, detail: N }, At.patch(Ze, { message: "Experiment running…" }), { ok: !0 };
    } catch (N) {
      const se = N instanceof Error ? N.message : "Experiment submission failed";
      return j.value = { status: "failed", message: se, runId: "", experimentId: "" }, At.fail(Ze, se), { ok: !1, error: se };
    }
  }
  async function Ke(oe) {
    const we = j.value.experimentId || j.value.runId;
    if (j.value = { ...j.value, status: "canceled", message: "Run canceled" }, we)
      try {
        await X1(we, oe);
      } catch {
      }
  }
  function Ne(oe) {
    re.value = oe;
    try {
      sc.write({ key: ae.value, generationId: oe ?? "" });
    } catch {
    }
  }
  function He(oe) {
    Ne(oe), j.value = { ...j.value, status: "succeeded", message: "Run completed" };
  }
  function Qe(oe) {
    j.value = { ...j.value, status: "failed", message: oe };
  }
  return {
    featureId: e,
    experimentMode: t,
    queueMode: s,
    activeMode: n,
    activeSubtool: o,
    workflowId: r,
    versionId: a,
    runContext: i,
    schema: l,
    controlValues: u,
    contextStatus: d,
    contextError: f,
    contextReasons: b,
    runnable: h,
    sourceOwnerKey: x,
    sourceUploading: T,
    sourceError: A,
    references: z,
    workflowMethods: R,
    outputOverride: J,
    presetId: $e,
    presetDirty: ne,
    runState: j,
    currentGenerationId: re,
    lastSubmitted: ve,
    submittedSource: Me,
    queue: Ie,
    experimentAxes: Oe,
    contextKey: ae,
    draftErrors: _,
    gateReason: S,
    isBusy: ue,
    queueCount: Ue,
    enabledAxes: ie,
    setFeature: bt,
    setExperimentMode: ke,
    setQueueMode: $,
    setTool: F,
    setControl: U,
    resetDraft: B,
    setSource: me,
    clearSource: v,
    beginUpload: k,
    commitUpload: P,
    failUpload: L,
    uploadSource: Z,
    addReference: Y,
    removeReference: E,
    setOutputOverride: G,
    clearOutputOverride: H,
    applyPreset: K,
    selectWorkflow: ye,
    buildPayload: le,
    submitRun: Te,
    enqueueCurrent: qe,
    removeQueued: st,
    clearQueue: et,
    drainQueue: te,
    setAxis: pe,
    clearAxes: he,
    submitExperimentDef: ze,
    cancelRun: Ke,
    noteSucceeded: He,
    noteFailed: Qe
  };
}), lx = { "data-testid": "vue-playground-controls" }, cx = {
  key: 0,
  class: "cmst:py-4 cmst:text-sm cmst:opacity-70"
}, ux = ["for"], dx = ["id", "value", "data-testid", "onInput"], fx = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-2 cmst:py-2"
}, mx = { class: "cmst:flex cmst:items-center cmst:gap-2" }, px = ["data-testid"], vx = ["data-testid", "onClick"], gx = { class: "cmst:cursor-pointer cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover" }, hx = ["onChange"], yx = ["data-testid", "onClick"], bx = {
  key: 2,
  class: "cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:py-2"
}, wx = ["for"], _x = ["id", "value", "min", "max", "step", "data-testid", "onInput"], xx = ["for"], kx = {
  key: 1,
  class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]"
}, Sx = ["id", "checked", "data-testid", "onChange"], Cx = ["id", "value", "data-testid", "onChange"], $x = ["value"], Ix = {
  key: 3,
  class: "cmst:flex cmst:items-center cmst:gap-2"
}, Rx = ["id", "value", "data-testid", "onInput"], Ax = ["data-testid", "onClick"], Ex = ["id", "value", "min", "max", "step", "data-testid", "onInput"], Ox = ["id", "value", "data-testid", "onInput"], hn = "cmst:h-9 cmst:w-full cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm cmst:text-cmst-fg", jo = "cmst:flex cmst:flex-col cmst:gap-1.5 cmst:py-2", Lo = "cmst:text-[13px] cmst:font-medium cmst:text-cmst-secondary-text", Tx = /* @__PURE__ */ Mt({
  __name: "PlaygroundControls",
  props: {
    schema: {},
    values: {},
    hideRoles: {}
  },
  emits: ["update", "pickImage", "uploadImage", "clearImage"],
  setup(e, { emit: t }) {
    const s = e, n = t;
    function o(A) {
      return s.schema[A] ?? {};
    }
    function r(A) {
      const z = o(A);
      return typeof z.label == "string" && z.label ? z.label : A.split("_").map((R) => R && R[0].toUpperCase() + R.slice(1)).join(" ");
    }
    function a(A) {
      return A === "prompt" || A === "negative_prompt" || A.endsWith("_prompt");
    }
    function i(A, z) {
      return A === "source_image" || A === "mask" ? !0 : z.control_kind === "image";
    }
    function l(A) {
      return A === "seed";
    }
    function u(A) {
      return A === "width" || A === "height";
    }
    function d(A, z) {
      return i(A, z) ? "image" : l(A) ? "seed" : typeof z.default == "boolean" || z.data_type === "BOOLEAN" ? "toggle" : Array.isArray(z.enum_options) && z.enum_options.length ? "select" : typeof z.default == "number" || z.data_type === "INT" || z.data_type === "FLOAT" ? "number" : a(A) ? "prompt" : "text";
    }
    const f = ge(() => {
      const A = new Set(s.hideRoles ?? []), z = Object.keys(s.schema).filter(
        (J) => s.schema[J]?.enabled !== !1 && !A.has(J)
      ), R = (J) => J === "prompt" ? 0 : J === "negative_prompt" ? 1 : a(J) ? 2 : J === "source_image" || J === "mask" ? 3 : u(J) ? 4 : l(J) ? 5 : 10;
      return z.sort((J, $e) => R(J) - R($e) || J.localeCompare($e));
    }), b = ge(() => f.value.filter((A) => d(A, o(A)) === "prompt")), h = ge(() => f.value.filter((A) => u(A))), O = ge(
      () => f.value.filter((A) => d(A, o(A)) === "image")
    ), x = ge(
      () => f.value.filter(
        (A) => !a(A) && !u(A) && d(A, o(A)) !== "image" && d(A, o(A)) !== "prompt"
      )
    );
    function C(A, z) {
      const R = z.target, J = R.files?.[0];
      J && n("uploadImage", A, J), R.value = "";
    }
    function T(A) {
      n("update", A, Math.floor(Math.random() * 2 ** 31));
    }
    return (A, z) => (g(), w("div", lx, [
      f.value.length ? Q("", !0) : (g(), w("div", cx, " This workflow exposes no controls yet. Map them in Workflows first. ")),
      (g(!0), w(de, null, Le(b.value, (R) => (g(), w("div", {
        key: R,
        class: Ve(jo)
      }, [
        c("label", {
          for: `pg-ctl-${R}`,
          class: Ve(Lo)
        }, M(r(R)), 9, ux),
        c("textarea", {
          id: `pg-ctl-${R}`,
          value: String(s.values[R] ?? ""),
          rows: "3",
          class: Ve(`${hn} cmst:h-auto cmst:py-2`),
          "data-testid": `vue-playground-control-${R}`,
          onInput: (J) => n("update", R, J.target.value)
        }, null, 42, dx)
      ]))), 128)),
      O.value.length ? (g(), w("div", fx, [
        (g(!0), w(de, null, Le(O.value, (R) => (g(), w("div", {
          key: R,
          class: Ve(jo)
        }, [
          c("span", {
            class: Ve(Lo)
          }, M(r(R)), 1),
          c("div", mx, [
            c("span", {
              class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]",
              "data-testid": `vue-playground-control-${R}`
            }, M(String(s.values[R] ?? "No image selected")), 9, px),
            c("button", {
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
              "data-testid": `vue-playground-pick-${R}`,
              onClick: (J) => n("pickImage", R)
            }, " Browse ", 8, vx),
            c("label", gx, [
              z[0] || (z[0] = D(" Upload ", -1)),
              c("input", {
                type: "file",
                accept: "image/*",
                class: "cmst:hidden",
                onChange: (J) => C(R, J)
              }, null, 40, hx)
            ]),
            s.values[R] ? (g(), w("button", {
              key: 0,
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:opacity-70 cmst:hover:bg-cmst-hover",
              "data-testid": `vue-playground-clear-${R}`,
              onClick: (J) => n("clearImage", R)
            }, " Clear ", 8, yx)) : Q("", !0)
          ])
        ]))), 128))
      ])) : Q("", !0),
      h.value.length ? (g(), w("div", bx, [
        (g(!0), w(de, null, Le(h.value, (R) => (g(), w("div", {
          key: R,
          class: Ve(jo)
        }, [
          c("label", {
            for: `pg-ctl-${R}`,
            class: Ve(Lo)
          }, M(r(R)), 9, wx),
          c("input", {
            id: `pg-ctl-${R}`,
            type: "number",
            value: Number(s.values[R] ?? o(R).default ?? 0),
            min: o(R).minimum,
            max: o(R).maximum,
            step: o(R).step ?? 1,
            class: Ve(hn),
            "data-testid": `vue-playground-control-${R}`,
            onInput: (J) => n("update", R, Number(J.target.value))
          }, null, 40, _x)
        ]))), 128))
      ])) : Q("", !0),
      (g(!0), w(de, null, Le(x.value, (R) => (g(), w("div", {
        key: R,
        class: Ve(jo)
      }, [
        d(R, o(R)) !== "toggle" ? (g(), w("label", {
          key: 0,
          for: `pg-ctl-${R}`,
          class: Ve(Lo)
        }, M(r(R)), 9, xx)) : Q("", !0),
        d(R, o(R)) === "toggle" ? (g(), w("label", kx, [
          c("input", {
            id: `pg-ctl-${R}`,
            type: "checkbox",
            checked: !!(s.values[R] ?? o(R).default ?? !1),
            "data-testid": `vue-playground-control-${R}`,
            onChange: (J) => n("update", R, J.target.checked)
          }, null, 40, Sx),
          D(" " + M(r(R)), 1)
        ])) : d(R, o(R)) === "select" ? (g(), w("select", {
          key: 2,
          id: `pg-ctl-${R}`,
          value: String(s.values[R] ?? ""),
          class: Ve(hn),
          "data-testid": `vue-playground-control-${R}`,
          onChange: (J) => n("update", R, J.target.value)
        }, [
          (g(!0), w(de, null, Le(o(R).enum_options ?? [], (J) => (g(), w("option", {
            key: String(J),
            value: String(J)
          }, M(String(J)), 9, $x))), 128))
        ], 40, Cx)) : d(R, o(R)) === "seed" ? (g(), w("div", Ix, [
          c("input", {
            id: `pg-ctl-${R}`,
            type: "number",
            value: Number(s.values[R] ?? 0),
            class: Ve(hn),
            "data-testid": `vue-playground-control-${R}`,
            onInput: (J) => n("update", R, Number(J.target.value))
          }, null, 40, Rx),
          c("button", {
            type: "button",
            class: "cmst:shrink-0 cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
            "data-testid": `vue-playground-randomize-${R}`,
            onClick: (J) => T(R)
          }, " Random ", 8, Ax)
        ])) : d(R, o(R)) === "number" ? (g(), w("input", {
          key: 4,
          id: `pg-ctl-${R}`,
          type: "number",
          value: Number(s.values[R] ?? o(R).default ?? 0),
          min: o(R).minimum,
          max: o(R).maximum,
          step: o(R).step ?? 1,
          class: Ve(hn),
          "data-testid": `vue-playground-control-${R}`,
          onInput: (J) => n("update", R, Number(J.target.value))
        }, null, 40, Ex)) : (g(), w("input", {
          key: 5,
          id: `pg-ctl-${R}`,
          type: "text",
          value: String(s.values[R] ?? ""),
          class: Ve(hn),
          "data-testid": `vue-playground-control-${R}`,
          onInput: (J) => n("update", R, J.target.value)
        }, null, 40, Ox))
      ]))), 128))
    ]));
  }
}), Px = {
  class: "cmst:flex cmst:flex-col cmst:gap-1",
  "data-testid": "vue-generate-bar"
}, Mx = { class: "cmst:flex cmst:items-stretch cmst:justify-center" }, Nx = { class: "cmst:flex cmst:overflow-hidden cmst:rounded-full cmst:bg-gradient-to-r cmst:from-cmst-primary cmst:to-[#7a5cff] cmst:p-[1.5px]" }, zx = ["disabled", "aria-label"], Dx = ["disabled", "aria-expanded"], jx = {
  key: 0,
  class: "cmst:flex cmst:justify-center",
  role: "menu",
  "aria-label": "Generation intent",
  "data-testid": "vue-generate-menu"
}, Lx = { class: "cmst:flex cmst:flex-col cmst:gap-0.5 cmst:rounded-xl cmst:bg-cmst-raised cmst:p-1.5 cmst:shadow-xl" }, Ux = {
  key: 1,
  class: "cmst:text-center cmst:text-[13px] cmst:text-cmst-muted",
  "data-testid": "vue-generate-gate-reason"
}, Vx = /* @__PURE__ */ Mt({
  __name: "PlaygroundGenerateBar",
  props: {
    disabled: { type: Boolean },
    reason: {},
    busy: { type: Boolean },
    busyLabel: {},
    queueCount: {},
    experimentMode: { type: Boolean },
    queueMode: { type: Boolean }
  },
  emits: ["submit"],
  setup(e, { emit: t }) {
    const s = e, n = t, o = /* @__PURE__ */ I(!1), r = ge(() => s.busy ? s.busyLabel ?? "Running…" : s.experimentMode ? "Run experiment" : s.queueMode ? s.queueCount > 0 ? `Queue (${s.queueCount})` : "Queue" : "Generate");
    function a(l) {
      o.value = !1, n("submit", l);
    }
    function i(l) {
      l.key === "Escape" && (o.value = !1), (l.key === "ArrowDown" || l.key === "Enter") && document.activeElement?.getAttribute("data-testid") === "vue-generate-menu-button" && (o.value = !0);
    }
    return window.addEventListener("keydown", i), Gc(() => window.removeEventListener("keydown", i)), (l, u) => (g(), w("div", Px, [
      c("div", Mx, [
        c("div", Nx, [
          c("button", {
            type: "button",
            disabled: e.disabled,
            class: "cmst:flex cmst:h-11 cmst:min-w-52 cmst:items-center cmst:justify-center cmst:gap-2 cmst:rounded-l-full cmst:bg-cmst-primary cmst:px-6 cmst:text-[15px] cmst:font-semibold cmst:text-white cmst:hover:bg-cmst-primary-hover cmst:disabled:cursor-not-allowed cmst:disabled:opacity-50",
            "data-testid": "vue-generate-submit",
            "aria-label": r.value,
            onClick: u[0] || (u[0] = (d) => a(e.experimentMode ? "experiment" : e.queueMode ? "queue" : "generate"))
          }, [
            e.experimentMode ? (g(), ft(m(zu), {
              key: 0,
              class: "cmst:size-4",
              "aria-hidden": "true"
            })) : e.queueMode ? (g(), ft(m(xv), {
              key: 1,
              class: "cmst:size-4",
              "aria-hidden": "true"
            })) : (g(), ft(m($v), {
              key: 2,
              class: "cmst:size-4",
              "aria-hidden": "true"
            })),
            D(" " + M(r.value), 1)
          ], 8, zx),
          c("button", {
            type: "button",
            disabled: e.disabled && !o.value,
            class: "cmst:flex cmst:h-11 cmst:w-11 cmst:items-center cmst:justify-center cmst:rounded-r-full cmst:bg-cmst-primary cmst:text-white cmst:hover:bg-cmst-primary-hover",
            "data-testid": "vue-generate-menu-button",
            "aria-label": "More generation options",
            "aria-haspopup": "menu",
            "aria-expanded": o.value ? "true" : "false",
            onClick: u[1] || (u[1] = (d) => o.value = !o.value)
          }, [
            V(m(uv), {
              class: "cmst:size-4",
              "aria-hidden": "true"
            })
          ], 8, Dx)
        ])
      ]),
      o.value ? (g(), w("div", jx, [
        c("div", Lx, [
          c("button", {
            type: "button",
            role: "menuitem",
            class: "cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover",
            "data-testid": "vue-generate-intent-generate",
            onClick: u[2] || (u[2] = (d) => a("generate"))
          }, " Generate — run now "),
          c("button", {
            type: "button",
            role: "menuitem",
            class: "cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover",
            "data-testid": "vue-generate-intent-queue",
            onClick: u[3] || (u[3] = (d) => a("queue"))
          }, " Queue — collect, then drain as a batch "),
          c("button", {
            type: "button",
            role: "menuitem",
            class: "cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover",
            "data-testid": "vue-generate-intent-experiment",
            onClick: u[4] || (u[4] = (d) => a("experiment"))
          }, " Experiment — sweep parameter axes ")
        ])
      ])) : Q("", !0),
      e.reason ? (g(), w("p", Ux, M(e.reason), 1)) : Q("", !0)
    ]));
  }
}), Fx = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2",
  "data-testid": "vue-playground-topbar"
}, Bx = ["value"], Wx = ["value"], Gx = ["value"], qx = ["value"], Hx = ["value"], Zx = ["value"], Kx = {
  key: 2,
  class: "cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "vue-playground-preset-dirty"
}, Qx = {
  class: "cmst:ml-auto cmst:flex cmst:items-center cmst:gap-1",
  role: "tablist",
  "aria-label": "Tool"
}, Jx = ["aria-selected", "data-testid", "onClick"], Yx = {
  class: "cmst:flex cmst:flex-wrap cmst:gap-1",
  role: "tablist",
  "aria-label": "Subtool",
  "data-testid": "vue-playground-subtools"
}, Xx = ["aria-selected", "disabled", "title", "data-testid", "onClick"], ek = { class: "cmst:grid cmst:flex-1 cmst:grid-cols-1 cmst:gap-4 cmst:lg:grid-cols-[minmax(0,1fr)_320px]" }, tk = {
  class: "cmst:flex cmst:min-w-0 cmst:flex-col cmst:gap-3",
  "data-testid": "vue-playground-workspace"
}, sk = {
  class: "cmst:flex cmst:min-h-64 cmst:flex-1 cmst:items-center cmst:justify-center cmst:overflow-hidden cmst:rounded-xl cmst:bg-cmst-matte",
  "data-testid": "vue-playground-canvas"
}, nk = ["src"], ok = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:items-center cmst:gap-2 cmst:p-4"
}, rk = ["src"], ak = {
  key: 2,
  class: "cmst:flex cmst:flex-col cmst:items-center cmst:gap-2 cmst:p-8 cmst:text-center"
}, ik = { class: "cmst:max-w-80 cmst:text-sm cmst:text-cmst-muted" }, lk = {
  key: 0,
  class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]",
  "data-testid": "vue-playground-run-status",
  role: "status"
}, ck = { class: "cmst:text-cmst-secondary-text" }, uk = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-playground-prompt-zone"
}, dk = ["for"], fk = ["id", "value", "rows", "data-testid", "onInput"], mk = {
  key: 2,
  class: "cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-playground-references"
}, pk = { class: "cmst:flex cmst:items-center cmst:justify-between" }, vk = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-muted"
}, gk = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-1.5"
}, hk = ["data-testid"], yk = ["src", "alt"], bk = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, wk = ["aria-label", "onClick"], _k = {
  key: 3,
  class: "cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-playground-sketch"
}, xk = { class: "cmst:flex cmst:items-center cmst:gap-2" }, kk = {
  key: 0,
  class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]"
}, Sk = {
  key: 1,
  class: "cmst:text-xs cmst:text-cmst-muted"
}, Ck = {
  key: 4,
  class: "cmst:flex cmst:flex-col cmst:gap-1.5",
  "data-testid": "vue-playground-queue"
}, $k = { class: "cmst:text-sm cmst:font-semibold" }, Ik = { class: "cmst:flex cmst:flex-col cmst:gap-1" }, Rk = ["data-testid"], Ak = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, Ek = ["aria-label", "onClick"], Ok = { class: "cmst:flex cmst:gap-2" }, Tk = {
  class: "cmst:min-w-0 cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4",
  "data-testid": "vue-playground-inspector",
  "aria-label": "Workflow controls"
}, Pk = {
  key: 0,
  role: "status",
  class: "cmst:py-4 cmst:text-sm cmst:opacity-70"
}, Mk = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-2 cmst:py-4",
  role: "alert"
}, Nk = { class: "cmst:text-sm" }, zk = {
  key: 3,
  class: "cmst:py-1 cmst:text-[13px] cmst:opacity-70",
  role: "status"
}, Dk = {
  key: 4,
  class: "cmst:py-1 cmst:text-[13px]",
  role: "alert"
}, jk = {
  key: 0,
  class: "cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4",
  "data-testid": "vue-playground-composer",
  role: "dialog",
  "aria-label": "Experiment composer"
}, Lk = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Uk = { class: "cmst:flex cmst:gap-2" }, Vk = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-2" }, Fk = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]" }, Bk = ["id", "checked", "data-testid", "onChange"], Wk = ["id", "value", "data-testid", "onInput"], Gk = {
  class: "cmst:bg-cmst-bg cmst:py-3",
  "data-testid": "vue-playground-action-zone"
}, qk = /* @__PURE__ */ Mt({
  __name: "PlaygroundView",
  setup(e) {
    const t = ix(), s = di(), n = Nn(), o = So(), r = ai(), a = /* @__PURE__ */ I(!1), i = /* @__PURE__ */ I("source_image"), l = /* @__PURE__ */ I(!1), u = /* @__PURE__ */ I({}), d = /* @__PURE__ */ I([]), f = ge(() => ec[t.activeMode]), b = ge(() => t.schema.prompt ? "prompt" : Object.keys(t.schema).find((ae) => ae.endsWith("_prompt")) ?? null), h = ge(() => t.activeSubtool !== "text" || !b.value ? [] : [b.value, "negative_prompt"].filter((ae) => t.schema[ae])), O = ge(
      () => t.currentGenerationId ? n.records.find((ae) => ae.id === t.currentGenerationId) ?? null : null
    ), x = ge(() => {
      const _ = O.value?.featuredOutput;
      if (!_) return null;
      try {
        return ho(_);
      } catch {
        return null;
      }
    }), C = ge(() => {
      const ae = t.controlValues.source_image;
      return typeof ae == "string" && ae ? ae : null;
    });
    function T() {
      return {
        ...o.outputPreferences ?? {},
        ...t.outputOverride
      };
    }
    async function A() {
      await s.initialize();
      const ae = t.workflowId, S = s.workflows.find((ue) => ue.workflow_id === ae) ?? s.workflows[0];
      S && await z(String(S.workflow_id));
    }
    async function z(ae) {
      try {
        await s.selectWorkflow(ae);
      } catch {
      }
      const _ = s.versions.find(
        (S) => S.workflow_version_id === s.selectedWorkflow?.latest_version_id
      ) ?? s.versions[s.versions.length - 1] ?? null;
      await t.selectWorkflow(ae, _?.workflow_version_id ?? ""), d.value = [];
    }
    async function R(ae) {
      try {
        await s.selectVersion(ae);
      } catch {
      }
      await t.selectWorkflow(t.workflowId, ae), d.value = [];
    }
    function J(ae) {
      const S = s.presets.find(
        (ue) => String(ue.preset_id ?? ue.id) === ae
      )?.state ?? null;
      t.applyPreset(S, ae);
    }
    async function $e(ae) {
      if (ae === "generate") {
        (await t.submitRun({ modalOptions: T() })).ok && await n.loadFeed();
        return;
      }
      if (ae === "queue") {
        t.setQueueMode(!0), t.enqueueCurrent();
        return;
      }
      t.setExperimentMode(!0), l.value = !0;
    }
    async function ne() {
      (await t.drainQueue({ modalOptions: T() })).ok && await n.loadFeed();
    }
    async function j() {
      (await t.submitExperimentDef({ modalOptions: T() })).ok && (l.value = !1, await n.loadFeed());
    }
    function re(ae) {
      i.value = ae, a.value = !0;
    }
    function ve(ae) {
      const _ = i.value;
      a.value = !1;
      const S = ae.featuredOutput, ue = S ? ho(S) : ae.id;
      _ === "source_image" ? (t.setSource(String(ue), t.contextKey), d.value = []) : t.addReference(String(ue));
    }
    function Me(ae, _) {
      t.setAxis(ae, { enabled: _ });
    }
    function Ie(ae) {
      return u.value[ae] ?? "";
    }
    function Oe(ae, _) {
      u.value = { ...u.value, [ae]: _ };
      const S = _.split(/[\n,]+/).map((ue) => ue.trim()).filter((ue) => ue !== "");
      t.setAxis(ae, { enabled: !0, values: S });
    }
    function Ye() {
      t.currentGenerationId ? r.push({ name: "history", query: { focus: t.currentGenerationId } }) : r.push({ name: "history" });
    }
    return Ns(async () => {
      await o.initialize().catch(() => {
      }), await n.initialize().catch(() => {
      }), await A();
    }), ss(
      () => t.controlValues.source_image,
      () => {
        d.value = [];
      }
    ), (ae, _) => (g(), w("section", {
      class: Ve(m(Tr)("cmst:h-full")),
      "data-testid": "vue-page-playground"
    }, [
      _[27] || (_[27] = c("h2", {
        class: "cmst:sr-only",
        "data-testid": "vue-playground-title"
      }, "Playground", -1)),
      c("div", Fx, [
        c("select", {
          id: "pg-workflow",
          value: m(t).workflowId,
          class: "cmst:h-9 cmst:max-w-64 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
          "aria-label": "Workflow",
          "data-testid": "vue-playground-workflow",
          onChange: _[0] || (_[0] = (S) => z(S.target.value))
        }, [
          _[12] || (_[12] = c("option", {
            value: "",
            disabled: ""
          }, "Select a workflow…", -1)),
          (g(!0), w(de, null, Le(m(s).workflows, (S) => (g(), w("option", {
            key: String(S.workflow_id),
            value: String(S.workflow_id)
          }, M(String(S.name || S.workflow_id)), 9, Wx))), 128))
        ], 40, Bx),
        m(s).versions.length ? (g(), w("select", {
          key: 0,
          id: "pg-version",
          value: m(t).versionId,
          class: "cmst:h-9 cmst:max-w-44 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
          "aria-label": "Version",
          "data-testid": "vue-playground-version",
          onChange: _[1] || (_[1] = (S) => R(S.target.value))
        }, [
          (g(!0), w(de, null, Le(m(s).versions, (S) => (g(), w("option", {
            key: String(S.workflow_version_id),
            value: String(S.workflow_version_id)
          }, " v" + M(String(S.version ?? S.workflow_version_id).slice(0, 8)), 9, qx))), 128))
        ], 40, Gx)) : Q("", !0),
        m(s).presets.length ? (g(), w("select", {
          key: 1,
          id: "pg-preset",
          value: m(t).presetId ?? "",
          class: "cmst:h-9 cmst:max-w-44 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
          "aria-label": "Preset",
          "data-testid": "vue-playground-preset",
          onChange: _[2] || (_[2] = (S) => J(S.target.value))
        }, [
          _[13] || (_[13] = c("option", { value: "" }, "No preset", -1)),
          (g(!0), w(de, null, Le(m(s).presets, (S) => (g(), w("option", {
            key: String(S.preset_id ?? S.id),
            value: String(S.preset_id ?? S.id)
          }, M(String(S.name ?? S.preset_id ?? S.id)), 9, Zx))), 128))
        ], 40, Hx)) : Q("", !0),
        m(t).presetDirty ? (g(), w("span", Kx, " Modified ")) : Q("", !0),
        c("div", Qx, [
          (g(), w(de, null, Le(["generate", "edit", "post"], (S) => c("button", {
            key: S,
            type: "button",
            role: "tab",
            "aria-selected": m(t).activeMode === S ? "true" : "false",
            class: Ve(["cmst:rounded-lg cmst:px-2.5 cmst:py-1.5 cmst:text-[13px] cmst:capitalize", m(t).activeMode === S ? "cmst:bg-cmst-raised cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-hover"]),
            "data-testid": `vue-playground-mode-${S}`,
            onClick: (ue) => m(t).setTool(S, m(ec)[S][0])
          }, M(S), 11, Jx)), 64))
        ])
      ]),
      c("div", Yx, [
        (g(!0), w(de, null, Le(f.value, (S) => (g(), w("button", {
          key: S,
          type: "button",
          role: "tab",
          "aria-selected": m(t).activeSubtool === S ? "true" : "false",
          disabled: m(Va).includes(S),
          title: m(Va).includes(S) ? "Arrives in a later phase — execution is disabled" : "",
          class: Ve(["cmst:rounded-lg cmst:px-2.5 cmst:py-1.5 cmst:text-[13px] cmst:capitalize cmst:disabled:cursor-not-allowed cmst:disabled:opacity-40", m(t).activeSubtool === S ? "cmst:bg-cmst-raised cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-hover"]),
          "data-testid": `vue-playground-subtool-${S}`,
          onClick: (ue) => m(t).setTool(m(t).activeMode, S)
        }, M(S), 11, Xx))), 128))
      ]),
      c("div", ek, [
        c("div", tk, [
          c("div", sk, [
            x.value ? (g(), w("img", {
              key: 0,
              src: x.value,
              alt: "Current generation result",
              class: "cmst:max-h-[52vh] cmst:w-full cmst:object-contain",
              "data-testid": "vue-playground-result"
            }, null, 8, nk)) : C.value ? (g(), w("div", ok, [
              c("img", {
                src: C.value,
                alt: "Source image",
                class: "cmst:max-h-[44vh] cmst:rounded cmst:object-contain",
                "data-testid": "vue-playground-source-preview"
              }, null, 8, rk),
              _[14] || (_[14] = c("span", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Source image", -1))
            ])) : (g(), w("div", ak, [
              V(m(hv), {
                class: "cmst:size-6 cmst:opacity-40",
                "aria-hidden": "true"
              }),
              c("p", ik, M(m(t).contextStatus === "loading" ? "Loading workflow…" : m(t).workflowId ? "No output yet. Describe the image, then Generate." : "Select a workflow to begin."), 1)
            ]))
          ]),
          m(t).runState.message ? (g(), w("div", lk, [
            c("span", ck, M(m(t).runState.message), 1),
            m(t).isBusy ? (g(), w("button", {
              key: 0,
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
              "data-testid": "vue-playground-cancel",
              onClick: _[3] || (_[3] = (S) => m(t).cancelRun())
            }, " Cancel ")) : Q("", !0),
            m(t).currentGenerationId && m(t).runState.status === "succeeded" ? (g(), w("button", {
              key: 1,
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
              "data-testid": "vue-playground-open-history",
              onClick: Ye
            }, " Open in History ")) : Q("", !0)
          ])) : Q("", !0),
          h.value.length ? (g(), w("div", uk, [
            (g(!0), w(de, null, Le(h.value, (S) => (g(), w("div", {
              key: S,
              class: "cmst:flex cmst:flex-col cmst:gap-1.5"
            }, [
              c("label", {
                for: `pg-center-${S}`,
                class: "cmst:text-[13px] cmst:font-medium cmst:text-cmst-secondary-text"
              }, M(S === "prompt" ? "Prompt" : "Negative prompt"), 9, dk),
              c("textarea", {
                id: `pg-center-${S}`,
                value: String(m(t).controlValues[S] ?? ""),
                rows: S === "prompt" ? 4 : 2,
                class: "cmst:w-full cmst:rounded-xl cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-3 cmst:py-2.5 cmst:text-[15px]",
                "data-testid": `vue-playground-prompt-${S}`,
                onInput: (ue) => m(t).setControl(S, ue.target.value)
              }, null, 40, fk)
            ]))), 128))
          ])) : Q("", !0),
          m(t).activeSubtool === "references" ? (g(), w("div", mk, [
            c("div", pk, [
              _[16] || (_[16] = c("h3", { class: "cmst:text-sm cmst:font-semibold" }, "References", -1)),
              V(ee, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-playground-add-reference",
                onClick: _[4] || (_[4] = (S) => re("references"))
              }, {
                default: X(() => [..._[15] || (_[15] = [
                  D(" Add from History ", -1)
                ])]),
                _: 1
              })
            ]),
            m(t).references.length ? (g(), w("ul", gk, [
              (g(!0), w(de, null, Le(m(t).references, (S) => (g(), w("li", {
                key: S.id,
                class: "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-lg cmst:bg-cmst-surface cmst:px-2.5 cmst:py-2 cmst:text-[13px]",
                "data-testid": `vue-playground-reference-${S.id}`
              }, [
                c("img", {
                  src: S.filename,
                  alt: S.filename,
                  class: "cmst:size-10 cmst:rounded cmst:object-cover",
                  loading: "lazy"
                }, null, 8, yk),
                c("span", bk, M(S.filename), 1),
                c("button", {
                  type: "button",
                  class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:hover:bg-cmst-hover",
                  "aria-label": `Remove ${S.filename}`,
                  onClick: (ue) => m(t).removeReference(S.id)
                }, " Remove ", 8, wk)
              ], 8, hk))), 128))
            ])) : (g(), w("p", vk, " No reference images. They ride alongside the run without entering control values. "))
          ])) : Q("", !0),
          m(t).activeSubtool === "sketch" ? (g(), w("div", _k, [
            _[18] || (_[18] = c("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Sketch base", -1)),
            _[19] || (_[19] = c("p", { class: "cmst:text-[13px] cmst:text-cmst-muted" }, " Changing the base clears overlay strokes. The flattened sketch commits to the source image on save. ", -1)),
            c("div", xk, [
              V(ee, {
                variant: "outline",
                size: "sm",
                "data-testid": "vue-playground-sketch-history",
                onClick: _[5] || (_[5] = (S) => re("source_image"))
              }, {
                default: X(() => [..._[17] || (_[17] = [
                  D(" Use History image as base ", -1)
                ])]),
                _: 1
              }),
              C.value ? (g(), w("span", kk, M(C.value), 1)) : Q("", !0),
              d.value.length ? (g(), w("span", Sk, M(d.value.length) + " strokes ", 1)) : Q("", !0)
            ])
          ])) : Q("", !0),
          m(t).queueMode && m(t).queueCount > 0 ? (g(), w("div", Ck, [
            c("h3", $k, "Queue (" + M(m(t).queueCount) + ")", 1),
            c("ul", Ik, [
              (g(!0), w(de, null, Le(m(t).queue, (S) => (g(), w("li", {
                key: S.id,
                class: "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-lg cmst:bg-cmst-surface cmst:px-2.5 cmst:py-1.5 cmst:text-[13px]",
                "data-testid": `vue-playground-queued-${S.id}`
              }, [
                c("span", Ak, M(S.label), 1),
                c("button", {
                  type: "button",
                  class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:hover:bg-cmst-hover",
                  "aria-label": `Remove ${S.label}`,
                  onClick: (ue) => m(t).removeQueued(S.id)
                }, " Remove ", 8, Ek)
              ], 8, Rk))), 128))
            ]),
            c("div", Ok, [
              V(ee, {
                variant: "default",
                size: "sm",
                "data-testid": "vue-playground-drain",
                onClick: ne
              }, {
                default: X(() => [..._[20] || (_[20] = [
                  D(" Drain queue ", -1)
                ])]),
                _: 1
              }),
              V(ee, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-playground-clear-queue",
                onClick: _[6] || (_[6] = (S) => m(t).clearQueue())
              }, {
                default: X(() => [..._[21] || (_[21] = [
                  D(" Clear ", -1)
                ])]),
                _: 1
              })
            ])
          ])) : Q("", !0)
        ]),
        c("aside", Tk, [
          m(t).contextStatus === "loading" ? (g(), w("div", Pk, " Loading workflow… ")) : m(t).contextStatus === "error" ? (g(), w("div", Mk, [
            c("p", Nk, M(m(t).contextError || "Workflow unavailable"), 1),
            V(ee, {
              variant: "outline",
              size: "sm",
              onClick: A
            }, {
              default: X(() => [
                V(m(Ov), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                }),
                _[22] || (_[22] = D(" Retry ", -1))
              ]),
              _: 1
            })
          ])) : (g(), ft(Tx, {
            key: 2,
            schema: m(t).schema,
            values: m(t).controlValues,
            "hide-roles": h.value,
            onUpdate: _[7] || (_[7] = (S, ue) => m(t).setControl(S, ue)),
            onPickImage: re,
            onUploadImage: _[8] || (_[8] = (S, ue) => {
              m(t).uploadSource(ue);
            }),
            onClearImage: _[9] || (_[9] = () => m(t).clearSource())
          }, null, 8, ["schema", "values", "hide-roles"])),
          m(t).sourceUploading ? (g(), w("div", zk, " Uploading… ")) : Q("", !0),
          m(t).sourceError ? (g(), w("div", Dk, M(m(t).sourceError), 1)) : Q("", !0)
        ])
      ]),
      l.value ? (g(), w("div", jk, [
        c("div", Lk, [
          _[25] || (_[25] = c("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Experiment axes", -1)),
          c("div", Uk, [
            V(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-playground-composer-close",
              onClick: _[10] || (_[10] = (S) => l.value = !1)
            }, {
              default: X(() => [..._[23] || (_[23] = [
                D(" Close ", -1)
              ])]),
              _: 1
            }),
            V(ee, {
              variant: "default",
              size: "sm",
              "data-testid": "vue-playground-composer-submit",
              onClick: j
            }, {
              default: X(() => [..._[24] || (_[24] = [
                D(" Submit experiment ", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        _[26] || (_[26] = c("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, " One value per line or comma-separated. The experiment entity itself lives in History once submitted. ", -1)),
        c("div", Vk, [
          (g(!0), w(de, null, Le(Object.keys(m(t).schema), (S) => (g(), w("div", {
            key: S,
            class: "cmst:flex cmst:flex-col cmst:gap-1"
          }, [
            c("label", Fk, [
              c("input", {
                id: `pg-axis-${S}`,
                type: "checkbox",
                checked: !!m(t).experimentAxes[S]?.enabled,
                "data-testid": `vue-playground-axis-${S}`,
                onChange: (ue) => Me(S, ue.target.checked)
              }, null, 40, Bk),
              D(" " + M(S), 1)
            ]),
            m(t).experimentAxes[S]?.enabled ? (g(), w("textarea", {
              key: 0,
              id: `pg-axis-values-${S}`,
              value: Ie(S),
              rows: "2",
              class: "cmst:w-full cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:py-1.5 cmst:text-sm",
              "data-testid": `vue-playground-axis-values-${S}`,
              placeholder: "one value per line",
              onInput: (ue) => Oe(S, ue.target.value)
            }, null, 40, Wk)) : Q("", !0)
          ]))), 128))
        ])
      ])) : Q("", !0),
      c("footer", Gk, [
        V(Vx, {
          disabled: m(t).gateReason !== null,
          reason: m(t).gateReason,
          busy: m(t).isBusy,
          "busy-label": m(t).runState.status === "submitting" ? "Submitting…" : "Running…",
          "queue-count": m(t).queueCount,
          "experiment-mode": m(t).experimentMode,
          "queue-mode": m(t).queueMode,
          onSubmit: $e
        }, null, 8, ["disabled", "reason", "busy", "busy-label", "queue-count", "experiment-mode", "queue-mode"])
      ]),
      a.value ? (g(), ft(yd, {
        key: 1,
        onSelect: ve,
        onCancel: _[11] || (_[11] = (S) => a.value = !1)
      })) : Q("", !0)
    ], 2));
  }
}), Hk = {
  class: "cmst:block cmst:min-h-[60vh]",
  "data-testid": "vue-page-settings"
}, Zk = {
  class: "cmst-settings-sheet",
  role: "dialog",
  "aria-modal": "true",
  "aria-label": "Settings",
  tabindex: "-1"
}, Kk = { class: "cmst-settings-head" }, Qk = { class: "cmst:flex cmst:items-center cmst:gap-1" }, Jk = ["disabled"], Yk = {
  key: 0,
  class: "cmst:px-5 cmst:pt-2 cmst:text-[13px] cmst:text-cmst-danger",
  role: "alert"
}, Xk = { class: "cmst-settings-body" }, e0 = {
  "aria-label": "Settings sections",
  class: "cmst-side-nav cmst:min-w-0 cmst:lg:pr-2"
}, t0 = ["aria-selected", "aria-current", "data-testid", "onClick"], s0 = { class: "cmst:capitalize" }, n0 = { class: "cmst:min-w-0 cmst:max-w-3xl" }, o0 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, r0 = { class: "cmst:mt-1" }, a0 = { class: "cmst-setting-row" }, i0 = ["value"], l0 = { class: "cmst-setting-row" }, c0 = { class: "cmst-setting-row" }, u0 = { class: "cmst-setting-row" }, d0 = ["value"], f0 = ["value"], m0 = {
  key: 0,
  class: "cmst-setting-row"
}, p0 = { class: "cmst-min-w-0" }, v0 = { class: "cmst-type-meta cmst:mt-0.5" }, g0 = {
  key: 0,
  class: "cmst-type-meta cmst:mt-0.5"
}, h0 = {
  class: "cmst:flex cmst:items-center cmst:gap-3",
  role: "radiogroup",
  "aria-label": "Active GPU order"
}, y0 = { class: "cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px]" }, b0 = ["checked"], w0 = {
  key: 0,
  class: "cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px]"
}, _0 = ["checked"], x0 = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted"
}, k0 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, S0 = { class: "cmst:mt-1" }, C0 = { class: "cmst-setting-row" }, $0 = { class: "cmst-setting-row" }, I0 = { class: "cmst-setting-row" }, R0 = { class: "cmst-setting-row" }, A0 = { class: "cmst-setting-row" }, E0 = { class: "cmst-setting-row" }, O0 = { class: "cmst:mt-3" }, T0 = { class: "cmst:mt-1" }, P0 = ["aria-pressed", "aria-label", "data-testid", "onClick"], M0 = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]" }, N0 = {
  key: 0,
  class: "cmst:py-3 cmst:text-xs cmst:text-cmst-muted"
}, z0 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, D0 = { class: "cmst:mt-1" }, j0 = { class: "cmst-setting-row" }, L0 = ["value"], U0 = ["value"], V0 = { class: "cmst-setting-row" }, F0 = ["value"], B0 = { class: "cmst-setting-row" }, W0 = ["value"], G0 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, q0 = { class: "cmst:mt-1" }, H0 = { class: "cmst-setting-row" }, Z0 = { class: "cmst:min-w-0" }, K0 = { class: "cmst:text-xs cmst:text-cmst-muted" }, Q0 = {
  key: 0,
  "data-testid": "vue-settings-restart-banner"
}, J0 = { class: "cmst-setting-row" }, Y0 = { class: "cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" }, X0 = /* @__PURE__ */ Mt({
  __name: "SettingsView",
  setup(e) {
    const t = So(), s = ai(), n = /* @__PURE__ */ I(75), o = /* @__PURE__ */ I(""), r = /* @__PURE__ */ I("original"), a = /* @__PURE__ */ I("balanced"), i = /* @__PURE__ */ I(!1), l = /* @__PURE__ */ I(!0), u = /* @__PURE__ */ I("off"), d = /* @__PURE__ */ I(70), f = /* @__PURE__ */ I("off"), b = /* @__PURE__ */ I(""), h = /* @__PURE__ */ I(!1), O = /* @__PURE__ */ I(!1), x = ge(() => t.config), C = ge(() => x.value?.available_gpus ?? []), T = ge(() => {
      const ae = t.selectedGoldenProfile;
      return ae ? t.goldenProfiles.find((_) => _.name === ae) ?? null : null;
    }), A = ge(() => {
      const ae = t.selectedGoldenProfile;
      return ae && t.goldenGpuOrder[ae] || "A";
    });
    function z(ae) {
      const _ = (Array.isArray(ae) ? ae : []).map(String);
      return _.length ? _.map((S) => {
        const ue = C.value.find((Ue) => String(Ue.value).toLowerCase() === S.toLowerCase());
        return ue?.label || ue?.value || S;
      }).join(" → ") : "—";
    }
    const R = /* @__PURE__ */ I(null);
    function J() {
      s.push({ name: "playground" });
    }
    function $e(ae) {
      ae.key !== "Escape" || ae.defaultPrevented || (ae.stopPropagation(), J());
    }
    function ne() {
      const ae = x.value;
      ae && (n.value = ae.quality, o.value = ae.save_folder, r.value = ae.output_format, a.value = ae.webp_lossless_compression, i.value = ae.auto_save_local, l.value = ae.save_metadata_sidecar, u.value = ae.data_saver_default, d.value = ae.data_saver_quality, f.value = t.profileLevel, b.value = ae.gpu, h.value = ae.skip_plan_validation);
    }
    Ns(async () => {
      await t.initialize().catch(() => {
      }), await t.loadGolden().catch(() => {
      }), ne(), R.value?.focus(), document.addEventListener("keydown", $e);
    }), xo(() => {
      document.removeEventListener("keydown", $e);
    });
    async function j() {
      await t.save({
        output_format: r.value,
        quality: Number(n.value),
        webp_lossless_compression: a.value,
        auto_save_local: i.value,
        save_folder: o.value,
        save_metadata_sidecar: l.value,
        data_saver_default: u.value,
        data_saver_quality: Number(d.value)
      }).catch(() => {
      }), ne();
    }
    async function re() {
      await t.save({ gpu: b.value }).catch(() => {
      }), ne();
    }
    async function ve() {
      await t.save({
        data_saver_default: u.value,
        data_saver_quality: Number(d.value)
      }).catch(() => {
      }), ne();
    }
    async function Me() {
      await t.setSkipPlanValidation(h.value).catch(() => {
      }), ne();
    }
    async function Ie() {
      await t.setProfile(f.value).catch(() => {
      }), ne();
    }
    async function Oe(ae) {
      await t.resetSection(ae), ne();
    }
    async function Ye() {
      if (!O.value) {
        O.value = !0;
        return;
      }
      O.value = !1, await t.resetAll(), ne();
    }
    return (ae, _) => (g(), w("section", Hk, [
      _[60] || (_[60] = c("div", {
        class: "cmst-settings-backdrop",
        "aria-hidden": "true"
      }, null, -1)),
      c("div", Zk, [
        c("div", Kk, [
          _[22] || (_[22] = c("h1", { class: "cmst-type-view" }, "Settings", -1)),
          c("div", Qk, [
            c("button", {
              type: "button",
              class: "cmst-icon-btn",
              "aria-label": "Reload settings",
              disabled: m(t).loading,
              "data-testid": "vue-settings-reload",
              onClick: _[0] || (_[0] = (S) => m(t).load().then(ne).catch(() => {
              }))
            }, [
              V(m(Rr), {
                class: Ve(["cmst:size-4", m(t).loading ? "cmst:animate-spin" : ""]),
                "aria-hidden": "true"
              }, null, 8, ["class"])
            ], 8, Jk),
            c("button", {
              ref_key: "closeBtn",
              ref: R,
              type: "button",
              class: "cmst-close-btn",
              "aria-label": "Close settings",
              "data-testid": "vue-settings-close",
              onClick: J
            }, [
              V(m(sr), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })
            ], 512)
          ])
        ]),
        m(t).error ? (g(), w("div", Yk, M(m(t).error), 1)) : Q("", !0),
        c("div", Xk, [
          c("nav", e0, [
            (g(!0), w(de, null, Le(m(Hu), (S) => (g(), w("button", {
              key: S,
              type: "button",
              class: "cmst-quiet-tab",
              "aria-selected": m(t).activeSection === S,
              "aria-current": m(t).activeSection === S ? "true" : void 0,
              "data-testid": `vue-settings-tab-${S}`,
              onClick: (ue) => m(t).setSection(S)
            }, [
              c("span", s0, M(S), 1)
            ], 8, t0))), 128))
          ]),
          c("div", n0, [
            m(t).activeSection === "generation" ? (g(), w(de, { key: 0 }, [
              c("div", o0, [
                _[24] || (_[24] = c("h2", { class: "cmst-type-section" }, "Generation", -1)),
                V(ee, {
                  variant: "ghost",
                  size: "sm",
                  "data-testid": "vue-settings-reset-generation",
                  onClick: _[1] || (_[1] = (S) => Oe("generation"))
                }, {
                  default: X(() => [..._[23] || (_[23] = [
                    D("Reset section", -1)
                  ])]),
                  _: 1
                })
              ]),
              c("div", r0, [
                c("div", a0, [
                  _[25] || (_[25] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "GPU"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Execution device for this workspace.")
                  ], -1)),
                  je(c("select", {
                    "onUpdate:modelValue": _[2] || (_[2] = (S) => b.value = S),
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "data-testid": "vue-settings-gpu",
                    "aria-label": "GPU",
                    onChange: re
                  }, [
                    (g(!0), w(de, null, Le(C.value, (S) => (g(), w("option", {
                      key: S.value,
                      value: S.value
                    }, M(S.label), 9, i0))), 128))
                  ], 544), [
                    [Qt, b.value]
                  ])
                ]),
                c("div", l0, [
                  _[27] || (_[27] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Data Saver default"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Serve bandwidth-saving variants unless asked otherwise.")
                  ], -1)),
                  je(c("select", {
                    "onUpdate:modelValue": _[3] || (_[3] = (S) => u.value = S),
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "Data Saver default",
                    onChange: ve
                  }, [..._[26] || (_[26] = [
                    c("option", { value: "off" }, "Off", -1),
                    c("option", { value: "on" }, "On", -1)
                  ])], 544), [
                    [Qt, u.value]
                  ])
                ]),
                c("div", c0, [
                  _[28] || (_[28] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Data Saver quality"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Quality level for Data Saver variants, 1–100.")
                  ], -1)),
                  je(c("input", {
                    "onUpdate:modelValue": _[4] || (_[4] = (S) => d.value = S),
                    type: "number",
                    min: "1",
                    max: "100",
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "Data Saver quality",
                    onChange: ve
                  }, null, 544), [
                    [
                      ut,
                      d.value,
                      void 0,
                      { number: !0 }
                    ]
                  ])
                ]),
                c("div", u0, [
                  _[30] || (_[30] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Golden profile"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Pinned known-good deployment profile.")
                  ], -1)),
                  c("select", {
                    value: m(t).selectedGoldenProfile,
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "data-testid": "vue-settings-golden-profile",
                    "aria-label": "Golden profile",
                    onChange: _[5] || (_[5] = (S) => m(t).selectGoldenProfile(S.target.value))
                  }, [
                    _[29] || (_[29] = c("option", { value: "" }, "None", -1)),
                    (g(!0), w(de, null, Le(m(t).goldenProfiles, (S) => (g(), w("option", {
                      key: S.name,
                      value: S.name
                    }, M(S.name), 9, f0))), 128))
                  ], 40, d0)
                ]),
                T.value ? (g(), w("div", m0, [
                  c("div", p0, [
                    _[31] || (_[31] = c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Active GPU order", -1)),
                    c("p", v0, "A: " + M(z(T.value.gpu_order_a)), 1),
                    T.value.gpu_order_b?.length ? (g(), w("p", g0, "B: " + M(z(T.value.gpu_order_b)), 1)) : Q("", !0)
                  ]),
                  c("div", h0, [
                    c("label", y0, [
                      c("input", {
                        type: "radio",
                        name: "vue-golden-order",
                        value: "A",
                        checked: A.value !== "B",
                        "data-testid": "vue-settings-golden-order-a",
                        onChange: _[6] || (_[6] = (S) => m(t).setGoldenGpuOrder(T.value.name, "A"))
                      }, null, 40, b0),
                      _[32] || (_[32] = D(" A ", -1))
                    ]),
                    T.value.gpu_order_b?.length ? (g(), w("label", w0, [
                      c("input", {
                        type: "radio",
                        name: "vue-golden-order",
                        value: "B",
                        checked: A.value === "B",
                        "data-testid": "vue-settings-golden-order-b",
                        onChange: _[7] || (_[7] = (S) => m(t).setGoldenGpuOrder(T.value.name, "B"))
                      }, null, 40, _0),
                      _[33] || (_[33] = D(" B ", -1))
                    ])) : Q("", !0)
                  ])
                ])) : Q("", !0)
              ]),
              x.value?.engine_migration_notice ? (g(), w("p", x0, M(x.value.engine_migration_notice), 1)) : Q("", !0)
            ], 64)) : Q("", !0),
            m(t).activeSection === "outputs" ? (g(), w(de, { key: 1 }, [
              c("div", k0, [
                _[35] || (_[35] = c("h2", { class: "cmst-type-section" }, "Outputs", -1)),
                V(ee, {
                  variant: "ghost",
                  size: "sm",
                  "data-testid": "vue-settings-reset-outputs",
                  onClick: _[8] || (_[8] = (S) => Oe("outputs"))
                }, {
                  default: X(() => [..._[34] || (_[34] = [
                    D("Reset section", -1)
                  ])]),
                  _: 1
                })
              ]),
              c("div", S0, [
                c("div", C0, [
                  _[37] || (_[37] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Output format"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Saved image format. Original keeps the engine default.")
                  ], -1)),
                  je(c("select", {
                    "onUpdate:modelValue": _[9] || (_[9] = (S) => r.value = S),
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "Output format"
                  }, [..._[36] || (_[36] = [
                    c("option", { value: "original" }, "Original", -1),
                    c("option", { value: "png" }, "PNG", -1),
                    c("option", { value: "jpeg" }, "JPEG", -1),
                    c("option", { value: "webp" }, "WebP", -1)
                  ])], 512), [
                    [Qt, r.value]
                  ])
                ]),
                c("div", $0, [
                  _[38] || (_[38] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Quality"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Compression quality for lossy formats, 1–100.")
                  ], -1)),
                  je(c("input", {
                    "onUpdate:modelValue": _[10] || (_[10] = (S) => n.value = S),
                    type: "number",
                    min: "1",
                    max: "100",
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "Quality"
                  }, null, 512), [
                    [
                      ut,
                      n.value,
                      void 0,
                      { number: !0 }
                    ]
                  ])
                ]),
                c("div", I0, [
                  _[40] || (_[40] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "WebP lossless compression"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Effort spent on lossless WebP encodes.")
                  ], -1)),
                  je(c("select", {
                    "onUpdate:modelValue": _[11] || (_[11] = (S) => a.value = S),
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "WebP lossless compression"
                  }, [..._[39] || (_[39] = [
                    c("option", { value: "balanced" }, "Balanced", -1),
                    c("option", { value: "fast" }, "Fast", -1),
                    c("option", { value: "best" }, "Best", -1)
                  ])], 512), [
                    [Qt, a.value]
                  ])
                ]),
                c("div", R0, [
                  _[41] || (_[41] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Save folder"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Local destination for saved outputs.")
                  ], -1)),
                  je(c("input", {
                    "onUpdate:modelValue": _[12] || (_[12] = (S) => o.value = S),
                    type: "text",
                    class: "cmst-field cmst:w-56 cmst:max-w-full cmst:font-mono",
                    "aria-label": "Save folder"
                  }, null, 512), [
                    [ut, o.value]
                  ])
                ]),
                c("div", A0, [
                  _[42] || (_[42] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Auto-save local"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Write a local copy of every output automatically.")
                  ], -1)),
                  je(c("input", {
                    "onUpdate:modelValue": _[13] || (_[13] = (S) => i.value = S),
                    type: "checkbox",
                    "aria-label": "Auto-save local"
                  }, null, 512), [
                    [un, i.value]
                  ])
                ]),
                c("div", E0, [
                  _[43] || (_[43] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Save metadata sidecar"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Keep generation parameters alongside each file.")
                  ], -1)),
                  je(c("input", {
                    "onUpdate:modelValue": _[14] || (_[14] = (S) => l.value = S),
                    type: "checkbox",
                    "aria-label": "Save metadata sidecar"
                  }, null, 512), [
                    [un, l.value]
                  ])
                ])
              ]),
              c("div", O0, [
                V(ee, {
                  size: "sm",
                  variant: "secondary",
                  disabled: m(t).saving,
                  "data-testid": "vue-settings-save-output",
                  onClick: j
                }, {
                  default: X(() => [
                    D(M(m(t).saving ? "Saving…" : "Save outputs"), 1)
                  ]),
                  _: 1
                }, 8, ["disabled"])
              ])
            ], 64)) : Q("", !0),
            m(t).activeSection === "accounts" ? (g(), w(de, { key: 2 }, [
              _[44] || (_[44] = c("h2", { class: "cmst-type-section" }, "Accounts & tokens", -1)),
              _[45] || (_[45] = c("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, "Sign-in status lives in Manage Modal.", -1)),
              c("div", T0, [
                (g(!0), w(de, null, Le(m(t).goldenProfiles, (S) => (g(), w("div", {
                  key: S.name,
                  class: "cmst-data-row"
                }, [
                  c("button", {
                    type: "button",
                    class: "cmst-icon-btn",
                    "aria-pressed": m(t).favoriteGoldenProfiles.includes(S.name) ? "true" : "false",
                    "aria-label": `Toggle favorite for ${S.name}`,
                    "data-testid": `vue-golden-favorite-${S.name}`,
                    onClick: (ue) => m(t).toggleGoldenFavorite(S.name)
                  }, [
                    V(m(tr), {
                      class: Ve(["cmst:size-3.5", m(t).favoriteGoldenProfiles.includes(S.name) ? "cmst:fill-cmst-primary cmst:text-cmst-primary" : ""]),
                      "aria-hidden": "true"
                    }, null, 8, ["class"])
                  ], 8, P0),
                  c("span", M0, M(S.name), 1)
                ]))), 128)),
                m(t).goldenProfiles.length ? Q("", !0) : (g(), w("p", N0, "Golden catalog not loaded yet."))
              ])
            ], 64)) : Q("", !0),
            m(t).activeSection === "interface" ? (g(), w(de, { key: 3 }, [
              c("div", z0, [
                _[47] || (_[47] = c("h2", { class: "cmst-type-section" }, "Interface", -1)),
                V(ee, {
                  variant: "ghost",
                  size: "sm",
                  onClick: _[15] || (_[15] = (S) => Oe("interface"))
                }, {
                  default: X(() => [..._[46] || (_[46] = [
                    D("Reset section", -1)
                  ])]),
                  _: 1
                })
              ]),
              c("div", D0, [
                c("div", j0, [
                  _[48] || (_[48] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "History grid columns"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Media grid density on the History page.")
                  ], -1)),
                  c("select", {
                    value: m(t).columnsPreference,
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "History grid columns",
                    onChange: _[16] || (_[16] = (S) => m(t).setHistoryColumns(S.target.value))
                  }, [
                    (g(), w(de, null, Le([2, 3, 4, 5, 6, 7, 8], (S) => c("option", {
                      key: S,
                      value: String(S)
                    }, M(S), 9, U0)), 64))
                  ], 40, L0)
                ]),
                c("div", V0, [
                  _[50] || (_[50] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Remote inventory refresh"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "How often shared inventory re-syncs in the background.")
                  ], -1)),
                  c("select", {
                    value: m(t).refreshIntervalPreference,
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "Remote inventory refresh",
                    onChange: _[17] || (_[17] = (S) => m(t).setInventoryInterval(S.target.value))
                  }, [..._[49] || (_[49] = [
                    Yo('<option value="0">Off</option><option value="60">1 minute</option><option value="300">5 minutes</option><option value="900">15 minutes</option><option value="1800">30 minutes</option>', 5)
                  ])], 40, F0)
                ]),
                c("div", B0, [
                  _[52] || (_[52] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Shell density"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Spacing rhythm for the Studio shell.")
                  ], -1)),
                  c("select", {
                    value: m(t).density,
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "data-testid": "vue-density-toggle",
                    "aria-label": "Shell density",
                    onChange: _[18] || (_[18] = (S) => m(t).setDensity(S.target.value))
                  }, [..._[51] || (_[51] = [
                    c("option", { value: "comfortable" }, "Comfortable", -1),
                    c("option", { value: "compact" }, "Compact", -1)
                  ])], 40, W0)
                ])
              ])
            ], 64)) : Q("", !0),
            m(t).activeSection === "advanced" ? (g(), w(de, { key: 4 }, [
              c("div", G0, [
                _[54] || (_[54] = c("h2", { class: "cmst-type-section" }, "Advanced", -1)),
                V(ee, {
                  variant: "ghost",
                  size: "sm",
                  onClick: _[19] || (_[19] = (S) => Oe("advanced"))
                }, {
                  default: X(() => [..._[53] || (_[53] = [
                    D("Reset section", -1)
                  ])]),
                  _: 1
                })
              ]),
              c("div", q0, [
                c("div", H0, [
                  c("div", Z0, [
                    _[56] || (_[56] = c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Heavy tracing", -1)),
                    c("p", K0, [
                      _[55] || (_[55] = D(" Requires ComfyUI restart. ", -1)),
                      m(t).profileLevel !== m(t).effectiveProfileLevel ? (g(), w("span", Q0, " Restart pending: selected " + M(m(t).profileLevel) + ", effective " + M(m(t).effectiveProfileLevel) + ". ", 1)) : Q("", !0)
                    ])
                  ]),
                  je(c("select", {
                    "onUpdate:modelValue": _[20] || (_[20] = (S) => f.value = S),
                    class: "cmst-field cmst:w-56 cmst:max-w-full",
                    "aria-label": "Heavy tracing",
                    onChange: Ie
                  }, [..._[57] || (_[57] = [
                    Yo('<option value="off">Off</option><option value="summary">Summary</option><option value="detailed">Detailed</option><option value="trace">Trace</option><option value="trace_verbose">Verbose trace</option>', 5)
                  ])], 544), [
                    [Qt, f.value]
                  ])
                ]),
                c("div", J0, [
                  _[58] || (_[58] = c("div", { class: "cmst:min-w-0" }, [
                    c("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Skip plan validation"),
                    c("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Temporary triage only. Re-enable after debugging.")
                  ], -1)),
                  je(c("input", {
                    "onUpdate:modelValue": _[21] || (_[21] = (S) => h.value = S),
                    type: "checkbox",
                    "data-testid": "vue-settings-skip-validation",
                    "aria-label": "Skip plan validation",
                    onChange: Me
                  }, null, 544), [
                    [un, h.value]
                  ])
                ])
              ]),
              c("div", Y0, [
                V(ee, {
                  variant: "outline",
                  size: "sm",
                  class: "cmst:text-cmst-danger",
                  "data-testid": "vue-settings-reset-all",
                  onClick: Ye
                }, {
                  default: X(() => [
                    D(M(O.value ? "Confirm reset all settings" : "Reset all settings"), 1)
                  ]),
                  _: 1
                }),
                _[59] || (_[59] = c("p", { class: "cmst:mt-1 cmst:text-xs cmst:text-cmst-muted" }, "Resets only Settings-owned keys. Credentials and user data are not affected.", -1))
              ])
            ], 64)) : Q("", !0)
          ])
        ])
      ])
    ]));
  }
}), eS = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, tS = { class: "cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted" }, sS = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, nS = { class: "cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px] cmst:text-cmst-muted" }, oS = {
  key: 0,
  class: "cmst:flex cmst:flex-col cmst:gap-2 cmst:border-y cmst:border-solid cmst:border-cmst-border cmst:py-3"
}, rS = {
  key: 0,
  class: "cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, aS = { class: "cmst:grid cmst:grid-cols-1 cmst:gap-6 cmst:lg:grid-cols-[300px_minmax(0,1fr)]" }, iS = { class: "cmst:min-w-0" }, lS = { class: "cmst:relative" }, cS = { class: "cmst:mt-2 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, uS = {
  class: "cmst-seg",
  role: "tablist",
  "aria-label": "Workflows or shared inventory"
}, dS = ["data-active", "aria-selected"], fS = ["data-active", "aria-selected"], mS = {
  key: 0,
  role: "listbox",
  "aria-label": "Workflows",
  class: "cmst:mt-2 cmst:min-w-0"
}, pS = ["aria-selected", "data-testid", "onClick"], vS = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, gS = { class: "cmst-type-object cmst:truncate" }, hS = {
  key: 0,
  class: "cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate"
}, yS = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, bS = {
  key: 0,
  class: "cmst:w-full cmst:min-w-0 cmst:max-w-4xl"
}, wS = { class: "cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3" }, _S = { class: "cmst:min-w-0" }, xS = { class: "cmst-type-view cmst:truncate" }, kS = {
  key: 0,
  class: "cmst-type-meta cmst:mt-0.5"
}, SS = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, CS = ["data-testid", "aria-pressed"], $S = { class: "cmst:relative" }, IS = { class: "cmst:absolute cmst:right-0 cmst:z-20 cmst:mt-1 cmst:flex cmst:w-52 cmst:flex-col cmst:gap-2 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-raised cmst:p-3 cmst:shadow-[var(--cmst-shadow-overlay)]" }, RS = { class: "cmst-field-label" }, AS = ["value"], ES = ["value"], OS = { class: "cmst:mt-3 cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4" }, TS = { class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, PS = { class: "cmst-field-label" }, MS = { class: "cmst-field-label" }, NS = { class: "cmst:mt-3" }, zS = {
  "aria-label": "Mapping",
  class: "cmst:mt-6"
}, DS = { class: "cmst-type-meta cmst:mt-0.5" }, jS = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, LS = {
  key: 0,
  class: "cmst:mt-2"
}, US = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, VS = { class: "cmst:mt-1.5" }, FS = {
  "aria-label": "Dependencies",
  class: "cmst:mt-6",
  "data-testid": "vue-dependencies"
}, BS = { class: "cmst-type-meta cmst:mt-0.5" }, WS = { class: "cmst:mt-2 cmst:flex cmst:max-h-56 cmst:flex-col cmst:gap-1 cmst:overflow-auto" }, GS = { class: "cmst:min-w-0 cmst:flex-1" }, qS = { class: "cmst:text-cmst-muted" }, HS = {
  class: "cmst-type-meta",
  "data-testid": "dependency-model-state"
}, ZS = {
  class: "cmst:flex cmst:items-center cmst:gap-1 cmst:text-xs cmst:text-cmst-muted",
  title: "Optional: skip this file when checking or installing requirements"
}, KS = ["checked", "onChange"], QS = ["href"], JS = ["onUpdate:modelValue", "aria-label", "data-testid"], YS = {
  key: 1,
  class: "cmst:w-full cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "dependency-model-install-note"
}, XS = { class: "cmst:min-w-0 cmst:flex-1" }, e2 = {
  key: 1,
  class: "cmst:w-full cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "dependency-node-install-note"
}, t2 = {
  "aria-label": "Portability",
  class: "cmst:mt-6"
}, s2 = { class: "cmst-type-meta cmst:mt-0.5" }, n2 = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, o2 = {
  key: 0,
  class: "cmst:mt-2"
}, r2 = { class: "cmst-field-label" }, a2 = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, i2 = {
  key: 1,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text",
  "data-testid": "vue-manifest-preview"
}, l2 = { class: "cmst:mt-1.5 cmst:flex cmst:gap-1.5" }, c2 = {
  "aria-label": "Presets",
  class: "cmst:mt-6"
}, u2 = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, d2 = { class: "cmst:mt-1" }, f2 = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, m2 = ["aria-label", "onKeyup"], p2 = { class: "cmst:truncate" }, v2 = { class: "cmst:flex cmst:shrink-0 cmst:gap-1" }, g2 = {
  key: 0,
  class: "cmst:mt-1 cmst:flex cmst:items-center cmst:gap-1.5"
}, h2 = ["onUpdate:modelValue", "aria-label"], y2 = ["value"], b2 = {
  "aria-label": "Guidance mapping",
  class: "cmst:mt-6"
}, w2 = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, _2 = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text",
  "data-testid": "vue-guidance-result"
}, x2 = {
  key: 1,
  class: "cmst:py-8 cmst:text-[13px] cmst:text-cmst-muted"
}, k2 = {
  key: 1,
  class: "cmst:min-w-0"
}, S2 = { class: "cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted" }, C2 = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, $2 = { class: "cmst:relative cmst:min-w-0 cmst:flex-1" }, I2 = ["value"], R2 = { class: "cmst-type-section cmst:mt-5" }, A2 = { class: "cmst-type-meta" }, E2 = {
  class: "cmst:mt-1 cmst:flex cmst:max-h-80 cmst:flex-col cmst:gap-1 cmst:overflow-auto",
  "data-testid": "vue-library-models"
}, O2 = ["aria-expanded", "onClick"], T2 = { class: "cmst-min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:font-medium" }, P2 = { class: "cmst-type-meta cmst:shrink-0" }, M2 = {
  key: 0,
  class: "cmst:mt-1 cmst:pl-1 cmst:text-xs cmst:text-cmst-muted"
}, N2 = { class: "cmst-type-meta" }, z2 = {
  key: 0,
  class: "cmst-type-meta cmst:mt-0.5"
}, D2 = ["title"], j2 = {
  key: 2,
  class: "cmst-type-meta cmst:mt-0.5"
}, L2 = {
  key: 3,
  class: "cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-secondary-text"
}, U2 = { class: "cmst:mt-1.5 cmst:flex cmst:flex-wrap cmst:gap-1.5" }, V2 = ["onUpdate:modelValue", "aria-label"], F2 = {
  key: 0,
  class: "cmst:py-3 cmst:text-[13px] cmst:text-cmst-muted"
}, B2 = { class: "cmst-type-section cmst:mt-5" }, W2 = { class: "cmst-type-meta" }, G2 = {
  class: "cmst:mt-1 cmst:flex cmst:max-h-80 cmst:flex-col cmst:gap-1 cmst:overflow-auto",
  "data-testid": "vue-library-nodes"
}, q2 = ["aria-expanded", "onClick"], H2 = { class: "cmst-min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:font-medium" }, Z2 = {
  key: 0,
  class: "cmst-type-meta cmst:shrink-0"
}, K2 = {
  key: 0,
  class: "cmst:mt-1 cmst:pl-1 cmst:text-xs cmst:text-cmst-muted"
}, Q2 = {
  key: 0,
  class: "cmst-type-meta cmst:truncate"
}, J2 = {
  key: 1,
  class: "cmst-type-meta cmst:mt-0.5"
}, Y2 = {
  key: 2,
  class: "cmst-type-meta cmst:mt-0.5"
}, X2 = {
  key: 0,
  class: "cmst:py-3 cmst:text-[13px] cmst:text-cmst-muted"
}, eC = {
  key: 1,
  "data-state": "open",
  "aria-hidden": "true",
  style: { display: "none" }
}, tC = { "data-studio-app": "" }, sC = ["onKeydown"], nC = { class: "cmst-inspector-head" }, oC = { class: "cmst:flex cmst:items-start cmst:justify-between cmst:gap-3" }, rC = { class: "cmst:min-w-0" }, aC = { class: "cmst-type-meta cmst:mt-0.5" }, iC = {
  class: "cmst-progress-thin cmst:mt-2",
  "aria-hidden": "true"
}, lC = { class: "cmst-inspector-body" }, cC = { class: "cmst-field-label cmst:mt-3" }, uC = ["value"], dC = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-warn",
  role: "status"
}, fC = { class: "cmst:mt-1" }, mC = ["data-testid"], pC = { class: "cmst:flex cmst:items-center cmst:gap-2" }, vC = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:font-medium" }, gC = { class: "cmst:mt-0.5 cmst:truncate cmst:text-xs cmst:text-cmst-muted" }, hC = {
  key: 0,
  class: "cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1"
}, yC = ["title", "onClick"], bC = {
  key: 1,
  class: "cmst:mt-1"
}, wC = { class: "cmst:mt-1" }, _C = ["data-testid"], xC = { class: "cmst:flex cmst:items-center cmst:gap-2" }, kC = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]" }, SC = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text",
  role: "status"
}, CC = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, $C = { class: "cmst:mt-2 cmst:text-[13px]" }, IC = { class: "cmst:mt-3 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" }, RC = { class: "cmst:text-[13px] cmst:text-cmst-muted" }, AC = { class: "cmst:mt-2" }, EC = { class: "cmst:mt-2 cmst:max-h-40 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text" }, OC = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-warn",
  role: "status",
  "data-testid": "vue-wizard-gate"
}, TC = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, PC = {
  key: 2,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text",
  role: "status"
}, MC = { class: "cmst:mt-3" }, NC = { class: "cmst-inspector-foot" }, zC = {
  key: 1,
  class: "cmst-type-meta"
}, DC = /* @__PURE__ */ Mt({
  __name: "WorkflowsView",
  setup(e) {
    const t = di(), s = Er(), n = /* @__PURE__ */ I(""), o = /* @__PURE__ */ I("workflows"), r = /* @__PURE__ */ I(""), a = /* @__PURE__ */ I(""), i = /* @__PURE__ */ I(""), l = /* @__PURE__ */ I(""), u = /* @__PURE__ */ I(""), d = /* @__PURE__ */ I(""), f = /* @__PURE__ */ I(!1), b = /* @__PURE__ */ I(""), h = /* @__PURE__ */ I(""), O = /* @__PURE__ */ I("txt2img"), x = /* @__PURE__ */ I(""), C = /* @__PURE__ */ I(!1), T = ge(() => Math.max(0, ks.indexOf(t.wizardDraft?.step ?? "feature-type"))), A = ge(() => ks[T.value]);
    function z(W) {
      return W.folder ? W.folder : (W.tags ?? []).find((y) => !!y) ?? "";
    }
    const R = ge(() => {
      const p = t.selectedVersion?.version;
      return typeof p == "number" ? `Version ${p}` : "";
    }), J = /* @__PURE__ */ new Set(["output", "outputBinding", "controls", "featureType", "step", "version"]), $e = ge(() => {
      const W = t.mapping;
      if (!W) return { configured: !1, bindings: 0, controls: 0 };
      const p = W.bindings, y = p && typeof p == "object" ? Object.keys(p).length : Object.keys(W).filter((ot) => !J.has(ot)).length, _e = W.controls;
      return {
        configured: !0,
        bindings: y,
        controls: Array.isArray(_e) ? _e.length : 0
      };
    }), ne = /* @__PURE__ */ I(!1), j = {
      "feature-type": "Feature",
      "required-bindings": "Bindings",
      "exposed-controls": "Controls",
      details: "Review"
    }, re = ge(() => j[A.value] ?? A.value), ve = ge(() => Wl(t.wizardDraft?.featureType ?? "t2i")), Me = ge(() => Gh(t.wizardDraft?.featureType ?? "t2i"));
    function Ie(W) {
      if (!W || typeof W != "object") return "graph target";
      const p = W;
      return String(p.nodeTitle ?? p.target ?? p.nodeId ?? "graph target");
    }
    function Oe(W) {
      return !W || typeof W != "object" ? !1 : W.confirmed === !0;
    }
    Ns(async () => {
      await Promise.all([t.initialize(), s.initialize()]), await t.maybeResumeWizard().catch(() => !1);
    });
    async function Ye() {
      t.query = n.value, await t.loadList();
    }
    async function ae(W) {
      await t.selectWorkflow(W);
      const p = t.selectedWorkflow;
      i.value = String(p?.name ?? ""), l.value = String(p?.folder ?? "");
    }
    function _() {
      t.openWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!0);
    }
    function S() {
      window.__comfymodalCancelStudioGraphBinding?.(), t.closeWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
    }
    function ue(W) {
      W.key !== "Escape" || W.defaultPrevented || t.wizardOpen && (W.stopPropagation(), S());
    }
    ss(
      () => t.wizardOpen,
      (W) => {
        W ? document.addEventListener("keydown", ue) : document.removeEventListener("keydown", ue);
      }
    ), xo(() => {
      document.removeEventListener("keydown", ue);
    });
    async function Ue(W) {
      const p = tn(W).label;
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = `Click a node in the ComfyUI graph for ${p}…`, await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: W,
          label: p,
          allowOutput: !1,
          onCapture: (y) => {
            t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, [W]: { ...y, confirmed: !0 } } }), a.value = `${p} bound to ${String(y.nodeTitle ?? y.nodeId ?? "graph target")}`;
          },
          onCancel: (y) => {
            a.value = y;
          }
        });
        return;
      }
      t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, [W]: { target: W, confirmed: !0 } } }), a.value = `${p} recorded without a live graph`;
    }
    function ie(W) {
      return (t.wizardDraft?.bindings ?? {})[W] ?? null;
    }
    async function tt(W) {
      const p = ie(W), y = p ? String(p.nodeId ?? p.node_id ?? "") : "";
      if (!y || !window.__comfymodalViewStudioGraphNode) {
        a.value = "Open the graph to locate this target";
        return;
      }
      const _e = await window.__comfymodalViewStudioGraphNode(y).catch(() => null);
      a.value = _e && _e.ok !== !1 ? `Centered ${tn(W).label} on the graph` : String(_e?.reason || "Node not found on the canvas");
    }
    const De = /* @__PURE__ */ I({});
    async function bt(W) {
      if (!window.__comfymodalSuggestStudioGraphTargets) {
        a.value = "Suggestions need the live graph";
        return;
      }
      const p = Hh(W);
      if (!p.length) {
        a.value = `No static hint for ${tn(W).label} — capture against the exact input`;
        return;
      }
      try {
        const y = await window.__comfymodalSuggestStudioGraphTargets(p, 3);
        De.value = { ...De.value, [W]: Array.isArray(y) ? y : [] }, De.value[W].length || (a.value = "No matching nodes on this graph");
      } catch {
        a.value = "Suggestion lookup failed";
      }
    }
    async function ke(W) {
      window.__comfymodalViewStudioGraphNode && await window.__comfymodalViewStudioGraphNode(String(W)).catch(() => null);
    }
    const $ = ge(() => {
      const W = t.wizardDraft?.featureType ?? "t2i", p = Wl(W).filter((y) => !Oe(ie(y))).map((y) => tn(y).label);
      return Oe(t.wizardDraft?.outputBinding) || p.push("Output"), p;
    });
    async function F() {
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = "Click the output node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "output",
          label: "output",
          allowOutput: !0,
          onCapture: (W) => {
            t.updateWizard({ outputBinding: { ...W, confirmed: !0 } }), a.value = `Output bound to ${String(W.nodeTitle ?? W.nodeId ?? "graph target")}`;
          },
          onCancel: (W) => {
            a.value = W;
          }
        });
        return;
      }
      t.updateWizard({ outputBinding: { target: "SaveImage.images", confirmed: !0 } }), a.value = "Output binding recorded";
    }
    async function U() {
      if ($.value.length > 0) {
        a.value = `Still needed: ${$.value.join(", ")}`;
        return;
      }
      a.value = "";
      try {
        await t.saveWizardMapping(), a.value = "Mapping saved", window.__comfymodalCancelStudioGraphBinding?.(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
      } catch (W) {
        a.value = W instanceof Error ? W.message : "Save failed";
      }
    }
    function B() {
      const W = ks[Math.min(ks.length - 1, T.value + 1)];
      t.setWizardStep(W);
    }
    function q() {
      const W = ks[Math.max(0, T.value - 1)];
      t.setWizardStep(W);
    }
    function me() {
      if (!r.value.trim()) return;
      const W = [...t.wizardDraft?.controls ?? [], { label: r.value.trim(), enabled: !0 }];
      t.updateWizard({ controls: W }), r.value = "";
    }
    function v(W) {
      const p = W ?? {};
      return String(p.preset_id || p.id || "");
    }
    const k = /* @__PURE__ */ I(""), P = /* @__PURE__ */ I(""), L = /* @__PURE__ */ I({});
    function Z(W) {
      k.value = v(W), P.value = String(W.name || "");
    }
    async function Y(W) {
      const p = v(W), y = P.value.trim();
      k.value = "", !(!p || !y) && await t.savePreset(p, { name: y }).catch(() => {
      });
    }
    async function E(W) {
      const p = v(W), y = L.value[p];
      !p || !y || await t.copyPresetForward(p, y).catch(() => {
      });
    }
    const G = /* @__PURE__ */ I(null);
    async function H() {
      G.value = null;
      try {
        G.value = await t.loadGuidance(h.value, O.value);
      } catch {
      }
    }
    async function K() {
      h.value.trim() && (await t.removeGuidance(h.value.trim(), O.value).catch(() => {
      }), G.value = null);
    }
    const ye = /* @__PURE__ */ I(""), le = /* @__PURE__ */ I("");
    async function Re() {
      le.value = "";
      try {
        await t.previewManifestImport(JSON.parse(ye.value || "{}"));
      } catch (W) {
        le.value = W instanceof Error ? W.message : "Preview failed";
      }
    }
    async function Te() {
      le.value = "";
      try {
        await t.commitManifestImport(JSON.parse(ye.value || "{}")), ye.value = "";
      } catch (W) {
        le.value = W instanceof Error ? W.message : "Import failed";
      }
    }
    async function qe() {
      d.value = "";
      try {
        const W = JSON.parse(u.value);
        await t.importNewWorkflow(W), u.value = "";
      } catch (W) {
        d.value = W instanceof Error ? W.message : "Import failed";
      }
    }
    async function st() {
      await t.updateMetadata({ name: i.value, folder: l.value }).catch(() => {
      });
    }
    async function et() {
      try {
        await t.saveMapping(JSON.parse(x.value || "{}"));
      } catch {
      }
    }
    const te = ge(() => t.dependencies ?? {}), pe = ge(() => {
      const W = te.value.models;
      if (!Array.isArray(W)) return [];
      const p = new Set(
        Array.isArray(te.value.nonessential_keys ?? te.value.nonessential) ? (te.value.nonessential_keys ?? te.value.nonessential).map(String) : []
      );
      return W.filter((y) => !!y && typeof y == "object").map((y, _e) => {
        const ot = String(y.key || y.filename || `model-${_e}`), Wt = Array.isArray(y.source_urls) ? y.source_urls : [];
        return {
          key: ot,
          filename: String(y.filename || ot),
          folder: String(y.folder || ""),
          state: String(y.state || "unknown"),
          nonessential: p.has(ot),
          hasSource: Wt.length > 0 || typeof y.remote_model == "object",
          message: t.dependencyInstallMessage[ot] ?? "",
          raw: y
        };
      }).sort((y, _e) => (y.state === "missing" ? 0 : 1) - (_e.state === "missing" ? 0 : 1));
    }), he = ge(() => {
      const W = te.value.custom_nodes;
      return Array.isArray(W) ? W.filter((p) => !!p && typeof p == "object").map((p, y) => {
        const _e = String(p.name || p.cnr_id || `node-${y}`);
        return {
          key: _e,
          name: String(p.name || _e),
          state: String(p.state || "unknown"),
          message: t.dependencyInstallMessage[_e] ?? "",
          raw: p
        };
      }) : [];
    }), ze = ge(() => {
      if (!t.dependencies) return "not loaded";
      const W = pe.value, p = he.value, y = [
        ...W.filter((Wt) => Wt.state === "missing" && !Wt.nonessential),
        ...p.filter((Wt) => Wt.state === "missing")
      ].length, _e = W.filter((Wt) => Wt.state === "missing" && Wt.nonessential).length, ot = [
        ...W.filter((Wt) => Wt.state === "installed" || Wt.state === "ready"),
        ...p.filter((Wt) => Wt.state === "installed")
      ].length;
      return y > 0 ? `${ot} installed · ${y} missing · attention` : _e > 0 ? `${ot} installed · ${_e} optional missing · ready` : !W.length && !p.length ? "no requirements" : `${ot} installed · ready`;
    }), Ke = ge(() => {
      const W = t.versionState;
      if (W && typeof W.runnable == "boolean")
        return W.runnable ? "Runnable" : "Not runnable — resolve dependencies";
      const p = t.selectedVersion;
      return p && typeof p.runnable == "boolean" ? p.runnable ? "Runnable" : "Not runnable — resolve dependencies" : "";
    }), Ne = ge(() => Ke.value === "Runnable");
    async function He(W, p) {
      const y = new Set(
        pe.value.filter((_e) => _e.nonessential).map((_e) => _e.key)
      );
      p ? y.add(W) : y.delete(W), await t.markNonessential([...y]).catch(() => {
      });
    }
    async function Qe(W) {
      const p = W.raw.remote_model && typeof W.raw.remote_model == "object" ? W.raw.remote_model : W.raw, y = String(p.url || p.download_url || ""), _e = y ? { url: y, filename: W.filename, save_path: W.folder } : { filename: W.filename, folder: W.folder };
      try {
        await s.installModel(_e);
      } catch {
      }
    }
    const oe = /* @__PURE__ */ I({});
    function we(W) {
      return t.modelInstallTarget(W.raw);
    }
    function it(W) {
      return (Array.isArray(W.raw.source_urls) ? W.raw.source_urls : []).map(String).find(Boolean) ?? "";
    }
    async function lt(W, p) {
      const y = p.trim();
      if (y) {
        t.dependencyInstallMessage[W.key] = "Queueing…";
        try {
          await s.installModelRequest({ url: y, filename: W.filename, save_path: W.folder }), t.dependencyInstallMessage[W.key] = "Queued for download";
        } catch (_e) {
          t.dependencyInstallMessage[W.key] = _e instanceof Error ? _e.message : "Queue failed";
        }
      }
    }
    async function At(W, p) {
      const y = p.trim();
      if (y)
        try {
          await s.installModel({ url: y, filename: W.filename, save_path: W.folder });
        } catch {
        }
    }
    function Ze(W) {
      t.libraryQuery = W, o.value = "models";
    }
    const N = /* @__PURE__ */ I(""), se = /* @__PURE__ */ I(""), Ae = /* @__PURE__ */ I({}), Be = ge(() => {
      const W = /* @__PURE__ */ new Set();
      for (const p of s.models) {
        const y = String(p.model_type || p.folder || "");
        y && W.add(y);
      }
      return [...W].sort();
    }), Et = ge(() => {
      const W = t.libraryQuery.trim().toLowerCase();
      return s.models.filter((p) => N.value && String(p.model_type || p.folder || "") !== N.value ? !1 : W ? [p.display_name, p.filename, p.folder, p.model_type, p.provider].map((_e) => String(_e || "").toLowerCase()).join(" ").includes(W) : !0);
    }), Ot = ge(() => {
      const W = t.libraryQuery.trim().toLowerCase();
      return W ? s.customNodes.filter((p) => {
        const y = Array.isArray(p.classes) ? p.classes.map(String).join(" ") : "";
        return [p.title, p.name, p.id, y].map((ot) => String(ot || "").toLowerCase()).join(" ").includes(W);
      }) : s.customNodes;
    });
    function wt(W) {
      const p = typeof W == "number" ? W : Number(W);
      if (!Number.isFinite(p) || p <= 0) return null;
      if (p < 1024) return `${p} B`;
      const y = ["KB", "MB", "GB", "TB"];
      let _e = p / 1024, ot = 0;
      for (; _e >= 1024 && ot < y.length - 1; )
        _e /= 1024, ot += 1;
      return `${_e >= 100 ? Math.round(_e) : _e.toFixed(1)} ${y[ot]}`;
    }
    async function Bt(W) {
      const p = String(W.model_id || W.filename || ""), y = (Ae.value[p] ?? "").trim();
      if (!(!W.model_id || !y))
        try {
          await s.updateModelNotes(String(W.model_id), { notes: y }), Ae.value[p] = "";
        } catch {
        }
    }
    async function Pr(W) {
      await t.installDependencyNode(W.raw);
    }
    return (W, p) => (g(), w("section", {
      class: Ve(m(Tr)()),
      "data-testid": "vue-page-workflows"
    }, [
      m(t).wizardOpen ? Q("", !0) : (g(), w(de, { key: 0 }, [
        c("div", eS, [
          c("div", null, [
            p[37] || (p[37] = c("h1", { class: "cmst-type-view" }, "Workflows", -1)),
            c("p", tS, M(m(t).workflows.length) + " workflows ", 1)
          ]),
          c("div", sS, [
            je(c("select", {
              "onUpdate:modelValue": p[0] || (p[0] = (y) => m(t).tagFilter = y),
              class: "cmst-field",
              "aria-label": "Filter by tag",
              onChange: p[1] || (p[1] = (y) => m(t).loadList())
            }, [...p[38] || (p[38] = [
              c("option", { value: "" }, "All tags", -1)
            ])], 544), [
              [Qt, m(t).tagFilter]
            ]),
            c("label", nS, [
              je(c("input", {
                "onUpdate:modelValue": p[2] || (p[2] = (y) => m(t).favoritesOnly = y),
                type: "checkbox",
                onChange: p[3] || (p[3] = (y) => m(t).loadList())
              }, null, 544), [
                [un, m(t).favoritesOnly]
              ]),
              p[39] || (p[39] = D(" Favorites ", -1))
            ]),
            V(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": "vue-workflow-import-toggle",
              onClick: p[4] || (p[4] = (y) => f.value = !f.value)
            }, {
              default: X(() => [
                V(m(bv), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                }),
                p[40] || (p[40] = D("Import ", -1))
              ]),
              _: 1
            })
          ])
        ]),
        f.value ? (g(), w("div", oS, [
          p[42] || (p[42] = c("label", {
            class: "cmst:text-[13px] cmst:font-medium",
            for: "vue-workflow-import-text"
          }, "Import workflow JSON", -1)),
          je(c("textarea", {
            id: "vue-workflow-import-text",
            "onUpdate:modelValue": p[5] || (p[5] = (y) => u.value = y),
            rows: "3",
            class: "cmst-field cmst:font-mono cmst:text-xs",
            placeholder: '{"name": "...", "static_graph": {...}}',
            "data-testid": "vue-workflow-import-input"
          }, null, 512), [
            [ut, u.value]
          ]),
          d.value ? (g(), w("p", rS, M(d.value), 1)) : Q("", !0),
          c("div", null, [
            V(ee, {
              size: "sm",
              "data-testid": "vue-workflow-import",
              onClick: qe
            }, {
              default: X(() => [...p[41] || (p[41] = [
                D("Import", -1)
              ])]),
              _: 1
            })
          ])
        ])) : Q("", !0),
        c("div", aS, [
          c("div", iS, [
            c("div", lS, [
              V(m(Ea), {
                class: "cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted",
                "aria-hidden": "true"
              }),
              je(c("input", {
                "onUpdate:modelValue": p[6] || (p[6] = (y) => n.value = y),
                class: "cmst-field cmst:w-full cmst:pl-8",
                placeholder: "Search workflows",
                "aria-label": "Search workflows",
                onKeyup: fs(Ye, ["enter"])
              }, null, 544), [
                [ut, n.value]
              ])
            ]),
            c("div", cS, [
              c("div", uS, [
                c("button", {
                  type: "button",
                  role: "tab",
                  class: "cmst-seg-btn",
                  "data-active": o.value === "workflows",
                  "aria-selected": o.value === "workflows",
                  onClick: p[7] || (p[7] = (y) => o.value = "workflows")
                }, [
                  V(m(Du), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  }),
                  p[43] || (p[43] = D("Workflows ", -1))
                ], 8, dS),
                c("button", {
                  type: "button",
                  role: "tab",
                  class: "cmst-seg-btn",
                  "data-active": o.value === "models",
                  "aria-selected": o.value === "models",
                  onClick: p[8] || (p[8] = (y) => o.value = "models")
                }, [
                  V(m(fv), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  }),
                  p[44] || (p[44] = D("Models / Nodes ", -1))
                ], 8, fS)
              ]),
              V(ee, {
                size: "sm",
                variant: "ghost",
                "aria-label": "Refresh workflows",
                onClick: p[9] || (p[9] = (y) => m(t).loadList())
              }, {
                default: X(() => [
                  V(m(Rr), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  })
                ]),
                _: 1
              })
            ]),
            o.value === "workflows" ? (g(), w("div", mS, [
              (g(!0), w(de, null, Le(m(t).workflows, (y) => (g(), w("button", {
                key: y.workflow_id,
                type: "button",
                role: "option",
                class: "cmst-object-row",
                "aria-selected": m(t).selectedWorkflow?.workflow_id === y.workflow_id,
                "data-testid": `vue-workflow-${y.workflow_id}`,
                onClick: (_e) => ae(y.workflow_id)
              }, [
                c("span", vS, [
                  y.favorite ? (g(), ft(m(tr), {
                    key: 0,
                    class: "cmst:size-3.5 cmst:shrink-0 cmst:fill-cmst-primary cmst:text-cmst-primary",
                    "aria-label": "Favorite"
                  })) : Q("", !0),
                  c("strong", gS, M(y.name || "Untitled workflow"), 1)
                ]),
                z(y) ? (g(), w("span", hS, M(z(y)), 1)) : Q("", !0)
              ], 8, pS))), 128)),
              m(t).workflows.length ? Q("", !0) : (g(), w("p", yS, " No workflows returned by the server. "))
            ])) : Q("", !0)
          ]),
          o.value === "workflows" ? (g(), w(de, { key: 0 }, [
            m(t).selectedWorkflow ? (g(), w("div", bS, [
              c("div", wS, [
                c("div", _S, [
                  c("h2", xS, M(m(t).selectedWorkflow.name), 1),
                  R.value ? (g(), w("p", kS, M(R.value), 1)) : Q("", !0),
                  Ke.value ? (g(), w("p", {
                    key: 1,
                    class: Ve(["cmst:mt-1.5 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-xs", Ne.value ? "cmst:text-cmst-ok" : "cmst:text-cmst-warn"]),
                    "data-testid": "vue-version-runnable"
                  }, [
                    c("span", {
                      class: Ve(["cmst:inline-block cmst:size-1.5 cmst:rounded-full", Ne.value ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-warn"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    D(" " + M(Ke.value), 1)
                  ], 2)) : Q("", !0)
                ]),
                c("div", SS, [
                  c("button", {
                    type: "button",
                    "data-testid": `vue-workflow-favorite-${m(t).selectedWorkflow.workflow_id}`,
                    "aria-pressed": !!m(t).selectedWorkflow.favorite,
                    "aria-label": "Toggle favorite",
                    class: Ve(["cmst:rounded-md cmst:p-1.5 cmst:hover:bg-cmst-hover", m(t).selectedWorkflow.favorite ? "cmst:text-cmst-primary" : "cmst:text-cmst-muted"]),
                    onClick: p[10] || (p[10] = (y) => m(t).toggleFavorite(m(t).selectedWorkflow.workflow_id, !m(t).selectedWorkflow.favorite))
                  }, [
                    V(m(tr), {
                      class: Ve(["cmst:size-4", m(t).selectedWorkflow.favorite ? "cmst:fill-cmst-primary" : ""]),
                      "aria-hidden": "true"
                    }, null, 8, ["class"])
                  ], 10, CS),
                  V(ee, {
                    size: "sm",
                    onClick: _
                  }, {
                    default: X(() => [
                      V(m(Lv), {
                        class: "cmst:size-4",
                        "aria-hidden": "true"
                      }),
                      p[45] || (p[45] = D("Setup workflow ", -1))
                    ]),
                    _: 1
                  }),
                  c("details", $S, [
                    p[49] || (p[49] = c("summary", {
                      class: "cmst:cursor-pointer cmst:list-none cmst:rounded-md cmst:px-2 cmst:py-1.5 cmst:text-[13px] cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg [&::-webkit-details-marker]:cmst:hidden",
                      "aria-label": "More workflow actions"
                    }, " ··· ", -1)),
                    c("div", IS, [
                      c("label", RS, [
                        p[46] || (p[46] = D("Version ", -1)),
                        c("select", {
                          value: m(t).selectedVersion?.workflow_version_id ?? "",
                          class: "cmst-field cmst:w-full",
                          "aria-label": "Select version",
                          "data-testid": "vue-version-select",
                          onChange: p[11] || (p[11] = (y) => m(t).selectVersion(y.target.value))
                        }, [
                          (g(!0), w(de, null, Le(m(t).versions, (y) => (g(), w("option", {
                            key: y.workflow_version_id,
                            value: y.workflow_version_id
                          }, " v" + M(y.version ?? y.workflow_version_id), 9, ES))), 128))
                        ], 40, AS)
                      ]),
                      V(ee, {
                        size: "sm",
                        variant: "outline",
                        "data-testid": "vue-version-capture",
                        onClick: p[12] || (p[12] = (y) => m(t).captureVersion({}))
                      }, {
                        default: X(() => [...p[47] || (p[47] = [
                          D(" Capture version ", -1)
                        ])]),
                        _: 1
                      }),
                      V(ee, {
                        size: "sm",
                        variant: "outline",
                        "data-testid": "vue-workflow-delete",
                        onClick: p[13] || (p[13] = (y) => m(t).deleteSelectedWorkflow())
                      }, {
                        default: X(() => [...p[48] || (p[48] = [
                          D(" Delete workflow ", -1)
                        ])]),
                        _: 1
                      })
                    ])
                  ])
                ])
              ]),
              c("div", OS, [
                c("div", TS, [
                  c("label", PS, [
                    p[50] || (p[50] = D("Name", -1)),
                    je(c("input", {
                      "onUpdate:modelValue": p[14] || (p[14] = (y) => i.value = y),
                      class: "cmst-field"
                    }, null, 512), [
                      [ut, i.value]
                    ])
                  ]),
                  c("label", MS, [
                    p[51] || (p[51] = D("Folder", -1)),
                    je(c("input", {
                      "onUpdate:modelValue": p[15] || (p[15] = (y) => l.value = y),
                      class: "cmst-field"
                    }, null, 512), [
                      [ut, l.value]
                    ])
                  ])
                ]),
                c("div", NS, [
                  V(ee, {
                    size: "sm",
                    variant: "secondary",
                    "data-testid": "vue-workflow-save-meta",
                    onClick: st
                  }, {
                    default: X(() => [...p[52] || (p[52] = [
                      D(" Save metadata ", -1)
                    ])]),
                    _: 1
                  })
                ])
              ]),
              c("section", zS, [
                p[55] || (p[55] = c("h3", { class: "cmst-type-section" }, "Mapping", -1)),
                c("p", DS, M($e.value.configured ? `${$e.value.bindings} bindings · ${$e.value.controls} controls` : "not configured"), 1),
                c("div", jS, [
                  V(ee, {
                    size: "sm",
                    variant: "ghost",
                    onClick: p[16] || (p[16] = (y) => m(t).loadMappingCandidates())
                  }, {
                    default: X(() => [...p[53] || (p[53] = [
                      D("Load candidates", -1)
                    ])]),
                    _: 1
                  }),
                  V(ee, {
                    size: "sm",
                    variant: "ghost",
                    onClick: p[17] || (p[17] = (y) => ne.value = !ne.value)
                  }, {
                    default: X(() => [
                      D(M(ne.value ? "Hide raw mapping" : "Edit raw mapping"), 1)
                    ]),
                    _: 1
                  })
                ]),
                ne.value ? (g(), w("div", LS, [
                  m(t).mappingCandidates ? (g(), w("pre", US, M(JSON.stringify(m(t).mappingCandidates, null, 1).slice(0, 800)), 1)) : Q("", !0),
                  je(c("textarea", {
                    "onUpdate:modelValue": p[18] || (p[18] = (y) => x.value = y),
                    rows: "3",
                    class: "cmst-field cmst:mt-2 cmst:w-full cmst:font-mono cmst:text-xs",
                    placeholder: '{"bindings": {...}}'
                  }, null, 512), [
                    [ut, x.value]
                  ]),
                  c("div", VS, [
                    V(ee, {
                      size: "sm",
                      variant: "secondary",
                      "data-testid": "vue-mapping-save",
                      onClick: et
                    }, {
                      default: X(() => [...p[54] || (p[54] = [
                        D("Save mapping", -1)
                      ])]),
                      _: 1
                    })
                  ])
                ])) : Q("", !0)
              ]),
              c("section", FS, [
                p[63] || (p[63] = c("h3", { class: "cmst-type-section" }, "Dependencies", -1)),
                c("p", BS, M(ze.value), 1),
                c("ul", WS, [
                  (g(!0), w(de, null, Le(pe.value, (y) => (g(), w("li", {
                    key: `model-${y.key}`,
                    class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:rounded-md cmst:px-2 cmst:py-2 cmst:text-[13px] cmst:hover:bg-cmst-hover",
                    "data-testid": "dependency-model-row"
                  }, [
                    c("span", {
                      class: Ve(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", y.state === "missing" ? "cmst:bg-cmst-danger" : y.state === "ready" || y.state === "installed" ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    c("span", GS, [
                      D(M(y.filename) + " ", 1),
                      c("span", qS, "(" + M(y.folder) + ")", 1)
                    ]),
                    c("span", HS, M(y.state), 1),
                    c("label", ZS, [
                      c("input", {
                        type: "checkbox",
                        checked: y.nonessential,
                        onChange: (_e) => He(y.key, _e.target.checked)
                      }, null, 40, KS),
                      p[56] || (p[56] = D(" Optional ", -1))
                    ]),
                    y.state === "missing" ? (g(), w(de, { key: 0 }, [
                      it(y) ? (g(), w("a", {
                        key: 0,
                        href: it(y),
                        target: "_blank",
                        rel: "noopener noreferrer",
                        class: "cmst:text-xs cmst:text-cmst-muted cmst:hover:text-cmst-fg"
                      }, "source", 8, QS)) : Q("", !0),
                      we(y).url ? (g(), w(de, { key: 1 }, [
                        V(ee, {
                          size: "sm",
                          variant: "ghost",
                          "data-testid": "dependency-model-install-now",
                          title: we(y).viaManager ? "Manager catalog match" : "Direct source",
                          onClick: (_e) => Qe(y)
                        }, {
                          default: X(() => [...p[57] || (p[57] = [
                            D("Install now", -1)
                          ])]),
                          _: 1
                        }, 8, ["title", "onClick"]),
                        V(ee, {
                          size: "sm",
                          variant: "ghost",
                          "data-testid": "dependency-model-queue",
                          onClick: (_e) => lt(y, we(y).url)
                        }, {
                          default: X(() => [...p[58] || (p[58] = [
                            D("Queue install", -1)
                          ])]),
                          _: 1
                        }, 8, ["onClick"])
                      ], 64)) : (g(), w(de, { key: 2 }, [
                        je(c("input", {
                          "onUpdate:modelValue": (_e) => oe.value[y.key] = _e,
                          class: "cmst-field cmst:w-44 cmst:max-w-full cmst:font-mono cmst:text-xs",
                          placeholder: "Paste source URL",
                          "aria-label": `Source URL for ${y.filename}`,
                          "data-testid": `dependency-model-url-${y.key}`
                        }, null, 8, JS), [
                          [ut, oe.value[y.key]]
                        ]),
                        V(ee, {
                          size: "sm",
                          variant: "ghost",
                          "data-testid": "dependency-model-install-url",
                          onClick: (_e) => At(y, oe.value[y.key] ?? "")
                        }, {
                          default: X(() => [...p[59] || (p[59] = [
                            D("Install", -1)
                          ])]),
                          _: 1
                        }, 8, ["onClick"])
                      ], 64)),
                      V(ee, {
                        size: "sm",
                        variant: "ghost",
                        "data-testid": "dependency-model-find",
                        onClick: (_e) => Ze(y.filename)
                      }, {
                        default: X(() => [...p[60] || (p[60] = [
                          D("Find in library", -1)
                        ])]),
                        _: 1
                      }, 8, ["onClick"])
                    ], 64)) : Q("", !0),
                    y.message ? (g(), w("span", YS, M(y.message), 1)) : Q("", !0)
                  ]))), 128)),
                  (g(!0), w(de, null, Le(he.value, (y) => (g(), w("li", {
                    key: `node-${y.key}`,
                    class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:rounded-md cmst:px-2 cmst:py-2 cmst:text-[13px] cmst:hover:bg-cmst-hover",
                    "data-testid": "dependency-node-row"
                  }, [
                    c("span", {
                      class: Ve(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", y.state === "missing" ? "cmst:bg-cmst-danger" : "cmst:bg-cmst-ok"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    c("span", XS, M(y.name) + " · " + M(y.state), 1),
                    y.state === "missing" ? (g(), w(de, { key: 0 }, [
                      m(t).resolveNodePlan(y.raw).kind !== "none" ? (g(), ft(ee, {
                        key: 0,
                        size: "sm",
                        variant: "ghost",
                        "data-testid": "dependency-node-install-now",
                        onClick: (_e) => Pr(y)
                      }, {
                        default: X(() => [...p[61] || (p[61] = [
                          D("Install now", -1)
                        ])]),
                        _: 1
                      }, 8, ["onClick"])) : Q("", !0),
                      V(ee, {
                        size: "sm",
                        variant: "ghost",
                        "data-testid": "dependency-node-find",
                        onClick: (_e) => Ze(y.name)
                      }, {
                        default: X(() => [...p[62] || (p[62] = [
                          D("Find in registry", -1)
                        ])]),
                        _: 1
                      }, 8, ["onClick"])
                    ], 64)) : Q("", !0),
                    y.message ? (g(), w("span", e2, M(y.message), 1)) : Q("", !0)
                  ]))), 128))
                ])
              ]),
              c("section", t2, [
                p[70] || (p[70] = c("h3", { class: "cmst-type-section" }, "Portability", -1)),
                c("p", s2, M(m(t).portability ? "analyzed" : "not analyzed"), 1),
                c("div", n2, [
                  V(ee, {
                    size: "sm",
                    variant: "ghost",
                    onClick: p[19] || (p[19] = (y) => m(t).recheckPortability())
                  }, {
                    default: X(() => [...p[64] || (p[64] = [
                      D("Recheck", -1)
                    ])]),
                    _: 1
                  }),
                  V(ee, {
                    size: "sm",
                    variant: "ghost",
                    "data-testid": "vue-manifest-export",
                    onClick: p[20] || (p[20] = (y) => m(t).exportManifest())
                  }, {
                    default: X(() => [...p[65] || (p[65] = [
                      D("Export manifest", -1)
                    ])]),
                    _: 1
                  }),
                  V(ee, {
                    size: "sm",
                    variant: "ghost",
                    "data-testid": "vue-manifest-import-toggle",
                    onClick: p[21] || (p[21] = (y) => C.value = !C.value)
                  }, {
                    default: X(() => [...p[66] || (p[66] = [
                      D("Import manifest", -1)
                    ])]),
                    _: 1
                  })
                ]),
                C.value ? (g(), w("div", o2, [
                  c("label", r2, [
                    p[67] || (p[67] = D("Manifest JSON ", -1)),
                    je(c("textarea", {
                      "onUpdate:modelValue": p[22] || (p[22] = (y) => ye.value = y),
                      rows: "3",
                      class: "cmst-field cmst:w-full cmst:font-mono cmst:text-xs",
                      placeholder: '{"workflows": [...]}',
                      "data-testid": "vue-manifest-import-input"
                    }, null, 512), [
                      [ut, ye.value]
                    ])
                  ]),
                  le.value ? (g(), w("p", a2, M(le.value), 1)) : Q("", !0),
                  m(t).manifestPreview ? (g(), w("pre", i2, M(JSON.stringify(m(t).manifestPreview, null, 1).slice(0, 800)), 1)) : Q("", !0),
                  c("div", l2, [
                    V(ee, {
                      size: "sm",
                      variant: "secondary",
                      "data-testid": "vue-manifest-preview",
                      onClick: Re
                    }, {
                      default: X(() => [...p[68] || (p[68] = [
                        D("Preview import", -1)
                      ])]),
                      _: 1
                    }),
                    V(ee, {
                      size: "sm",
                      variant: "ghost",
                      "data-testid": "vue-manifest-commit",
                      disabled: !m(t).manifestPreview,
                      onClick: Te
                    }, {
                      default: X(() => [...p[69] || (p[69] = [
                        D("Commit import", -1)
                      ])]),
                      _: 1
                    }, 8, ["disabled"])
                  ])
                ])) : Q("", !0)
              ]),
              c("section", c2, [
                p[79] || (p[79] = c("h3", { class: "cmst-type-section" }, "Presets", -1)),
                p[80] || (p[80] = c("p", { class: "cmst-type-meta cmst:mt-0.5" }, "image-free configuration only", -1)),
                c("div", u2, [
                  je(c("input", {
                    "onUpdate:modelValue": p[23] || (p[23] = (y) => b.value = y),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "Preset name",
                    "aria-label": "Preset name"
                  }, null, 512), [
                    [ut, b.value]
                  ]),
                  V(ee, {
                    size: "sm",
                    variant: "secondary",
                    "data-testid": "vue-preset-create",
                    onClick: p[24] || (p[24] = (y) => {
                      m(t).createPreset({ name: b.value || "Untitled", studio_state: {} }), b.value = "";
                    })
                  }, {
                    default: X(() => [...p[71] || (p[71] = [
                      D("Create preset", -1)
                    ])]),
                    _: 1
                  })
                ]),
                c("ul", d2, [
                  (g(!0), w(de, null, Le(m(t).presets, (y, _e) => (g(), w("li", {
                    key: _e,
                    class: "cmst:rounded-md cmst:px-2 cmst:py-1.5 cmst:text-[13px] cmst:hover:bg-cmst-hover"
                  }, [
                    c("div", f2, [
                      k.value === v(y) ? (g(), w(de, { key: 0 }, [
                        je(c("input", {
                          "onUpdate:modelValue": p[25] || (p[25] = (ot) => P.value = ot),
                          class: "cmst-field cmst:min-w-0 cmst:flex-1 cmst:text-xs",
                          "aria-label": `Rename ${String(y.name || "preset")}`,
                          onKeyup: [
                            fs((ot) => Y(y), ["enter"]),
                            p[26] || (p[26] = fs((ot) => k.value = "", ["esc"]))
                          ]
                        }, null, 40, m2), [
                          [ut, P.value]
                        ]),
                        V(ee, {
                          size: "sm",
                          variant: "secondary",
                          onClick: (ot) => Y(y)
                        }, {
                          default: X(() => [...p[72] || (p[72] = [
                            D("Save", -1)
                          ])]),
                          _: 1
                        }, 8, ["onClick"]),
                        V(ee, {
                          size: "sm",
                          variant: "ghost",
                          onClick: p[27] || (p[27] = (ot) => k.value = "")
                        }, {
                          default: X(() => [...p[73] || (p[73] = [
                            D("Cancel", -1)
                          ])]),
                          _: 1
                        })
                      ], 64)) : (g(), w(de, { key: 1 }, [
                        c("span", p2, M(String(y.name || `preset ${_e}`)), 1),
                        c("span", v2, [
                          V(ee, {
                            size: "sm",
                            variant: "ghost",
                            onClick: (ot) => Z(y)
                          }, {
                            default: X(() => [...p[74] || (p[74] = [
                              D("Rename", -1)
                            ])]),
                            _: 1
                          }, 8, ["onClick"]),
                          V(ee, {
                            size: "sm",
                            variant: "ghost",
                            onClick: (ot) => m(t).duplicateCurrentPreset(v(y))
                          }, {
                            default: X(() => [...p[75] || (p[75] = [
                              D("Duplicate", -1)
                            ])]),
                            _: 1
                          }, 8, ["onClick"]),
                          V(ee, {
                            size: "sm",
                            variant: "ghost",
                            onClick: (ot) => m(t).removePreset(v(y))
                          }, {
                            default: X(() => [...p[76] || (p[76] = [
                              D("Delete", -1)
                            ])]),
                            _: 1
                          }, 8, ["onClick"])
                        ])
                      ], 64))
                    ]),
                    m(t).versions.length > 1 ? (g(), w("div", g2, [
                      p[78] || (p[78] = c("span", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Copy to", -1)),
                      je(c("select", {
                        "onUpdate:modelValue": (ot) => L.value[v(y)] = ot,
                        class: "cmst-field cmst:min-w-0 cmst:flex-1 cmst:text-xs",
                        "aria-label": `Copy ${String(y.name || "preset")} to version`
                      }, [
                        (g(!0), w(de, null, Le(m(t).versions, (ot) => (g(), w("option", {
                          key: ot.workflow_version_id,
                          value: ot.workflow_version_id
                        }, "v" + M(ot.version ?? ot.workflow_version_id), 9, y2))), 128))
                      ], 8, h2), [
                        [Qt, L.value[v(y)]]
                      ]),
                      V(ee, {
                        size: "sm",
                        variant: "ghost",
                        onClick: (ot) => E(y)
                      }, {
                        default: X(() => [...p[77] || (p[77] = [
                          D("Copy", -1)
                        ])]),
                        _: 1
                      }, 8, ["onClick"])
                    ])) : Q("", !0)
                  ]))), 128))
                ])
              ]),
              c("section", b2, [
                p[84] || (p[84] = c("h3", { class: "cmst-type-section" }, "Guidance mapping", -1)),
                c("div", w2, [
                  je(c("input", {
                    "onUpdate:modelValue": p[28] || (p[28] = (y) => h.value = y),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "model sha256",
                    "aria-label": "Model sha256"
                  }, null, 512), [
                    [ut, h.value]
                  ]),
                  je(c("select", {
                    "onUpdate:modelValue": p[29] || (p[29] = (y) => O.value = y),
                    class: "cmst-field",
                    "aria-label": "Guidance mode"
                  }, [...p[81] || (p[81] = [
                    c("option", { value: "txt2img" }, "txt2img", -1),
                    c("option", { value: "i2i" }, "i2i", -1)
                  ])], 512), [
                    [Qt, O.value]
                  ]),
                  V(ee, {
                    size: "sm",
                    variant: "outline",
                    "data-testid": "vue-guidance-load",
                    onClick: H
                  }, {
                    default: X(() => [...p[82] || (p[82] = [
                      D("Load", -1)
                    ])]),
                    _: 1
                  }),
                  G.value ? (g(), ft(ee, {
                    key: 0,
                    size: "sm",
                    variant: "ghost",
                    "data-testid": "vue-guidance-remove",
                    onClick: K
                  }, {
                    default: X(() => [...p[83] || (p[83] = [
                      D("Remove", -1)
                    ])]),
                    _: 1
                  })) : Q("", !0)
                ]),
                G.value ? (g(), w("pre", _2, M(JSON.stringify(G.value, null, 1).slice(0, 800)), 1)) : Q("", !0)
              ])
            ])) : (g(), w("p", x2, " Select a workflow to inspect its versions, mapping, and dependencies. "))
          ], 64)) : (g(), w("div", k2, [
            p[91] || (p[91] = c("h2", { class: "cmst-type-view" }, "Shared models & nodes", -1)),
            c("p", S2, "Models: " + M(m(s).models.length) + " · Custom nodes: " + M(m(s).customNodes.length), 1),
            c("div", C2, [
              c("div", $2, [
                V(m(Ea), {
                  class: "cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted",
                  "aria-hidden": "true"
                }),
                je(c("input", {
                  "onUpdate:modelValue": p[30] || (p[30] = (y) => m(t).libraryQuery = y),
                  class: "cmst-field cmst:w-full cmst:pl-8",
                  placeholder: "Search models and nodes",
                  "aria-label": "Search models and nodes",
                  "data-testid": "vue-library-search"
                }, null, 512), [
                  [ut, m(t).libraryQuery]
                ])
              ]),
              je(c("select", {
                "onUpdate:modelValue": p[31] || (p[31] = (y) => N.value = y),
                class: "cmst-field",
                "aria-label": "Filter by model type",
                "data-testid": "vue-library-type"
              }, [
                p[85] || (p[85] = c("option", { value: "" }, "All types", -1)),
                (g(!0), w(de, null, Le(Be.value, (y) => (g(), w("option", {
                  key: y,
                  value: y
                }, M(y), 9, I2))), 128))
              ], 512), [
                [Qt, N.value]
              ]),
              V(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-library-rescan",
                onClick: p[32] || (p[32] = (y) => m(s).rescanModelsNow(!0))
              }, {
                default: X(() => [...p[86] || (p[86] = [
                  D("Rescan", -1)
                ])]),
                _: 1
              }),
              V(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-library-refresh-nodes",
                onClick: p[33] || (p[33] = (y) => m(s).refreshCustomNodesNow())
              }, {
                default: X(() => [...p[87] || (p[87] = [
                  D("Refresh nodes", -1)
                ])]),
                _: 1
              })
            ]),
            c("h3", R2, [
              p[88] || (p[88] = D("Models ", -1)),
              c("span", A2, M(Et.value.length), 1)
            ]),
            c("ul", E2, [
              (g(!0), w(de, null, Le(Et.value, (y) => (g(), w("li", {
                key: String(y.model_id || y.filename),
                class: "cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover",
                "data-testid": "vue-library-model-row"
              }, [
                c("button", {
                  type: "button",
                  class: "cmst:flex cmst:w-full cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:bg-transparent cmst:text-left",
                  "aria-expanded": se.value === `model:${String(y.model_id || y.filename)}`,
                  onClick: (_e) => se.value = se.value === `model:${String(y.model_id || y.filename)}` ? "" : `model:${String(y.model_id || y.filename)}`
                }, [
                  c("span", T2, M(String(y.display_name || y.filename)), 1),
                  c("span", P2, M(String(y.model_type || y.folder || "")), 1)
                ], 8, O2),
                se.value === `model:${String(y.model_id || y.filename)}` ? (g(), w("div", M2, [
                  c("p", N2, [
                    D(M(String(y.filename)) + " · " + M(String(y.folder || "")), 1),
                    wt(y.size) ? (g(), w(de, { key: 0 }, [
                      D(" · " + M(wt(y.size)), 1)
                    ], 64)) : Q("", !0),
                    y.hash ? (g(), w(de, { key: 1 }, [
                      D(" · hash " + M(String(y.hash).slice(0, 12)), 1)
                    ], 64)) : Q("", !0)
                  ]),
                  y.provider || y.revision ? (g(), w("p", z2, M([y.provider, y.revision].filter(Boolean).join(" · ")), 1)) : Q("", !0),
                  (m(t).modelUsage[String(y.filename)] ?? []).length ? (g(), w("p", {
                    key: 1,
                    class: "cmst-type-meta cmst:mt-0.5",
                    title: (m(t).modelUsage[String(y.filename)] ?? []).join(", ")
                  }, [
                    D(" Used by " + M((m(t).modelUsage[String(y.filename)] ?? []).length) + " workflow" + M((m(t).modelUsage[String(y.filename)] ?? []).length === 1 ? "" : "s") + " ", 1),
                    c("button", {
                      type: "button",
                      class: "cmst:ml-1 cmst:text-cmst-secondary-text cmst:hover:text-cmst-fg",
                      onClick: p[34] || (p[34] = (_e) => o.value = "workflows")
                    }, "View")
                  ], 8, D2)) : Q("", !0),
                  Array.isArray(y.tags) && y.tags.length ? (g(), w("p", j2, "Tags: " + M(y.tags.map(String).join(", ")), 1)) : Q("", !0),
                  y.notes ? (g(), w("p", L2, M(String(y.notes)), 1)) : Q("", !0),
                  c("div", U2, [
                    je(c("input", {
                      "onUpdate:modelValue": (_e) => Ae.value[String(y.model_id || y.filename)] = _e,
                      class: "cmst-field cmst:min-w-0 cmst:flex-1 cmst:text-xs",
                      placeholder: "Note",
                      "aria-label": `Note for ${String(y.filename)}`
                    }, null, 8, V2), [
                      [ut, Ae.value[String(y.model_id || y.filename)]]
                    ]),
                    V(ee, {
                      size: "sm",
                      variant: "ghost",
                      onClick: (_e) => Bt(y)
                    }, {
                      default: X(() => [...p[89] || (p[89] = [
                        D("Save note", -1)
                      ])]),
                      _: 1
                    }, 8, ["onClick"])
                  ])
                ])) : Q("", !0)
              ]))), 128)),
              Et.value.length ? Q("", !0) : (g(), w("li", F2, "No models match."))
            ]),
            c("h3", B2, [
              p[90] || (p[90] = D("Custom nodes ", -1)),
              c("span", W2, M(Ot.value.length), 1)
            ]),
            c("ul", G2, [
              (g(!0), w(de, null, Le(Ot.value, (y) => (g(), w("li", {
                key: String(y.name || y.id),
                class: "cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover",
                "data-testid": "vue-library-node-row"
              }, [
                c("button", {
                  type: "button",
                  class: "cmst:flex cmst:w-full cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:bg-transparent cmst:text-left",
                  "aria-expanded": se.value === `node:${String(y.name || y.id)}`,
                  onClick: (_e) => se.value = se.value === `node:${String(y.name || y.id)}` ? "" : `node:${String(y.name || y.id)}`
                }, [
                  c("span", H2, M(String(y.title || y.name || y.id)), 1),
                  y.version ? (g(), w("span", Z2, M(String(y.version)), 1)) : Q("", !0)
                ], 8, q2),
                se.value === `node:${String(y.name || y.id)}` ? (g(), w("div", K2, [
                  y.repository_url ? (g(), w("p", Q2, M(String(y.repository_url)), 1)) : Q("", !0),
                  y.installed_commit ? (g(), w("p", J2, "Commit " + M(String(y.installed_commit).slice(0, 12)), 1)) : Q("", !0),
                  Array.isArray(y.classes) && y.classes.length ? (g(), w("p", Y2, [
                    D(M(y.classes.slice(0, 8).map(String).join(" · ")), 1),
                    y.classes.length > 8 ? (g(), w(de, { key: 0 }, [
                      D(" · +" + M(y.classes.length - 8) + " more", 1)
                    ], 64)) : Q("", !0)
                  ])) : Q("", !0)
                ])) : Q("", !0)
              ]))), 128)),
              Ot.value.length ? Q("", !0) : (g(), w("li", X2, "No custom nodes match."))
            ])
          ]))
        ])
      ], 64)),
      m(t).wizardOpen ? (g(), w("div", eC)) : Q("", !0),
      (g(), ft(Vc, { to: "body" }, [
        c("div", tC, [
          m(t).wizardOpen ? (g(), w("aside", {
            key: 0,
            class: "cmst-inspector",
            "data-state": "open",
            "data-testid": "vue-workflow-wizard",
            role: "complementary",
            "aria-label": "Setup workflow",
            tabindex: "-1",
            onKeydown: fs(mo(S, ["stop"]), ["esc"])
          }, [
            c("div", nC, [
              c("div", oC, [
                c("div", rC, [
                  p[92] || (p[92] = c("h2", { class: "cmst-type-section cmst:truncate" }, "Setup workflow", -1)),
                  c("p", aC, "Step " + M(T.value + 1) + " of " + M(m(ks).length) + " · " + M(re.value), 1)
                ]),
                c("button", {
                  type: "button",
                  "aria-label": "Close wizard",
                  class: "cmst-close-btn",
                  onClick: S
                }, [
                  V(m(sr), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  })
                ])
              ]),
              c("div", iC, [
                c("span", {
                  style: Pn({ width: `${Math.round((T.value + 1) / m(ks).length * 100)}%` })
                }, null, 4)
              ])
            ]),
            c("div", lC, [
              A.value === "feature-type" ? (g(), w(de, { key: 0 }, [
                p[95] || (p[95] = c("h3", { class: "cmst-type-object" }, "1 · Feature", -1)),
                p[96] || (p[96] = c("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, "Choose what this workflow does. This decides which bindings and controls the next steps ask for.", -1)),
                c("label", cC, [
                  p[94] || (p[94] = D("Feature type ", -1)),
                  c("select", {
                    class: "cmst-field cmst:w-full",
                    value: m(t).wizardDraft?.featureType,
                    onChange: p[35] || (p[35] = (y) => m(t).updateWizard({ featureType: y.target.value }))
                  }, [...p[93] || (p[93] = [
                    c("option", { value: "t2i" }, "Text to Image", -1),
                    c("option", { value: "i2i" }, "Image to Image", -1),
                    c("option", { value: "inpaint" }, "Inpaint", -1),
                    c("option", { value: "sketch" }, "Sketch", -1),
                    c("option", { value: "outpaint" }, "Outpaint", -1)
                  ])], 40, uC)
                ])
              ], 64)) : A.value === "required-bindings" ? (g(), w(de, { key: 1 }, [
                p[102] || (p[102] = c("h3", { class: "cmst-type-object" }, "2 · Bindings", -1)),
                p[103] || (p[103] = c("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, " Bind each control to its graph target — click Capture, then click the node input in the ComfyUI graph. ", -1)),
                ze.value.includes("attention") ? (g(), w("p", dC, " Dependencies need attention (" + M(ze.value) + ") — bindings still work, but runs may fail until models arrive. ", 1)) : Q("", !0),
                p[104] || (p[104] = c("h4", { class: "cmst-micro cmst:mt-4" }, "Required", -1)),
                c("ul", fC, [
                  (g(!0), w(de, null, Le(ve.value, (y) => (g(), w("li", {
                    key: y,
                    class: "cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover",
                    "data-testid": `vue-wizard-role-${y}`
                  }, [
                    c("div", pC, [
                      c("span", {
                        class: Ve(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", Oe(ie(y)) ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-warn"]),
                        "aria-hidden": "true"
                      }, null, 2),
                      c("span", vC, M(m(tn)(y).label), 1),
                      Oe(ie(y)) ? (g(), ft(ee, {
                        key: 1,
                        size: "sm",
                        variant: "ghost",
                        "data-testid": `vue-wizard-view-${y}`,
                        onClick: (_e) => tt(y)
                      }, {
                        default: X(() => [...p[98] || (p[98] = [
                          D("View", -1)
                        ])]),
                        _: 1
                      }, 8, ["data-testid", "onClick"])) : (g(), ft(ee, {
                        key: 0,
                        size: "sm",
                        variant: "secondary",
                        "data-testid": `vue-wizard-capture-${y}`,
                        onClick: (_e) => Ue(y)
                      }, {
                        default: X(() => [...p[97] || (p[97] = [
                          D("Capture", -1)
                        ])]),
                        _: 1
                      }, 8, ["data-testid", "onClick"]))
                    ]),
                    c("p", gC, [
                      Oe(ie(y)) ? (g(), w(de, { key: 0 }, [
                        D(M(Ie(ie(y))), 1)
                      ], 64)) : (g(), w(de, { key: 1 }, [
                        D("Look for: " + M(m(tn)(y).hint), 1)
                      ], 64))
                    ]),
                    !Oe(ie(y)) && De.value[y]?.length ? (g(), w("div", hC, [
                      (g(!0), w(de, null, Le(De.value[y], (_e) => (g(), w("button", {
                        key: `${_e.nodeId}:${_e.widgetName || ""}`,
                        type: "button",
                        class: "cmst:rounded cmst:bg-cmst-raised cmst:px-1.5 cmst:py-0.5 cmst:font-mono cmst:text-[11px] cmst:text-cmst-secondary-text cmst:hover:text-cmst-fg",
                        title: `Show ${_e.nodeTitle} on the graph`,
                        onClick: (ot) => ke(_e.nodeId)
                      }, M(_e.nodeTitle), 9, yC))), 128))
                    ])) : Q("", !0),
                    Oe(ie(y)) ? Q("", !0) : (g(), w("div", bC, [
                      V(ee, {
                        size: "sm",
                        variant: "ghost",
                        onClick: (_e) => bt(y)
                      }, {
                        default: X(() => [...p[99] || (p[99] = [
                          D("Suggest targets", -1)
                        ])]),
                        _: 1
                      }, 8, ["onClick"])
                    ]))
                  ], 8, mC))), 128))
                ]),
                p[105] || (p[105] = c("h4", { class: "cmst-micro cmst:mt-4" }, "Optional", -1)),
                c("ul", wC, [
                  (g(!0), w(de, null, Le(Me.value, (y) => (g(), w("li", {
                    key: y,
                    class: "cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover",
                    "data-testid": `vue-wizard-role-${y}`
                  }, [
                    c("div", xC, [
                      c("span", {
                        class: Ve(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", Oe(ie(y)) ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
                        "aria-hidden": "true"
                      }, null, 2),
                      c("span", kC, M(m(tn)(y).label), 1),
                      Oe(ie(y)) ? (g(), ft(ee, {
                        key: 1,
                        size: "sm",
                        variant: "ghost",
                        "data-testid": `vue-wizard-view-${y}`,
                        onClick: (_e) => tt(y)
                      }, {
                        default: X(() => [...p[101] || (p[101] = [
                          D("View", -1)
                        ])]),
                        _: 1
                      }, 8, ["data-testid", "onClick"])) : (g(), ft(ee, {
                        key: 0,
                        size: "sm",
                        variant: "ghost",
                        "data-testid": `vue-wizard-capture-${y}`,
                        onClick: (_e) => Ue(y)
                      }, {
                        default: X(() => [...p[100] || (p[100] = [
                          D("Capture", -1)
                        ])]),
                        _: 1
                      }, 8, ["data-testid", "onClick"]))
                    ])
                  ], 8, _C))), 128))
                ]),
                a.value ? (g(), w("p", SC, M(a.value), 1)) : Q("", !0)
              ], 64)) : A.value === "exposed-controls" ? (g(), w(de, { key: 2 }, [
                p[109] || (p[109] = c("h3", { class: "cmst-type-object" }, "3 · Controls", -1)),
                p[110] || (p[110] = c("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, " Add the controls this workflow exposes. Each control becomes one field (Steps, CFG, Seed) — not a generic form builder. ", -1)),
                c("div", CC, [
                  je(c("input", {
                    "onUpdate:modelValue": p[36] || (p[36] = (y) => r.value = y),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "Control label, e.g. Steps",
                    "aria-label": "Control label"
                  }, null, 512), [
                    [ut, r.value]
                  ]),
                  V(ee, {
                    size: "sm",
                    variant: "secondary",
                    onClick: me
                  }, {
                    default: X(() => [...p[106] || (p[106] = [
                      D("Add control", -1)
                    ])]),
                    _: 1
                  })
                ]),
                c("ul", $C, [
                  (g(!0), w(de, null, Le(m(t).wizardDraft?.controls ?? [], (y, _e) => (g(), w("li", {
                    key: _e,
                    class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-1.5 first:cmst:border-t-0"
                  }, " · " + M(String(y.label ?? y)), 1))), 128))
                ]),
                c("div", IC, [
                  c("p", RC, [
                    p[107] || (p[107] = D(" Select the output node in the ComfyUI graph so runs know where images land. ", -1)),
                    m(t).wizardDraft?.outputBinding ? (g(), w("span", {
                      key: 0,
                      class: Ve(["cmst:ml-1 cmst:rounded cmst:px-1.5 cmst:py-0.5 cmst:text-[11px] cmst:font-medium", Oe(m(t).wizardDraft?.outputBinding) ? "cmst:bg-cmst-ok/15 cmst:text-cmst-ok" : "cmst:bg-cmst-warn/15 cmst:text-cmst-warn"])
                    }, M(Oe(m(t).wizardDraft?.outputBinding) ? "Bound" : "Pending"), 3)) : Q("", !0)
                  ]),
                  c("div", AC, [
                    V(ee, {
                      size: "sm",
                      variant: "outline",
                      onClick: F
                    }, {
                      default: X(() => [...p[108] || (p[108] = [
                        D("Capture output binding", -1)
                      ])]),
                      _: 1
                    })
                  ])
                ])
              ], 64)) : (g(), w(de, { key: 3 }, [
                p[111] || (p[111] = c("h3", { class: "cmst-type-object" }, "4 · Review", -1)),
                p[112] || (p[112] = c("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, "Review the explicit bindings before saving the version mapping.", -1)),
                c("pre", EC, M(JSON.stringify({ bindings: m(t).wizardDraft?.bindings, output: m(t).wizardDraft?.outputBinding, controls: m(t).wizardDraft?.controls }, null, 1)), 1),
                $.value.length ? (g(), w("p", OC, " Still needed: " + M($.value.join(", ")) + " — bind them in step 2 before saving. ", 1)) : Q("", !0),
                m(t).wizardError ? (g(), w("p", TC, M(m(t).wizardError), 1)) : a.value ? (g(), w("p", PC, M(a.value), 1)) : Q("", !0),
                c("div", MC, [
                  V(ee, {
                    size: "sm",
                    disabled: m(t).wizardSaving || $.value.length > 0,
                    "data-testid": "vue-wizard-save",
                    onClick: U
                  }, {
                    default: X(() => [
                      D(M(m(t).wizardSaving ? "Saving…" : "Save mapping"), 1)
                    ]),
                    _: 1
                  }, 8, ["disabled"])
                ])
              ], 64))
            ]),
            c("div", NC, [
              V(ee, {
                variant: "ghost",
                size: "sm",
                disabled: T.value === 0,
                onClick: q
              }, {
                default: X(() => [...p[113] || (p[113] = [
                  D("Back", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              T.value < m(ks).length - 1 ? (g(), ft(ee, {
                key: 0,
                size: "sm",
                onClick: B
              }, {
                default: X(() => [...p[114] || (p[114] = [
                  D("Next", -1)
                ])]),
                _: 1
              })) : (g(), w("span", zC, "Review → Save mapping"))
            ])
          ], 40, sC)) : Q("", !0)
        ])
      ]))
    ], 2));
  }
}), jC = {
  playground: qk,
  history: Z1,
  workflows: DC,
  backend: Qw,
  settings: X0
};
function LC(e = {}) {
  let t;
  return e.memory || !e.win ? t = Mp() : t = fb(e.win, e.initial), ev({
    history: t,
    routes: Lu.map((n) => ({
      path: `/${n}`,
      name: n,
      component: jC[n]
    }))
  });
}
function UC(e, t = {}) {
  const s = Hm(), n = LC({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), o = Wm(ub);
  return o.use(s), o.use(n), o.mount(e), {
    app: o,
    router: n,
    pinia: s,
    unmount: () => {
      o.unmount();
    }
  };
}
export {
  UC as mountStudioPreview
};

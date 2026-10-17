/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function Aa(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const st = {}, Hs = [], Xt = () => {
}, Ll = () => !1, Yr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), Xr = (e) => e.startsWith("onUpdate:"), _t = Object.assign, Ea = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, sd = Object.prototype.hasOwnProperty, Ye = (e, t) => sd.call(e, t), $e = Array.isArray, Ps = (e) => or(e) === "[object Map]", ys = (e) => or(e) === "[object Set]", ti = (e) => or(e) === "[object Date]", Ne = (e) => typeof e == "function", ct = (e) => typeof e == "string", jt = (e) => typeof e == "symbol", et = (e) => e !== null && typeof e == "object", Ul = (e) => (et(e) || Ne(e)) && Ne(e.then) && Ne(e.catch), Vl = Object.prototype.toString, or = (e) => Vl.call(e), nd = (e) => or(e).slice(8, -1), Fl = (e) => or(e) === "[object Object]", eo = (e) => ct(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, Ln = /* @__PURE__ */ Aa(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), to = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, rd = /-\w/g, Et = to(
  (e) => e.replace(rd, (t) => t.slice(1).toUpperCase())
), od = /\B([A-Z])/g, Ls = to(
  (e) => e.replace(od, "-$1").toLowerCase()
), so = to((e) => e.charAt(0).toUpperCase() + e.slice(1)), xo = to(
  (e) => e ? `on${so(e)}` : ""
), Qt = (e, t) => !Object.is(e, t), Rr = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Wl = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, no = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let si;
const ro = () => si || (si = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function wn(e) {
  if ($e(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = ct(n) ? cd(n) : wn(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (ct(e) || et(e))
    return e;
}
const ad = /;(?![^(]*\))/g, id = /:([^]+)/, ld = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function cd(e) {
  const t = {};
  return e.replace(ld, (s) => s.startsWith("/*") ? "" : s).split(ad).forEach((s) => {
    if (s) {
      const n = s.split(id);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function Ae(e) {
  let t = "";
  if (ct(e))
    t = e;
  else if ($e(e))
    for (let s = 0; s < e.length; s++) {
      const n = Ae(e[s]);
      n && (t += n + " ");
    }
  else if (et(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const ud = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", dd = /* @__PURE__ */ Aa(ud);
function Bl(e) {
  return !!e || e === "";
}
function fd(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = bs(e[r], t[r], s);
  return n;
}
function ni(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let a = -1;
    for (let i = 0; i < n.length; i++)
      if (!r[i] && bs(o, n[i], s)) {
        a = i;
        break;
      }
    if (a < 0) return !1;
    r[a] = 1;
  }
  return !0;
}
function md(e, t, s) {
  let n = Ps(e), r = Ps(t);
  if (n || r || (n = ys(e), r = ys(t), n || r))
    return n && r ? ni(e, t, s) : !1;
  const o = Object.keys(e).length, a = Object.keys(t).length;
  if (o !== a)
    return !1;
  for (const i in e) {
    const l = e.hasOwnProperty(i), c = t.hasOwnProperty(i);
    if (l && !c || !l && c || !bs(e[i], t[i], s))
      return !1;
  }
  return String(e) === String(t);
}
function ri(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const a = n(e, t, s);
  return r.delete(e), o.delete(t), a;
}
function bs(e, t, s) {
  if (e === t) return !0;
  let n = ti(e), r = ti(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = jt(e), r = jt(t), n || r ? e === t : (n = $e(e), r = $e(t), n || r ? n && r ? ri(e, t, s, fd) : !1 : (n = et(e), r = et(t), n || r ? !n || !r ? !1 : ri(e, t, s, md) : String(e) === String(t))));
}
function Oa(e, t) {
  return e.findIndex((s) => bs(s, t));
}
const ql = (e) => !!(e && e.__v_isRef === !0), L = (e) => ct(e) ? e : e == null ? "" : $e(e) || et(e) && (e.toString === Vl || !Ne(e.toString)) ? ql(e) ? L(e.value) : JSON.stringify(e, Gl, 2) : String(e), Gl = (e, t) => ql(t) ? Gl(e, t.value) : Ps(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[ko(n, o) + " =>"] = r, s),
    {}
  )
} : ys(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => ko(s))
} : jt(t) ? ko(t) : et(t) && !$e(t) && !Fl(t) ? String(t) : t, ko = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    jt(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let yt;
class Hl {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && yt && (yt.active ? (this.parent = yt, this.index = (yt.scopes || (yt.scopes = [])).push(
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
      const s = yt;
      try {
        return yt = this, t();
      } finally {
        yt = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = yt, yt = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (yt === this)
        yt = this.prevScope;
      else {
        let t = yt;
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
function Zl(e) {
  return new Hl(e);
}
function Kl() {
  return yt;
}
function pd(e, t = !1) {
  yt && yt.cleanups.push(e);
}
let nt;
const So = /* @__PURE__ */ new WeakSet();
class Jl {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, yt && (yt.active ? yt.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, So.has(this) && (So.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || Yl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, oi(this), Xl(this);
    const t = nt, s = Ft;
    nt = this, Ft = !0;
    try {
      return this.fn();
    } finally {
      ec(this), nt = t, Ft = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        Na(t);
      this.deps = this.depsTail = void 0, oi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? So.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    Yo(this) && this.run();
  }
  get dirty() {
    return Yo(this);
  }
}
let Ql = 0, Un, Vn;
function Yl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = Vn, Vn = e;
    return;
  }
  e.next = Un, Un = e;
}
function Ta() {
  Ql++;
}
function Pa() {
  if (--Ql > 0)
    return;
  if (Vn) {
    let t = Vn;
    for (Vn = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; Un; ) {
    let t = Un;
    for (Un = void 0; t; ) {
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
function Xl(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function ec(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), Na(n), hd(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function Yo(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (tc(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function tc(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === Gn) || (e.globalVersion = Gn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !Yo(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = nt, n = Ft;
  nt = e, Ft = !0;
  try {
    Xl(e);
    const r = e.fn(e._value);
    (t.version === 0 || Qt(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    nt = s, Ft = n, ec(e), e.flags &= -3;
  }
}
function Na(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      Na(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function hd(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let Ft = !0;
const sc = [];
function ss() {
  sc.push(Ft), Ft = !1;
}
function ns() {
  const e = sc.pop();
  Ft = e === void 0 ? !0 : e;
}
function oi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = nt;
    nt = void 0;
    try {
      t();
    } finally {
      nt = s;
    }
  }
}
let Gn = 0;
class gd {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Ma {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!nt || !Ft || nt === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== nt)
      s = this.activeLink = new gd(nt, this), nt.deps ? (s.prevDep = nt.depsTail, nt.depsTail.nextDep = s, nt.depsTail = s) : nt.deps = nt.depsTail = s, nc(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = nt.depsTail, s.nextDep = void 0, nt.depsTail.nextDep = s, nt.depsTail = s, nt.deps === s && (nt.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, Gn++, this.notify(t);
  }
  notify(t) {
    Ta();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      Pa();
    }
  }
}
function nc(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        nc(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const Tr = /* @__PURE__ */ new WeakMap(), Ks = /* @__PURE__ */ Symbol(
  ""
), Xo = /* @__PURE__ */ Symbol(
  ""
), Hn = /* @__PURE__ */ Symbol(
  ""
);
function St(e, t, s) {
  if (Ft && nt) {
    let n = Tr.get(e);
    n || Tr.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new Ma()), r.map = n, r.key = s), r.track();
  }
}
function fs(e, t, s, n, r, o) {
  const a = Tr.get(e);
  if (!a) {
    Gn++;
    return;
  }
  const i = (l) => {
    l && l.trigger();
  };
  if (Ta(), t === "clear")
    a.forEach(i);
  else {
    const l = $e(e), c = l && eo(s);
    if (l && s === "length") {
      const d = Number(n);
      a.forEach((f, y) => {
        (y === "length" || y === Hn || !jt(y) && y >= d) && i(f);
      });
    } else
      switch ((s !== void 0 || a.has(void 0)) && i(a.get(s)), c && i(a.get(Hn)), t) {
        case "add":
          l ? c && i(a.get("length")) : (i(a.get(Ks)), Ps(e) && i(a.get(Xo)));
          break;
        case "delete":
          l || (i(a.get(Ks)), Ps(e) && i(a.get(Xo)));
          break;
        case "set":
          Ps(e) && i(a.get(Ks));
          break;
      }
  }
  Pa();
}
function vd(e, t) {
  const s = Tr.get(e);
  return s && s.get(t);
}
function Xs(e) {
  const t = /* @__PURE__ */ Je(e);
  return t === e || (St(t, "iterate", Hn), /* @__PURE__ */ Mt(e)) ? t : /* @__PURE__ */ rs(e) ? /* @__PURE__ */ es(e) ? t.map((s) => Ms(Dt(s))) : t.map(Ms) : t.map(Dt);
}
function oo(e) {
  return St(e = /* @__PURE__ */ Je(e), "iterate", Hn), e;
}
function Zt(e, t) {
  return /* @__PURE__ */ rs(e) ? Ms(/* @__PURE__ */ es(e) ? Dt(t) : t) : Dt(t);
}
const yd = {
  __proto__: null,
  [Symbol.iterator]() {
    return Co(this, Symbol.iterator, (e) => Zt(this, e));
  },
  concat(...e) {
    return Xs(this).concat(
      ...e.map((t) => $e(t) ? Xs(t) : t)
    );
  },
  entries() {
    return Co(this, "entries", (e) => (e[1] = Zt(this, e[1]), e));
  },
  every(e, t) {
    return as(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return as(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => Zt(this, n)),
      arguments
    );
  },
  find(e, t) {
    return as(
      this,
      "find",
      e,
      t,
      (s) => Zt(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return as(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return as(
      this,
      "findLast",
      e,
      t,
      (s) => Zt(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return as(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return as(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return $o(this, "includes", e);
  },
  indexOf(...e) {
    return $o(this, "indexOf", e);
  },
  join(e) {
    return Xs(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return $o(this, "lastIndexOf", e);
  },
  map(e, t) {
    return as(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return Sn(this, "pop");
  },
  push(...e) {
    return Sn(this, "push", e);
  },
  reduce(e, ...t) {
    return ii(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return ii(this, "reduceRight", e, t);
  },
  shift() {
    return Sn(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return as(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return Sn(this, "splice", e);
  },
  toReversed() {
    return Xs(this).toReversed();
  },
  toSorted(e) {
    return Xs(this).toSorted(e);
  },
  toSpliced(...e) {
    return Xs(this).toSpliced(...e);
  },
  unshift(...e) {
    return Sn(this, "unshift", e);
  },
  values() {
    return Co(this, "values", (e) => Zt(this, e));
  }
};
function Co(e, t, s) {
  const n = oo(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ Mt(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const a = Object.create(Object.getPrototypeOf(o));
      return a.next = () => ai(o.next(), s), r !== rc[t] && Object.defineProperties(a, {
        return: {
          get() {
            const i = o.return;
            return typeof i == "function" ? i.bind(o) : i;
          }
        },
        throw: {
          get() {
            const i = o.throw;
            return typeof i == "function" ? i.bind(o) : i;
          }
        }
      }), a;
    }
    o._next = o.next, o.next = () => ai(o._next(), s);
  }
  return o;
}
function ai(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const rc = Array.prototype;
function as(e, t, s, n, r, o) {
  const a = oo(e), i = a !== e && !/* @__PURE__ */ Mt(e), l = a[t];
  if (l !== rc[t]) {
    const f = l.apply(e, o);
    return i ? Dt(f) : f;
  }
  let c = s;
  a !== e && (i ? c = function(f, y) {
    return s.call(this, Zt(e, f), y, e);
  } : s.length > 2 && (c = function(f, y) {
    return s.call(this, f, y, e);
  }));
  const d = l.call(a, c, n);
  return i && r ? r(d) : d;
}
function ii(e, t, s, n) {
  const r = oo(e), o = r !== e && !/* @__PURE__ */ Mt(e);
  let a = s, i = !1;
  r !== e && (o ? (i = n.length === 0, a = function(c, d, f) {
    return i && (i = !1, c = Zt(e, c)), s.call(this, c, Zt(e, d), f, e);
  }) : s.length > 3 && (a = function(c, d, f) {
    return s.call(this, c, d, f, e);
  }));
  const l = r[t](a, ...n);
  return i ? Zt(e, l) : l;
}
function $o(e, t, s) {
  const n = /* @__PURE__ */ Je(e);
  St(n, "iterate", Hn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ ao(s[0]) ? (s[0] = /* @__PURE__ */ Je(s[0]), n[t](...s)) : r;
}
function Sn(e, t, s = []) {
  ss(), Ta();
  const n = (/* @__PURE__ */ Je(e))[t].apply(e, s);
  return Pa(), ns(), n;
}
const bd = /* @__PURE__ */ Aa("__proto__,__v_isRef,__isVue"), oc = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(jt)
);
function wd(e) {
  jt(e) || (e = String(e));
  const t = /* @__PURE__ */ Je(this);
  return St(t, "has", e), t.hasOwnProperty(e);
}
class ac {
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
      return n === (r ? o ? Ed : uc : o ? cc : lc).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const a = $e(t);
    if (!r) {
      let l;
      if (a && (l = yd[s]))
        return l;
      if (s === "hasOwnProperty")
        return wd;
    }
    const i = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ ft(t) ? t : n
    );
    if ((jt(s) ? oc.has(s) : bd(s)) || (r || St(t, "get", s), o))
      return i;
    if (/* @__PURE__ */ ft(i)) {
      const l = a && eo(s) ? i : i.value;
      return r && et(l) ? /* @__PURE__ */ ta(l) : l;
    }
    return et(i) ? r ? /* @__PURE__ */ ta(i) : /* @__PURE__ */ ar(i) : i;
  }
}
class ic extends ac {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const a = $e(t) && eo(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ rs(o);
      if (!/* @__PURE__ */ Mt(n) && !/* @__PURE__ */ rs(n) && (o = /* @__PURE__ */ Je(o), n = /* @__PURE__ */ Je(n)), !a && /* @__PURE__ */ ft(o) && !/* @__PURE__ */ ft(n))
        return c || (o.value = n), !0;
    }
    const i = a ? Number(s) < t.length : Ye(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ ft(t) ? t : r
    );
    return t === /* @__PURE__ */ Je(r) && l && (i ? Qt(n, o) && fs(t, "set", s, n) : fs(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = Ye(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && fs(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!jt(s) || !oc.has(s)) && St(t, "has", s), n;
  }
  ownKeys(t) {
    return St(
      t,
      "iterate",
      $e(t) ? "length" : Ks
    ), Reflect.ownKeys(t);
  }
}
class _d extends ac {
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
const xd = /* @__PURE__ */ new ic(), kd = /* @__PURE__ */ new _d(), Sd = /* @__PURE__ */ new ic(!0);
const ea = (e) => e, mr = (e) => Reflect.getPrototypeOf(e);
function Cd(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ Je(r), a = Ps(o), i = e === "entries" || e === Symbol.iterator && a, l = e === "keys" && a, c = r[e](...n), d = s ? ea : t ? Ms : Dt;
    return !t && St(
      o,
      "iterate",
      l ? Xo : Ks
    ), _t(
      // inheriting all iterator properties
      Object.create(c),
      {
        // iterator protocol
        next() {
          const { value: f, done: y } = c.next();
          return y ? { value: f, done: y } : {
            value: i ? [d(f[0]), d(f[1])] : d(f),
            done: y
          };
        }
      }
    );
  };
}
function pr(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function $d(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, a = /* @__PURE__ */ Je(o), i = /* @__PURE__ */ Je(r);
      e || (Qt(r, i) && St(a, "get", r), St(a, "get", i));
      const { has: l } = mr(a), c = t ? ea : e ? Ms : Dt;
      if (l.call(a, r))
        return c(o.get(r));
      if (l.call(a, i))
        return c(o.get(i));
      o !== a && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && St(/* @__PURE__ */ Je(r), "iterate", Ks), r.size;
    },
    has(r) {
      const o = this.__v_raw, a = /* @__PURE__ */ Je(o), i = /* @__PURE__ */ Je(r);
      return e || (Qt(r, i) && St(a, "has", r), St(a, "has", i)), r === i ? o.has(r) : o.has(r) || o.has(i);
    },
    forEach(r, o) {
      const a = this, i = a.__v_raw, l = /* @__PURE__ */ Je(i), c = t ? ea : e ? Ms : Dt;
      return !e && St(l, "iterate", Ks), i.forEach((d, f) => r.call(o, c(d), c(f), a));
    }
  };
  return _t(
    s,
    e ? {
      add: pr("add"),
      set: pr("set"),
      delete: pr("delete"),
      clear: pr("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ Je(this), a = mr(o), i = /* @__PURE__ */ Je(r), l = !t && !/* @__PURE__ */ Mt(r) && !/* @__PURE__ */ rs(r) ? i : r;
        return a.has.call(o, l) || Qt(r, l) && a.has.call(o, r) || Qt(i, l) && a.has.call(o, i) || (o.add(l), fs(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ Mt(o) && !/* @__PURE__ */ rs(o) && (o = /* @__PURE__ */ Je(o));
        const a = /* @__PURE__ */ Je(this), { has: i, get: l } = mr(a);
        let c = i.call(a, r);
        c || (r = /* @__PURE__ */ Je(r), c = i.call(a, r));
        const d = l.call(a, r);
        return a.set(r, o), c ? Qt(o, d) && fs(a, "set", r, o) : fs(a, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ Je(this), { has: a, get: i } = mr(o);
        let l = a.call(o, r);
        l || (r = /* @__PURE__ */ Je(r), l = a.call(o, r)), i && i.call(o, r);
        const c = o.delete(r);
        return l && fs(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ Je(this), o = r.size !== 0, a = r.clear();
        return o && fs(
          r,
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
  ].forEach((r) => {
    s[r] = Cd(r, e, t);
  }), s;
}
function za(e, t) {
  const s = $d(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    Ye(s, r) && r in n ? s : n,
    r,
    o
  );
}
const Id = {
  get: /* @__PURE__ */ za(!1, !1)
}, Rd = {
  get: /* @__PURE__ */ za(!1, !0)
}, Ad = {
  get: /* @__PURE__ */ za(!0, !1)
};
const lc = /* @__PURE__ */ new WeakMap(), cc = /* @__PURE__ */ new WeakMap(), uc = /* @__PURE__ */ new WeakMap(), Ed = /* @__PURE__ */ new WeakMap();
function Od(e) {
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
function ar(e) {
  return /* @__PURE__ */ rs(e) ? e : ja(
    e,
    !1,
    xd,
    Id,
    lc
  );
}
// @__NO_SIDE_EFFECTS__
function dc(e) {
  return ja(
    e,
    !1,
    Sd,
    Rd,
    cc
  );
}
// @__NO_SIDE_EFFECTS__
function ta(e) {
  return ja(
    e,
    !0,
    kd,
    Ad,
    uc
  );
}
function ja(e, t, s, n, r) {
  if (!et(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const a = Od(nd(e));
  if (a === 0)
    return e;
  const i = new Proxy(
    e,
    a === 2 ? n : s
  );
  return r.set(e, i), i;
}
// @__NO_SIDE_EFFECTS__
function es(e) {
  return /* @__PURE__ */ rs(e) ? /* @__PURE__ */ es(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function rs(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function Mt(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function ao(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function Je(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ Je(t) : e;
}
function Da(e) {
  return !Ye(e, "__v_skip") && Object.isExtensible(e) && Wl(e, "__v_skip", !0), e;
}
const Dt = (e) => et(e) ? /* @__PURE__ */ ar(e) : e, Ms = (e) => et(e) ? /* @__PURE__ */ ta(e) : e;
// @__NO_SIDE_EFFECTS__
function ft(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function T(e) {
  return fc(e, !1);
}
// @__NO_SIDE_EFFECTS__
function Td(e) {
  return fc(e, !0);
}
function fc(e, t) {
  return /* @__PURE__ */ ft(e) ? e : new Pd(e, t);
}
class Pd {
  constructor(t, s) {
    this.dep = new Ma(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ Je(t), this._value = s ? t : Dt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ Mt(t) || /* @__PURE__ */ rs(t);
    t = n ? t : /* @__PURE__ */ Je(t), Qt(t, s) && (this._rawValue = t, this._value = n ? t : Dt(t), this.dep.trigger());
  }
}
function p(e) {
  return /* @__PURE__ */ ft(e) ? e.value : e;
}
const Nd = {
  get: (e, t, s) => t === "__v_raw" ? e : p(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ ft(r) && !/* @__PURE__ */ ft(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function mc(e) {
  return /* @__PURE__ */ es(e) ? e : new Proxy(e, Nd);
}
// @__NO_SIDE_EFFECTS__
function Md(e) {
  const t = $e(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = jd(e, s);
  return t;
}
class zd {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = jt(s) ? s : String(s), this._raw = /* @__PURE__ */ Je(t);
    let r = !0, o = t;
    if (!$e(t) || jt(this._key) || !eo(this._key))
      do
        r = !/* @__PURE__ */ ao(o) || /* @__PURE__ */ Mt(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = p(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ ft(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ ft(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return vd(this._raw, this._key);
  }
}
function jd(e, t, s) {
  return new zd(e, t, s);
}
class Dd {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new Ma(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = Gn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    nt !== this)
      return Yl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return tc(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function Ld(e, t, s = !1) {
  let n, r;
  return Ne(e) ? n = e : (n = e.get, r = e.set), new Dd(n, r, s);
}
const hr = {}, Pr = /* @__PURE__ */ new WeakMap();
let qs;
function Ud(e, t = !1, s = qs) {
  if (s) {
    let n = Pr.get(s);
    n || Pr.set(s, n = []), n.push(e);
  }
}
function Vd(e, t, s = st) {
  const { immediate: n, deep: r, once: o, scheduler: a, augmentJob: i, call: l } = s, c = (R) => r ? R : /* @__PURE__ */ Mt(R) || r === !1 || r === 0 ? ms(R, 1) : ms(R);
  let d, f, y, v, A = !1, b = !1;
  if (/* @__PURE__ */ ft(e) ? (f = () => e.value, A = /* @__PURE__ */ Mt(e)) : /* @__PURE__ */ es(e) ? (f = () => c(e), A = !0) : $e(e) ? (b = !0, A = e.some((R) => /* @__PURE__ */ es(R) || /* @__PURE__ */ Mt(R)), f = () => e.map((R) => {
    if (/* @__PURE__ */ ft(R))
      return R.value;
    if (/* @__PURE__ */ es(R))
      return c(R);
    if (Ne(R))
      return l ? l(R, 2) : R();
  })) : Ne(e) ? t ? f = l ? () => l(e, 2) : e : f = () => {
    if (y) {
      ss();
      try {
        y();
      } finally {
        ns();
      }
    }
    const R = qs;
    qs = d;
    try {
      return l ? l(e, 3, [v]) : e(v);
    } finally {
      qs = R;
    }
  } : f = Xt, t && r) {
    const R = f, J = r === !0 ? 1 / 0 : r;
    f = () => ms(R(), J);
  }
  const w = Kl(), O = () => {
    d.stop(), w && w.active && Ea(w.effects, d);
  };
  if (o && t) {
    const R = t;
    t = (...J) => {
      try {
        return R(...J);
      } finally {
        O();
      }
    };
  }
  let I = b ? new Array(e.length).fill(hr) : hr;
  const V = (R) => {
    if (!(!(d.flags & 1) || !d.dirty && !R))
      if (t) {
        const J = d.run();
        if (R || r || A || (b ? J.some((be, ee) => Qt(be, I[ee])) : Qt(J, I))) {
          const be = qs;
          ss();
          try {
            y && y(), qs = d;
            const ee = [
              J,
              // pass undefined as the old value when it's changed for the first time
              I === hr ? void 0 : b && I[0] === hr ? [] : I,
              v
            ];
            I = J, l ? l(t, 3, ee) : (
              // @ts-expect-error
              t(...ee)
            );
          } finally {
            qs = be, ns();
          }
        }
      } else
        d.run();
  };
  return i && i(V), d = new Jl(f), d.scheduler = a ? () => a(V, !1) : V, v = (R) => Ud(R, !1, d), y = d.onStop = () => {
    const R = Pr.get(d);
    if (R) {
      if (l)
        l(R, 4);
      else
        for (const J of R) J();
      Pr.delete(d);
    }
  }, t ? n ? V(!0) : I = d.run() : a ? a(V.bind(null, !0), !0) : d.run(), O.pause = d.pause.bind(d), O.resume = d.resume.bind(d), O.stop = O, O;
}
function ms(e, t = 1 / 0, s) {
  if (t <= 0 || !et(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ ft(e))
    ms(e.value, t, s);
  else if ($e(e))
    for (let n = 0; n < e.length; n++)
      ms(e[n], t, s);
  else if (ys(e) || Ps(e))
    e.forEach((n) => {
      ms(n, t, s);
    });
  else if (Fl(e)) {
    for (const n in e)
      ms(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && ms(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function ir(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (r) {
    io(r, t, s);
  }
}
function Bt(e, t, s, n) {
  if (Ne(e)) {
    const r = ir(e, t, s, n);
    return r && Ul(r) && r.catch((o) => {
      io(o, t, s);
    }), r;
  }
  if ($e(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(Bt(e[o], t, s, n));
    return r;
  }
}
function io(e, t, s, n = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: a } = t && t.appContext.config || st;
  if (t) {
    let i = t.parent;
    const l = t.proxy, c = `https://vuejs.org/error-reference/#runtime-${s}`;
    for (; i; ) {
      const d = i.ec;
      if (d) {
        for (let f = 0; f < d.length; f++)
          if (d[f](e, l, c) === !1)
            return;
      }
      i = i.parent;
    }
    if (o) {
      ss(), ir(o, null, 10, [
        e,
        l,
        c
      ]), ns();
      return;
    }
  }
  Fd(e, s, r, n, a);
}
function Fd(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const At = [];
let Vt = -1;
const Kt = [];
let As = null, nn = 0;
const pc = /* @__PURE__ */ Promise.resolve();
let Nr = null;
function lr(e) {
  const t = Nr || pc;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function Wd(e) {
  let t = Vt + 1, s = At.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = At[n], o = Zn(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function La(e) {
  if (!(e.flags & 1)) {
    const t = Zn(e), s = At[At.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= Zn(s) ? At.push(e) : At.splice(Wd(t), 0, e), e.flags |= 1, hc();
  }
}
function hc() {
  Nr || (Nr = pc.then(yc));
}
function Bd(e) {
  if (!$e(e))
    As && e.id === -1 ? As.splice(nn + 1, 0, e) : e.flags & 1 || (Kt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Kt.push(e[t]);
  hc();
}
function gc(e, t, s, n = Vt + 1) {
  for (; n < At.length; n++) {
    const r = At[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      At.splice(n, 1), n = e ? n - 1 : Vt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function vc(e, t, s = 0) {
  if (Kt.length) {
    let n = Kt, r = 0;
    if (t) {
      n = [];
      for (let a = 0; a < Kt.length; a++) {
        const i = Kt[a];
        (i.i !== void 0 ? !i.i || i.i.uid < s : t.has(i)) ? Kt[r++] = i : n.push(i);
      }
    }
    const o = [...new Set(n)].sort((a, i) => Zn(a) - Zn(i));
    if (Kt.length = r, As) {
      for (let a = 0; a < o.length; a++)
        As.push(o[a]);
      return;
    }
    for (As = o, nn = 0; nn < As.length; nn++) {
      const a = As[nn];
      a.flags & 4 && (a.flags &= -2), a.flags & 8 || a(), a.flags &= -2;
    }
    As = null, nn = 0;
  }
}
let Io = !1;
function qd(e, t) {
  if (Io) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Kt);
  e(), Io = !0;
  try {
    gc(void 0, t), vc(void 0, s, t);
  } finally {
    Io = !1;
  }
}
const Zn = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function yc(e) {
  try {
    for (Vt = 0; Vt < At.length; Vt++) {
      const t = At[Vt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), ir(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; Vt < At.length; Vt++) {
      const t = At[Vt];
      t && (t.flags &= -2);
    }
    Vt = -1, At.length = 0, vc(), Nr = null, (At.length || Kt.length) && yc();
  }
}
let wt = null, bc = null;
function Mr(e) {
  const t = wt;
  return wt = e, bc = e && e.type.__scopeId || null, t;
}
function se(e, t = wt, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && Lr(-1);
    const o = Mr(t), a = vs.length;
    let i;
    try {
      i = e(...r);
    } finally {
      for (let l = vs.length; l > a; l--) Ba();
      Mr(o), n._d && Lr(1);
    }
    return i;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Fe(e, t) {
  if (wt === null)
    return e;
  const s = po(wt), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, a, i, l = st] = t[r];
    o && (Ne(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && ms(a), n.push({
      dir: o,
      instance: s,
      value: a,
      oldValue: void 0,
      arg: i,
      modifiers: l
    }));
  }
  return e;
}
function Vs(e, t, s, n) {
  const r = e.dirs, o = t && t.dirs;
  for (let a = 0; a < r.length; a++) {
    const i = r[a];
    o && (i.oldValue = o[a].value);
    let l = i.dir[n];
    l && (ss(), Bt(l, s, 8, [
      e.el,
      i,
      e,
      t
    ]), ns());
  }
}
function Ar(e, t) {
  if (Ct) {
    let s = Ct.provides;
    const n = Ct.parent && Ct.parent.provides;
    n === s && (s = Ct.provides = Object.create(n)), s[e] = t;
  }
}
function zt(e, t, s = !1) {
  const n = Jc();
  if (n || Js) {
    let r = Js ? Js._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && Ne(t) ? t.call(n && n.proxy) : t;
  }
}
function Gd() {
  return !!(Jc() || Js);
}
const Hd = /* @__PURE__ */ Symbol.for("v-scx"), Zd = () => zt(Hd);
function Wt(e, t, s) {
  return wc(e, t, s);
}
function wc(e, t, s = st) {
  const { immediate: n, deep: r, flush: o, once: a } = s, i = _t({}, s), l = t && n || !t && o !== "post";
  let c;
  if (Qn) {
    if (o === "sync") {
      const v = Zd();
      c = v.__watcherHandles || (v.__watcherHandles = []);
    } else if (!l) {
      const v = () => {
      };
      return v.stop = Xt, v.resume = Xt, v.pause = Xt, v;
    }
  }
  const d = Ct;
  i.call = (v, A, b) => Bt(v, d, A, b);
  let f = !1;
  o === "post" ? i.scheduler = (v) => {
    v.i = d, It(v, d && d.suspense);
  } : o !== "sync" && (f = !0, i.scheduler = (v, A) => {
    A ? v() : La(v);
  }), i.augmentJob = (v) => {
    t && (v.flags |= 4), f && (v.flags |= 2, d && (v.id = d.uid, v.i = d));
  };
  const y = Vd(e, t, i);
  return Qn && (c ? c.push(y) : l && y()), y;
}
function Kd(e, t, s) {
  const n = this.proxy, r = ct(e) ? e.includes(".") ? _c(n, e) : () => n[e] : e.bind(n, n);
  let o;
  Ne(t) ? o = t : (o = t.handler, s = t);
  const a = cr(this), i = wc(r, o.bind(n), s);
  return a(), i;
}
function _c(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const Is = /* @__PURE__ */ new WeakMap(), xc = /* @__PURE__ */ Symbol("_vte"), lo = (e) => e.__isTeleport, Gs = (e) => e && (e.disabled || e.disabled === ""), Jd = (e) => e && (e.defer || e.defer === ""), li = (e) => typeof SVGElement < "u" && e instanceof SVGElement, ci = (e) => typeof MathMLElement == "function" && e instanceof MathMLElement, sa = (e, t) => {
  const s = e && e.to;
  return ct(s) ? t ? t(s) : null : s;
}, Qd = {
  name: "Teleport",
  __isTeleport: !0,
  process(e, t, s, n, r, o, a, i, l, c) {
    const {
      mc: d,
      pc: f,
      pbc: y,
      o: { insert: v, querySelector: A, createText: b, createComment: w, parentNode: O }
    } = c, I = Gs(t.props);
    let { dynamicChildren: V } = t;
    const R = (ee, M, C) => {
      ee.shapeFlag & 16 && d(
        ee.children,
        M,
        C,
        r,
        o,
        a,
        i,
        l
      );
    }, J = (ee = t) => {
      const M = Gs(ee.props), C = ee.target = sa(ee.props, A), F = na(C, ee, b, v);
      C && (a !== "svg" && li(C) ? a = "svg" : a !== "mathml" && ci(C) && (a = "mathml"), r && r.isCE && (r.ce._teleportTargets || (r.ce._teleportTargets = /* @__PURE__ */ new Set())).add(C), M || (R(ee, C, F), Pn(ee, !1)));
    }, be = (ee) => {
      const M = () => {
        if (Is.get(ee) === M) {
          if (Is.delete(ee), Gs(ee.props)) {
            const C = O(ee.el) || s;
            R(ee, C, ee.anchor), Pn(ee, !0);
          }
          J(ee);
        }
      };
      Is.set(ee, M), It(M, o);
    };
    if (e == null) {
      const ee = t.el = b(""), M = t.anchor = b("");
      if (v(ee, s, n), v(M, s, n), Jd(t.props) || o && o.pendingBranch) {
        be(t);
        return;
      }
      I && (R(t, s, M), Pn(t, !0)), J();
    } else {
      t.el = e.el;
      const ee = t.anchor = e.anchor, M = Is.get(e);
      if (M) {
        M.flags |= 8, Is.delete(e), be(t);
        return;
      }
      t.targetStart = e.targetStart;
      const C = t.target = e.target, F = t.targetAnchor = e.targetAnchor, Se = Gs(e.props), Ce = Se ? s : C, Me = Se ? ee : F;
      if (a === "svg" || li(C) ? a = "svg" : (a === "mathml" || ci(C)) && (a = "mathml"), V ? (y(
        e.dynamicChildren,
        V,
        Ce,
        r,
        o,
        a,
        i
      ), Wa(e, t, !0)) : l || f(
        e,
        t,
        Ce,
        Me,
        r,
        o,
        a,
        i,
        !1
      ), I)
        Se ? t.props && e.props && t.props.to !== e.props.to && (t.props.to = e.props.to) : gr(
          t,
          s,
          ee,
          c,
          1
        );
      else if ((t.props && t.props.to) !== (e.props && e.props.to)) {
        const He = sa(t.props, A);
        He && (t.target = He, gr(
          t,
          He,
          null,
          c,
          0
        ));
      } else Se && gr(
        t,
        C,
        F,
        c,
        1
      );
      Pn(t, I);
    }
  },
  remove(e, t, s, { um: n, o: { remove: r } }, o) {
    const {
      shapeFlag: a,
      children: i,
      anchor: l,
      targetStart: c,
      targetAnchor: d,
      target: f,
      props: y
    } = e, v = Gs(y), A = o || !v, b = Is.get(e);
    if (b && (b.flags |= 8, Is.delete(e)), f && (r(c), r(d)), o && r(l), !b && (v || f) && a & 16)
      for (let w = 0; w < i.length; w++) {
        const O = i[w];
        n(
          O,
          t,
          s,
          A,
          !!O.dynamicChildren
        );
      }
  },
  move: gr,
  hydrate: Yd
};
function gr(e, t, s, { o: { insert: n }, m: r }, o = 2) {
  o === 0 && (e.targetStart && n(e.targetStart, t, s), n(e.targetAnchor, t, s), s = e.targetAnchor);
  const { el: a, anchor: i, shapeFlag: l, children: c, props: d } = e, f = o === 2;
  if (f && n(a, t, s), !Is.has(e) && (!f || Gs(d)) && l & 16)
    for (let y = 0; y < c.length; y++)
      r(
        c[y],
        t,
        s,
        2
      );
  f && n(i, t, s);
}
function Yd(e, t, s, n, r, o, {
  o: { nextSibling: a, parentNode: i, querySelector: l, insert: c, createText: d }
}, f) {
  function y(w, O) {
    let I = O;
    for (; I; ) {
      if (I && I.nodeType === 8) {
        if (I.data === "teleport start anchor")
          t.targetStart = I;
        else if (I.data === "teleport anchor") {
          t.targetAnchor = I, w._lpa = t.targetAnchor && a(t.targetAnchor);
          break;
        }
      }
      I = a(I);
    }
  }
  function v(w, O) {
    O.anchor = f(
      a(w),
      O,
      i(w),
      s,
      n,
      r,
      o
    );
  }
  const A = t.target = sa(
    t.props,
    l
  ), b = Gs(t.props);
  if (A) {
    const w = A._lpa || A.firstChild;
    t.shapeFlag & 16 && (b ? (v(e, t), y(A, w), t.targetAnchor || na(
      A,
      t,
      d,
      c,
      // if target is the same as the main view, insert anchors before current node
      // to avoid hydrating mismatch
      i(e) === A ? e : null
    )) : (t.anchor = a(e), y(A, w), t.targetAnchor || na(A, t, d, c), f(
      w && a(w),
      t,
      A,
      s,
      n,
      r,
      o
    ))), Pn(t, b);
  } else b && t.shapeFlag & 16 && (v(e, t), t.targetStart = e, t.targetAnchor = a(e));
  return t.anchor && a(t.anchor);
}
const kc = Qd;
function Pn(e, t) {
  const s = e.ctx;
  if (s && s.ut) {
    let n, r;
    for (t ? (n = e.el, r = e.anchor) : (n = e.targetStart, r = e.targetAnchor); n && n !== r; )
      n.nodeType === 1 && n.setAttribute("data-v-owner", s.uid), n = n.nextSibling;
    s.ut();
  }
}
function na(e, t, s, n, r = null) {
  const o = t.targetStart = s(""), a = t.targetAnchor = s("");
  return o[xc] = a, e && (n(o, e, r), n(a, e, r)), a;
}
const Ro = /* @__PURE__ */ Symbol("_leaveCb");
function Xd(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const s of e)
      if (s.type !== Lt) {
        t = s;
        break;
      }
  }
  return t;
}
function Sc(e) {
  if (!Ua(e))
    return lo(e.type) && e.children ? Xd(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && Ne(s.default))
      return s.default();
  }
}
function zr(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    zr(
      lo(s.type) && Sc(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === fe && $e(e.children)) {
    const s = Mc(e.children, !1);
    s && zr(s, t);
  }
}
function ra(e) {
  if (e.component)
    return ra(e.component.subTree);
  if (e.type === fe) {
    const t = $e(e.children) && Mc(e.children, !1);
    return t ? ra(t) : void 0;
  }
  if (e.type !== Lt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function xt(e, t) {
  return Ne(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    _t({ name: e.name }, t, { setup: e })
  ) : e;
}
function Cc(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function ui(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const jr = /* @__PURE__ */ new WeakMap();
function Fn(e, t, s, n, r = !1) {
  if ($e(e)) {
    e.forEach(
      (b, w) => Fn(
        b,
        t && ($e(t) ? t[w] : t),
        s,
        n,
        r
      )
    );
    return;
  }
  if (an(n) && !r) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && Fn(e, t, s, n.component.subTree);
    return;
  }
  const o = n.shapeFlag & 4 ? po(n.component) : n.el, a = r ? null : o, { i, r: l } = e, c = t && t.r, d = i.refs === st ? i.refs = {} : i.refs, f = i.setupState, y = /* @__PURE__ */ Je(f), v = f === st ? Ll : (b) => ui(d, b) ? !1 : Ye(y, b), A = (b, w) => !(w && ui(d, w));
  if (c != null && c !== l) {
    if (di(t), ct(c))
      d[c] = null, v(c) && (f[c] = null);
    else if (/* @__PURE__ */ ft(c)) {
      const b = t;
      A(c, b.k) && (c.value = null), b.k && (d[b.k] = null);
    }
  }
  if (Ne(l))
    ir(l, i, 12, [a, d]);
  else {
    const b = ct(l), w = /* @__PURE__ */ ft(l);
    if (b || w) {
      const O = () => {
        if (e.f) {
          const I = b ? v(l) ? f[l] : d[l] : A() || !e.k ? l.value : d[e.k];
          if (r)
            $e(I) && Ea(I, o);
          else if ($e(I))
            I.includes(o) || I.push(o);
          else if (b)
            d[l] = [o], v(l) && (f[l] = d[l]);
          else {
            const V = [o];
            A(l, e.k) && (l.value = V), e.k && (d[e.k] = V);
          }
        } else b ? (d[l] = a, v(l) && (f[l] = a)) : w && (A(l, e.k) && (l.value = a), e.k && (d[e.k] = a));
      };
      if (a) {
        const I = () => {
          O(), jr.delete(e);
        };
        I.id = -1, jr.set(e, I), It(I, s);
      } else
        di(e), O();
    }
  }
}
function di(e) {
  const t = jr.get(e);
  t && (t.flags |= 8, jr.delete(e));
}
ro().requestIdleCallback;
ro().cancelIdleCallback;
const an = (e) => !!e.type.__asyncLoader, Ua = (e) => e.type.__isKeepAlive;
function ef(e, t) {
  $c(e, "a", t);
}
function tf(e, t) {
  $c(e, "da", t);
}
function $c(e, t, s = Ct) {
  const n = e.__wdc || (e.__wdc = () => {
    let r = s;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (co(t, n, s), s) {
    let r = s.parent;
    for (; r && r.parent; )
      Ua(r.parent.vnode) && sf(n, t, s, r), r = r.parent;
  }
}
function sf(e, t, s, n) {
  const r = co(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  uo(() => {
    Ea(n[t], r);
  }, s);
}
function co(e, t, s = Ct, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...a) => {
      ss();
      const i = cr(s), l = Bt(t, s, e, a);
      return i(), ns(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const _s = (e) => (t, s = Ct) => {
  (!Qn || e === "sp") && co(e, (...n) => t(...n), s);
}, nf = _s("bm"), xs = _s("m"), rf = _s(
  "bu"
), of = _s("u"), Ic = _s(
  "bum"
), uo = _s("um"), af = _s(
  "sp"
), lf = _s("rtg"), cf = _s("rtc");
function uf(e, t = Ct) {
  co("ec", e, t);
}
const df = "components", Rc = /* @__PURE__ */ Symbol.for("v-ndc");
function fi(e) {
  return ct(e) ? ff(df, e, !1) || e : e || Rc;
}
function ff(e, t, s = !0, n = !1) {
  const r = wt || Ct;
  if (r) {
    const o = r.type;
    {
      const i = Kf(
        o,
        !1
      );
      if (i && (i === t || i === Et(t) || i === so(Et(t))))
        return o;
    }
    const a = (
      // local registration
      // check instance[type] first which is resolved for options API
      mi(r[e] || o[e], t) || // global registration
      mi(r.appContext[e], t)
    );
    return !a && n ? o : a;
  }
}
function mi(e, t) {
  return e && (e[t] || e[Et(t)] || e[so(Et(t))]);
}
function ze(e, t, s, n) {
  let r;
  const o = s, a = $e(e);
  if (a || ct(e)) {
    const i = a && /* @__PURE__ */ es(e);
    let l = !1, c = !1;
    i && (l = !/* @__PURE__ */ Mt(e), c = /* @__PURE__ */ rs(e), e = oo(e)), r = new Array(e.length);
    for (let d = 0, f = e.length; d < f; d++)
      r[d] = t(
        l ? c ? Ms(Dt(e[d])) : Dt(e[d]) : e[d],
        d,
        void 0,
        o
      );
  } else if (typeof e == "number")
    if (!Number.isInteger(e) || e < 0)
      r = [];
    else {
      r = new Array(e);
      for (let i = 0; i < e; i++)
        r[i] = t(i + 1, i, void 0, o);
    }
  else if (et(e))
    if (e[Symbol.iterator])
      r = Array.from(
        e,
        (i, l) => t(i, l, void 0, o)
      );
    else {
      const i = Object.keys(e);
      r = new Array(i.length);
      for (let l = 0, c = i.length; l < c; l++) {
        const d = i[l];
        r[l] = t(e[d], d, l, o);
      }
    }
  else
    r = [];
  return r;
}
function Ac(e, t, s, n, r, o) {
  if (s == null && (s = {}), wt.ce || wt.parent && an(wt.parent) && wt.parent.ce) {
    const c = s, d = Object.keys(c).length > 0;
    return k(), ut(
      fe,
      null,
      [H("slot", c, n)],
      d ? -2 : 64
    );
  }
  let a = e[t];
  a && a._c && (a._d = !1);
  const i = vs.length;
  k();
  let l;
  try {
    const c = a && Ec(a(s)), d = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = ut(
      fe,
      {
        key: (d && !jt(d) ? d : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let d = vs.length; d > i; d--) Ba();
    throw c;
  } finally {
    a && a._c && (a._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function Ec(e) {
  return e.some((t) => cn(t) ? !(t.type === Lt || t.type === fe && !Ec(t.children)) : !0) ? e : null;
}
const oa = (e) => e ? Qc(e) ? po(e) : oa(e.parent) : null, Wn = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ _t(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => oa(e.parent),
    $root: (e) => oa(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => Tc(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      La(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = lr.bind(e.proxy)),
    $watch: (e) => Kd.bind(e)
  })
), Ao = (e, t) => e !== st && !e.__isScriptSetup && Ye(e, t), mf = {
  get({ _: e }, t) {
    if (t === "__v_skip")
      return !0;
    const { ctx: s, setupState: n, data: r, props: o, accessCache: a, type: i, appContext: l } = e;
    if (t[0] !== "$") {
      const y = a[t];
      if (y !== void 0)
        switch (y) {
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
        if (Ao(n, t))
          return a[t] = 1, n[t];
        if (r !== st && Ye(r, t))
          return a[t] = 2, r[t];
        if (Ye(o, t))
          return a[t] = 3, o[t];
        if (s !== st && Ye(s, t))
          return a[t] = 4, s[t];
        aa && (a[t] = 0);
      }
    }
    const c = Wn[t];
    let d, f;
    if (c)
      return t === "$attrs" && St(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (d = i.__cssModules) && (d = d[t])
    )
      return d;
    if (s !== st && Ye(s, t))
      return a[t] = 4, s[t];
    if (
      // global properties
      f = l.config.globalProperties, Ye(f, t)
    )
      return f[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: r, ctx: o } = e;
    return Ao(r, t) ? (r[t] = s, !0) : n !== st && Ye(n, t) ? (n[t] = s, !0) : Ye(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: a }
  }, i) {
    let l;
    return !!(s[i] || e !== st && i[0] !== "$" && Ye(e, i) || Ao(t, i) || Ye(o, i) || Ye(n, i) || Ye(Wn, i) || Ye(r.config.globalProperties, i) || (l = a.__cssModules) && l[i]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : Ye(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function pi(e) {
  return $e(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let aa = !0;
function pf(e) {
  const t = Tc(e), s = e.proxy, n = e.ctx;
  aa = !1, t.beforeCreate && hi(t.beforeCreate, e, "bc");
  const {
    // state
    data: r,
    computed: o,
    methods: a,
    watch: i,
    provide: l,
    inject: c,
    // lifecycle
    created: d,
    beforeMount: f,
    mounted: y,
    beforeUpdate: v,
    updated: A,
    activated: b,
    deactivated: w,
    beforeDestroy: O,
    beforeUnmount: I,
    destroyed: V,
    unmounted: R,
    render: J,
    renderTracked: be,
    renderTriggered: ee,
    errorCaptured: M,
    serverPrefetch: C,
    // public API
    expose: F,
    inheritAttrs: Se,
    // assets
    components: Ce,
    directives: Me,
    filters: He
  } = t;
  if (c && hf(c, n, null), a)
    for (const E in a) {
      const _ = a[E];
      Ne(_) && (n[E] = _.bind(s));
    }
  if (r) {
    const E = r.call(s, s);
    et(E) && (e.data = /* @__PURE__ */ ar(E));
  }
  if (aa = !0, o)
    for (const E in o) {
      const _ = o[E], X = Ne(_) ? _.bind(s, s) : Ne(_.get) ? _.get.bind(s, s) : Xt, ne = !Ne(_) && Ne(_.set) ? _.set.bind(s) : Xt, Xe = ye({
        get: X,
        set: ne
      });
      Object.defineProperty(n, E, {
        enumerable: !0,
        configurable: !0,
        get: () => Xe.value,
        set: (qe) => Xe.value = qe
      });
    }
  if (i)
    for (const E in i)
      Oc(i[E], n, s, E);
  if (l) {
    const E = Ne(l) ? l.call(s) : l;
    Reflect.ownKeys(E).forEach((_) => {
      Ar(_, E[_]);
    });
  }
  d && hi(d, e, "c");
  function W(E, _) {
    $e(_) ? _.forEach((X) => E(X.bind(s))) : _ && E(_.bind(s));
  }
  if (W(nf, f), W(xs, y), W(rf, v), W(of, A), W(ef, b), W(tf, w), W(uf, M), W(cf, be), W(lf, ee), W(Ic, I), W(uo, R), W(af, C), $e(F))
    if (F.length) {
      const E = e.exposed || (e.exposed = {});
      F.forEach((_) => {
        Object.defineProperty(E, _, {
          get: () => s[_],
          set: (X) => s[_] = X,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  J && e.render === Xt && (e.render = J), Se != null && (e.inheritAttrs = Se), Ce && (e.components = Ce), Me && (e.directives = Me), C && Cc(e);
}
function hf(e, t, s = Xt) {
  $e(e) && (e = ia(e));
  for (const n in e) {
    const r = e[n];
    let o;
    et(r) ? "default" in r ? o = zt(
      r.from || n,
      r.default,
      !0
    ) : o = zt(r.from || n) : o = zt(r), /* @__PURE__ */ ft(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (a) => o.value = a
    }) : t[n] = o;
  }
}
function hi(e, t, s) {
  Bt(
    $e(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function Oc(e, t, s, n) {
  let r = n.includes(".") ? _c(s, n) : () => s[n];
  if (ct(e)) {
    const o = t[e];
    Ne(o) && Wt(r, o);
  } else if (Ne(e))
    Wt(r, e.bind(s));
  else if (et(e))
    if ($e(e))
      e.forEach((o) => Oc(o, t, s, n));
    else {
      const o = Ne(e.handler) ? e.handler.bind(s) : t[e.handler];
      Ne(o) && Wt(r, o, e);
    }
}
function Tc(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: a }
  } = e.appContext, i = o.get(t);
  let l;
  return i ? l = i : !r.length && !s && !n ? l = t : (l = {}, r.length && r.forEach(
    (c) => Dr(l, c, a, !0)
  ), Dr(l, t, a)), et(t) && o.set(t, l), l;
}
function Dr(e, t, s, n = !1) {
  const { mixins: r, extends: o } = t;
  o && Dr(e, o, s, !0), r && r.forEach(
    (a) => Dr(e, a, s, !0)
  );
  for (const a in t)
    if (!(n && a === "expose")) {
      const i = gf[a] || s && s[a];
      e[a] = i ? i(e[a], t[a]) : t[a];
    }
  return e;
}
const gf = {
  data: gi,
  props: vi,
  emits: vi,
  // objects
  methods: Nn,
  computed: Nn,
  // lifecycle
  beforeCreate: $t,
  created: $t,
  beforeMount: $t,
  mounted: $t,
  beforeUpdate: $t,
  updated: $t,
  beforeDestroy: $t,
  beforeUnmount: $t,
  destroyed: $t,
  unmounted: $t,
  activated: $t,
  deactivated: $t,
  errorCaptured: $t,
  serverPrefetch: $t,
  // assets
  components: Nn,
  directives: Nn,
  // watch
  watch: yf,
  // provide / inject
  provide: gi,
  inject: vf
};
function gi(e, t) {
  return t ? e ? function() {
    return _t(
      Ne(e) ? e.call(this, this) : e,
      Ne(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function vf(e, t) {
  return Nn(ia(e), ia(t));
}
function ia(e) {
  if ($e(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function $t(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function Nn(e, t) {
  return e ? _t(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function vi(e, t) {
  return e ? $e(e) && $e(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : _t(
    /* @__PURE__ */ Object.create(null),
    pi(e),
    pi(t ?? {})
  ) : t;
}
function yf(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = _t(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = $t(e[n], t[n]);
  return s;
}
function Pc() {
  return {
    app: null,
    config: {
      isNativeTag: Ll,
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
let bf = 0;
function wf(e, t) {
  return function(n, r = null) {
    Ne(n) || (n = _t({}, n)), r != null && !et(r) && (r = null);
    const o = Pc(), a = /* @__PURE__ */ new WeakSet(), i = [];
    let l = !1;
    const c = o.app = {
      _uid: bf++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: Qf,
      get config() {
        return o.config;
      },
      set config(d) {
      },
      use(d, ...f) {
        return a.has(d) || (d && Ne(d.install) ? (a.add(d), d.install(c, ...f)) : Ne(d) && (a.add(d), d(c, ...f))), c;
      },
      mixin(d) {
        return o.mixins.includes(d) || o.mixins.push(d), c;
      },
      component(d, f) {
        return f ? (o.components[d] = f, c) : o.components[d];
      },
      directive(d, f) {
        return f ? (o.directives[d] = f, c) : o.directives[d];
      },
      mount(d, f, y) {
        if (!l) {
          const v = c._ceVNode || H(n, r);
          return v.appContext = o, y === !0 ? y = "svg" : y === !1 && (y = void 0), e(v, d, y), l = !0, c._container = d, d.__vue_app__ = c, po(v.component);
        }
      },
      onUnmount(d) {
        i.push(d);
      },
      unmount() {
        l && (Bt(
          i,
          c._instance,
          16
        ), e(null, c._container), delete c._container.__vue_app__);
      },
      provide(d, f) {
        return o.provides[d] = f, c;
      },
      runWithContext(d) {
        const f = Js;
        Js = c;
        try {
          return d();
        } finally {
          Js = f;
        }
      }
    };
    return c;
  };
}
let Js = null;
const _f = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${Et(t)}Modifiers`] || e[`${Ls(t)}Modifiers`];
function xf(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || st;
  let r = s;
  const o = t.startsWith("update:"), a = o && _f(n, t.slice(7));
  a && (a.trim && (r = s.map((d) => ct(d) ? d.trim() : d)), a.number && (r = r.map(no)));
  let i, l = n[i = xo(t)] || // also try camelCase event handler (#2249)
  n[i = xo(Et(t))];
  !l && o && (l = n[i = xo(Ls(t))]), l && Bt(
    l,
    e,
    6,
    r
  );
  const c = n[i + "Once"];
  if (c) {
    if (!e.emitted)
      e.emitted = {};
    else if (e.emitted[i])
      return;
    e.emitted[i] = !0, Bt(
      c,
      e,
      6,
      r
    );
  }
}
const kf = /* @__PURE__ */ new WeakMap();
function Nc(e, t, s = !1) {
  const n = s ? kf : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let a = {}, i = !1;
  if (!Ne(e)) {
    const l = (c) => {
      const d = Nc(c, t, !0);
      d && (i = !0, _t(a, d));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !i ? (et(e) && n.set(e, null), null) : ($e(o) ? o.forEach((l) => a[l] = null) : _t(a, o), et(e) && n.set(e, a), a);
}
function fo(e, t) {
  return !e || !Yr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), Ye(e, t[0].toLowerCase() + t.slice(1)) || Ye(e, Ls(t)) || Ye(e, t));
}
function yi(e) {
  const {
    type: t,
    vnode: s,
    proxy: n,
    withProxy: r,
    propsOptions: [o],
    slots: a,
    attrs: i,
    emit: l,
    render: c,
    renderCache: d,
    props: f,
    data: y,
    setupState: v,
    ctx: A,
    inheritAttrs: b
  } = e, w = Mr(e);
  let O, I;
  try {
    if (s.shapeFlag & 4) {
      const R = r || n, J = R;
      O = Jt(
        c.call(
          J,
          R,
          d,
          f,
          v,
          y,
          A
        )
      ), I = i;
    } else {
      const R = t;
      O = Jt(
        R.length > 1 ? R(
          f,
          { attrs: i, slots: a, emit: l }
        ) : R(
          f,
          null
        )
      ), I = t.props ? i : Sf(i);
    }
  } catch (R) {
    vs.length = 0, io(R, e, 1), O = H(Lt);
  }
  let V = O;
  if (I && b !== !1) {
    const R = Object.keys(I), { shapeFlag: J } = V;
    R.length && J & 7 && (o && R.some(Xr) && (I = Cf(
      I,
      o
    )), V = un(V, I, !1, !0));
  }
  if (s.dirs && (V = un(V, null, !1, !0), V.dirs = V.dirs ? V.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const R = lo(V.type) && Sc(V) || V;
    zr(R, s.transition);
  }
  return O = V, Mr(w), O;
}
function Mc(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const r = e[n];
    if (cn(r)) {
      if (r.type !== Lt || r.children === "v-if") {
        if (s)
          return;
        s = r;
      }
    } else
      return;
  }
  return s;
}
const Sf = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || Yr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, Cf = (e, t) => {
  const s = {};
  for (const n in e)
    (!Xr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function $f(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: a, children: i, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? bi(n, a, c) : !!a;
    if (l & 8) {
      const d = t.dynamicProps;
      for (let f = 0; f < d.length; f++) {
        const y = d[f];
        if (zc(a, n, y) && !fo(c, y))
          return !0;
      }
    }
  } else
    return (r || i) && (!i || !i.$stable) ? !0 : n === a ? !1 : n ? a ? bi(n, a, c) : !0 : !!a;
  return !1;
}
function bi(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!Ye(e, o) || zc(t, e, o) && !fo(s, o))
      return !0;
  }
  return !1;
}
function zc(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && et(n) && et(r) ? !bs(n, r) : n !== r;
}
function If({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const jc = {}, Dc = () => Object.create(jc), Lc = (e) => Object.getPrototypeOf(e) === jc;
function Rf(e, t, s, n = !1) {
  const r = {}, o = Dc();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), Uc(e, t, r, o);
  for (const a in e.propsOptions[0])
    a in r || (r[a] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ dc(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function Af(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: a }
  } = e, i = /* @__PURE__ */ Je(r), [l] = e.propsOptions;
  let c = !1;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (n || a > 0) && !(a & 16)
  ) {
    if (a & 8) {
      const d = e.vnode.dynamicProps;
      for (let f = 0; f < d.length; f++) {
        let y = d[f];
        if (fo(e.emitsOptions, y))
          continue;
        const v = t[y];
        if (l)
          if (Ye(o, y))
            v !== o[y] && (o[y] = v, c = !0);
          else {
            const A = Et(y);
            r[A] = la(
              l,
              i,
              A,
              v,
              e,
              !1
            );
          }
        else
          v !== o[y] && (o[y] = v, c = !0);
      }
    }
  } else {
    Uc(e, t, r, o) && (c = !0);
    let d;
    for (const f in i)
      (!t || // for camelCase
      !Ye(t, f) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((d = Ls(f)) === f || !Ye(t, d))) && (l ? s && // for camelCase
      (s[f] !== void 0 || // for kebab-case
      s[d] !== void 0) && (r[f] = la(
        l,
        i,
        f,
        void 0,
        e,
        !0
      )) : delete r[f]);
    if (o !== i)
      for (const f in o)
        (!t || !Ye(t, f)) && (delete o[f], c = !0);
  }
  c && fs(e.attrs, "set", "");
}
function Uc(e, t, s, n) {
  const [r, o] = e.propsOptions;
  let a = !1, i;
  if (t)
    for (let l in t) {
      if (Ln(l))
        continue;
      const c = t[l];
      let d;
      r && Ye(r, d = Et(l)) ? !o || !o.includes(d) ? s[d] = c : (i || (i = {}))[d] = c : fo(e.emitsOptions, l) || (!(l in n) || c !== n[l]) && (n[l] = c, a = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ Je(s), c = i || st;
    for (let d = 0; d < o.length; d++) {
      const f = o[d];
      s[f] = la(
        r,
        l,
        f,
        c[f],
        e,
        !Ye(c, f)
      );
    }
  }
  return a;
}
function la(e, t, s, n, r, o) {
  const a = e[s];
  if (a != null) {
    const i = Ye(a, "default");
    if (i && n === void 0) {
      const l = a.default;
      if (a.type !== Function && !a.skipFactory && Ne(l)) {
        const { propsDefaults: c } = r;
        if (s in c)
          n = c[s];
        else {
          const d = cr(r);
          n = c[s] = l.call(
            null,
            t
          ), d();
        }
      } else
        n = l;
      r.ce && r.ce._setProp(s, n);
    }
    a[
      0
      /* shouldCast */
    ] && (o && !i ? n = !1 : a[
      1
      /* shouldCastTrue */
    ] && (n === "" || n === Ls(s)) && (n = !0));
  }
  return n;
}
const Ef = /* @__PURE__ */ new WeakMap();
function Vc(e, t, s = !1) {
  const n = s ? Ef : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, a = {}, i = [];
  let l = !1;
  if (!Ne(e)) {
    const d = (f) => {
      l = !0;
      const [y, v] = Vc(f, t, !0);
      _t(a, y), v && i.push(...v);
    };
    !s && t.mixins.length && t.mixins.forEach(d), e.extends && d(e.extends), e.mixins && e.mixins.forEach(d);
  }
  if (!o && !l)
    return et(e) && n.set(e, Hs), Hs;
  if ($e(o))
    for (let d = 0; d < o.length; d++) {
      const f = Et(o[d]);
      wi(f) && (a[f] = st);
    }
  else if (o)
    for (const d in o) {
      const f = Et(d);
      if (wi(f)) {
        const y = o[d], v = a[f] = $e(y) || Ne(y) ? { type: y } : _t({}, y), A = v.type;
        let b = !1, w = !0;
        if ($e(A))
          for (let O = 0; O < A.length; ++O) {
            const I = A[O], V = Ne(I) && I.name;
            if (V === "Boolean") {
              b = !0;
              break;
            } else V === "String" && (w = !1);
          }
        else
          b = Ne(A) && A.name === "Boolean";
        v[
          0
          /* shouldCast */
        ] = b, v[
          1
          /* shouldCastTrue */
        ] = w, (b || Ye(v, "default")) && i.push(f);
      }
    }
  const c = [a, i];
  return et(e) && n.set(e, c), c;
}
function wi(e) {
  return e[0] !== "$" && !Ln(e);
}
const Va = (e) => e === "_" || e === "_ctx" || e === "$stable", Fa = (e) => $e(e) ? e.map(Jt) : [Jt(e)], Of = (e, t, s) => {
  if (t._n)
    return t;
  const n = se((...r) => Fa(t(...r)), s);
  return n._c = !1, n;
}, Fc = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (Va(r)) continue;
    const o = e[r];
    if (Ne(o))
      t[r] = Of(r, o, n);
    else if (o != null) {
      const a = Fa(o);
      t[r] = () => a;
    }
  }
}, Wc = (e, t) => {
  const s = Fa(t);
  e.slots.default = () => s;
}, Bc = (e, t, s) => {
  for (const n in t)
    (s || !Va(n)) && (e[n] = t[n]);
}, Tf = (e, t, s) => {
  const n = e.slots = Dc();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (Bc(n, t, s), s && Wl(n, "_", r, !0)) : Fc(t, n);
  } else t && Wc(e, t);
}, Pf = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, a = st;
  if (n.shapeFlag & 32) {
    const i = t._;
    i ? s && i === 1 ? o = !1 : Bc(r, t, s) : (o = !t.$stable, Fc(t, r)), a = t;
  } else t && (Wc(e, t), a = { default: 1 });
  if (o)
    for (const i in r)
      !Va(i) && a[i] == null && delete r[i];
}, It = Df;
function Nf(e) {
  return Mf(e);
}
function Mf(e, t) {
  const s = ro();
  s.__VUE__ = !0;
  const {
    insert: n,
    remove: r,
    patchProp: o,
    createElement: a,
    createText: i,
    createComment: l,
    setText: c,
    setElementText: d,
    parentNode: f,
    nextSibling: y,
    setScopeId: v = Xt,
    insertStaticContent: A
  } = e, b = (g, x, P, z = null, $ = null, m = null, h = void 0, N = null, U = !!x.dynamicChildren) => {
    if (g === x)
      return;
    g && !Cn(g, x) && (z = q(g), qe(g, $, m, !0), g = null), x.patchFlag === -2 && (U = !1, x.dynamicChildren = null), x.dynamicChildren && g && g.dynamicChildren && g.dynamicChildren.hasOnce && (x.dynamicChildren === Hs && (x.dynamicChildren = []), x.dynamicChildren.hasOnce = !0);
    const { type: G, ref: ge, shapeFlag: ie } = x;
    switch (G) {
      case mo:
        w(g, x, P, z);
        break;
      case Lt:
        O(g, x, P, z);
        break;
      case Er:
        g == null && I(x, P, z, h);
        break;
      case fe:
        Ce(
          g,
          x,
          P,
          z,
          $,
          m,
          h,
          N,
          U
        );
        break;
      default:
        ie & 1 ? J(
          g,
          x,
          P,
          z,
          $,
          m,
          h,
          N,
          U
        ) : ie & 6 ? Me(
          g,
          x,
          P,
          z,
          $,
          m,
          h,
          N,
          U
        ) : (ie & 64 || ie & 128) && G.process(
          g,
          x,
          P,
          z,
          $,
          m,
          h,
          N,
          U,
          D
        );
    }
    ge != null && $ ? Fn(ge, g && g.ref, m, x || g, !x) : ge == null && g && g.ref != null && Fn(g.ref, null, m, g, !0);
  }, w = (g, x, P, z) => {
    if (g == null)
      n(
        x.el = i(x.children),
        P,
        z
      );
    else {
      const $ = x.el = g.el;
      x.children !== g.children && c($, x.children);
    }
  }, O = (g, x, P, z) => {
    g == null ? n(
      x.el = l(x.children || ""),
      P,
      z
    ) : x.el = g.el;
  }, I = (g, x, P, z) => {
    [g.el, g.anchor] = A(
      g.children,
      x,
      P,
      z,
      g.el,
      g.anchor
    );
  }, V = ({ el: g, anchor: x }, P, z) => {
    let $;
    for (; g && g !== x; )
      $ = y(g), n(g, P, z), g = $;
    n(x, P, z);
  }, R = ({ el: g, anchor: x }) => {
    let P;
    for (; g && g !== x; )
      P = y(g), r(g), g = P;
    r(x);
  }, J = (g, x, P, z, $, m, h, N, U) => {
    if (x.type === "svg" ? h = "svg" : x.type === "math" && (h = "mathml"), g == null)
      be(
        x,
        P,
        z,
        $,
        m,
        h,
        N,
        U
      );
    else {
      const G = g.el && g.el._isVueCE ? g.el : null;
      try {
        G && G._beginPatch(), C(
          g,
          x,
          $,
          m,
          h,
          N,
          U
        );
      } finally {
        G && G._endPatch();
      }
    }
  }, be = (g, x, P, z, $, m, h, N) => {
    let U, G;
    const { props: ge, shapeFlag: ie, transition: xe, dirs: Ie } = g;
    if (U = g.el = a(
      g.type,
      m,
      ge && ge.is,
      ge
    ), ie & 8 ? d(U, g.children) : ie & 16 && M(
      g.children,
      U,
      null,
      z,
      $,
      Eo(g, m),
      h,
      N
    ), Ie && Vs(g, null, z, "created"), ee(U, g, g.scopeId, h, z), ge) {
      for (const Ze in ge)
        Ze !== "value" && !Ln(Ze) && o(U, Ze, null, ge[Ze], m, z);
      "value" in ge && o(U, "value", null, ge.value, m), (G = ge.onVnodeBeforeMount) && Gt(G, z, g);
    }
    Ie && Vs(g, null, z, "beforeMount");
    const Le = zf($, xe);
    Le && xe.beforeEnter(U), n(U, x, P), ((G = ge && ge.onVnodeMounted) || Le || Ie) && It(() => {
      try {
        G && Gt(G, z, g), Le && xe.enter(U), Ie && Vs(g, null, z, "mounted");
      } finally {
      }
    }, $);
  }, ee = (g, x, P, z, $) => {
    if (P && v(g, P), z)
      for (let m = 0; m < z.length; m++)
        v(g, z[m]);
    if ($) {
      let m = $.subTree;
      if (x === m || Gc(m.type) && (m.ssContent === x || m.ssFallback === x)) {
        const h = $.vnode;
        ee(
          g,
          h,
          h.scopeId,
          h.slotScopeIds,
          $.parent
        );
      }
    }
  }, M = (g, x, P, z, $, m, h, N, U = 0) => {
    for (let G = U; G < g.length; G++) {
      const ge = g[G] = N ? ds(g[G]) : Jt(g[G]);
      b(
        null,
        ge,
        x,
        P,
        z,
        $,
        m,
        h,
        N
      );
    }
  }, C = (g, x, P, z, $, m, h) => {
    const N = x.el = g.el;
    let { patchFlag: U, dynamicChildren: G, dirs: ge } = x;
    U |= g.patchFlag & 16;
    const ie = g.props || st, xe = x.props || st;
    let Ie;
    if (P && Fs(P, !1), (Ie = xe.onVnodeBeforeUpdate) && Gt(Ie, P, x, g), ge && Vs(x, g, P, "beforeUpdate"), P && Fs(P, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    G && (!g.dynamicChildren || g.dynamicChildren.length !== G.length) && (U = 0, h = !1, G = null), (ie.innerHTML && xe.innerHTML == null || ie.textContent && xe.textContent == null) && d(N, ""), G ? F(
      g.dynamicChildren,
      G,
      N,
      P,
      z,
      Eo(x, $),
      m
    ) : h || _(
      g,
      x,
      N,
      null,
      P,
      z,
      Eo(x, $),
      m,
      !1
    ), U > 0) {
      if (U & 16)
        Se(N, ie, xe, P, $);
      else if (U & 2 && ie.class !== xe.class && o(N, "class", null, xe.class, $), U & 4 && o(N, "style", ie.style, xe.style, $), U & 8) {
        const Le = x.dynamicProps;
        for (let Ze = 0; Ze < Le.length; Ze++) {
          const Q = Le[Ze], de = ie[Q], ce = xe[Q];
          (ce !== de || Q === "value") && o(N, Q, de, ce, $, P);
        }
      }
      U & 1 && g.children !== x.children && d(N, x.children);
    } else !h && G == null && Se(N, ie, xe, P, $);
    ((Ie = xe.onVnodeUpdated) || ge) && It(() => {
      Ie && Gt(Ie, P, x, g), ge && Vs(x, g, P, "updated");
    }, z);
  }, F = (g, x, P, z, $, m, h) => {
    for (let N = 0; N < x.length; N++) {
      const U = g[N], G = x[N], ge = U.el || ca(U), ie = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        ge && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (U.type === fe || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !Cn(U, G) || // - In the case of a component, it could contain anything.
        U.shapeFlag & 198) ? f(ge) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          P
        )
      );
      b(
        U,
        G,
        ie,
        null,
        z,
        $,
        m,
        h,
        !0
      );
    }
  }, Se = (g, x, P, z, $) => {
    if (x !== P) {
      if (x !== st)
        for (const m in x)
          !Ln(m) && !(m in P) && o(
            g,
            m,
            x[m],
            null,
            $,
            z
          );
      for (const m in P) {
        if (Ln(m)) continue;
        const h = P[m], N = x[m];
        h !== N && m !== "value" && o(g, m, N, h, $, z);
      }
      "value" in P && o(g, "value", x.value, P.value, $);
    }
  }, Ce = (g, x, P, z, $, m, h, N, U) => {
    const G = x.el = g ? g.el : i(""), ge = x.anchor = g ? g.anchor : i("");
    let { patchFlag: ie, dynamicChildren: xe, slotScopeIds: Ie } = x;
    Ie && (N = N ? N.concat(Ie) : Ie), g == null ? (n(G, P, z), n(ge, P, z), M(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      x.children || [],
      P,
      ge,
      $,
      m,
      h,
      N,
      U
    )) : ie > 0 && ie & 64 && xe && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    g.dynamicChildren && g.dynamicChildren.length === xe.length ? (F(
      g.dynamicChildren,
      xe,
      P,
      $,
      m,
      h,
      N
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (x.key != null || $ && x === $.subTree) && Wa(
      g,
      x,
      !0
      /* shallow */
    )) : _(
      g,
      x,
      P,
      ge,
      $,
      m,
      h,
      N,
      U
    );
  }, Me = (g, x, P, z, $, m, h, N, U) => {
    x.slotScopeIds = N, g == null ? x.shapeFlag & 512 ? $.ctx.activate(
      x,
      P,
      z,
      h,
      U
    ) : He(
      x,
      P,
      z,
      $,
      m,
      h,
      U
    ) : ue(g, x, U);
  }, He = (g, x, P, z, $, m, h) => {
    const N = g.component = Bf(
      g,
      z,
      $
    );
    if (Ua(g) && (N.ctx.renderer = D), qf(N, !1, h), N.asyncDep) {
      if ($ && $.registerDep(
        N,
        W,
        h,
        m
      ), !g.el) {
        const U = N.subTree = H(Lt);
        O(null, U, x, P), g.placeholder = U.el;
      }
    } else
      W(
        N,
        g,
        x,
        P,
        $,
        m,
        h
      );
  }, ue = (g, x, P) => {
    const z = x.component = g.component;
    if ($f(g, x, P))
      if (z.asyncDep && !z.asyncResolved) {
        x.el = g.el, x.placeholder = g.placeholder, E(z, x, P);
        return;
      } else
        z.next = x, z.update();
    else
      x.el = g.el, x.placeholder = g.placeholder, z.vnode = x;
  }, W = (g, x, P, z, $, m, h) => {
    const N = () => {
      if (g.isMounted) {
        let { next: ie, bu: xe, u: Ie, parent: Le, vnode: Ze } = g;
        {
          const je = qc(g);
          if (je) {
            ie && (ie.el = Ze.el, E(g, ie, h)), je.asyncDep.then(() => {
              It(() => {
                g.isUnmounted || G();
              }, $);
            });
            return;
          }
        }
        let Q = ie, de;
        Fs(g, !1), ie ? (ie.el = Ze.el, E(g, ie, h)) : ie = Ze, xe && Rr(xe), (de = ie.props && ie.props.onVnodeBeforeUpdate) && Gt(de, Le, ie, Ze), Fs(g, !0);
        const ce = yi(g), Ee = g.subTree;
        g.subTree = ce, b(
          Ee,
          ce,
          // parent may have changed if it's in a teleport
          f(Ee.el),
          // anchor may have changed if it's in a fragment
          q(Ee),
          g,
          $,
          m
        ), ie.el = ce.el, Q === null && If(g, ce.el), Ie && It(Ie, $), (de = ie.props && ie.props.onVnodeUpdated) && It(
          () => Gt(de, Le, ie, Ze),
          $
        );
      } else {
        let ie;
        const { el: xe, props: Ie } = x, { bm: Le, m: Ze, parent: Q, root: de, type: ce } = g, Ee = an(x);
        Fs(g, !1), Le && Rr(Le), !Ee && (ie = Ie && Ie.onVnodeBeforeMount) && Gt(ie, Q, x), Fs(g, !0);
        {
          de.ce && de.ce._hasShadowRoot() && de.ce._injectChildStyle(
            ce,
            g.parent ? g.parent.type : void 0
          );
          const je = g.subTree = yi(g);
          b(
            null,
            je,
            P,
            z,
            g,
            $,
            m
          ), x.el = je.el;
        }
        if (Ze && It(Ze, $), !Ee && (ie = Ie && Ie.onVnodeMounted)) {
          const je = x;
          It(
            () => Gt(ie, Q, je),
            $
          );
        }
        (x.shapeFlag & 256 || Q && an(Q.vnode) && Q.vnode.shapeFlag & 256) && g.a && It(g.a, $), g.isMounted = !0, x = P = z = null;
      }
    };
    g.scope.on();
    const U = g.effect = new Jl(N);
    g.scope.off();
    const G = g.update = U.run.bind(U), ge = g.job = U.runIfDirty.bind(U);
    ge.i = g, ge.id = g.uid, U.scheduler = () => La(ge), Fs(g, !0), G();
  }, E = (g, x, P) => {
    x.component = g;
    const z = g.vnode.props;
    g.vnode = x, g.next = null, Af(g, x.props, z, P), Pf(g, x.children, P), ss(), gc(g), ns();
  }, _ = (g, x, P, z, $, m, h, N, U = !1) => {
    const G = g && g.children, ge = g ? g.shapeFlag : 0, ie = x.children, { patchFlag: xe, shapeFlag: Ie } = x;
    if (xe > 0) {
      if (xe & 128) {
        ne(
          G,
          ie,
          P,
          z,
          $,
          m,
          h,
          N,
          U
        );
        return;
      } else if (xe & 256) {
        X(
          G,
          ie,
          P,
          z,
          $,
          m,
          h,
          N,
          U
        );
        return;
      }
    }
    Ie & 8 ? (ge & 16 && Oe(G, $, m), ie !== G && d(P, ie)) : ge & 16 ? Ie & 16 ? ne(
      G,
      ie,
      P,
      z,
      $,
      m,
      h,
      N,
      U
    ) : Oe(G, $, m, !0) : (ge & 8 && d(P, ""), Ie & 16 && M(
      ie,
      P,
      z,
      $,
      m,
      h,
      N,
      U
    ));
  }, X = (g, x, P, z, $, m, h, N, U) => {
    g = g || Hs, x = x || Hs;
    const G = g.length, ge = x.length, ie = Math.min(G, ge);
    let xe;
    for (xe = 0; xe < ie; xe++) {
      const Ie = x[xe] = U ? ds(x[xe]) : Jt(x[xe]);
      b(
        g[xe],
        Ie,
        P,
        null,
        $,
        m,
        h,
        N,
        U
      );
    }
    G > ge ? Oe(
      g,
      $,
      m,
      !0,
      !1,
      ie
    ) : M(
      x,
      P,
      z,
      $,
      m,
      h,
      N,
      U,
      ie
    );
  }, ne = (g, x, P, z, $, m, h, N, U) => {
    let G = 0;
    const ge = x.length;
    let ie = g.length - 1, xe = ge - 1;
    for (; G <= ie && G <= xe; ) {
      const Ie = g[G], Le = x[G] = U ? ds(x[G]) : Jt(x[G]);
      if (Cn(Ie, Le))
        b(
          Ie,
          Le,
          P,
          null,
          $,
          m,
          h,
          N,
          U
        );
      else
        break;
      G++;
    }
    for (; G <= ie && G <= xe; ) {
      const Ie = g[ie], Le = x[xe] = U ? ds(x[xe]) : Jt(x[xe]);
      if (Cn(Ie, Le))
        b(
          Ie,
          Le,
          P,
          null,
          $,
          m,
          h,
          N,
          U
        );
      else
        break;
      ie--, xe--;
    }
    if (G > ie) {
      if (G <= xe) {
        const Ie = xe + 1, Le = Ie < ge ? x[Ie].el : z;
        for (; G <= xe; )
          b(
            null,
            x[G] = U ? ds(x[G]) : Jt(x[G]),
            P,
            Le,
            $,
            m,
            h,
            N,
            U
          ), G++;
      }
    } else if (G > xe)
      for (; G <= ie; )
        qe(g[G], $, m, !0), G++;
    else {
      const Ie = G, Le = G, Ze = /* @__PURE__ */ new Map();
      for (G = Le; G <= xe; G++) {
        const Y = x[G] = U ? ds(x[G]) : Jt(x[G]);
        Y.key != null && Ze.set(Y.key, G);
      }
      let Q, de = 0;
      const ce = xe - Le + 1;
      let Ee = !1, je = 0;
      const Re = new Array(ce);
      for (G = 0; G < ce; G++) Re[G] = 0;
      for (G = Ie; G <= ie; G++) {
        const Y = g[G];
        if (de >= ce) {
          qe(Y, $, m, !0);
          continue;
        }
        let _e;
        if (Y.key != null)
          _e = Ze.get(Y.key);
        else
          for (Q = Le; Q <= xe; Q++)
            if (Re[Q - Le] === 0 && Cn(Y, x[Q])) {
              _e = Q;
              break;
            }
        _e === void 0 ? qe(Y, $, m, !0) : (Re[_e - Le] = G + 1, _e >= je ? je = _e : Ee = !0, b(
          Y,
          x[_e],
          P,
          null,
          $,
          m,
          h,
          N,
          U
        ), de++);
      }
      const B = Ee ? jf(Re) : Hs;
      for (Q = B.length - 1, G = ce - 1; G >= 0; G--) {
        const Y = Le + G, _e = x[Y], Z = x[Y + 1], pe = Y + 1 < ge ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          Z.el || ca(Z)
        ) : z;
        Re[G] === 0 ? b(
          null,
          _e,
          P,
          pe,
          $,
          m,
          h,
          N,
          U
        ) : Ee && (Q < 0 || G !== B[Q] ? Xe(_e, P, pe, 2) : Q--);
      }
    }
  }, Xe = (g, x, P, z, $ = null) => {
    const { el: m, type: h, transition: N, children: U, shapeFlag: G } = g;
    if (G & 6) {
      Xe(g.component.subTree, x, P, z);
      return;
    }
    if (G & 128) {
      g.suspense.move(x, P, z);
      return;
    }
    if (G & 64) {
      h.move(g, x, P, D);
      return;
    }
    if (h === fe) {
      n(m, x, P);
      for (let ie = 0; ie < U.length; ie++)
        Xe(U[ie], x, P, z);
      n(g.anchor, x, P);
      return;
    }
    if (h === Er) {
      V(g, x, P);
      return;
    }
    if (z !== 2 && G & 1 && N)
      if (z === 0)
        N.persisted && !m[Ro] ? n(m, x, P) : (N.beforeEnter(m), n(m, x, P), It(() => N.enter(m), $));
      else {
        const { leave: ie, delayLeave: xe, afterLeave: Ie } = N, Le = () => {
          g.ctx.isUnmounted ? r(m) : n(m, x, P);
        }, Ze = () => {
          const Q = m._isLeaving || !!m[Ro];
          m._isLeaving && m[Ro](
            !0
            /* cancelled */
          ), N.persisted && !Q ? Le() : ie(m, () => {
            Le(), Ie && Ie();
          });
        };
        xe ? xe(m, Le, Ze) : Ze();
      }
    else
      n(m, x, P);
  }, qe = (g, x, P, z = !1, $ = !1) => {
    const {
      type: m,
      props: h,
      ref: N,
      children: U,
      dynamicChildren: G,
      shapeFlag: ge,
      patchFlag: ie,
      dirs: xe,
      cacheIndex: Ie,
      memo: Le
    } = g;
    if ((ie === -2 || G && G.hasOnce) && ($ = !1), N != null && (ss(), Fn(N, null, P, g, !0), ns()), Ie != null && (!g.ctx || g.ctx === x) && (x.renderCache[Ie] = void 0), ge & 256) {
      x.ctx.deactivate(g);
      return;
    }
    const Ze = ge & 1 && xe, Q = !an(g);
    let de;
    if (Q && (de = h && h.onVnodeBeforeUnmount) && Gt(de, x, g), ge & 6)
      We(g.component, P, z);
    else {
      if (ge & 128) {
        g.suspense.unmount(P, z);
        return;
      }
      Ze && Vs(g, null, x, "beforeUnmount"), ge & 64 ? g.type.remove(
        g,
        x,
        P,
        D,
        z
      ) : G && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !G.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (m !== fe || ie > 0 && ie & 64) ? Oe(
        G,
        x,
        P,
        !1,
        !0
      ) : (m === fe && ie & 384 || !$ && ge & 16) && Oe(U, x, P), z && mt(g);
    }
    const ce = Le != null && Ie == null;
    (Q && (de = h && h.onVnodeUnmounted) || Ze || ce) && It(() => {
      de && Gt(de, x, g), Ze && Vs(g, null, x, "unmounted"), ce && (g.el = null);
    }, P);
  }, mt = (g) => {
    const { type: x, el: P, anchor: z, transition: $ } = g, m = x === fe;
    if (m && !$) {
      at(P, z);
      return;
    }
    if (x === Er) {
      R(g), $ && !$.persisted && $.afterLeave && $.afterLeave();
      return;
    }
    const h = m ? ra(g) : g, N = () => {
      m ? f(P) && at(P, z) : r(P), $ && !$.persisted && $.afterLeave && $.afterLeave();
    };
    if (h && h.shapeFlag & 1 && $ && !$.persisted) {
      const { leave: U, delayLeave: G } = $, ge = h.el, ie = () => U(ge, N);
      G ? G(ge, N, ie) : ie();
    } else
      N();
  }, at = (g, x) => {
    let P;
    for (; g !== x; )
      P = y(g), r(g), g = P;
    r(x);
  }, We = (g, x, P) => {
    const { bum: z, scope: $, job: m, subTree: h, um: N, m: U, a: G } = g;
    _i(U), _i(G), z && Rr(z), $.stop(), m ? (m.flags |= 8, qe(h, g, x, P)) : g.vnode.el && h && (h.transition = g.vnode.transition, qe(h, g, x, P)), N && It(N, x), It(() => {
      g.isUnmounted = !0;
    }, x);
  }, Oe = (g, x, P, z = !1, $ = !1, m = 0) => {
    for (let h = m; h < g.length; h++)
      qe(g[h], x, P, z, $);
  }, q = (g) => {
    if (g.shapeFlag & 6)
      return q(g.component.subTree);
    if (g.shapeFlag & 128)
      return g.suspense.next();
    const x = y(g.anchor || g.el), P = x && x[xc];
    return P ? y(P) : x;
  }, j = (g, x, P) => {
    const z = g && x._vnode ? void 0 : g && g.component ? g.component.uid : Wf();
    qd(() => {
      g == null ? x._vnode && qe(x._vnode, null, null, !0) : b(
        x._vnode || null,
        g,
        x,
        null,
        null,
        null,
        P
      ), x._vnode = g;
    }, z);
  }, D = {
    p: b,
    um: qe,
    m: Xe,
    r: mt,
    mt: He,
    mc: M,
    pc: _,
    pbc: F,
    n: q,
    o: e
  };
  return {
    render: j,
    hydrate: void 0,
    createApp: wf(j)
  };
}
function Eo({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function Fs({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function zf(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function Wa(e, t, s = !1) {
  const n = e.children, r = t.children;
  if ($e(n) && $e(r))
    for (let o = 0; o < n.length; o++) {
      const a = n[o];
      let i = r[o];
      i.shapeFlag & 1 && !i.dynamicChildren && ((i.patchFlag <= 0 || i.patchFlag === 32) && (i = r[o] = ds(r[o]), i.el = a.el), !s && i.patchFlag !== -2 && Wa(a, i)), i.type === mo && (i.patchFlag === -1 && (i = r[o] = ds(i)), i.el = a.el), i.type === Lt && !i.el && (i.el = a.el);
    }
}
function jf(e) {
  const t = e.slice(), s = [0];
  let n, r, o, a, i;
  const l = e.length;
  for (n = 0; n < l; n++) {
    const c = e[n];
    if (c !== 0) {
      if (r = s[s.length - 1], e[r] < c) {
        t[n] = r, s.push(n);
        continue;
      }
      for (o = 0, a = s.length - 1; o < a; )
        i = o + a >> 1, e[s[i]] < c ? o = i + 1 : a = i;
      c < e[s[o]] && (o > 0 && (t[n] = s[o - 1]), s[o] = n);
    }
  }
  for (o = s.length, a = s[o - 1]; o-- > 0; )
    s[o] = a, a = t[a];
  return s;
}
function qc(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : qc(t);
}
function _i(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function ca(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? ca(t.subTree) : null;
}
const Gc = (e) => e.__isSuspense;
function Df(e, t) {
  t && t.pendingBranch ? $e(e) ? t.effects.push(...e) : t.effects.push(e) : Bd(e);
}
const fe = /* @__PURE__ */ Symbol.for("v-fgt"), mo = /* @__PURE__ */ Symbol.for("v-txt"), Lt = /* @__PURE__ */ Symbol.for("v-cmt"), Er = /* @__PURE__ */ Symbol.for("v-stc"), vs = [];
let Nt = null;
function k(e = !1) {
  vs.push(Nt = e ? null : []);
}
function Ba() {
  vs.pop(), Nt = vs[vs.length - 1] || null;
}
let Kn = 1;
function Lr(e, t = !1) {
  Kn += e, e < 0 && Nt && t && (Nt.hasOnce = !0);
}
function Hc(e) {
  return e.dynamicChildren = Kn > 0 ? Nt || Hs : null, Ba(), Kn > 0 && Nt && Nt.push(e), e;
}
function S(e, t, s, n, r, o) {
  return Hc(
    u(
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
function ut(e, t, s, n, r) {
  return Hc(
    H(
      e,
      t,
      s,
      n,
      r,
      !0
    )
  );
}
function cn(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function Cn(e, t) {
  return e.type === t.type && e.key === t.key;
}
const Zc = ({ key: e }) => e ?? null, Or = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? ct(e) || /* @__PURE__ */ ft(e) || Ne(e) ? { i: wt, r: e, k: t, f: !!s } : e : null);
function u(e, t = null, s = null, n = 0, r = null, o = e === fe ? 0 : 1, a = !1, i = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Zc(t),
    ref: t && Or(t),
    scopeId: bc,
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
    ctx: wt
  };
  return i ? (Vr(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= ct(s) ? 8 : 16), Kn > 0 && // avoid a block node from tracking itself
  !a && // has current parent block
  Nt && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && Nt.push(l), l;
}
const H = Lf;
function Lf(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === Rc) && (e = Lt), cn(e)) {
    const i = un(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && Vr(i, s), Kn > 0 && !o && Nt && (i.shapeFlag & 6 ? Nt[Nt.indexOf(e)] = i : Nt.push(i)), i.patchFlag = -2, i;
  }
  if (Jf(e) && (e = e.__vccOpts), t) {
    t = Uf(t);
    let { class: i, style: l } = t;
    i && !ct(i) && (t.class = Ae(i)), et(l) && (/* @__PURE__ */ ao(l) && !$e(l) && (l = _t({}, l)), t.style = wn(l));
  }
  const a = ct(e) ? 1 : Gc(e) ? 128 : lo(e) ? 64 : et(e) ? 4 : Ne(e) ? 2 : 0;
  return u(
    e,
    t,
    s,
    n,
    r,
    a,
    o,
    !0
  );
}
function Uf(e) {
  return e ? /* @__PURE__ */ ao(e) || Lc(e) ? _t({}, e) : e : null;
}
function un(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: a, children: i, transition: l } = e, c = t ? Vf(r || {}, t) : r, d = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Zc(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? $e(o) ? o.concat(Or(t)) : [o, Or(t)] : Or(t)
    ) : o,
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
    patchFlag: t && e.type !== fe ? a === -1 ? 16 : a | 16 : a,
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
    ssContent: e.ssContent && un(e.ssContent),
    ssFallback: e.ssFallback && un(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && zr(
    d,
    l.clone(d)
  ), d;
}
function K(e = " ", t = 0) {
  return H(mo, null, e, t);
}
function Ur(e, t) {
  const s = H(Er, null, e);
  return s.staticCount = t, s;
}
function te(e = "", t = !1) {
  return t ? (k(), ut(Lt, null, e)) : H(Lt, null, e);
}
function Jt(e) {
  return e == null || typeof e == "boolean" ? H(Lt) : $e(e) ? H(
    fe,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : cn(e) ? ds(e) : H(mo, null, String(e));
}
function ds(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : un(e);
}
function Vr(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if ($e(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), Vr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !Lc(t) ? t._ctx = wt : r === 3 && wt && (wt.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (Ne(t)) {
    if (n & 65) {
      Vr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: wt }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [K(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function Vf(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = Ae([t.class, n.class]));
      else if (r === "style")
        t.style = wn([t.style, n.style]);
      else if (Yr(r)) {
        const o = t[r], a = n[r];
        a && o !== a && !($e(o) && o.includes(a)) ? t[r] = o ? [].concat(o, a) : a : a == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !Xr(r) && (t[r] = a);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function Gt(e, t, s, n = null) {
  Bt(e, t, 7, [
    s,
    n
  ]);
}
const Ff = Pc();
let Kc = 0;
function Wf() {
  return Kc;
}
function Bf(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || Ff, o = {
    uid: Kc++,
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
    scope: new Hl(
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
    propsOptions: Vc(n, r),
    emitsOptions: Nc(n, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: st,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: st,
    data: st,
    props: st,
    attrs: st,
    slots: st,
    refs: st,
    setupState: st,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = xf.bind(null, o), e.ce && e.ce(o), o;
}
let Ct = null;
const Jc = () => Ct || wt;
let Fr, Jn;
{
  const e = ro(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((a) => a(o)) : r[0](o);
    };
  };
  Fr = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => Ct = s
  ), Jn = t(
    "__VUE_SSR_SETTERS__",
    (s) => Qn = s
  );
}
const cr = (e) => {
  const t = Ct;
  return Fr(e), e.scope.on(), () => {
    e.scope.off(), Fr(t);
  };
}, xi = () => {
  Ct && Ct.scope.off(), Fr(null);
};
function Qc(e) {
  return e.vnode.shapeFlag & 4;
}
let Qn = !1;
function qf(e, t = !1, s = !1) {
  t && Jn(t);
  const { props: n, children: r } = e.vnode, o = Qc(e);
  Rf(e, n, o, t), Tf(e, r, s || t);
  const a = o ? Gf(e, t) : void 0;
  return t && Jn(!1), a;
}
function Gf(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, mf);
  const { setup: n } = s;
  if (n) {
    ss();
    const r = e.setupContext = n.length > 1 ? Zf(e) : null, o = cr(e), a = ir(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), i = Ul(a);
    if (ns(), o(), (i || e.sp) && !an(e) && Cc(e), i) {
      if (a.then(xi, xi), t)
        return a.then((l) => {
          Jn(!0);
          try {
            ki(e, l, t);
          } finally {
            Jn(!1);
          }
        }).catch((l) => {
          io(l, e, 0);
        });
      e.asyncDep = a;
    } else
      ki(e, a);
  } else
    Yc(e);
}
function ki(e, t, s) {
  Ne(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : et(t) && (e.setupState = mc(t)), Yc(e);
}
function Yc(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || Xt);
  {
    const r = cr(e);
    ss();
    try {
      pf(e);
    } finally {
      ns(), r();
    }
  }
}
const Hf = {
  get(e, t) {
    return St(e, "get", ""), e[t];
  }
};
function Zf(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Hf),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function po(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(mc(Da(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in Wn)
        return Wn[s](e);
    },
    has(t, s) {
      return s in t || s in Wn;
    }
  })) : e.proxy;
}
function Kf(e, t = !0) {
  return Ne(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function Jf(e) {
  return Ne(e) && "__vccOpts" in e;
}
const ye = (e, t) => /* @__PURE__ */ Ld(e, t, Qn);
function Yn(e, t, s) {
  try {
    Lr(-1);
    const n = arguments.length;
    return n === 2 ? et(t) && !$e(t) ? cn(t) ? H(e, null, [t]) : H(e, t) : H(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && cn(s) && (s = [s]), H(e, t, s));
  } finally {
    Lr(1);
  }
}
const Qf = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let ua;
const Si = typeof window < "u" && window.trustedTypes;
if (Si)
  try {
    ua = /* @__PURE__ */ Si.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const Xc = ua ? (e) => ua.createHTML(e) : (e) => e, Yf = "http://www.w3.org/2000/svg", Xf = "http://www.w3.org/1998/Math/MathML", us = typeof document < "u" ? document : null, Ci = us && /* @__PURE__ */ us.createElement("template"), em = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? us.createElementNS(Yf, e) : t === "mathml" ? us.createElementNS(Xf, e) : s ? us.createElement(e, { is: s }) : us.createElement(e);
    return e === "select" && n && n.multiple != null && r.setAttribute("multiple", n.multiple), r;
  },
  createText: (e) => us.createTextNode(e),
  createComment: (e) => us.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => us.querySelector(e),
  setScopeId(e, t) {
    e.setAttribute(t, "");
  },
  // __UNSAFE__
  // Reason: innerHTML.
  // Static content here can only come from compiled templates.
  // As long as the user only uses trusted templates, this is safe.
  insertStaticContent(e, t, s, n, r, o) {
    const a = s ? s.previousSibling : t.lastChild;
    if (r && (r === o || r.nextSibling))
      for (; t.insertBefore(r.cloneNode(!0), s), !(r === o || !(r = r.nextSibling)); )
        ;
    else {
      Ci.innerHTML = Xc(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const i = Ci.content;
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
}, tm = /* @__PURE__ */ Symbol("_vtc");
function sm(e, t, s) {
  const n = e[tm];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const $i = /* @__PURE__ */ Symbol("_vod"), nm = /* @__PURE__ */ Symbol("_vsh"), rm = /* @__PURE__ */ Symbol(""), om = /(?:^|;)\s*display\s*:/;
function am(e, t, s) {
  const n = e.style, r = ct(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (ct(t))
        for (const a of t.split(";")) {
          const i = a.slice(0, a.indexOf(":")).trim();
          s[i] == null && Mn(n, i, "");
        }
      else
        for (const a in t)
          s[a] == null && Mn(n, a, "");
    for (const a in s) {
      a === "display" && (o = !0);
      const i = s[a];
      i != null ? lm(
        e,
        a,
        !ct(t) && t ? t[a] : void 0,
        i
      ) || Mn(n, a, i) : Mn(n, a, "");
    }
  } else if (r) {
    if (t !== s) {
      const a = n[rm];
      a && (s += ";" + a), n.cssText = s, o = om.test(s);
    }
  } else t && e.removeAttribute("style");
  $i in e && ((!r || t !== s) && (e[$i] = o ? n.display : ""), e[nm] && (n.display = "none"));
}
const vr = /\s*!important$/;
function Mn(e, t, s) {
  if ($e(s))
    s.forEach((n) => Mn(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    vr.test(s) ? e.setProperty(t, s.replace(vr, ""), "important") : e.setProperty(t, s);
  else {
    const n = im(e, t);
    vr.test(s) ? e.setProperty(
      Ls(n),
      s.replace(vr, ""),
      "important"
    ) : e[n] = s;
  }
}
const Ii = ["Webkit", "Moz", "ms"], Oo = {};
function im(e, t) {
  const s = Oo[t];
  if (s)
    return s;
  let n = Et(t);
  if (n !== "filter" && n in e)
    return Oo[t] = n;
  n = so(n);
  for (let r = 0; r < Ii.length; r++) {
    const o = Ii[r] + n;
    if (o in e)
      return Oo[t] = o;
  }
  return t;
}
function lm(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && ct(n) && s === n;
}
const Ri = "http://www.w3.org/1999/xlink";
function Ai(e, t, s, n, r, o = dd(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(Ri, t.slice(6, t.length)) : e.setAttributeNS(Ri, t, s) : s == null || o && !Bl(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : jt(s) ? String(s) : s
  );
}
function Ei(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? Xc(s) : s);
    return;
  }
  const o = e.tagName;
  if (t === "value" && o !== "PROGRESS" && // custom elements may use _value internally
  !o.includes("-")) {
    const i = o === "OPTION" ? e.getAttribute("value") || "" : e.value, l = s == null ? (
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
    i === "boolean" ? s = Bl(s) : s == null && i === "string" ? (s = "", a = !0) : i === "number" && (s = 0, a = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  a && e.removeAttribute(r || t);
}
function Ts(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function cm(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const Oi = /* @__PURE__ */ Symbol("_vei");
function um(e, t, s, n, r = null) {
  const o = e[Oi] || (e[Oi] = {}), a = o[t];
  if (n && a)
    a.value = n;
  else {
    const [i, l] = mm(t);
    if (n) {
      const c = o[t] = gm(
        n,
        r
      );
      Ts(e, i, c, l);
    } else a && (cm(e, i, a, l), o[t] = void 0);
  }
}
const dm = /(Once|Passive|Capture)$/, fm = /^on:?(?:Once|Passive|Capture)$/;
function mm(e) {
  let t, s;
  for (; (s = e.match(dm)) && !fm.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Ls(e.slice(2)), t];
}
let To = 0;
const pm = /* @__PURE__ */ Promise.resolve(), hm = () => To || (pm.then(() => To = 0), To = Date.now());
function gm(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if ($e(r)) {
      const o = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        o.call(n), n._stopped = !0;
      };
      const a = r.slice(), i = [n];
      for (let l = 0; l < a.length && !n._stopped; l++) {
        const c = a[l];
        c && Bt(
          c,
          t,
          5,
          i
        );
      }
    } else
      Bt(
        r,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = hm(), s;
}
const Ti = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, vm = (e, t, s, n, r, o) => {
  const a = r === "svg";
  t === "class" ? sm(e, n, a) : t === "style" ? am(e, s, n) : Yr(t) ? Xr(t) || um(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : ym(e, t, n, a)) ? (Ei(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && Ai(e, t, n, a, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (bm(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !ct(n))) ? Ei(e, Et(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), Ai(e, t, n, a));
};
function ym(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && Ti(t) && Ne(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return Ti(t) && ct(s) ? !1 : t in e;
}
function bm(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = Et(t);
  return Array.isArray(s) ? s.some((r) => Et(r) === n) : Object.keys(s).some((r) => Et(r) === n);
}
const dn = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return $e(t) ? (s) => Rr(t, s) : t;
};
function wm(e) {
  e.target.composing = !0;
}
function Pi(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const Yt = /* @__PURE__ */ Symbol("_assign"), yr = /* @__PURE__ */ Symbol("_initialValue");
function Po(e, t, s) {
  return t && (e = e.trim()), s && (e = no(e)), e;
}
const lt = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[yr] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[yr] = e.defaultValue.replace(/\r\n?/g, `
`))), e[Yt] = dn(r);
    const o = n || r.props && r.props.type === "number";
    Ts(e, t ? "change" : "input", (a) => {
      a.target.composing || e[Yt](Po(e.value, s, o));
    }), (s || o) && Ts(e, "change", () => {
      e.value = Po(e.value, s, o);
    }), t || (Ts(e, "compositionstart", wm), Ts(e, "compositionend", Pi), Ts(e, "change", Pi));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[yr];
    delete e[yr], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[Yt](Po(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, a) {
    if (e[Yt] = dn(a), e.composing) return;
    const i = (o || e.type === "number") && !/^0\d/.test(e.value) ? no(e.value) : e.value, l = t ?? "";
    if (i === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, ln = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[Yt] = dn(s), Ts(e, "change", () => {
      const n = e._modelValue, r = Xn(e), o = e.checked, a = e[Yt];
      if ($e(n)) {
        const i = Oa(n, r), l = i !== -1;
        if (o && !l)
          a(n.concat(r));
        else if (!o && l) {
          const c = [...n];
          c.splice(i, 1), a(c);
        }
      } else if (ys(n)) {
        const i = new Set(n);
        o ? i.add(r) : i.delete(r), a(i);
      } else
        a(eu(e, o));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: Ni,
  beforeUpdate(e, t, s) {
    e[Yt] = dn(s), Ni(e, t, s);
  }
};
function Ni(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let r;
  if ($e(t))
    r = Oa(t, n.props.value) > -1;
  else if (ys(t))
    r = t.has(n.props.value);
  else {
    if (t === s) return;
    r = bs(t, eu(e, !0));
  }
  e.checked !== r && (e.checked = r);
}
const ps = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, Ts(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? no(Xn(l)) : Xn(l)
      ), o = e.multiple, a = o ? ys(e._modelValue) ? new Set(r) : r : r[0], i = e._pendingValue = [
        o,
        o ? $e(a) ? r.slice() : r : a
      ];
      try {
        e[Yt](a);
      } finally {
        lr(() => {
          e._pendingValue === i && (e._pendingValue = void 0);
        });
      }
    }), e[Yt] = dn(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    Mi(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[Yt] = dn(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !_m(t, s[1], s[0])) && Mi(e, t);
  }
};
function _m(e, t, s) {
  if (!s || $e(e)) return bs(e, t);
  if (ys(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function Mi(e, t) {
  const s = e.multiple, n = $e(t);
  if (!(s && !n && !ys(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const a = e.options[r], i = Xn(a);
      if (s)
        if (n) {
          const l = typeof i;
          l === "string" || l === "number" ? a.selected = t.some((c) => String(c) === String(i)) : a.selected = Oa(t, i) > -1;
        } else
          a.selected = t.has(i);
      else if (bs(Xn(a), t)) {
        e.selectedIndex !== r && (e.selectedIndex = r);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function Xn(e) {
  return "_value" in e ? e._value : e.value;
}
function eu(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const xm = ["ctrl", "shift", "alt", "meta"], km = {
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
  exact: (e, t) => xm.some((s) => e[`${s}Key`] && !t.includes(s))
}, er = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((r, ...o) => {
    for (let a = 0; a < t.length; a++) {
      const i = km[t[a]];
      if (i && i(r, t)) return;
    }
    return e(r, ...o);
  }));
}, Sm = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
}, zs = (e, t) => {
  const s = e._withKeys || (e._withKeys = {}), n = t.join(".");
  return s[n] || (s[n] = ((r) => {
    if (!("key" in r))
      return;
    const o = Ls(r.key);
    if (t.some(
      (a) => a === o || Sm[a] === o
    ))
      return e(r);
  }));
}, Cm = /* @__PURE__ */ _t({ patchProp: vm }, em);
let zi;
function $m() {
  return zi || (zi = Nf(Cm));
}
const Im = ((...e) => {
  const t = $m().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = Am(n);
    if (!r) return;
    const o = t._component;
    !Ne(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const a = s(r, !1, Rm(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), a;
  }, t;
});
function Rm(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function Am(e) {
  return ct(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let tu;
const ho = (e) => tu = e, su = (
  /* istanbul ignore next */
  Symbol()
);
function da(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var Bn;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(Bn || (Bn = {}));
function Em() {
  const e = Zl(!0), t = e.run(() => /* @__PURE__ */ T({}));
  let s = [], n = [];
  const r = Da({
    install(o) {
      ho(r), r._a = o, o.provide(su, r), o.config.globalProperties.$pinia = r, n.forEach((a) => s.push(a)), n = [];
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
const nu = () => {
};
function ji(e, t, s, n = nu) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && Kl() && pd(r), r;
}
function en(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const Om = (e) => e(), Di = Symbol(), No = Symbol();
function fa(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    da(r) && da(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ ft(n) && !/* @__PURE__ */ es(n) ? e[s] = fa(r, n) : e[s] = n;
  }
  return e;
}
const Tm = (
  /* istanbul ignore next */
  Symbol()
);
function Pm(e) {
  return !da(e) || !Object.prototype.hasOwnProperty.call(e, Tm);
}
const { assign: Rs } = Object;
function Nm(e) {
  return !!(/* @__PURE__ */ ft(e) && e.effect);
}
function Mm(e, t, s, n) {
  const { state: r, actions: o, getters: a } = t, i = s.state.value[e];
  let l;
  function c() {
    i || (s.state.value[e] = r ? r() : {});
    const d = /* @__PURE__ */ Md(s.state.value[e]);
    return Rs(d, o, Object.keys(a || {}).reduce((f, y) => (f[y] = Da(ye(() => {
      ho(s);
      const v = s._s.get(e);
      return a[y].call(v, v);
    })), f), {}));
  }
  return l = ru(e, c, t, s, n, !0), l;
}
function ru(e, t, s = {}, n, r, o) {
  let a;
  const i = Rs({ actions: {} }, s), l = { deep: !0 };
  let c, d, f = /* @__PURE__ */ new Set(), y = /* @__PURE__ */ new Set(), v;
  const A = n.state.value[e];
  !o && !A && (n.state.value[e] = {});
  let b;
  function w(M) {
    let C;
    c = d = !1, typeof M == "function" ? (M(n.state.value[e]), C = {
      type: Bn.patchFunction,
      storeId: e,
      events: v
    }) : (fa(n.state.value[e], M), C = {
      type: Bn.patchObject,
      payload: M,
      storeId: e,
      events: v
    });
    const F = b = Symbol();
    lr().then(() => {
      b === F && (c = !0);
    }), d = !0, en(f, C, n.state.value[e]);
  }
  const O = o ? function() {
    const { state: C } = s, F = C ? C() : {};
    this.$patch((Se) => {
      Rs(Se, F);
    });
  } : (
    /* istanbul ignore next */
    nu
  );
  function I() {
    a.stop(), f.clear(), y.clear(), n._s.delete(e);
  }
  const V = (M, C = "") => {
    if (Di in M)
      return M[No] = C, M;
    const F = function() {
      ho(n);
      const Se = Array.from(arguments), Ce = /* @__PURE__ */ new Set(), Me = /* @__PURE__ */ new Set();
      function He(E) {
        Ce.add(E);
      }
      function ue(E) {
        Me.add(E);
      }
      en(y, {
        args: Se,
        name: F[No],
        store: J,
        after: He,
        onError: ue
      });
      let W;
      try {
        W = M.apply(this && this.$id === e ? this : J, Se);
      } catch (E) {
        throw en(Me, E), E;
      }
      return W instanceof Promise ? W.then((E) => (en(Ce, E), E)).catch((E) => (en(Me, E), Promise.reject(E))) : (en(Ce, W), W);
    };
    return F[Di] = !0, F[No] = C, F;
  }, R = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: ji.bind(null, y),
    $patch: w,
    $reset: O,
    $subscribe(M, C = {}) {
      const F = ji(f, M, C.detached, () => Se()), Se = a.run(() => Wt(() => n.state.value[e], (Ce) => {
        (C.flush === "sync" ? d : c) && M({
          storeId: e,
          type: Bn.direct,
          events: v
        }, Ce);
      }, Rs({}, l, C)));
      return F;
    },
    $dispose: I
  }, J = /* @__PURE__ */ ar(R);
  n._s.set(e, J);
  const ee = (n._a && n._a.runWithContext || Om)(() => n._e.run(() => (a = Zl()).run(() => t({ action: V }))));
  for (const M in ee) {
    const C = ee[M];
    if (/* @__PURE__ */ ft(C) && !Nm(C) || /* @__PURE__ */ es(C))
      o || (A && Pm(C) && (/* @__PURE__ */ ft(C) ? C.value = A[M] : fa(C, A[M])), n.state.value[e][M] = C);
    else if (typeof C == "function") {
      const F = V(C, M);
      ee[M] = F, i.actions[M] = C;
    }
  }
  return Rs(J, ee), Rs(/* @__PURE__ */ Je(J), ee), Object.defineProperty(J, "$state", {
    get: () => n.state.value[e],
    set: (M) => {
      w((C) => {
        Rs(C, M);
      });
    }
  }), n._p.forEach((M) => {
    Rs(J, a.run(() => M({
      store: J,
      app: n._a,
      pinia: n,
      options: i
    })));
  }), A && o && s.hydrate && s.hydrate(J.$state, A), c = !0, d = !0, J;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function _n(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(a, i) {
    const l = Gd();
    return a = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    a || (l ? zt(su, null) : null), a && ho(a), a = tu, a._s.has(e) || (r ? ru(e, t, n, a) : Mm(e, n, a)), a._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const rn = typeof document < "u";
function ou(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function zm(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && ou(e.default);
}
const rt = Object.assign;
function Mo(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = qt(r) ? r.map(e) : e(r);
  }
  return s;
}
const qn = () => {
}, qt = Array.isArray;
function Li(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const au = /#/g, jm = /&/g, Dm = /\//g, Lm = /=/g, Um = /\?/g, iu = /\+/g, Vm = /%5B/g, Fm = /%5D/g, lu = /%5E/g, Wm = /%60/g, cu = /%7B/g, Bm = /%7C/g, uu = /%7D/g, qm = /%20/g;
function qa(e) {
  return e == null ? "" : encodeURI("" + e).replace(Bm, "|").replace(Vm, "[").replace(Fm, "]");
}
function Gm(e) {
  return qa(e).replace(cu, "{").replace(uu, "}").replace(lu, "^");
}
function ma(e) {
  return qa(e).replace(iu, "%2B").replace(qm, "+").replace(au, "%23").replace(jm, "%26").replace(Wm, "`").replace(cu, "{").replace(uu, "}").replace(lu, "^");
}
function Hm(e) {
  return ma(e).replace(Lm, "%3D");
}
function Zm(e) {
  return qa(e).replace(au, "%23").replace(Um, "%3F");
}
function Km(e) {
  return Zm(e).replace(Dm, "%2F");
}
function tr(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const Jm = /\/$/, Qm = (e) => e.replace(Jm, "");
function zo(e, t, s = "/") {
  let n, r = {}, o = "", a = "";
  const i = t.indexOf("#");
  let l = t.indexOf("?");
  return l = i >= 0 && l > i ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, i > 0 ? i : t.length), r = e(o.slice(1))), i >= 0 && (n = n || t.slice(0, i), a = t.slice(i, t.length)), n = tp(n ?? t, s), {
    fullPath: n + o + a,
    path: n,
    query: r,
    hash: tr(a)
  };
}
function Ym(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Xm(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && fn(t.matched[n], s.matched[r]) && du(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function fn(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function du(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!ep(e[s], t[s])) return !1;
  return !0;
}
function ep(e, t) {
  return qt(e) ? Ui(e, t) : qt(t) ? Ui(t, e) : e?.valueOf() === t?.valueOf();
}
function Ui(e, t) {
  return qt(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function tp(e, t) {
  if (e.startsWith("/")) return e;
  if (!e) return t;
  const s = t.split("/"), n = e.split("/"), r = n[n.length - 1];
  (r === ".." || r === ".") && n.push("");
  let o = s.length - 1, a, i;
  for (a = 0; a < n.length; a++)
    if (i = n[a], i !== ".")
      if (i === "..")
        o > 1 && o--;
      else break;
  return s.slice(0, o).join("/") + "/" + n.slice(a).join("/");
}
const Ss = {
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
let pa = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), Vi = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const jo = "";
function sp(e) {
  if (!e) if (rn) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), Qm(e);
}
const np = /^[^#]+#/;
function rp(e, t) {
  return e.replace(np, "#") + t;
}
function op(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const ap = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function ip(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = op(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function Fi(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const ha = /* @__PURE__ */ new Map();
function lp(e, t) {
  ha.set(e, t);
}
function cp(e) {
  const t = ha.get(e);
  return ha.delete(e), t;
}
function up(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function fu(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let dt = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const mu = Symbol("");
dt.MATCHER_NOT_FOUND + "", dt.NAVIGATION_GUARD_REDIRECT + "", dt.NAVIGATION_ABORTED + "", dt.NAVIGATION_CANCELLED + "", dt.NAVIGATION_DUPLICATED + "";
function mn(e, t) {
  return rt(/* @__PURE__ */ new Error(), {
    type: e,
    [mu]: !0
  }, t);
}
function is(e, t) {
  return e instanceof Error && mu in e && (t == null || !!(e.type & t));
}
const dp = [
  "params",
  "query",
  "hash"
];
function fp(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of dp) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function mp(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(iu, " "), o = r.indexOf("="), a = tr(o < 0 ? r : r.slice(0, o)), i = o < 0 ? null : tr(r.slice(o + 1));
    if (a in t) {
      let l = t[a];
      qt(l) || (l = t[a] = [l]), l.push(i);
    } else t[a] = i;
  }
  return t;
}
function Wi(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Hm(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (qt(n) ? n.map((r) => r && ma(r)) : [n && ma(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function pp(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = qt(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const hp = Symbol(""), Bi = Symbol(""), go = Symbol(""), Ga = Symbol(""), ga = Symbol("");
function $n() {
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
function Es(e, t, s, n, r, o = (a) => a()) {
  const a = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((i, l) => {
    const c = (y) => {
      y === !1 ? l(mn(dt.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : y instanceof Error ? l(y) : up(y) ? l(mn(dt.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: y
      })) : (a && n.enterCallbacks[r] === a && typeof y == "function" && a.push(y), i());
    }, d = o(() => e.call(n && n.instances[r], t, s, c));
    let f = Promise.resolve(d);
    e.length < 3 && (f = f.then(c)), f.catch((y) => l(y));
  });
}
function Do(e, t, s, n, r = (o) => o()) {
  const o = [];
  for (const a of e)
    for (const i in a.components) {
      let l = a.components[i];
      if (!(t !== "beforeRouteEnter" && !a.instances[i]))
        if (ou(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(Es(c, s, n, a, i, r));
        } else {
          let c = l();
          o.push(() => c.then((d) => {
            if (!d) throw new Error(`Couldn't resolve component "${i}" at "${a.path}"`);
            const f = zm(d) ? d.default : d;
            a.mods[i] = d, a.components[i] = f;
            const y = (f.__vccOpts || f)[t];
            return y && Es(y, s, n, a, i, r)();
          }));
        }
    }
  return o;
}
function gp(e, t) {
  const s = [], n = [], r = [], o = Math.max(t.matched.length, e.matched.length);
  for (let a = 0; a < o; a++) {
    const i = t.matched[a];
    i && (e.matched.find((c) => fn(c, i)) ? n.push(i) : s.push(i));
    const l = e.matched[a];
    l && (t.matched.find((c) => fn(c, l)) || r.push(l));
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
function vp(e = "") {
  let t = [], s = [[jo, {}]], n = 0;
  e = sp(e);
  function r(i, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([i, l]);
  }
  function o(i, l, { direction: c, delta: d }) {
    const f = {
      direction: c,
      delta: d,
      type: pa.pop
    };
    for (const y of t) y(i, l, f);
  }
  const a = {
    location: jo,
    state: {},
    base: e,
    createHref: rp.bind(null, e),
    replace(i, l) {
      s.splice(n--, 1), r(i, l);
    },
    push(i, l) {
      r(i, l);
    },
    listen(i) {
      return t.push(i), () => {
        const l = t.indexOf(i);
        l > -1 && t.splice(l, 1);
      };
    },
    destroy() {
      t = [], s = [[jo, {}]], n = 0;
    },
    go(i, l = !0) {
      const c = this.location, d = i < 0 ? Vi.back : Vi.forward;
      n = Math.max(0, Math.min(n + i, s.length - 1)), l && o(this.location, c, {
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
let Zs = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var vt = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(vt || {});
const yp = {
  type: Zs.Static,
  value: ""
}, bp = /[a-zA-Z0-9_]/;
function wp(e) {
  if (!e) return [[]];
  if (e === "/") return [[yp]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(v) {
    throw new Error(`ERR (${s})/"${c}": ${v}`);
  }
  let s = vt.Static, n = s;
  const r = [];
  let o;
  function a() {
    o && r.push(o), o = [];
  }
  let i = 0, l, c = "", d = "";
  function f() {
    c && (s === vt.Static ? o.push({
      type: Zs.Static,
      value: c
    }) : s === vt.Param || s === vt.ParamRegExp || s === vt.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: Zs.Param,
      value: c,
      regexp: d,
      repeatable: l === "*" || l === "+",
      optional: l === "*" || l === "?"
    })) : t("Invalid state to consume buffer"), c = "");
  }
  function y() {
    c += l;
  }
  for (; i < e.length; ) {
    if (l = e[i++], l === "\\" && s !== vt.ParamRegExp) {
      n = s, s = vt.EscapeNext;
      continue;
    }
    switch (s) {
      case vt.Static:
        l === "/" ? (c && f(), a()) : l === ":" ? (f(), s = vt.Param) : y();
        break;
      case vt.EscapeNext:
        y(), s = n;
        break;
      case vt.Param:
        l === "(" ? s = vt.ParamRegExp : bp.test(l) ? y() : (f(), s = vt.Static, l !== "*" && l !== "?" && l !== "+" && i--);
        break;
      case vt.ParamRegExp:
        l === ")" ? d[d.length - 1] == "\\" ? d = d.slice(0, -1) + l : s = vt.ParamRegExpEnd : d += l;
        break;
      case vt.ParamRegExpEnd:
        f(), s = vt.Static, l !== "*" && l !== "?" && l !== "+" && i--, d = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === vt.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), f(), a(), r;
}
const qi = "[^/]+?", _p = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var Rt = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(Rt || {});
const xp = /[.+*?^${}()[\]/\\]/g;
function kp(e, t) {
  const s = rt({}, _p, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const d = c.length ? [] : [Rt.Root];
    s.strict && !c.length && (r += "/");
    for (let f = 0; f < c.length; f++) {
      const y = c[f];
      let v = Rt.Segment + (s.sensitive ? Rt.BonusCaseSensitive : 0);
      if (y.type === Zs.Static)
        f || (r += "/"), r += y.value.replace(xp, "\\$&"), v += Rt.Static;
      else if (y.type === Zs.Param) {
        const { value: A, repeatable: b, optional: w, regexp: O } = y;
        o.push({
          name: A,
          repeatable: b,
          optional: w
        });
        const I = O || qi;
        if (I !== qi) {
          v += Rt.BonusCustomRegExp;
          try {
            `${I}`;
          } catch (R) {
            throw new Error(`Invalid custom RegExp for param "${A}" (${I}): ` + R.message);
          }
        }
        let V = b ? `((?:${I})(?:/(?:${I}))*)` : `(${I})`;
        f || (V = w && c.length < 2 ? `(?:/${V})` : "/" + V), w && (V += "?"), r += V, v += Rt.Dynamic, w && (v += Rt.BonusOptional), b && (v += Rt.BonusRepeatable), I === ".*" && (v += Rt.BonusWildcard);
      }
      d.push(v);
    }
    n.push(d);
  }
  if (s.strict && s.end) {
    const c = n.length - 1;
    n[c][n[c].length - 1] += Rt.BonusStrict;
  }
  s.strict || (r += "/?"), s.end ? r += "$" : s.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const a = new RegExp(r, s.sensitive ? "" : "i");
  function i(c) {
    const d = c.match(a), f = {};
    if (!d) return null;
    for (let y = 1; y < d.length; y++) {
      const v = d[y] || "", A = o[y - 1];
      f[A.name] = v && A.repeatable ? v.split("/") : v;
    }
    return f;
  }
  function l(c) {
    let d = "", f = !1;
    for (const y of e) {
      (!f || !d.endsWith("/")) && (d += "/"), f = !1;
      for (const v of y) if (v.type === Zs.Static) d += v.value;
      else if (v.type === Zs.Param) {
        const { value: A, repeatable: b, optional: w } = v, O = A in c ? c[A] : "";
        if (qt(O) && !b) throw new Error(`Provided param "${A}" is an array but it is not repeatable (* or + modifiers)`);
        const I = qt(O) ? O.join("/") : O;
        if (!I) if (w)
          y.length < 2 && (d.endsWith("/") ? d = d.slice(0, -1) : f = !0);
        else throw new Error(`Missing required param "${A}"`);
        d += I;
      }
    }
    return d || "/";
  }
  return {
    re: a,
    score: n,
    keys: o,
    parse: i,
    stringify: l
  };
}
function Sp(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === Rt.Static + Rt.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === Rt.Static + Rt.Segment ? 1 : -1 : 0;
}
function pu(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = Sp(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (Gi(n)) return 1;
    if (Gi(r)) return -1;
  }
  return r.length - n.length;
}
function Gi(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const Cp = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function $p(e, t, s) {
  const n = kp(wp(e.path), s), r = rt(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function Ip(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = Li(Cp, t);
  function r(f) {
    return n.get(f);
  }
  function o(f, y, v) {
    const A = !v, b = Zi(f);
    b.aliasOf = v && v.record;
    const w = Li(t, f), O = [b];
    if ("alias" in f) {
      const R = typeof f.alias == "string" ? [f.alias] : f.alias;
      for (const J of R) O.push(Zi(rt({}, b, {
        components: v ? v.record.components : b.components,
        path: J,
        aliasOf: v ? v.record : b
      })));
    }
    let I, V;
    for (const R of O) {
      const { path: J } = R;
      if (y && J[0] !== "/") {
        const be = y.record.path, ee = be[be.length - 1] === "/" ? "" : "/";
        R.path = y.record.path + (J && ee + J);
      }
      if (I = $p(R, y, w), v ? v.alias.push(I) : (V = V || I, V !== I && V.alias.push(I), A && f.name && !Ki(I) && a(f.name)), hu(I) && l(I), b.children) {
        const be = b.children;
        for (let ee = 0; ee < be.length; ee++) o(be[ee], I, v && v.children[ee]);
      }
      v = v || I;
    }
    return V ? () => {
      a(V);
    } : qn;
  }
  function a(f) {
    if (fu(f)) {
      const y = n.get(f);
      y && (n.delete(f), s.splice(s.indexOf(y), 1), y.children.forEach(a), y.alias.forEach(a));
    } else {
      const y = s.indexOf(f);
      y > -1 && (s.splice(y, 1), f.record.name && n.delete(f.record.name), f.children.forEach(a), f.alias.forEach(a));
    }
  }
  function i() {
    return s;
  }
  function l(f) {
    const y = Ep(f, s);
    s.splice(y, 0, f), f.record.name && !Ki(f) && n.set(f.record.name, f);
  }
  function c(f, y) {
    let v, A = {}, b, w;
    if ("name" in f && f.name) {
      if (v = n.get(f.name), !v) throw mn(dt.MATCHER_NOT_FOUND, { location: f });
      w = v.record.name, A = rt(Hi(y.params, v.keys.filter((V) => !V.optional).concat(v.parent ? v.parent.keys.filter((V) => V.optional) : []).map((V) => V.name)), f.params && Hi(f.params, v.keys.map((V) => V.name))), b = v.stringify(A);
    } else if (f.path != null)
      b = f.path, v = s.find((V) => V.re.test(b)), v && (A = v.parse(b), w = v.record.name);
    else {
      if (v = y.name ? n.get(y.name) : s.find((V) => V.re.test(y.path)), !v) throw mn(dt.MATCHER_NOT_FOUND, {
        location: f,
        currentLocation: y
      });
      w = v.record.name, A = rt({}, y.params, f.params), b = v.stringify(A);
    }
    const O = [];
    let I = v;
    for (; I; )
      O.unshift(I.record), I = I.parent;
    return {
      name: w,
      path: b,
      params: A,
      matched: O,
      meta: Ap(O)
    };
  }
  e.forEach((f) => o(f));
  function d() {
    s.length = 0, n.clear();
  }
  return {
    addRoute: o,
    resolve: c,
    removeRoute: a,
    clearRoutes: d,
    getRoutes: i,
    getRecordMatcher: r
  };
}
function Hi(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function Zi(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: Rp(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function Rp(e) {
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
function Ap(e) {
  return e.reduce((t, s) => rt(t, s.meta), {});
}
function Ep(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    pu(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = Op(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function Op(e) {
  let t = e;
  for (; t = t.parent; ) if (hu(t) && pu(e, t) === 0) return t;
}
function hu({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function Ji(e) {
  const t = zt(go), s = zt(Ga), n = ye(() => {
    const l = p(e.to);
    return t.resolve(l);
  }), r = ye(() => {
    const { matched: l } = n.value, { length: c } = l, d = l[c - 1], f = s.matched;
    if (!d || !f.length) return -1;
    const y = f.findIndex(fn.bind(null, d));
    if (y > -1) return y;
    const v = Qi(l[c - 2]);
    return c > 1 && Qi(d) === v && f[f.length - 1].path !== v ? f.findIndex(fn.bind(null, l[c - 2])) : y;
  }), o = ye(() => r.value > -1 && Mp(s.params, n.value.params)), a = ye(() => r.value > -1 && r.value === s.matched.length - 1 && du(s.params, n.value.params));
  function i(l = {}) {
    if (Np(l)) {
      const c = t[p(e.replace) ? "replace" : "push"](p(e.to)).catch(qn);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: ye(() => n.value.href),
    isActive: o,
    isExactActive: a,
    navigate: i
  };
}
function Tp(e) {
  return e.length === 1 ? e[0] : e;
}
const Pp = /* @__PURE__ */ xt({
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
    const s = /* @__PURE__ */ ar(Ji(e)), { options: n } = zt(go), r = ye(() => ({
      [Yi(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [Yi(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && Tp(t.default(s));
      return e.custom ? o : Yn("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), va = Pp;
function Np(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function Mp(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!qt(r) || r.length !== n.length || n.some((o, a) => o.valueOf() !== r[a].valueOf())) return !1;
  }
  return !0;
}
function Qi(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const Yi = (e, t, s) => e ?? t ?? s, zp = /* @__PURE__ */ xt({
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
    const n = zt(ga), r = ye(() => e.route || n.value), o = zt(Bi, 0), a = ye(() => {
      let c = p(o);
      const { matched: d } = r.value;
      let f;
      for (; (f = d[c]) && !f.components; ) c++;
      return c;
    }), i = ye(() => r.value.matched[a.value]);
    Ar(Bi, ye(() => a.value + 1)), Ar(hp, i), Ar(ga, r);
    const l = /* @__PURE__ */ T();
    return Wt(() => [
      l.value,
      i.value,
      e.name
    ], ([c, d, f], [y, v, A]) => {
      d && (d.instances[f] = c, v && v !== d && c && c === y && (d.leaveGuards.size || (d.leaveGuards = v.leaveGuards), d.updateGuards.size || (d.updateGuards = v.updateGuards))), c && d && (!v || !fn(d, v) || !y) && (d.enterCallbacks[f] || []).forEach((b) => b(c));
    }, { flush: "post" }), () => {
      const c = r.value, d = e.name, f = i.value, y = f && f.components[d];
      if (!y) return Xi(s.default, {
        Component: y,
        route: c
      });
      const v = f.props[d], A = v ? v === !0 ? c.params : typeof v == "function" ? v(c) : v : null, w = Yn(y, rt({}, A, t, {
        onVnodeUnmounted: (O) => {
          O.component.isUnmounted && (f.instances[d] = null);
        },
        ref: l
      }));
      return Xi(s.default, {
        Component: w,
        route: c
      }) || w;
    };
  }
});
function Xi(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const gu = zp;
function jp(e) {
  const t = Ip(e.routes, e), s = e.parseQuery || mp, n = e.stringifyQuery || Wi, r = e.history, o = $n(), a = $n(), i = $n(), l = /* @__PURE__ */ Td(Ss);
  let c = Ss;
  rn && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const d = Mo.bind(null, (q) => "" + q), f = Mo.bind(null, Km), y = Mo.bind(null, tr);
  function v(q, j) {
    let D, le;
    return fu(q) ? (D = t.getRecordMatcher(q), le = j) : le = q, t.addRoute(le, D);
  }
  function A(q) {
    const j = t.getRecordMatcher(q);
    j && t.removeRoute(j);
  }
  function b() {
    return t.getRoutes().map((q) => q.record);
  }
  function w(q) {
    return !!t.getRecordMatcher(q);
  }
  function O(q, j) {
    if (j = rt({}, j || l.value), typeof q == "string") {
      const z = zo(s, q, j.path), $ = t.resolve({ path: z.path }, j), m = r.createHref(z.fullPath);
      return rt(z, $, {
        params: y($.params),
        hash: tr(z.hash),
        redirectedFrom: void 0,
        href: m
      });
    }
    let D;
    if (q.path != null)
      D = rt({}, q, { path: zo(s, q.path, j.path).path });
    else {
      const z = rt({}, q.params);
      for (const $ in z) z[$] == null && delete z[$];
      D = rt({}, q, { params: f(z) }), j.params = f(j.params);
    }
    const le = t.resolve(D, j), g = q.hash || "";
    le.params = d(y(le.params));
    const x = Ym(n, rt({}, q, {
      hash: Gm(g),
      path: le.path
    })), P = r.createHref(x);
    return rt({
      fullPath: x,
      hash: g,
      query: n === Wi ? pp(q.query) : q.query || {}
    }, le, {
      redirectedFrom: void 0,
      href: P
    });
  }
  function I(q) {
    return typeof q == "string" ? zo(s, q, l.value.path) : rt({}, q);
  }
  function V(q, j) {
    if (c !== q) return mn(dt.NAVIGATION_CANCELLED, {
      from: j,
      to: q
    });
  }
  function R(q) {
    return ee(q);
  }
  function J(q) {
    return R(rt(I(q), { replace: !0 }));
  }
  function be(q, j) {
    const D = q.matched[q.matched.length - 1];
    if (D && D.redirect) {
      const { redirect: le } = D;
      let g = typeof le == "function" ? le(q, j) : le;
      return typeof g == "string" && (g = g.includes("?") || g.includes("#") ? g = I(g) : { path: g }, g.params = {}), rt({
        query: q.query,
        hash: q.hash,
        params: g.path != null ? {} : q.params
      }, g);
    }
  }
  function ee(q, j) {
    const D = c = O(q), le = l.value, g = q.state, x = q.force, P = q.replace === !0, z = be(D, le);
    if (z) return ee(rt(I(z), {
      state: typeof z == "object" ? rt({}, g, z.state) : g,
      force: x,
      replace: P
    }), j || D);
    const $ = D;
    $.redirectedFrom = j;
    let m;
    return !x && Xm(n, le, D) && (m = mn(dt.NAVIGATION_DUPLICATED, {
      to: $,
      from: le
    }), Xe(le, le, !0, !1)), (m ? Promise.resolve(m) : F($, le)).catch((h) => is(h) ? is(h, dt.NAVIGATION_GUARD_REDIRECT) ? h : ne(h) : _(h, $, le)).then((h) => {
      if (h) {
        if (is(h, dt.NAVIGATION_GUARD_REDIRECT))
          return ee(rt({ replace: P }, I(h.to), {
            state: typeof h.to == "object" ? rt({}, g, h.to.state) : g,
            force: x
          }), j || $);
      } else h = Ce($, le, !0, P, g);
      return Se($, le, h), h;
    });
  }
  function M(q, j) {
    const D = V(q, j);
    return D ? Promise.reject(D) : Promise.resolve();
  }
  function C(q) {
    const j = at.values().next().value;
    return j && typeof j.runWithContext == "function" ? j.runWithContext(q) : q();
  }
  function F(q, j) {
    let D;
    const [le, g, x] = gp(q, j);
    D = Do(le.reverse(), "beforeRouteLeave", q, j);
    for (const z of le) z.leaveGuards.forEach(($) => {
      D.push(Es($, q, j));
    });
    const P = M.bind(null, q, j);
    return D.push(P), Oe(D).then(() => {
      D = [];
      for (const z of o.list()) D.push(Es(z, q, j));
      return D.push(P), Oe(D);
    }).then(() => {
      D = Do(g, "beforeRouteUpdate", q, j);
      for (const z of g) z.updateGuards.forEach(($) => {
        D.push(Es($, q, j));
      });
      return D.push(P), Oe(D);
    }).then(() => {
      D = [];
      for (const z of x) if (z.beforeEnter) if (qt(z.beforeEnter)) for (const $ of z.beforeEnter) D.push(Es($, q, j));
      else D.push(Es(z.beforeEnter, q, j));
      return D.push(P), Oe(D);
    }).then(() => (q.matched.forEach((z) => z.enterCallbacks = {}), D = Do(x, "beforeRouteEnter", q, j, C), D.push(P), Oe(D))).then(() => {
      D = [];
      for (const z of a.list()) D.push(Es(z, q, j));
      return D.push(P), Oe(D);
    }).catch((z) => is(z, dt.NAVIGATION_CANCELLED) ? z : Promise.reject(z));
  }
  function Se(q, j, D) {
    i.list().forEach((le) => C(() => le(q, j, D)));
  }
  function Ce(q, j, D, le, g) {
    const x = V(q, j);
    if (x) return x;
    const P = j === Ss, z = rn ? history.state : {};
    D && (le || P ? r.replace(q.fullPath, rt({ scroll: P && z && z.scroll }, g)) : r.push(q.fullPath, g)), l.value = q, Xe(q, j, D, P), ne();
  }
  let Me;
  function He() {
    Me || (Me = r.listen((q, j, D) => {
      if (!We.listening) return;
      const le = O(q), g = be(le, We.currentRoute.value);
      if (g) {
        ee(rt(g, {
          replace: !0,
          force: !0
        }), le).catch(qn);
        return;
      }
      c = le;
      const x = l.value;
      rn && lp(Fi(x.fullPath, D.delta), ap()), F(le, x).catch((P) => is(P, dt.NAVIGATION_ABORTED | dt.NAVIGATION_CANCELLED) ? P : is(P, dt.NAVIGATION_GUARD_REDIRECT) ? (ee(rt(I(P.to), { force: !0 }), le).then((z) => {
        is(z, dt.NAVIGATION_ABORTED | dt.NAVIGATION_DUPLICATED) && !D.delta && D.type === pa.pop && r.go(-1, !1);
      }).catch(qn), Promise.reject()) : (D.delta && r.go(-D.delta, !1), _(P, le, x))).then((P) => {
        P = P || Ce(le, x, !1), P && (D.delta && !is(P, dt.NAVIGATION_CANCELLED) ? r.go(-D.delta, !1) : D.type === pa.pop && is(P, dt.NAVIGATION_ABORTED | dt.NAVIGATION_DUPLICATED) && r.go(-1, !1)), Se(le, x, P);
      }).catch(qn);
    }));
  }
  let ue = $n(), W = $n(), E;
  function _(q, j, D) {
    ne(q);
    const le = W.list();
    return le.length ? le.forEach((g) => g(q, j, D)) : console.error(q), Promise.reject(q);
  }
  function X() {
    return E && l.value !== Ss ? Promise.resolve() : new Promise((q, j) => {
      ue.add([q, j]);
    });
  }
  function ne(q) {
    return E || (E = !q, He(), ue.list().forEach(([j, D]) => q ? D(q) : j()), ue.reset()), q;
  }
  function Xe(q, j, D, le) {
    const { scrollBehavior: g } = e;
    if (!rn || !g) return Promise.resolve();
    const x = !D && cp(Fi(q.fullPath, 0)) || (le || !D) && history.state && history.state.scroll || null;
    return lr().then(() => g(q, j, x)).then((P) => P && ip(P)).catch((P) => _(P, q, j));
  }
  const qe = (q) => r.go(q);
  let mt;
  const at = /* @__PURE__ */ new Set(), We = {
    currentRoute: l,
    listening: !0,
    addRoute: v,
    removeRoute: A,
    clearRoutes: t.clearRoutes,
    hasRoute: w,
    getRoutes: b,
    resolve: O,
    options: e,
    push: R,
    replace: J,
    go: qe,
    back: () => qe(-1),
    forward: () => qe(1),
    beforeEach: o.add,
    beforeResolve: a.add,
    afterEach: i.add,
    onError: W.add,
    isReady: X,
    install(q) {
      q.component("RouterLink", va), q.component("RouterView", gu), q.config.globalProperties.$router = We, Object.defineProperty(q.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => p(l)
      }), rn && !mt && l.value === Ss && (mt = !0, R(r.location).catch((le) => {
      }));
      const j = {};
      for (const le in Ss) Object.defineProperty(j, le, {
        get: () => l.value[le],
        enumerable: !0
      });
      q.provide(go, We), q.provide(Ga, /* @__PURE__ */ dc(j)), q.provide(ga, l);
      const D = q.unmount;
      at.add(q), q.unmount = function() {
        at.delete(q), at.size < 1 && (c = Ss, Me && Me(), Me = null, l.value = Ss, mt = !1, E = !1), D();
      };
    }
  };
  function Oe(q) {
    return q.reduce((j, D) => j.then(() => C(D)), Promise.resolve());
  }
  return We;
}
function vu() {
  return zt(go);
}
function yu(e) {
  return zt(Ga);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ws = {
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
const el = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Lo(e) {
  return e != null;
}
function Dp(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (y) => s[y] ?? y, r = e.size ?? e.width ?? Ws.width, o = e.size ?? e.height ?? Ws.height, a = e.aliases?.filter((y) => typeof y == "string" && y.trim() !== "").map((y) => `lucide-${y}`) ?? [], i = [...e.name ? [`lucide-${e.name}`] : [], ...a], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? el(...l) : el("lucide", ...i, ...l), d = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? Ws["stroke-width"]) * Number(e.size ?? e.width ?? Ws.width) / Number(t.size ?? t.width ?? Ws.width) : t.strokeWidth ?? Ws["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(Ws).reduce((y, [v, A]) => (y[n(v)] = A, y), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && Lo(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && Lo(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && Lo(t.height) && {
        [n("height")]: t.height
      },
      [n("stroke-width")]: d,
      ...c && {
        [n("class")]: c
      },
      [n("viewBox")]: `0 0 ${r} ${o}`,
      ...t.hasA11yProp === !1 ? {
        [n("aria-hidden")]: "true"
      } : {},
      ..."attributes" in t && t.attributes
    },
    e.node.map((y) => {
      const [v, A, b] = y, w = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...A } : A;
      return b ? [v, w, b] : [v, w];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Lp = (e) => {
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
const br = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Up = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Vp = /* @__PURE__ */ Symbol("lucide-icons");
function Fp() {
  return zt(Vp, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Wp = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && Up(e),
    node: t ?? s ?? [],
    size: 24,
    aliases: []
  },
  absoluteStrokeWidth: r,
  "absolute-stroke-width": o,
  nonScalingStroke: a,
  "non-scaling-stroke": i,
  strokeWidth: l,
  "stroke-width": c,
  size: d,
  width: f = d,
  height: y = d,
  color: v,
  ...A
}, { slots: b }) => {
  const {
    size: w,
    color: O,
    strokeWidth: I = 2,
    absoluteStrokeWidth: V = !1,
    nonScalingStroke: R = !1,
    class: J = ""
  } = Fp(), be = br(r) || br(o) || r === !0 || o === !0 || V === !0, ee = br(a) || br(i) || a === !0 || i === !0 || R === !0;
  delete A.class;
  const M = b.default?.(), [, C, F = []] = Dp(n, {
    color: v ?? O,
    width: f ?? d ?? w,
    height: y ?? d ?? w,
    strokeWidth: l ?? c ?? I,
    absoluteStrokeWidth: be,
    nonScalingStroke: ee,
    className: J,
    hasA11yProp: M != null && M.length > 0 || Lp(A),
    attributes: A
  });
  return Yn("svg", C, [
    ...F.map(([Se, Ce]) => Yn(Se, Ce)),
    ...M ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function ht(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => Yn(
    Wp,
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
const Bp = {
  name: "check",
  size: 24,
  node: [["path", { d: "M20 6 9 17l-5-5", key: "1gmf2c" }]]
}, qp = ht(Bp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Gp = {
  name: "chevron-down",
  size: 24,
  node: [["path", { d: "m6 9 6 6 6-6", key: "qrunsl" }]]
}, Hp = ht(Gp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Zp = {
  name: "database",
  size: 24,
  node: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]
}, Kp = ht(Zp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Jp = {
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
}, bu = ht(Jp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Qp = {
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
}, Yp = ht(Qp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Xp = {
  name: "image-plus",
  size: 24,
  node: [
    ["path", { d: "M16 5h6", key: "1vod17" }],
    ["path", { d: "M19 2v6", key: "4bpg5p" }],
    ["path", { d: "M21 11.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7.5", key: "1ue2ih" }],
    ["path", { d: "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21", key: "1xmnt7" }],
    ["circle", { cx: "9", cy: "9", r: "2", key: "af1f0g" }]
  ]
}, eh = ht(Xp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const th = {
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
}, sh = ht(th);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const nh = {
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
}, wu = ht(nh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const rh = {
  name: "list-plus",
  size: 24,
  node: [
    ["path", { d: "M16 5H3", key: "m91uny" }],
    ["path", { d: "M11 12H3", key: "51ecnj" }],
    ["path", { d: "M16 19H3", key: "zzsher" }],
    ["path", { d: "M18 9v6", key: "1twb98" }],
    ["path", { d: "M21 12h-6", key: "bt1uis" }]
  ]
}, oh = ht(rh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ah = {
  name: "menu",
  size: 24,
  node: [
    ["path", { d: "M4 5h16", key: "1tepv9" }],
    ["path", { d: "M4 12h16", key: "1lakjw" }],
    ["path", { d: "M4 19h16", key: "1djgab" }]
  ]
}, ih = ht(ah);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const lh = {
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
}, ch = ht(lh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const uh = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, vo = ht(uh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const dh = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, fh = ht(dh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const mh = {
  name: "rotate-ccw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }]
  ]
}, ph = ht(mh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const hh = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, _u = ht(hh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const gh = {
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
}, vh = ht(gh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const yh = {
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
}, bh = ht(yh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const wh = {
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
}, Wr = ht(wh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const _h = {
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
}, xh = ht(_h);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const kh = {
  name: "x",
  size: 24,
  node: [
    ["path", { d: "M18 6 6 18", key: "1bl5f8" }],
    ["path", { d: "m6 6 12 12", key: "d8bk6v" }]
  ]
}, ya = ht(kh), xu = "comfymodal", ku = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], Uo = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function js(e) {
  return typeof e == "string" && ku.indexOf(e) !== -1;
}
function wr(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function Su(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || wr(r.slice(0, o)) !== xu) return t;
  const a = wr(r.slice(o + 1));
  if (!js(a)) return t;
  let i = null;
  for (let l = 1; l < n.length; l++) {
    const c = n[l], d = c.indexOf("=");
    if (d === -1 || wr(c.slice(0, d)) !== "focus") continue;
    const f = wr(c.slice(d + 1));
    i = f === null || f === "" ? null : f;
    break;
  }
  return { matched: !0, page: a, focus: i };
}
function Cu(e) {
  if (!js(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + xu + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function tl(e, t) {
  if (!t || !js(t.page)) return "none";
  if (!e || !js(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function Sh(e, t) {
  if (e && js(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = Su(t);
  return s.matched && js(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
var Qe;
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
    for (const a of r)
      o[a] = a;
    return o;
  }, e.getValidEnumValues = (r) => {
    const o = e.objectKeys(r).filter((i) => typeof r[r[i]] != "number"), a = {};
    for (const i of o)
      a[i] = r[i];
    return e.objectValues(a);
  }, e.objectValues = (r) => e.objectKeys(r).map(function(o) {
    return r[o];
  }), e.objectKeys = typeof Object.keys == "function" ? (r) => Object.keys(r) : (r) => {
    const o = [];
    for (const a in r)
      Object.prototype.hasOwnProperty.call(r, a) && o.push(a);
    return o;
  }, e.find = (r, o) => {
    for (const a of r)
      if (o(a))
        return a;
  }, e.isInteger = typeof Number.isInteger == "function" ? (r) => Number.isInteger(r) : (r) => typeof r == "number" && Number.isFinite(r) && Math.floor(r) === r;
  function n(r, o = " | ") {
    return r.map((a) => typeof a == "string" ? `'${a}'` : a).join(o);
  }
  e.joinValues = n, e.jsonStringifyReplacer = (r, o) => typeof o == "bigint" ? o.toString() : o;
})(Qe || (Qe = {}));
var sl;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(sl || (sl = {}));
const we = Qe.arrayToEnum([
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
]), Os = (e) => {
  switch (typeof e) {
    case "undefined":
      return we.undefined;
    case "string":
      return we.string;
    case "number":
      return Number.isNaN(e) ? we.nan : we.number;
    case "boolean":
      return we.boolean;
    case "function":
      return we.function;
    case "bigint":
      return we.bigint;
    case "symbol":
      return we.symbol;
    case "object":
      return Array.isArray(e) ? we.array : e === null ? we.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? we.promise : typeof Map < "u" && e instanceof Map ? we.map : typeof Set < "u" && e instanceof Set ? we.set : typeof Date < "u" && e instanceof Date ? we.date : we.object;
    default:
      return we.unknown;
  }
}, ae = Qe.arrayToEnum([
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
class ws extends Error {
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
      for (const a of o.issues)
        if (a.code === "invalid_union")
          a.unionErrors.map(r);
        else if (a.code === "invalid_return_type")
          r(a.returnTypeError);
        else if (a.code === "invalid_arguments")
          r(a.argumentsError);
        else if (a.path.length === 0)
          n._errors.push(s(a));
        else {
          let i = n, l = 0;
          for (; l < a.path.length; ) {
            const c = a.path[l];
            l === a.path.length - 1 ? (i[c] = i[c] || { _errors: [] }, i[c]._errors.push(s(a))) : i[c] = i[c] || { _errors: [] }, i = i[c], l++;
          }
        }
    };
    return r(this), n;
  }
  static assert(t) {
    if (!(t instanceof ws))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, Qe.jsonStringifyReplacer, 2);
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
ws.create = (e) => new ws(e);
const ba = (e, t) => {
  let s;
  switch (e.code) {
    case ae.invalid_type:
      e.received === we.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case ae.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, Qe.jsonStringifyReplacer)}`;
      break;
    case ae.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${Qe.joinValues(e.keys, ", ")}`;
      break;
    case ae.invalid_union:
      s = "Invalid input";
      break;
    case ae.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${Qe.joinValues(e.options)}`;
      break;
    case ae.invalid_enum_value:
      s = `Invalid enum value. Expected ${Qe.joinValues(e.options)}, received '${e.received}'`;
      break;
    case ae.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case ae.invalid_return_type:
      s = "Invalid function return type";
      break;
    case ae.invalid_date:
      s = "Invalid date";
      break;
    case ae.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : Qe.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case ae.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case ae.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case ae.custom:
      s = "Invalid input";
      break;
    case ae.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case ae.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case ae.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, Qe.assertNever(e);
  }
  return { message: s };
};
let Ch = ba;
function $h() {
  return Ch;
}
const Ih = (e) => {
  const { data: t, path: s, errorMaps: n, issueData: r } = e, o = [...s, ...r.path || []], a = {
    ...r,
    path: o
  };
  if (r.message !== void 0)
    return {
      ...r,
      path: o,
      message: r.message
    };
  let i = "";
  const l = n.filter((c) => !!c).slice().reverse();
  for (const c of l)
    i = c(a, { data: t, defaultError: i }).message;
  return {
    ...r,
    path: o,
    message: i
  };
};
function me(e, t) {
  const s = $h(), n = Ih({
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
      s === ba ? void 0 : ba
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(n);
}
class Ot {
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
        return Pe;
      r.status === "dirty" && t.dirty(), n.push(r.value);
    }
    return { status: t.value, value: n };
  }
  static async mergeObjectAsync(t, s) {
    const n = [];
    for (const r of s) {
      const o = await r.key, a = await r.value;
      n.push({
        key: o,
        value: a
      });
    }
    return Ot.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const r of s) {
      const { key: o, value: a } = r;
      if (o.status === "aborted" || a.status === "aborted")
        return Pe;
      o.status === "dirty" && t.dirty(), a.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof a.value < "u" || r.alwaysSet) && (n[o.value] = a.value);
    }
    return { status: t.value, value: n };
  }
}
const Pe = Object.freeze({
  status: "aborted"
}), zn = (e) => ({ status: "dirty", value: e }), Ut = (e) => ({ status: "valid", value: e }), nl = (e) => e.status === "aborted", rl = (e) => e.status === "dirty", pn = (e) => e.status === "valid", Br = (e) => typeof Promise < "u" && e instanceof Promise;
var ke;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(ke || (ke = {}));
class os {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const ol = (e, t) => {
  if (pn(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new ws(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function De(e) {
  if (!e)
    return {};
  const { errorMap: t, invalid_type_error: s, required_error: n, description: r } = e;
  if (t && (s || n))
    throw new Error(`Can't use "invalid_type_error" or "required_error" in conjunction with custom error map.`);
  return t ? { errorMap: t, description: r } : { errorMap: (a, i) => {
    const { message: l } = e;
    return a.code === "invalid_enum_value" ? { message: l ?? i.defaultError } : typeof i.data > "u" ? { message: l ?? n ?? i.defaultError } : a.code !== "invalid_type" ? { message: i.defaultError } : { message: l ?? s ?? i.defaultError };
  }, description: r };
}
class Ge {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return Os(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: Os(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new Ot(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: Os(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (Br(s))
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
      parsedType: Os(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return ol(n, r);
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
      parsedType: Os(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return pn(n) ? {
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
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => pn(n) ? {
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
      parsedType: Os(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (Br(r) ? r : Promise.resolve(r));
    return ol(n, o);
  }
  refine(t, s) {
    const n = (r) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(r) : s;
    return this._refinement((r, o) => {
      const a = t(r), i = () => o.addIssue({
        code: ae.custom,
        ...n(r)
      });
      return typeof Promise < "u" && a instanceof Promise ? a.then((l) => l ? !0 : (i(), !1)) : a ? !0 : (i(), !1);
    });
  }
  refinement(t, s) {
    return this._refinement((n, r) => t(n) ? !0 : (r.addIssue(typeof s == "function" ? s(n, r) : s), !1));
  }
  _refinement(t) {
    return new vn({
      schema: this,
      typeName: Te.ZodEffects,
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
    return Ns.create(this, this._def);
  }
  nullable() {
    return yn.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return ts.create(this);
  }
  promise() {
    return Kr.create(this, this._def);
  }
  or(t) {
    return Gr.create([this, t], this._def);
  }
  and(t) {
    return Hr.create(this, t, this._def);
  }
  transform(t) {
    return new vn({
      ...De(this._def),
      schema: this,
      typeName: Te.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new xa({
      ...De(this._def),
      innerType: this,
      defaultValue: s,
      typeName: Te.ZodDefault
    });
  }
  brand() {
    return new Jh({
      typeName: Te.ZodBranded,
      type: this,
      ...De(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new ka({
      ...De(this._def),
      innerType: this,
      catchValue: s,
      typeName: Te.ZodCatch
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
    return Ha.create(this, t);
  }
  readonly() {
    return Sa.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const Rh = /^c[^\s-]{8,}$/i, Ah = /^[0-9a-z]+$/, Eh = /^[0-9A-HJKMNP-TV-Z]{26}$/i, Oh = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, Th = /^[a-z0-9_-]{21}$/i, Ph = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, Nh = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Mh = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, zh = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let Vo;
const jh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, Dh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, Lh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, Uh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, Vh = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, Fh = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, $u = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", Wh = new RegExp(`^${$u}$`);
function Iu(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function Bh(e) {
  return new RegExp(`^${Iu(e)}$`);
}
function qh(e) {
  let t = `${$u}T${Iu(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function Gh(e, t) {
  return !!((t === "v4" || !t) && jh.test(e) || (t === "v6" || !t) && Lh.test(e));
}
function Hh(e, t) {
  if (!Ph.test(e))
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
function Zh(e, t) {
  return !!((t === "v4" || !t) && Dh.test(e) || (t === "v6" || !t) && Uh.test(e));
}
class hs extends Ge {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== we.string) {
      const o = this._getOrReturnCtx(t);
      return me(o, {
        code: ae.invalid_type,
        expected: we.string,
        received: o.parsedType
      }), Pe;
    }
    const n = new Ot();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), me(r, {
          code: ae.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), me(r, {
          code: ae.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const a = t.data.length > o.value, i = t.data.length < o.value;
        (a || i) && (r = this._getOrReturnCtx(t, r), a ? me(r, {
          code: ae.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : i && me(r, {
          code: ae.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        Mh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "email",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        Vo || (Vo = new RegExp(zh, "u")), Vo.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "emoji",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        Oh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "uuid",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        Th.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "nanoid",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        Rh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "cuid",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        Ah.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "cuid2",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        Eh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
          validation: "ulid",
          code: ae.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), me(r, {
            validation: "url",
            code: ae.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "regex",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? qh(o).test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? Wh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? Bh(o).test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? Nh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "duration",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? Gh(t.data, o.version) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "ip",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? Hh(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "jwt",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Zh(t.data, o.version) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "cidr",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? Vh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "base64",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? Fh.test(t.data) || (r = this._getOrReturnCtx(t, r), me(r, {
        validation: "base64url",
        code: ae.invalid_string,
        message: o.message
      }), n.dirty()) : Qe.assertNever(o);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((r) => t.test(r), {
      validation: s,
      code: ae.invalid_string,
      ...ke.errToObj(n)
    });
  }
  _addCheck(t) {
    return new hs({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...ke.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...ke.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...ke.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...ke.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...ke.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...ke.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...ke.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...ke.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...ke.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...ke.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...ke.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...ke.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...ke.errToObj(t) });
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
      ...ke.errToObj(t?.message)
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
      ...ke.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...ke.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...ke.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...ke.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...ke.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...ke.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...ke.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...ke.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...ke.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, ke.errToObj(t));
  }
  trim() {
    return new hs({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new hs({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new hs({
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
hs.create = (e) => new hs({
  checks: [],
  typeName: Te.ZodString,
  coerce: e?.coerce ?? !1,
  ...De(e)
});
function Kh(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), a = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % a / 10 ** r;
}
class hn extends Ge {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== we.number) {
      const o = this._getOrReturnCtx(t);
      return me(o, {
        code: ae.invalid_type,
        expected: we.number,
        received: o.parsedType
      }), Pe;
    }
    let n;
    const r = new Ot();
    for (const o of this._def.checks)
      o.kind === "int" ? Qe.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? Kh(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.not_finite,
        message: o.message
      }), r.dirty()) : Qe.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, ke.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, ke.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, ke.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, ke.toString(s));
  }
  setLimit(t, s, n, r) {
    return new hn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: ke.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new hn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: ke.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: ke.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: ke.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: ke.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: ke.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: ke.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: ke.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: ke.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: ke.toString(t)
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && Qe.isInteger(t.value));
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
hn.create = (e) => new hn({
  checks: [],
  typeName: Te.ZodNumber,
  coerce: e?.coerce || !1,
  ...De(e)
});
class sr extends Ge {
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
    if (this._getType(t) !== we.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new Ot();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), me(n, {
        code: ae.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : Qe.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return me(s, {
      code: ae.invalid_type,
      expected: we.bigint,
      received: s.parsedType
    }), Pe;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, ke.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, ke.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, ke.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, ke.toString(s));
  }
  setLimit(t, s, n, r) {
    return new sr({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: ke.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new sr({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: ke.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: ke.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: ke.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: ke.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: ke.toString(s)
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
sr.create = (e) => new sr({
  checks: [],
  typeName: Te.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...De(e)
});
class wa extends Ge {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== we.boolean) {
      const n = this._getOrReturnCtx(t);
      return me(n, {
        code: ae.invalid_type,
        expected: we.boolean,
        received: n.parsedType
      }), Pe;
    }
    return Ut(t.data);
  }
}
wa.create = (e) => new wa({
  typeName: Te.ZodBoolean,
  coerce: e?.coerce || !1,
  ...De(e)
});
class qr extends Ge {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== we.date) {
      const o = this._getOrReturnCtx(t);
      return me(o, {
        code: ae.invalid_type,
        expected: we.date,
        received: o.parsedType
      }), Pe;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return me(o, {
        code: ae.invalid_date
      }), Pe;
    }
    const n = new Ot();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), me(r, {
        code: ae.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), n.dirty()) : Qe.assertNever(o);
    return {
      status: n.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new qr({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: ke.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: ke.toString(s)
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
qr.create = (e) => new qr({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: Te.ZodDate,
  ...De(e)
});
class al extends Ge {
  _parse(t) {
    if (this._getType(t) !== we.symbol) {
      const n = this._getOrReturnCtx(t);
      return me(n, {
        code: ae.invalid_type,
        expected: we.symbol,
        received: n.parsedType
      }), Pe;
    }
    return Ut(t.data);
  }
}
al.create = (e) => new al({
  typeName: Te.ZodSymbol,
  ...De(e)
});
class il extends Ge {
  _parse(t) {
    if (this._getType(t) !== we.undefined) {
      const n = this._getOrReturnCtx(t);
      return me(n, {
        code: ae.invalid_type,
        expected: we.undefined,
        received: n.parsedType
      }), Pe;
    }
    return Ut(t.data);
  }
}
il.create = (e) => new il({
  typeName: Te.ZodUndefined,
  ...De(e)
});
class ll extends Ge {
  _parse(t) {
    if (this._getType(t) !== we.null) {
      const n = this._getOrReturnCtx(t);
      return me(n, {
        code: ae.invalid_type,
        expected: we.null,
        received: n.parsedType
      }), Pe;
    }
    return Ut(t.data);
  }
}
ll.create = (e) => new ll({
  typeName: Te.ZodNull,
  ...De(e)
});
class cl extends Ge {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return Ut(t.data);
  }
}
cl.create = (e) => new cl({
  typeName: Te.ZodAny,
  ...De(e)
});
class ul extends Ge {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return Ut(t.data);
  }
}
ul.create = (e) => new ul({
  typeName: Te.ZodUnknown,
  ...De(e)
});
class Ds extends Ge {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return me(s, {
      code: ae.invalid_type,
      expected: we.never,
      received: s.parsedType
    }), Pe;
  }
}
Ds.create = (e) => new Ds({
  typeName: Te.ZodNever,
  ...De(e)
});
class dl extends Ge {
  _parse(t) {
    if (this._getType(t) !== we.undefined) {
      const n = this._getOrReturnCtx(t);
      return me(n, {
        code: ae.invalid_type,
        expected: we.void,
        received: n.parsedType
      }), Pe;
    }
    return Ut(t.data);
  }
}
dl.create = (e) => new dl({
  typeName: Te.ZodVoid,
  ...De(e)
});
class ts extends Ge {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== we.array)
      return me(s, {
        code: ae.invalid_type,
        expected: we.array,
        received: s.parsedType
      }), Pe;
    if (r.exactLength !== null) {
      const a = s.data.length > r.exactLength.value, i = s.data.length < r.exactLength.value;
      (a || i) && (me(s, {
        code: a ? ae.too_big : ae.too_small,
        minimum: i ? r.exactLength.value : void 0,
        maximum: a ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (me(s, {
      code: ae.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (me(s, {
      code: ae.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((a, i) => r.type._parseAsync(new os(s, a, s.path, i)))).then((a) => Ot.mergeArray(n, a));
    const o = [...s.data].map((a, i) => r.type._parseSync(new os(s, a, s.path, i)));
    return Ot.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new ts({
      ...this._def,
      minLength: { value: t, message: ke.toString(s) }
    });
  }
  max(t, s) {
    return new ts({
      ...this._def,
      maxLength: { value: t, message: ke.toString(s) }
    });
  }
  length(t, s) {
    return new ts({
      ...this._def,
      exactLength: { value: t, message: ke.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
ts.create = (e, t) => new ts({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: Te.ZodArray,
  ...De(t)
});
function on(e) {
  if (e instanceof pt) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = Ns.create(on(n));
    }
    return new pt({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof ts ? new ts({
    ...e._def,
    type: on(e.element)
  }) : e instanceof Ns ? Ns.create(on(e.unwrap())) : e instanceof yn ? yn.create(on(e.unwrap())) : e instanceof Qs ? Qs.create(e.items.map((t) => on(t))) : e;
}
class pt extends Ge {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = Qe.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== we.object) {
      const c = this._getOrReturnCtx(t);
      return me(c, {
        code: ae.invalid_type,
        expected: we.object,
        received: c.parsedType
      }), Pe;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: a } = this._getCached(), i = [];
    if (!(this._def.catchall instanceof Ds && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        a.includes(c) || i.push(c);
    const l = [];
    for (const c of a) {
      const d = o[c], f = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: d._parse(new os(r, f, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof Ds) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const d of i)
          l.push({
            key: { status: "valid", value: d },
            value: { status: "valid", value: r.data[d] }
          });
      else if (c === "strict")
        i.length > 0 && (me(r, {
          code: ae.unrecognized_keys,
          keys: i
        }), n.dirty());
      else if (c !== "strip") throw new Error("Internal ZodObject error: invalid unknownKeys value.");
    } else {
      const c = this._def.catchall;
      for (const d of i) {
        const f = r.data[d];
        l.push({
          key: { status: "valid", value: d },
          value: c._parse(
            new os(r, f, r.path, d)
            //, ctx.child(key), value, getParsedType(value)
          ),
          alwaysSet: d in r.data
        });
      }
    }
    return r.common.async ? Promise.resolve().then(async () => {
      const c = [];
      for (const d of l) {
        const f = await d.key, y = await d.value;
        c.push({
          key: f,
          value: y,
          alwaysSet: d.alwaysSet
        });
      }
      return c;
    }).then((c) => Ot.mergeObjectSync(n, c)) : Ot.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return ke.errToObj, new pt({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: ke.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new pt({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new pt({
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
    return new pt({
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
    return new pt({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: Te.ZodObject
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
    return new pt({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of Qe.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new pt({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of Qe.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new pt({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return on(this);
  }
  partial(t) {
    const s = {};
    for (const n of Qe.objectKeys(this.shape)) {
      const r = this.shape[n];
      t && !t[n] ? s[n] = r : s[n] = r.optional();
    }
    return new pt({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of Qe.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let o = this.shape[n];
        for (; o instanceof Ns; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new pt({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return Ru(Qe.objectKeys(this.shape));
  }
}
pt.create = (e, t) => new pt({
  shape: () => e,
  unknownKeys: "strip",
  catchall: Ds.create(),
  typeName: Te.ZodObject,
  ...De(t)
});
pt.strictCreate = (e, t) => new pt({
  shape: () => e,
  unknownKeys: "strict",
  catchall: Ds.create(),
  typeName: Te.ZodObject,
  ...De(t)
});
pt.lazycreate = (e, t) => new pt({
  shape: e,
  unknownKeys: "strip",
  catchall: Ds.create(),
  typeName: Te.ZodObject,
  ...De(t)
});
class Gr extends Ge {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const i of o)
        if (i.result.status === "valid")
          return i.result;
      for (const i of o)
        if (i.result.status === "dirty")
          return s.common.issues.push(...i.ctx.common.issues), i.result;
      const a = o.map((i) => new ws(i.ctx.common.issues));
      return me(s, {
        code: ae.invalid_union,
        unionErrors: a
      }), Pe;
    }
    if (s.common.async)
      return Promise.all(n.map(async (o) => {
        const a = {
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
            parent: a
          }),
          ctx: a
        };
      })).then(r);
    {
      let o;
      const a = [];
      for (const l of n) {
        const c = {
          ...s,
          common: {
            ...s.common,
            issues: []
          },
          parent: null
        }, d = l._parseSync({
          data: s.data,
          path: s.path,
          parent: c
        });
        if (d.status === "valid")
          return d;
        d.status === "dirty" && !o && (o = { result: d, ctx: c }), c.common.issues.length && a.push(c.common.issues);
      }
      if (o)
        return s.common.issues.push(...o.ctx.common.issues), o.result;
      const i = a.map((l) => new ws(l));
      return me(s, {
        code: ae.invalid_union,
        unionErrors: i
      }), Pe;
    }
  }
  get options() {
    return this._def.options;
  }
}
Gr.create = (e, t) => new Gr({
  options: e,
  typeName: Te.ZodUnion,
  ...De(t)
});
function _a(e, t) {
  const s = Os(e), n = Os(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === we.object && n === we.object) {
    const r = Qe.objectKeys(t), o = Qe.objectKeys(e).filter((i) => r.indexOf(i) !== -1), a = { ...e, ...t };
    for (const i of o) {
      const l = _a(e[i], t[i]);
      if (!l.valid)
        return { valid: !1 };
      a[i] = l.data;
    }
    return { valid: !0, data: a };
  } else if (s === we.array && n === we.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const a = e[o], i = t[o], l = _a(a, i);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === we.date && n === we.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class Hr extends Ge {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, a) => {
      if (nl(o) || nl(a))
        return Pe;
      const i = _a(o.value, a.value);
      return i.valid ? ((rl(o) || rl(a)) && s.dirty(), { status: s.value, value: i.data }) : (me(n, {
        code: ae.invalid_intersection_types
      }), Pe);
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
    ]).then(([o, a]) => r(o, a)) : r(this._def.left._parseSync({
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
Hr.create = (e, t, s) => new Hr({
  left: e,
  right: t,
  typeName: Te.ZodIntersection,
  ...De(s)
});
class Qs extends Ge {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== we.array)
      return me(n, {
        code: ae.invalid_type,
        expected: we.array,
        received: n.parsedType
      }), Pe;
    if (n.data.length < this._def.items.length)
      return me(n, {
        code: ae.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), Pe;
    !this._def.rest && n.data.length > this._def.items.length && (me(n, {
      code: ae.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((a, i) => {
      const l = this._def.items[i] || this._def.rest;
      return l ? l._parse(new os(n, a, n.path, i)) : null;
    }).filter((a) => !!a);
    return n.common.async ? Promise.all(o).then((a) => Ot.mergeArray(s, a)) : Ot.mergeArray(s, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Qs({
      ...this._def,
      rest: t
    });
  }
}
Qs.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Qs({
    items: e,
    typeName: Te.ZodTuple,
    rest: null,
    ...De(t)
  });
};
class Zr extends Ge {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== we.object)
      return me(n, {
        code: ae.invalid_type,
        expected: we.object,
        received: n.parsedType
      }), Pe;
    const r = [], o = this._def.keyType, a = this._def.valueType;
    for (const i in n.data)
      r.push({
        key: o._parse(new os(n, i, n.path, i)),
        value: a._parse(new os(n, n.data[i], n.path, i)),
        alwaysSet: i in n.data
      });
    return n.common.async ? Ot.mergeObjectAsync(s, r) : Ot.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof Ge ? new Zr({
      keyType: t,
      valueType: s,
      typeName: Te.ZodRecord,
      ...De(n)
    }) : new Zr({
      keyType: hs.create(),
      valueType: t,
      typeName: Te.ZodRecord,
      ...De(s)
    });
  }
}
class fl extends Ge {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== we.map)
      return me(n, {
        code: ae.invalid_type,
        expected: we.map,
        received: n.parsedType
      }), Pe;
    const r = this._def.keyType, o = this._def.valueType, a = [...n.data.entries()].map(([i, l], c) => ({
      key: r._parse(new os(n, i, n.path, [c, "key"])),
      value: o._parse(new os(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const i = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of a) {
          const c = await l.key, d = await l.value;
          if (c.status === "aborted" || d.status === "aborted")
            return Pe;
          (c.status === "dirty" || d.status === "dirty") && s.dirty(), i.set(c.value, d.value);
        }
        return { status: s.value, value: i };
      });
    } else {
      const i = /* @__PURE__ */ new Map();
      for (const l of a) {
        const c = l.key, d = l.value;
        if (c.status === "aborted" || d.status === "aborted")
          return Pe;
        (c.status === "dirty" || d.status === "dirty") && s.dirty(), i.set(c.value, d.value);
      }
      return { status: s.value, value: i };
    }
  }
}
fl.create = (e, t, s) => new fl({
  valueType: t,
  keyType: e,
  typeName: Te.ZodMap,
  ...De(s)
});
class nr extends Ge {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== we.set)
      return me(n, {
        code: ae.invalid_type,
        expected: we.set,
        received: n.parsedType
      }), Pe;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (me(n, {
      code: ae.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (me(n, {
      code: ae.too_big,
      maximum: r.maxSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.maxSize.message
    }), s.dirty());
    const o = this._def.valueType;
    function a(l) {
      const c = /* @__PURE__ */ new Set();
      for (const d of l) {
        if (d.status === "aborted")
          return Pe;
        d.status === "dirty" && s.dirty(), c.add(d.value);
      }
      return { status: s.value, value: c };
    }
    const i = [...n.data.values()].map((l, c) => o._parse(new os(n, l, n.path, c)));
    return n.common.async ? Promise.all(i).then((l) => a(l)) : a(i);
  }
  min(t, s) {
    return new nr({
      ...this._def,
      minSize: { value: t, message: ke.toString(s) }
    });
  }
  max(t, s) {
    return new nr({
      ...this._def,
      maxSize: { value: t, message: ke.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
nr.create = (e, t) => new nr({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: Te.ZodSet,
  ...De(t)
});
class ml extends Ge {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
ml.create = (e, t) => new ml({
  getter: e,
  typeName: Te.ZodLazy,
  ...De(t)
});
class pl extends Ge {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return me(s, {
        received: s.data,
        code: ae.invalid_literal,
        expected: this._def.value
      }), Pe;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
pl.create = (e, t) => new pl({
  value: e,
  typeName: Te.ZodLiteral,
  ...De(t)
});
function Ru(e, t) {
  return new gn({
    values: e,
    typeName: Te.ZodEnum,
    ...De(t)
  });
}
class gn extends Ge {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return me(s, {
        expected: Qe.joinValues(n),
        received: s.parsedType,
        code: ae.invalid_type
      }), Pe;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return me(s, {
        received: s.data,
        code: ae.invalid_enum_value,
        options: n
      }), Pe;
    }
    return Ut(t.data);
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
    return gn.create(t, {
      ...this._def,
      ...s
    });
  }
  exclude(t, s = this._def) {
    return gn.create(this.options.filter((n) => !t.includes(n)), {
      ...this._def,
      ...s
    });
  }
}
gn.create = Ru;
class hl extends Ge {
  _parse(t) {
    const s = Qe.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== we.string && n.parsedType !== we.number) {
      const r = Qe.objectValues(s);
      return me(n, {
        expected: Qe.joinValues(r),
        received: n.parsedType,
        code: ae.invalid_type
      }), Pe;
    }
    if (this._cache || (this._cache = new Set(Qe.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = Qe.objectValues(s);
      return me(n, {
        received: n.data,
        code: ae.invalid_enum_value,
        options: r
      }), Pe;
    }
    return Ut(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
hl.create = (e, t) => new hl({
  values: e,
  typeName: Te.ZodNativeEnum,
  ...De(t)
});
class Kr extends Ge {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== we.promise && s.common.async === !1)
      return me(s, {
        code: ae.invalid_type,
        expected: we.promise,
        received: s.parsedType
      }), Pe;
    const n = s.parsedType === we.promise ? s.data : Promise.resolve(s.data);
    return Ut(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
Kr.create = (e, t) => new Kr({
  type: e,
  typeName: Te.ZodPromise,
  ...De(t)
});
class vn extends Ge {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === Te.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (a) => {
        me(n, a), a.fatal ? s.abort() : s.dirty();
      },
      get path() {
        return n.path;
      }
    };
    if (o.addIssue = o.addIssue.bind(o), r.type === "preprocess") {
      const a = r.transform(n.data, o);
      if (n.common.async)
        return Promise.resolve(a).then(async (i) => {
          if (s.value === "aborted")
            return Pe;
          const l = await this._def.schema._parseAsync({
            data: i,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? Pe : l.status === "dirty" || s.value === "dirty" ? zn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return Pe;
        const i = this._def.schema._parseSync({
          data: a,
          path: n.path,
          parent: n
        });
        return i.status === "aborted" ? Pe : i.status === "dirty" || s.value === "dirty" ? zn(i.value) : i;
      }
    }
    if (r.type === "refinement") {
      const a = (i) => {
        const l = r.refinement(i, o);
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
        return i.status === "aborted" ? Pe : (i.status === "dirty" && s.dirty(), a(i.value), { status: s.value, value: i.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => i.status === "aborted" ? Pe : (i.status === "dirty" && s.dirty(), a(i.value).then(() => ({ status: s.value, value: i.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const a = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!pn(a))
          return Pe;
        const i = r.transform(a.value, o);
        if (i instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: i };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => pn(a) ? Promise.resolve(r.transform(a.value, o)).then((i) => ({
          status: s.value,
          value: i
        })) : Pe);
    Qe.assertNever(r);
  }
}
vn.create = (e, t, s) => new vn({
  schema: e,
  typeName: Te.ZodEffects,
  effect: t,
  ...De(s)
});
vn.createWithPreprocess = (e, t, s) => new vn({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: Te.ZodEffects,
  ...De(s)
});
class Ns extends Ge {
  _parse(t) {
    return this._getType(t) === we.undefined ? Ut(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Ns.create = (e, t) => new Ns({
  innerType: e,
  typeName: Te.ZodOptional,
  ...De(t)
});
class yn extends Ge {
  _parse(t) {
    return this._getType(t) === we.null ? Ut(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
yn.create = (e, t) => new yn({
  innerType: e,
  typeName: Te.ZodNullable,
  ...De(t)
});
class xa extends Ge {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === we.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
xa.create = (e, t) => new xa({
  innerType: e,
  typeName: Te.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...De(t)
});
class ka extends Ge {
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
    return Br(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new ws(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new ws(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
ka.create = (e, t) => new ka({
  innerType: e,
  typeName: Te.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...De(t)
});
class gl extends Ge {
  _parse(t) {
    if (this._getType(t) !== we.nan) {
      const n = this._getOrReturnCtx(t);
      return me(n, {
        code: ae.invalid_type,
        expected: we.nan,
        received: n.parsedType
      }), Pe;
    }
    return { status: "valid", value: t.data };
  }
}
gl.create = (e) => new gl({
  typeName: Te.ZodNaN,
  ...De(e)
});
class Jh extends Ge {
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
class Ha extends Ge {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? Pe : o.status === "dirty" ? (s.dirty(), zn(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? Pe : r.status === "dirty" ? (s.dirty(), {
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
    return new Ha({
      in: t,
      out: s,
      typeName: Te.ZodPipeline
    });
  }
}
class Sa extends Ge {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (pn(r) && (r.value = Object.freeze(r.value)), r);
    return Br(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Sa.create = (e, t) => new Sa({
  innerType: e,
  typeName: Te.ZodReadonly,
  ...De(t)
});
var Te;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(Te || (Te = {}));
const bt = hs.create, Fo = hn.create, _r = wa.create;
Ds.create;
const Au = ts.create, Za = pt.create;
Gr.create;
Hr.create;
Qs.create;
const Qh = Zr.create, Ca = gn.create;
Kr.create;
Ns.create;
yn.create;
const Yh = "comfymodal.studio.vue.";
function Xh() {
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
function eg() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return Xh();
}
function gs(e, t, s, n) {
  const r = Yh + e, o = eg();
  return {
    key: r,
    read() {
      let a = null;
      try {
        a = o.getItem(r);
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
        o.setItem(r, JSON.stringify(a));
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
const tg = "/comfymodal";
class sg extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function ng(e, t) {
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
        const a = r[o];
        if (typeof a == "string" && a.trim() !== "") return a;
      }
    }
  }
  return t;
}
function rg(e, t) {
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
async function oe(e, t = {}, s = fetch) {
  const {
    method: n = "GET",
    body: r,
    signal: o,
    timeoutMs: a,
    headers: i = {}
  } = t, { signal: l, cleanup: c } = rg(o, a);
  try {
    if (l && l.aborted) throw l.reason;
    const d = await s(tg + e, {
      method: n,
      headers: {
        "Content-Type": "application/json",
        ...i
      },
      body: r === void 0 ? void 0 : JSON.stringify(r),
      signal: l
    }), f = await d.text();
    let y = null;
    if (f !== "")
      try {
        y = JSON.parse(f);
      } catch {
        y = f;
      }
    if (!d.ok)
      throw new sg(
        d.status,
        ng(y, `Request failed with status ${d.status}`),
        y
      );
    return y;
  } finally {
    c();
  }
}
const og = Za({ value: bt(), label: bt() }).passthrough(), ag = Za({
  gpu: bt().default(""),
  default_gpu: bt().default(""),
  available_gpus: Au(og).default([]),
  persisted_gpu: bt().default(""),
  output_format: bt().default("original"),
  quality: Fo().default(75),
  webp_lossless_compression: bt().default("balanced"),
  auto_save_local: _r().default(!1),
  save_folder: bt().default(""),
  save_metadata_sidecar: _r().default(!0),
  preview_default: Ca(["off", "on"]).default("off"),
  preview_codec: bt().default("webp"),
  preview_quality: Fo().default(70),
  data_saver_default: Ca(["off", "on"]).default("off"),
  data_saver_codec: bt().default("webp"),
  data_saver_quality: Fo().default(70),
  execution_mode: bt().default("v2"),
  execution_mode_source: bt().default(""),
  execution_mode_locked: _r().default(!1),
  engine_migration_notice: bt().nullable().default(null),
  skip_plan_validation: _r().default(!1),
  golden_gpu_order: Qh(bt()).default({})
}).passthrough(), ig = Za({ status: bt().optional(), level: bt().default("off"), effective: bt().default("off") }).passthrough();
async function xr() {
  return ag.parse(await oe("/config"));
}
async function lg(e) {
  return oe("/config", { method: "POST", body: e });
}
async function vl() {
  return ig.parse(await oe("/profile/level"));
}
async function cg(e) {
  return oe("/profile/level", { method: "POST", body: { level: e } });
}
async function ug() {
  return oe("/studio/golden/profiles");
}
async function dg(e, t) {
  return oe("/studio/golden/gpu-order", { method: "POST", body: { profile: e, order: t } });
}
async function fg(e) {
  return oe("/studio/golden/deploy", { method: "POST", body: { profile: e } });
}
async function yl(e) {
  return oe(`/studio/golden/deploy?profile=${encodeURIComponent(e)}`);
}
const In = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function bl(e) {
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
    localStorage.setItem(In.outputFormat, s.output_format), localStorage.setItem(In.quality, String(s.quality)), localStorage.setItem(In.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(In.saveFolder, s.save_folder), localStorage.setItem(In.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const Eu = "comfymodal-studio";
function yo(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(Eu), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function tt(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(Eu);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
function bn() {
  let e = 0, t = null;
  return {
    run: (n) => {
      e += 1;
      const r = e, o = t;
      o && (o.superseded = !0, o.controller.abort());
      const a = new AbortController(), i = { controller: a, superseded: !1 };
      let l;
      const c = new Promise((y) => {
        l = () => y({ stale: !0 });
      }), d = () => l();
      a.signal.addEventListener("abort", d, { once: !0 }), t = i;
      const f = () => {
        a.signal.removeEventListener("abort", d), t === i && (t = null);
      };
      return (async () => {
        try {
          return await Promise.race([
            n(a.signal).then((y) => r !== e || i.superseded || a.signal.aborted ? { stale: !0 } : { stale: !1, value: y }),
            c
          ]);
        } catch (y) {
          if (i.superseded || r !== e || a.signal.aborted)
            return { stale: !0 };
          throw y;
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
function mg(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function pg(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function jn(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let a = 0;
  for (; ; ) {
    mg(s), a += 1, o && o(a);
    const i = await n(s, a);
    if (r(i)) return i;
    await pg(t, s);
  }
}
const hg = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function Wo(e) {
  return hg.has(e);
}
let wl = 0;
function gg() {
  return wl += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${wl}`;
}
const Pt = /* @__PURE__ */ _n("studio-operations", () => {
  const e = /* @__PURE__ */ T(/* @__PURE__ */ new Map()), t = ye(() => [...e.value.values()]), s = ye(
    () => t.value.filter((y) => y.status === "pending" || y.status === "running")
  );
  function n(y) {
    return e.value.get(y);
  }
  function r(y) {
    const v = Date.now(), A = gg(), b = y.status === "pending" ? "pending" : "running";
    return e.value.set(A, {
      id: A,
      kind: y.kind,
      label: y.label,
      status: b,
      progress: y.progress,
      message: y.message,
      startedAt: v,
      finishedAt: void 0,
      workspaceId: y.workspaceId
    }), A;
  }
  function o(y, v) {
    const A = e.value.get(y);
    if (!A) return;
    const { status: b, ...w } = v, O = { ...A, ...w };
    !Wo(A.status) && b !== void 0 && !Wo(b) && (O.status = b), e.value.set(y, O);
  }
  function a(y, v, A) {
    const b = e.value.get(y);
    !b || Wo(b.status) || e.value.set(y, {
      ...b,
      status: v,
      message: A === void 0 ? b.message : A,
      finishedAt: Date.now()
    });
  }
  function i(y, v) {
    a(y, "completed", v);
  }
  function l(y, v) {
    a(y, "failed", v);
  }
  function c(y, v) {
    a(y, "canceled", v);
  }
  function d(y) {
    e.value.delete(y);
  }
  function f() {
    e.value.clear();
  }
  return {
    byId: e,
    all: t,
    active: s,
    get: n,
    start: r,
    patch: o,
    finish: i,
    fail: l,
    cancel: c,
    remove: d,
    clear: f
  };
}), vg = Ca(["comfortable", "compact"]), Bo = gs(
  "shell.density",
  "comfortable",
  vg
), yg = [
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
], Ou = [
  "generation",
  "outputs",
  "accounts",
  "interface",
  "advanced"
];
function bg(e) {
  try {
    return localStorage.getItem(e);
  } catch {
    return null;
  }
}
function Rn(e, t) {
  try {
    localStorage.setItem(e, t);
  } catch {
  }
}
function An(e) {
  for (const t of e)
    try {
      localStorage.removeItem(t);
    } catch {
    }
}
const ur = /* @__PURE__ */ _n("studio-settings", () => {
  const e = /* @__PURE__ */ T("generation"), t = /* @__PURE__ */ T(Bo.read()), s = /* @__PURE__ */ T(null), n = /* @__PURE__ */ T("off"), r = /* @__PURE__ */ T("off"), o = /* @__PURE__ */ T(!1), a = /* @__PURE__ */ T(!1), i = /* @__PURE__ */ T(null), l = /* @__PURE__ */ T(!1), c = /* @__PURE__ */ T([]), d = /* @__PURE__ */ T(null), f = /* @__PURE__ */ T(null), y = /* @__PURE__ */ T(!1);
  let v = !1, A = null;
  const b = gs("golden.profile", "", bt()), w = gs(
    "golden.favorites",
    [],
    Au(bt())
  ), O = gs("history.columns", "6"), I = gs("inventory.interval", "300"), V = /* @__PURE__ */ T(b.read()), R = /* @__PURE__ */ T(w.read()), J = /* @__PURE__ */ T(O.read()), be = /* @__PURE__ */ T(I.read()), ee = ye(() => s.value?.gpu ?? ""), M = ye(() => {
    const j = s.value?.golden_gpu_order;
    return j && typeof j == "object" ? j : {};
  });
  async function C() {
    o.value = !0, i.value = null;
    try {
      const [j, D] = await Promise.all([xr(), vl()]);
      s.value = j, n.value = D.level, r.value = D.effective || D.level, bl(j), l.value = !0;
    } catch (j) {
      throw i.value = j instanceof Error ? j.message : "Could not load Settings", j;
    } finally {
      o.value = !1, v && (v = !1, C());
    }
  }
  async function F(j) {
    a.value = !0, i.value = null;
    try {
      await lg(j);
      const D = await xr();
      s.value = D, bl(D), tt("settings");
    } catch (D) {
      try {
        s.value = await xr();
      } catch {
      }
      throw i.value = D instanceof Error ? D.message : "Could not save Settings", D;
    } finally {
      a.value = !1;
    }
  }
  async function Se(j) {
    const D = n.value;
    n.value = j, Rn("comfymodal_heavy_tracing", j);
    try {
      await cg(j);
      const le = await vl();
      r.value = le.effective || le.level, tt("settings");
    } catch (le) {
      throw n.value = D, Rn("comfymodal_heavy_tracing", D), le;
    }
  }
  async function Ce(j) {
    const D = bg("comfymodal_skip_plan_validation");
    Rn("comfymodal_skip_plan_validation", j ? "1" : "0");
    try {
      await F({ skip_plan_validation: j });
    } catch (le) {
      if (D === null)
        try {
          localStorage.removeItem("comfymodal_skip_plan_validation");
        } catch {
        }
      else
        Rn("comfymodal_skip_plan_validation", D);
      throw le;
    }
  }
  async function Me() {
    d.value = null;
    try {
      const j = await ug();
      if (!j || j.status !== "ok" || !Array.isArray(j.profiles))
        throw new Error(
          j && j.message || "invalid catalog response"
        );
      const D = new Set(
        j.profiles.filter((x) => x && typeof x.name == "string").map((x) => x.name)
      );
      c.value = j.profiles.filter((x) => x && D.has(x.name));
      const le = s.value?.golden_profile, g = typeof le == "string" ? le : "";
      if (D.has(g))
        V.value = g;
      else if (!D.has(V.value)) {
        const x = typeof j.defaultProfile == "string" && D.has(j.defaultProfile) ? j.defaultProfile : "";
        V.value = x;
      }
      b.write(V.value), V.value && (f.value = await yl(
        V.value
      ));
    } catch (j) {
      throw d.value = j instanceof Error ? j.message : "Could not load Golden profiles", j;
    }
  }
  function He(j) {
    V.value = j, b.write(j);
  }
  function ue(j) {
    const D = R.value.includes(j) ? R.value.filter((le) => le !== j) : [...R.value, j];
    R.value = D, w.write(D);
  }
  async function W(j, D) {
    await dg(j, D);
    const le = await xr();
    s.value = le, tt("settings");
  }
  async function E(j) {
    const D = Pt(), le = D.start({ kind: "deploy", label: `Deploy Golden ${j}` });
    y.value = !0;
    try {
      await fg(j), await jn({
        intervalMs: 2e3,
        run: async () => {
          const g = await yl(j), x = String(g?.state ?? "unknown");
          return D.patch(le, { message: `Golden deploy: ${x}` }), g;
        },
        done: (g) => g?.state === "done" || g?.state === "failed"
      }).then((g) => {
        if (g?.state === "failed")
          throw new Error(String(g.output || g.message || "Golden deploy failed"));
        f.value = g;
      }), D.finish(le, "Golden deploy finished"), await Me();
    } catch (g) {
      throw D.fail(
        le,
        g instanceof Error ? g.message : "Golden deploy failed"
      ), g;
    } finally {
      y.value = !1;
    }
    return le;
  }
  function _(j) {
    J.value = j, O.write(j);
  }
  function X(j) {
    be.value = j, I.write(j);
  }
  async function ne(j) {
    if (j === "generation") {
      An(["comfymodal_gpu", "comfymodal_preview_default", "comfymodal_preview_codec", "comfymodal_preview_quality", "comfymodal_data_saver_default", "comfymodal_data_saver_codec", "comfymodal_data_saver_quality"]);
      const D = s.value?.default_gpu || "rtx-pro-6000";
      await F({ gpu: D, golden_profile: null }), He("");
    } else j === "outputs" ? (An(["comfymodal_output_format", "comfymodal_quality", "comfymodal_webp_lossless_compression", "comfymodal_auto_save_local", "comfymodal_save_folder", "comfymodal_save_metadata_sidecar"]), await F({
      output_format: "original",
      quality: 75,
      webp_lossless_compression: "balanced",
      auto_save_local: !1,
      save_metadata_sidecar: !0
    })) : j === "interface" ? (An(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1", "comfymodal_remote_inventory_refresh_interval_s", "comfymodal-studio-history-columns"]), _("6"), X("300")) : j === "advanced" && (An(["comfymodal_heavy_tracing", "comfymodal_skip_plan_validation"]), await Se("off").catch(() => {
    }), await F({ skip_plan_validation: !1 }).catch(() => {
    }));
    tt("settings");
  }
  async function Xe() {
    An(yg), He(""), R.value = [], w.write([]), _("6"), X("300");
    const j = s.value?.default_gpu || "rtx-pro-6000";
    await F({ gpu: j, golden_profile: null }).catch(() => {
    }), await Se("off").catch(() => {
    }), await F({ skip_plan_validation: !1 }).catch(() => {
    }), await C().catch(() => {
    });
  }
  async function qe() {
    A || (A = yo((j) => {
      if (j === "settings") {
        if (o.value) {
          v = !0;
          return;
        }
        C();
      }
    })), l.value || await C(), Rn("comfymodal_heavy_tracing", n.value);
  }
  function mt(j) {
    Ou.includes(j) && (e.value = j);
  }
  function at(j) {
    t.value = j, Bo.write(j);
  }
  function We() {
    e.value = "generation", t.value = "comfortable", Bo.write("comfortable");
  }
  const Oe = bn();
  async function q(j) {
    const D = await Oe.run(j);
    return D.stale ? null : D.value;
  }
  return {
    activeSection: e,
    density: t,
    config: s,
    profileLevel: n,
    effectiveProfileLevel: r,
    loading: o,
    saving: a,
    error: i,
    bootstrapped: l,
    goldenProfiles: c,
    goldenError: d,
    goldenDeployState: f,
    goldenDeploying: y,
    selectedGoldenProfile: V,
    favoriteGoldenProfiles: R,
    columnsPreference: J,
    refreshIntervalPreference: be,
    gpu: ee,
    goldenGpuOrder: M,
    outputPreferences: ye(() => s.value ? {
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
    load: C,
    initialize: qe,
    save: F,
    setProfile: Se,
    setSkipPlanValidation: Ce,
    loadGolden: Me,
    selectGoldenProfile: He,
    toggleGoldenFavorite: ue,
    setGoldenGpuOrder: W,
    deployGoldenProfile: E,
    setHistoryColumns: _,
    setInventoryInterval: X,
    resetSection: ne,
    resetAll: Xe,
    loadSubresource: q,
    setSection: mt,
    setDensity: at,
    reset: We
  };
});
function qo(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const r = String(n.id ?? "");
    return { id: r, label: String(n.label ?? r), isActive: r !== "" && r === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function Tu(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function wg(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function _g() {
  return oe("/workspaces");
}
async function xg(e) {
  return oe("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function _l() {
  return Tu(await oe("/deploy/status"));
}
async function kg() {
  return oe("/deploy", { method: "POST" });
}
async function Sg() {
  return oe("/deploy/log");
}
async function Cg(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return oe(`/studio/inventory/refresh${t}`);
}
async function $g(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return oe(`/studio/models${s}`);
}
async function Ig(e = !1) {
  return oe("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function Rg() {
  return oe("/studio/custom-nodes");
}
async function Ag() {
  return oe("/studio/custom-nodes/refresh", { method: "POST" });
}
async function Eg(e) {
  return oe("/workspaces", { method: "POST", body: e });
}
async function Og(e) {
  return oe("/workspaces/swap", { method: "POST", body: e });
}
async function Tg(e) {
  return oe(`/workspaces/swap/${encodeURIComponent(e)}`);
}
function Pg(e, t) {
  return { workspace_id: e, confirm: !0, selected_keys: t.slice() };
}
function xl(e) {
  const t = String(e && e.phase || "");
  if (t === "downloading_models") {
    const s = String(e && e.download_message || ""), n = Number(e && e.download_completed || 0), r = Number(e && e.download_total || 0) + Number(e && e.download_skipped || 0);
    return s || `Preparing downloads… ${n}/${r}`;
  }
  return t === "syncing_custom_nodes" ? String(e && e.sync_message || "Syncing custom nodes to Modal…") : t === "deploying" ? String(e && e.deploy_message || "Deploying workspace…") : t ? `Phase: ${t.replace(/_/g, " ")}` : "";
}
async function Ng() {
  return oe("/studio/custom-nodes/sync-status");
}
async function Mg() {
  return oe("/studio/custom-nodes/sync", { method: "POST" });
}
async function zg() {
  return oe("/studio/custom-nodes/sync/rebuild-dependencies", { method: "POST" });
}
async function jg(e) {
  return oe(`/studio/custom-nodes/sync/status/${encodeURIComponent(e)}`);
}
async function Dg(e) {
  return oe("/model/install", { method: "POST", body: e });
}
function Lg(e) {
  const s = String(e || "").split("?")[0].split("#")[0].split("/").filter(Boolean).pop() || "";
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}
async function Ug(e) {
  return oe(`/download/status/${encodeURIComponent(e || "")}`);
}
async function Vg(e) {
  return oe("/studio/models/install-request", { method: "POST", body: e });
}
async function Fg(e) {
  return oe("/studio/custom-nodes/install-request", { method: "POST", body: e });
}
async function Wg() {
  return oe("/manifest/repair/scan", { method: "POST" });
}
async function Bg(e) {
  return oe("/manifest/repair/apply", { method: "POST", body: { updates: e } });
}
async function qg(e, t) {
  return oe("/manifest/repair/delete-placeholder", { method: "POST", body: { folder: e, filename: t } });
}
async function Gg() {
  return oe("/auth/status");
}
async function kl(e) {
  return oe(e === "civitai" ? "/civitai-token" : "/hf-token");
}
async function Hg(e, t) {
  return oe(e === "civitai" ? "/civitai-token" : "/hf-token", { method: "POST", body: { token: t } });
}
function Sl(e) {
  return !!(e && typeof e == "object" && typeof e.token == "string" && e.token !== "");
}
async function Zg() {
  return oe("/health?mode=deploy");
}
const bo = /* @__PURE__ */ _n("studio-infrastructure", () => {
  const e = /* @__PURE__ */ T("unknown"), t = /* @__PURE__ */ T(null), s = /* @__PURE__ */ T(null), n = /* @__PURE__ */ T([]), r = /* @__PURE__ */ T(null), o = /* @__PURE__ */ T(Tu(null)), a = /* @__PURE__ */ T(null), i = /* @__PURE__ */ T([]), l = /* @__PURE__ */ T([]), c = /* @__PURE__ */ T([]), d = /* @__PURE__ */ T(null), f = /* @__PURE__ */ T(!1), y = /* @__PURE__ */ T(null), v = /* @__PURE__ */ T(!1), A = /* @__PURE__ */ T(null), b = /* @__PURE__ */ T(null), w = /* @__PURE__ */ T(!1), O = /* @__PURE__ */ T(null), I = /* @__PURE__ */ T(!1), V = /* @__PURE__ */ T(!1), R = /* @__PURE__ */ T(null), J = /* @__PURE__ */ T(null), be = /* @__PURE__ */ T(null), ee = bn(), M = /* @__PURE__ */ T(null), C = /* @__PURE__ */ T(null), F = /* @__PURE__ */ T(null);
  let Se = !1, Ce = null;
  const Me = ye(() => n.value.find((Q) => Q.isActive) ?? null);
  function He(Q, de) {
    e.value = Q, t.value = de ?? null;
  }
  function ue(Q) {
    s.value = Q;
  }
  function W() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  function E(Q) {
    A.value = Q;
  }
  async function _() {
    const Q = qo(await _g());
    n.value = Q.rows, r.value = Q.activeId;
  }
  async function X() {
    o.value = await _l(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function ne() {
    const Q = await ee.run(async (Ee) => {
      const [je, Re] = await Promise.all([$g(), Rg()]);
      return Ee.aborted ? null : { modelResult: je, nodeResult: Re };
    });
    if (Q.stale || !Q.value) return;
    const de = Q.value.modelResult.models;
    i.value = (Array.isArray(de) ? de : []).filter(
      (Ee) => !!Ee && typeof Ee == "object"
    );
    const ce = Q.value.nodeResult.custom_nodes;
    c.value = (Array.isArray(ce) ? ce : []).filter(
      (Ee) => !!Ee && typeof Ee == "object"
    );
  }
  async function Xe() {
    f.value = !0, y.value = null;
    try {
      await Promise.all([_(), X(), ne()]), s.value = "server inventory loaded";
    } catch (Q) {
      throw y.value = Q instanceof Error ? Q.message : "Could not load infrastructure", Q;
    } finally {
      f.value = !1, Se && (Se = !1, Xe());
    }
  }
  async function qe() {
    Ce || (Ce = yo((Q) => {
      if (Q === "workspace") {
        if (f.value) {
          Se = !0;
          return;
        }
        Xe();
      }
    })), n.value.length || await Xe();
  }
  async function mt(Q) {
    v.value = !0;
    try {
      const de = await Eg(Q), ce = qo(de);
      n.value = ce.rows, r.value = ce.activeId, tt("workspace");
    } finally {
      v.value = !1;
    }
  }
  async function at(Q) {
    if (C.value || F.value)
      throw new Error("Cannot change workspace while an operation is active");
    v.value = !0;
    const de = n.value;
    try {
      const ce = await xg(Q);
      if (!ce || ce.status !== "ok")
        throw new Error(String(ce?.message || "Activation failed"));
      const Ee = qo(ce);
      n.value = Ee.rows, r.value = Ee.activeId, E(`Active workspace is now ${Ee.rows.find((je) => je.isActive)?.label || Q}.`), await X(), tt("workspace");
    } catch (ce) {
      throw n.value = de, ce;
    } finally {
      v.value = !1;
    }
  }
  async function We(Q, de) {
    const ce = Pt();
    if (C.value || F.value)
      throw new Error("Another operation is already active");
    v.value = !0, w.value = !1, b.value = null;
    const Ee = r.value ?? void 0, je = ce.start({
      kind: "workspace-swap",
      label: "Swap workspace",
      workspaceId: Ee
    });
    F.value = je;
    const Re = new AbortController(), B = window.setTimeout(() => Re.abort(), 1800 * 1e3);
    try {
      const Y = await Og({ workspace_id: Q, ...de || {} }), _e = String(Y.status || "");
      if (_e === "busy") throw new Error(String(Y.message || "Deploy already running — try again later."));
      if (_e === "error") throw new Error(String(Y.message || "Workspace swap failed."));
      if (_e === "confirm_required") {
        w.value = !0, ce.patch(je, { status: "pending", message: "Confirmation required" });
        return;
      }
      if (_e === "repair_required")
        throw ce.fail(je, String(Y.message || "manifest repair required")), await P(), new Error(String(Y.message || "manifest repair required"));
      if (_e === "review_required") {
        const Z = (Array.isArray(Y.to_install) ? Y.to_install : []).map((pe) => {
          const Be = pe;
          return {
            key: `${String(Be.save_path || Be.folder || "")}/${String(Be.filename || "")}`,
            filename: String(Be.filename || ""),
            folder: String(Be.folder || Be.save_path || "")
          };
        });
        b.value = {
          workspaceLabel: String(Y.workspace_label || Q),
          toInstall: Z,
          installCount: Number(Y.install_count || Z.length),
          presentCount: Number(Y.present_count || 0),
          removeCount: Array.isArray(Y.to_remove) ? Y.to_remove.length : 0
        }, ce.patch(je, { status: "pending", message: "Review required" });
        return;
      }
      if (_e === "started" && Y.swap_id) {
        await D(String(Y.swap_id), je, Re.signal, Ee);
        return;
      }
      throw new Error(String(Y.message || "Unexpected swap response."));
    } catch (Y) {
      if (w.value || b.value) throw Y;
      const _e = Y instanceof Error ? Y.message : "Workspace swap failed";
      throw ce.fail(je, _e), E(_e), Y;
    } finally {
      window.clearTimeout(B), !w.value && !b.value && (F.value = null), v.value = !1;
    }
  }
  async function Oe(Q) {
    w.value = !1, F.value = null, await We(Q, { confirm_prompt_interrupt: !0 });
  }
  async function q(Q, de) {
    const ce = F.value;
    b.value = null, F.value = null, ce && Pt().cancel(ce, "Superseded by review confirmation"), await We(Q, Pg(Q, de));
  }
  async function j() {
    const Q = F.value;
    w.value = !1, b.value = null, F.value = null, v.value = !1, Q && Pt().cancel(Q, "Swap cancelled."), E("Swap cancelled.");
  }
  async function D(Q, de, ce, Ee) {
    const je = Pt();
    try {
      await jn({
        intervalMs: 1e3,
        signal: ce,
        run: async () => {
          const Re = await Tg(Q);
          return je.patch(de, { message: xl(Re) || "Working…" }), E(xl(Re) || "Working…"), Re;
        },
        done: (Re) => String(Re.status || "") !== "running"
      }).then((Re) => {
        const B = String(Re.status || "");
        if (B === "ok") {
          const Y = String(Re.workspace_label || "workspace");
          je.finish(de, `Swap done — ${Y}. Deploy started.`), E(`Done — ${Y}. Deploy started.`);
        } else throw B === "repair_required" ? (je.fail(de, String(Re.message || "manifest repair required")), P(), new Error(String(Re.message || "manifest repair required"))) : B === "not_found" ? new Error("Swap status unavailable.") : new Error(
          String(Re.message || Re.error || Re.deploy_message || "Workspace swap failed")
        );
      }), Ee && r.value, await _(), await X(), tt("workspace");
    } catch (Re) {
      if (!w.value && !b.value) {
        const B = Re instanceof Error ? Re.message : "Workspace swap failed";
        try {
          je.fail(de, B);
        } catch {
        }
        E(B);
      }
      throw Re;
    } finally {
      F.value = null;
    }
  }
  async function le() {
    const Q = Pt();
    if (C.value) return C.value;
    if (F.value) throw new Error("Cannot deploy while a swap is active");
    const de = r.value ?? void 0, ce = Q.start({
      kind: "deploy",
      label: "Deploy workspace",
      workspaceId: de
    });
    C.value = ce;
    const Ee = new AbortController();
    M.value = Ee;
    const je = window.setTimeout(() => Ee.abort(new DOMException("Deployment polling timed out", "TimeoutError")), 600 * 1e3);
    try {
      await kg(), Q.patch(ce, { status: "running", message: "Deployment started" });
      const Re = await jn({
        intervalMs: 3e3,
        signal: Ee.signal,
        run: async () => {
          const B = await _l();
          return o.value = B, e.value = B.state, t.value = B.message || null, Q.patch(ce, { message: B.message || `Deployment: ${B.state}` }), B;
        },
        done: (B) => B.state === "ready" || B.state === "deployed_unwarmed" || B.state !== "deploying" && B.state !== "starting" && B.state !== "unknown"
      });
      if (!wg(Re.state)) throw new Error(Re.message || `Deployment ended in ${Re.state}`);
      if (de && r.value !== de) throw new Error("Deployment target workspace changed");
      Q.finish(ce, Re.message || "Deployment completed");
    } catch (Re) {
      const B = Re instanceof Error ? Re.message : "Deployment failed";
      throw Q.fail(ce, B), Re;
    } finally {
      window.clearTimeout(je), M.value = null, C.value = null;
    }
    return ce;
  }
  async function g() {
    const [Q, de, ce] = await Promise.all([
      Gg().catch(() => null),
      kl("hf").catch(() => null),
      kl("civitai").catch(() => null)
    ]);
    O.value = !!(Q && Q.connected === !0), I.value = Sl(de), V.value = Sl(ce);
  }
  async function x(Q, de) {
    const ce = await Hg(Q, de);
    if (!ce || ce.status !== "ok")
      throw new Error(String(ce?.message || ce?.error || "Save failed."));
    return await g(), de ? "Saved." : "Cleared.";
  }
  async function P() {
    J.value = null;
    const Q = await Wg();
    R.value = Q;
  }
  async function z(Q) {
    J.value = null;
    const de = await Bg(Q);
    J.value = String(de.message || "Repairs applied."), R.value = de;
  }
  async function $(Q, de) {
    await qg(Q, de), await P();
  }
  async function m() {
    d.value = await Ng();
  }
  async function h() {
    const Q = Pt(), de = Q.start({ kind: "node-sync", label: "Push custom-node plugins" });
    try {
      await Mg(), Q.finish(de, "Plugins pushed"), await m(), tt("workspace");
    } catch (ce) {
      throw Q.fail(de, ce instanceof Error ? ce.message : "Push failed"), ce;
    }
  }
  async function N() {
    const Q = Pt(), de = Q.start({ kind: "node-sync", label: "Rebuild custom-node dependencies" });
    try {
      const ce = await zg(), Ee = String(ce.sync_id || ce.syncId || "");
      Ee && await jn({
        intervalMs: 3e3,
        run: async () => {
          const je = await jg(Ee);
          return Q.patch(de, { message: String(je.message || "Rebuilding…") }), je;
        },
        done: (je) => String(je.status || "") !== "running"
      }), Q.finish(de, "Dependencies rebuilt"), await m(), tt("workspace");
    } catch (ce) {
      throw Q.fail(de, ce instanceof Error ? ce.message : "Rebuild failed"), ce;
    }
  }
  async function U(Q) {
    const de = Pt(), ce = de.start({ kind: "model-download", label: `Download ${String(Q.filename || Q.url || "model")}` });
    try {
      const Ee = await Dg(Q), je = String(Ee.download_id || Ee.downloadId || "");
      if (!je) {
        de.finish(ce, "Install request accepted"), await ne();
        return;
      }
      await jn({
        intervalMs: 2e3,
        run: async () => {
          const Re = await Ug(je);
          return de.patch(ce, {
            progress: typeof Re.progress == "number" ? Re.progress : void 0,
            message: String(Re.message || "Downloading…")
          }), Re;
        },
        done: (Re) => String(Re.status || "") !== "running"
      }).then((Re) => {
        if (String(Re.status || "") === "error")
          throw new Error(String(Re.message || "Download failed"));
      }), de.finish(ce, "Download complete"), await ne(), tt("workspace");
    } catch (Ee) {
      throw de.fail(ce, Ee instanceof Error ? Ee.message : "Download failed"), Ee;
    }
  }
  async function G(Q) {
    await Vg(Q), await ne();
  }
  async function ge(Q) {
    await Fg(Q), await ne();
  }
  async function ie() {
    await Cg(0), await ne(), s.value = "inventory refreshed", tt("workspace");
  }
  async function xe(Q = !0) {
    const de = await Ig(Q);
    i.value = Array.isArray(de.models) ? de.models.filter((ce) => !!ce && typeof ce == "object") : i.value, await ne();
  }
  async function Ie() {
    const Q = await Ag();
    c.value = Array.isArray(Q.custom_nodes) ? Q.custom_nodes.filter((de) => !!de && typeof de == "object") : c.value, await ne();
  }
  async function Le() {
    a.value = await Sg();
  }
  async function Ze() {
    be.value = await Zg();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: r,
    activeWorkspace: Me,
    deployStatus: o,
    deployLog: a,
    models: i,
    modelTypes: l,
    customNodes: c,
    customNodeSync: d,
    loading: f,
    error: y,
    busy: v,
    progress: A,
    swapReview: b,
    swapConfirmRequired: w,
    authConnected: O,
    hfConfigured: I,
    civitaiConfigured: V,
    repairIssues: R,
    repairMessage: J,
    health: be,
    deploymentOperationId: C,
    swapOperationId: F,
    setDeploy: He,
    setSyncSummary: ue,
    reset: W,
    load: Xe,
    initialize: qe,
    loadWorkspaces: _,
    loadDeployment: X,
    loadInventory: ne,
    saveWorkspace: mt,
    selectWorkspace: at,
    startSwap: We,
    confirmSwapInterrupt: Oe,
    confirmSwapReview: q,
    cancelSwapDialog: j,
    deploy: le,
    loadCredentials: g,
    saveCredential: x,
    scanRepair: P,
    applyRepair: z,
    deletePlaceholder: $,
    loadSyncStatus: m,
    pushPlugins: h,
    rebuildDependencies: N,
    installModel: U,
    installModelRequest: G,
    installCustomNode: ge,
    refreshRemoteInventoryNow: ie,
    rescanModelsNow: xe,
    refreshCustomNodesNow: Ie,
    loadLog: Le,
    loadHealth: Ze
  };
});
function Ka(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return Object.prototype.hasOwnProperty.call(t, "workflow") ? t.workflow : Object.prototype.hasOwnProperty.call(t, "version") ? t.version : Object.prototype.hasOwnProperty.call(t, "mapping") ? t.mapping : e;
}
async function Kg(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.tag && t.set("tag", e.tag), e.folder && t.set("folder", e.folder), e.favorite && t.set("favorite", "1");
  const s = t.toString() ? `?${t}` : "";
  return oe(`/studio/workflows${s}`);
}
async function Jg(e) {
  return oe(`/studio/workflows/${encodeURIComponent(e)}`).then((t) => ({ ...t, workflow: Ka(t) }));
}
async function Qg(e) {
  return oe(`/studio/workflows/${encodeURIComponent(e)}/versions`);
}
async function Yg(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}`).then((t) => Ka(t));
}
async function Xg(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`).then((t) => Ka(t));
}
async function ev(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/candidates`);
}
async function tv(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/dependencies`);
}
async function sv(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`);
}
async function Cl(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/portability`);
}
async function nv() {
  return oe("/studio/workflows/folders");
}
async function rv() {
  return oe("/studio/workflows/tags");
}
async function $l(e, t) {
  return oe(`/studio/workflows/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function ov(e) {
  return oe("/studio/workflows", { method: "POST", body: e });
}
async function av(e) {
  return oe("/studio/workflows/import", { method: "POST", body: e });
}
async function iv(e) {
  return oe(`/studio/workflows/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function lv(e) {
  return oe("/studio/workflows/folders", { method: "POST", body: { path: e } });
}
async function cv(e, t) {
  return oe(`/studio/workflows/${encodeURIComponent(e)}/versions`, { method: "POST", body: t });
}
async function uv(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/state`);
}
async function dv(e, t) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`, { method: "POST", body: t });
}
async function fv(e, t) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/revision`, { method: "POST", body: t });
}
async function mv(e, t) {
  return oe(`/studio/workflows/${encodeURIComponent(e)}/dependencies/nonessential`, { method: "POST", body: { keys: t } });
}
async function pv(e, t) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`, { method: "PATCH", body: t });
}
async function hv(e, t) {
  return oe(`/studio/method-compat?workflow_id=${encodeURIComponent(e)}&version_id=${encodeURIComponent(t)}`);
}
async function gv(e) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`);
}
async function vv(e, t) {
  return oe(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`, { method: "POST", body: t });
}
async function yv(e, t) {
  return oe(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function bv(e) {
  return oe(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function wv(e, t = {}) {
  return oe(`/studio/workflows/presets/${encodeURIComponent(e)}/duplicate`, { method: "POST", body: t });
}
async function _v(e, t) {
  return oe(`/studio/workflows/presets/${encodeURIComponent(e)}/copy-to-version`, { method: "POST", body: { workflow_version_id: t } });
}
async function xv(e, t) {
  return oe(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`);
}
async function kv(e) {
  return oe("/studio/guidance-mappings", { method: "POST", body: { mapping: e } });
}
async function Sv(e, t) {
  return oe(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`, { method: "DELETE" });
}
async function Cv(e) {
  const t = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(e)}/export`);
  if (!t.ok) return { ok: !1, message: `Export failed with status ${t.status}` };
  const s = await t.blob(), n = t.headers.get("Content-Disposition") || "", r = /filename="?([^";]+)"?/.exec(n);
  return { ok: !0, blob: s, filename: r ? r[1].trim() : "manifest.json" };
}
async function Il(e, t = !0) {
  return oe(`/studio/workflows/import-manifest?dry_run=${t ? "1" : "0"}`, { method: "POST", body: e });
}
function $v(e) {
  const t = String(e || "t2i").toLowerCase();
  return t === "txt2img" ? "t2i" : t;
}
const cs = ["feature-type", "required-bindings", "exposed-controls", "details"];
function Dn(e) {
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
function Iv(e, t, s) {
  if (!e || e.length > 12e3) return null;
  try {
    const n = JSON.parse(e);
    return n.v !== 1 || n.workflowId !== t || n.versionId !== s ? null : Dn(n);
  } catch {
    return null;
  }
}
async function dr(e, t) {
  try {
    const s = await fetch(e, t);
    let n = "";
    try {
      n = await s.text();
    } catch {
      n = "";
    }
    let r = null;
    if (n)
      try {
        r = JSON.parse(n);
      } catch {
        r = { message: n };
      }
    return { ok: s.ok, status: s.status, data: r };
  } catch {
    return null;
  }
}
async function Rv(e) {
  return dr("/customnode/install/git_url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: e })
  });
}
async function Av(e) {
  return dr("/manager/queue/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(e || {})
  });
}
async function Ev() {
  return dr("/manager/queue/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
}
async function Ov() {
  return dr("/customnode/getlist?mode=default&skip_update=true");
}
async function Tv() {
  return dr("/customnode/getmappings?mode=default");
}
function $a(e) {
  return String(e || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}
function Pu(e) {
  return String(e || "").split("/").filter(Boolean).pop() || "";
}
function Pv(e) {
  try {
    return new RegExp(e);
  } catch {
    return null;
  }
}
function Nv(e, t) {
  const s = {}, n = {}, r = {}, o = [], a = (l, c, d) => {
    const f = String(c ?? "").toLowerCase();
    f && !l[f] && (l[f] = d);
  }, i = (l, c) => {
    const d = {
      key: String(l),
      name: String(c.title || c.name || l),
      cnrId: String(c.cnr_id || c.id || l),
      repository: String(c.repository || ""),
      version: String(c.version || "unknown"),
      selected_version: String(c.selected_version || "latest"),
      channel: String(c.channel || "default"),
      mode: String(c.mode || "default"),
      install_type: String(c.install_type || ""),
      files: Array.isArray(c.files) ? c.files : []
    };
    s[String(l).toLowerCase()] = d;
    const f = String(c.repository || "");
    return f && (a(s, $a(f), d), a(s, Pu(f).toLowerCase(), d)), d;
  };
  for (const [l, c] of Object.entries(e || {}))
    c && typeof c == "object" && i(l, c);
  if (t && typeof t == "object")
    for (const [l, c] of Object.entries(t)) {
      const d = Array.isArray(c) ? c[0] : c.classes, f = Array.isArray(c) ? c[1] : {}, y = s[String(l).toLowerCase()] || s[$a(l)];
      if (y) {
        if (Array.isArray(f.preemptions))
          for (const v of f.preemptions) a(r, v, y);
        if (typeof f.nodename_pattern == "string") {
          const v = Pv(f.nodename_pattern);
          v && o.push({ re: v, record: y });
        }
      }
      for (const v of Array.isArray(d) ? d : [])
        y && a(n, v, y);
    }
  return { packs: s, byClass: n, preemptions: r, patterns: o };
}
function Mv(e, t) {
  if (!t || !e) return null;
  for (const r of [e.cnr_id, e.aux_id]) {
    if (!r) continue;
    const o = String(r), a = t.packs[o.toLowerCase()] || t.packs[$a(o)] || t.packs[Pu(o).toLowerCase()];
    if (a) return a;
  }
  const s = Array.isArray(e.classes) ? e.classes : e.classes ? [e.classes] : [], n = s.map((r) => String(r ?? "").toLowerCase()).filter(Boolean);
  for (const r of n)
    if (t.preemptions[r]) return t.preemptions[r];
  for (const r of n)
    if (t.byClass[r]) return t.byClass[r];
  for (const r of s) {
    const o = String(r ?? "");
    if (o) {
      for (const a of t.patterns || [])
        if (a.re.test(o)) return a.record;
    }
  }
  return null;
}
function zv(e, t) {
  const s = Mv(e, t);
  if (s)
    return { kind: "cnr", pack: s, url: "", name: s.name || String(e.name || "") };
  const n = String(e.repository_url || "");
  return n ? { kind: "git", pack: null, url: n, name: String(e.name || "") } : { kind: "none", pack: null, url: "", name: String(e.name || "") };
}
function jv(e) {
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
async function Dv(e) {
  if (!e || e.kind === "none")
    return { ok: !1, message: "No Manager install target identified for this pack." };
  try {
    if (e.kind === "cnr") {
      const r = await Av(jv(e.pack));
      if (!r) return { ok: !1, message: "Could not reach ComfyUI-Manager." };
      if (r.status === 403)
        return { ok: !1, message: "Manager refused the CNR install (403). Raise Manager's security level, then retry." };
      if (!r.ok) {
        const a = r.data, i = a && (a.message || a.error) || `HTTP ${r.status}`;
        return { ok: !1, message: `Install failed: ${String(i)}` };
      }
      const o = await Ev();
      return !o || !o.ok ? { ok: !1, message: "Install queued, but Manager did not start it. Open ComfyUI-Manager and press Start." } : { ok: !0, message: "Install queued through ComfyUI-Manager — restart ComfyUI to load it." };
    }
    const t = await Rv(e.url);
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
const En = "comfymodal.studio.wizard.draft.v1", Ja = /* @__PURE__ */ _n("studio-workflows", () => {
  const e = /* @__PURE__ */ T([]), t = /* @__PURE__ */ T(null), s = /* @__PURE__ */ T(null), n = /* @__PURE__ */ T([]), r = /* @__PURE__ */ T(null), o = /* @__PURE__ */ T(null), a = /* @__PURE__ */ T(null), i = /* @__PURE__ */ T(null), l = /* @__PURE__ */ T(null), c = /* @__PURE__ */ T(null), d = /* @__PURE__ */ T([]), f = /* @__PURE__ */ T(null), y = /* @__PURE__ */ T(null), v = /* @__PURE__ */ T(""), A = /* @__PURE__ */ T(""), b = /* @__PURE__ */ T(!1), w = /* @__PURE__ */ T(""), O = /* @__PURE__ */ T(!1), I = /* @__PURE__ */ T(null), V = /* @__PURE__ */ T(!1), R = /* @__PURE__ */ T(null), J = /* @__PURE__ */ T(!1), be = /* @__PURE__ */ T(null), ee = /* @__PURE__ */ T(null), M = /* @__PURE__ */ T(null), C = /* @__PURE__ */ T(null), F = bn(), Se = /* @__PURE__ */ T(null), Ce = /* @__PURE__ */ T({});
  let Me = null;
  function He(B) {
    t.value = B;
  }
  function ue() {
    t.value = null, s.value = null, n.value = [], r.value = null;
  }
  async function W() {
    O.value = !0, I.value = null;
    try {
      const [B, Y, _e] = await Promise.all([
        Kg({ search: w.value, tag: v.value || void 0, folder: A.value || void 0, favorite: b.value || void 0 }),
        nv().catch(() => null),
        rv().catch(() => null)
      ]);
      e.value = B.workflows ?? [], f.value = Y, y.value = _e;
    } catch (B) {
      throw I.value = B instanceof Error ? B.message : "Could not load workflows", B;
    } finally {
      O.value = !1;
    }
  }
  async function E() {
    Me || (Me = yo((B) => {
      B === "workflows" && !O.value && W();
    })), e.value.length || await W();
  }
  async function _(B) {
    t.value = B;
    const Y = await F.run(async (pe) => {
      const [Be, it] = await Promise.all([Jg(B), Qg(B)]);
      return pe.aborted ? null : { workflowResponse: Be, versionsResponse: it };
    });
    if (Y.stale || !Y.value) return;
    s.value = Y.value.workflowResponse.workflow ?? null, n.value = Y.value.versionsResponse.versions ?? [];
    const _e = s.value?.latest_version_id, Z = n.value.find((pe) => pe.workflow_version_id === _e) ?? n.value.at(-1) ?? null;
    Z && await X(Z.workflow_version_id);
  }
  async function X(B) {
    const Y = await F.run(async (Z) => {
      const [pe, Be, it, kt, Ue, Ke, Tt] = await Promise.all([
        Yg(B),
        Xg(B),
        tv(B),
        sv(B),
        Cl(B),
        gv(B),
        uv(B)
      ]);
      return Z.aborted ? null : { versionResponse: pe, mappingResponse: Be, dependencyResponse: it, compatibilityResponse: kt, portabilityResponse: Ue, presetsResponse: Ke, stateResponse: Tt };
    });
    if (Y.stale || !Y.value) return;
    r.value = Y.value.versionResponse, o.value = Y.value.mappingResponse, a.value = null, i.value = Y.value.dependencyResponse, l.value = Y.value.compatibilityResponse, c.value = Y.value.portabilityResponse, ee.value = Y.value.stateResponse;
    const _e = Y.value.presetsResponse;
    d.value = _e.presets ?? [], s.value && B && (M.value = await hv(s.value.workflow_id, B).catch(() => null));
  }
  async function ne() {
    r.value && (a.value = await ev(r.value.workflow_version_id));
  }
  function Xe() {
    const B = s.value?.workflow_id ?? "", Y = r.value?.workflow_version_id ?? "";
    try {
      R.value = Iv(sessionStorage.getItem(En), B, Y) ?? Dn({ workflowId: B, versionId: Y, featureType: $v(s.value?.workflow_type) });
    } catch {
      R.value = Dn({ workflowId: B, versionId: Y });
    }
    V.value = !0;
  }
  function qe() {
    try {
      const B = typeof performance < "u" && typeof performance.getEntriesByType == "function" ? performance.getEntriesByType("navigation") : [], Y = B && B[0] && B[0].type;
      if (Y) return Y === "reload" || Y === "back_forward";
      const _e = performance.navigation;
      return !!_e && _e.type !== 0;
    } catch {
      return !1;
    }
  }
  async function mt() {
    if (V.value || !qe()) return !1;
    let B = null;
    try {
      B = sessionStorage.getItem(En);
    } catch {
      return !1;
    }
    if (!B) return !1;
    let Y = null;
    try {
      const _e = JSON.parse(B);
      if (_e.v !== 1 || !_e.workflowId || !_e.versionId) return !1;
      Y = Dn(_e);
    } catch {
      return !1;
    }
    try {
      await _(Y.workflowId);
    } catch {
      return !1;
    }
    return r.value?.workflow_version_id !== Y.versionId ? !1 : (R.value = Y, V.value = !0, !0);
  }
  function at(B) {
    if (R.value) {
      R.value = Dn({ ...R.value, ...B });
      try {
        sessionStorage.setItem(En, JSON.stringify(R.value));
      } catch {
      }
    }
  }
  function We(B) {
    at({ step: B });
  }
  function Oe() {
    V.value = !1, R.value = null;
    try {
      sessionStorage.removeItem(En);
    } catch {
    }
  }
  async function q(B) {
    t.value && (await $l(t.value, B), await W(), await _(t.value), tt("workflows"));
  }
  async function j(B, Y) {
    await $l(B, { favorite: Y }), await W(), tt("workflows");
  }
  async function D(B) {
    await ov(B), await W(), tt("workflows");
  }
  async function le(B) {
    const Y = Pt(), _e = Y.start({ kind: "workflow-import", label: "Import workflow" });
    try {
      await av(B), Y.finish(_e, "Workflow imported"), await W(), tt("workflows");
    } catch (Z) {
      throw Y.fail(_e, Z instanceof Error ? Z.message : "Import failed"), Z;
    }
  }
  async function g() {
    t.value && (await iv(t.value), ue(), await W(), tt("workflows"));
  }
  async function x(B) {
    await lv(B), await W();
  }
  async function P(B) {
    t.value && (await cv(t.value, B), await _(t.value), tt("workflows"));
  }
  async function z(B) {
    const Y = r.value?.workflow_version_id;
    if (!Y) throw new Error("No version selected");
    const _e = o.value;
    !!_e && typeof _e.mapping_id == "string" ? await fv(Y, B) : await dv(Y, B), await X(Y), tt("workflows");
  }
  async function $(B) {
    t.value && (await mv(t.value, B), r.value && await X(r.value.workflow_version_id));
  }
  async function m() {
    if (Se.value) return Se.value;
    try {
      const [B, Y] = await Promise.all([
        Ov(),
        Tv()
      ]), _e = (B?.data ?? {}).node_packs, Z = Y?.data ?? {};
      Se.value = Nv(
        _e ?? {},
        Z
      );
    } catch {
      Se.value = null;
    }
    return Se.value;
  }
  async function h(B) {
    const Y = String(B.name || B.cnr_id || "node"), _e = await m(), Z = zv(B, _e);
    Ce.value = { ...Ce.value, [Y]: "Installing…" };
    const pe = await Dv(Z);
    Ce.value = { ...Ce.value, [Y]: pe.message }, pe.ok && await bo().loadInventory().catch(() => {
    });
  }
  async function N(B) {
    r.value && (await pv(r.value.workflow_version_id, B), await X(r.value.workflow_version_id));
  }
  async function U() {
    r.value && (c.value = await Cl(r.value.workflow_version_id));
  }
  async function G() {
    if (!r.value) return;
    const B = await Cv(r.value.workflow_version_id);
    if (!B.ok || !B.blob) throw new Error(B.message || "Export failed");
    const Y = URL.createObjectURL(B.blob);
    try {
      const _e = document.createElement("a");
      _e.href = Y, _e.download = B.filename || "manifest.json", document.body.appendChild(_e), _e.click(), _e.remove();
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(Y), 1e3);
    }
  }
  async function ge(B) {
    const Y = await Il(B, !0);
    return C.value = Y, Y;
  }
  async function ie(B) {
    await Il(B, !1), C.value = null, await W(), tt("workflows");
  }
  function xe(B) {
    const Y = {};
    for (const [_e, Z] of Object.entries(B))
      Z instanceof Blob || typeof Z == "string" && (Z.startsWith("blob:") || Z.startsWith("data:image/")) || _e === "sourceImage" || _e === "referenceImages" || _e === "mask" || _e === "sketch" || _e === "generatedImages" || _e === "compareImages" || (Y[_e] = Z);
    return Y;
  }
  async function Ie(B) {
    r.value && (await vv(r.value.workflow_version_id, {
      ...B,
      studio_state: xe(B.studio_state)
    }), await X(r.value.workflow_version_id));
  }
  async function Le(B, Y) {
    const _e = Y.studio_state && typeof Y.studio_state == "object" ? { ...Y, studio_state: xe(Y.studio_state) } : Y;
    await yv(B, _e), r.value && await X(r.value.workflow_version_id);
  }
  async function Ze(B) {
    await bv(B), r.value && await X(r.value.workflow_version_id);
  }
  async function Q(B, Y) {
    await wv(B, Y ? { name: Y } : {}), r.value && await X(r.value.workflow_version_id);
  }
  async function de(B, Y) {
    await _v(B, Y), tt("workflows");
  }
  async function ce(B, Y) {
    return xv(B, Y);
  }
  async function Ee(B) {
    await kv(B);
  }
  async function je(B, Y) {
    await Sv(B, Y);
  }
  async function Re() {
    const B = R.value;
    if (!B) throw new Error("No wizard draft");
    const Y = B.bindings || {};
    if (!Object.values(Y).filter(
      (Z) => Z && typeof Z == "object" && Z.confirmed === !0
    ).length) throw new Error("Confirm at least one graph binding first");
    if (!B.outputBinding) throw new Error("Capture the output binding first");
    J.value = !0, be.value = null;
    try {
      await z({
        feature_type: B.featureType,
        bindings: B.bindings,
        output_binding: B.outputBinding,
        controls: B.controls,
        details: B.details
      });
      try {
        sessionStorage.removeItem(En);
      } catch {
      }
      R.value = null, V.value = !1;
    } catch (Z) {
      throw be.value = Z instanceof Error ? Z.message : "Mapping save failed", Z;
    } finally {
      J.value = !1;
    }
  }
  return {
    workflows: e,
    selectedId: t,
    selectedWorkflow: s,
    versions: n,
    selectedVersion: r,
    mapping: o,
    mappingCandidates: a,
    dependencies: i,
    compatibility: l,
    portability: c,
    presets: d,
    folders: f,
    tags: y,
    tagFilter: v,
    folderFilter: A,
    favoritesOnly: b,
    versionState: ee,
    methodCompat: M,
    manifestPreview: C,
    query: w,
    loading: O,
    error: I,
    wizardOpen: V,
    wizardDraft: R,
    wizardSaving: J,
    wizardError: be,
    select: He,
    clear: ue,
    loadList: W,
    initialize: E,
    selectWorkflow: _,
    selectVersion: X,
    loadMappingCandidates: ne,
    openWizard: Xe,
    updateWizard: at,
    setWizardStep: We,
    closeWizard: Oe,
    updateMetadata: q,
    maybeResumeWizard: mt,
    toggleFavorite: j,
    createNewWorkflow: D,
    importNewWorkflow: le,
    deleteSelectedWorkflow: g,
    createFolder: x,
    captureVersion: P,
    saveMapping: z,
    markNonessential: $,
    saveCompatibility: N,
    recheckPortability: U,
    loadManagerIndex: m,
    installDependencyNode: h,
    dependencyInstallMessage: Ce,
    exportManifest: G,
    previewManifestImport: ge,
    commitManifestImport: ie,
    sanitizePresetState: xe,
    createPreset: Ie,
    savePreset: Le,
    removePreset: Ze,
    duplicateCurrentPreset: Q,
    copyPresetForward: de,
    loadGuidance: ce,
    saveGuidance: Ee,
    removeGuidance: je,
    saveWizardMapping: Re
  };
});
function Nu(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = Nu(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function Mu() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = Nu(e)) && (n && (n += " "), n += t);
  return n;
}
const Lv = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, Uv = (e, t) => ({
  classGroupId: e,
  validator: t
}), zu = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), Jr = "-", Rl = [], Vv = "arbitrary..", Fv = (e) => {
  const t = Bv(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (a) => {
      if (a.startsWith("[") && a.endsWith("]"))
        return Wv(a);
      const i = a.split(Jr), l = i[0] === "" && i.length > 1 ? 1 : 0;
      return ju(i, l, t);
    },
    getConflictingClassGroupIds: (a, i) => {
      if (i) {
        const l = n[a], c = s[a];
        return l ? c ? Lv(c, l) : l : c || Rl;
      }
      return s[a] || Rl;
    }
  };
}, ju = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const r = e[t], o = s.nextPart.get(r);
  if (o) {
    const c = ju(e, t + 1, o);
    if (c) return c;
  }
  const a = s.validators;
  if (a === null)
    return;
  const i = t === 0 ? e.join(Jr) : e.slice(t).join(Jr), l = a.length;
  for (let c = 0; c < l; c++) {
    const d = a[c];
    if (d.validator(i))
      return d.classGroupId;
  }
}, Wv = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? Vv + n : void 0;
})(), Bv = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return qv(s, t);
}, qv = (e, t) => {
  const s = zu();
  for (const n in e) {
    const r = e[n];
    Qa(r, s, n, t);
  }
  return s;
}, Qa = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const a = e[o];
    Gv(a, t, s, n);
  }
}, Gv = (e, t, s, n) => {
  if (typeof e == "string") {
    Hv(e, t, s);
    return;
  }
  if (typeof e == "function") {
    Zv(e, t, s, n);
    return;
  }
  Kv(e, t, s, n);
}, Hv = (e, t, s) => {
  const n = e === "" ? t : Du(t, e);
  n.classGroupId = s;
}, Zv = (e, t, s, n) => {
  if (Jv(e)) {
    Qa(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(Uv(s, e));
}, Kv = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let a = 0; a < o; a++) {
    const [i, l] = r[a];
    Qa(l, Du(t, i), s, n);
  }
}, Du = (e, t) => {
  let s = e;
  const n = t.split(Jr), r = n.length;
  for (let o = 0; o < r; o++) {
    const a = n[o];
    let i = s.nextPart.get(a);
    i || (i = zu(), s.nextPart.set(a, i)), s = i;
  }
  return s;
}, Jv = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Qv = (e) => {
  if (e < 1)
    return {
      get: () => {
      },
      set: () => {
      }
    };
  let t = 0, s = /* @__PURE__ */ Object.create(null), n = /* @__PURE__ */ Object.create(null);
  const r = (o, a) => {
    s[o] = a, t++, t > e && (t = 0, n = s, s = /* @__PURE__ */ Object.create(null));
  };
  return {
    get(o) {
      let a = s[o];
      if (a !== void 0)
        return a;
      if ((a = n[o]) !== void 0)
        return r(o, a), a;
    },
    set(o, a) {
      o in s ? s[o] = a : r(o, a);
    }
  };
}, Ia = "!", Al = ":", Yv = [], El = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), Xv = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let a = 0, i = 0, l = 0, c;
    const d = r.length;
    for (let b = 0; b < d; b++) {
      const w = r[b];
      if (a === 0 && i === 0) {
        if (w === Al) {
          o.push(r.slice(l, b)), l = b + 1;
          continue;
        }
        if (w === "/") {
          c = b;
          continue;
        }
      }
      w === "[" ? a++ : w === "]" ? a-- : w === "(" ? i++ : w === ")" && i--;
    }
    const f = o.length === 0 ? r : r.slice(l);
    let y = f, v = !1;
    f.endsWith(Ia) ? (y = f.slice(0, -1), v = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      f.startsWith(Ia) && (y = f.slice(1), v = !0)
    );
    const A = c && c > l ? c - l : void 0;
    return El(o, v, y, A);
  };
  if (t) {
    const r = t + Al, o = n;
    n = (a) => a.startsWith(r) ? o(a.slice(r.length)) : El(Yv, !1, a, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, ey = (e) => {
  const t = /* @__PURE__ */ new Map();
  return e.orderSensitiveModifiers.forEach((s, n) => {
    t.set(s, 1e6 + n);
  }), (s) => {
    const n = [];
    let r = [];
    for (let o = 0; o < s.length; o++) {
      const a = s[o], i = a[0] === "[", l = t.has(a);
      i || l ? (r.length > 0 && (r.sort(), n.push(...r), r = []), n.push(a)) : r.push(a);
    }
    return r.length > 0 && (r.sort(), n.push(...r)), n;
  };
}, ty = (e) => ({
  cache: Qv(e.cacheSize),
  parseClassName: Xv(e),
  sortModifiers: ey(e),
  postfixLookupClassGroupIds: sy(e),
  ...Fv(e)
}), sy = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, ny = /\s+/, ry = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: a
  } = t, i = [], l = e.trim().split(ny);
  let c = "";
  for (let d = l.length - 1; d >= 0; d -= 1) {
    const f = l[d], {
      isExternal: y,
      modifiers: v,
      hasImportantModifier: A,
      baseClassName: b,
      maybePostfixModifierPosition: w
    } = s(f);
    if (y) {
      c = f + (c.length > 0 ? " " + c : c);
      continue;
    }
    let O = !!w, I;
    if (O) {
      const ee = b.substring(0, w);
      I = n(ee);
      const M = I && a[I] ? n(b) : void 0;
      M && M !== I && (I = M, O = !1);
    } else
      I = n(b);
    if (!I) {
      if (!O) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (I = n(b), !I) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      O = !1;
    }
    const V = v.length === 0 ? "" : v.length === 1 ? v[0] : o(v).join(":"), R = A ? V + Ia : V, J = R + I;
    if (i.indexOf(J) > -1)
      continue;
    i.push(J);
    const be = r(I, O);
    for (let ee = 0; ee < be.length; ++ee) {
      const M = be[ee];
      i.push(R + M);
    }
    c = f + (c.length > 0 ? " " + c : c);
  }
  return c;
}, oy = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = Lu(s)) && (r && (r += " "), r += n);
  return r;
}, Lu = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = Lu(e[n])) && (s && (s += " "), s += t);
  return s;
}, ay = (e, ...t) => {
  let s, n, r, o;
  const a = (l) => {
    const c = t.reduce((d, f) => f(d), e());
    return s = ty(c), n = s.cache.get, r = s.cache.set, o = i, i(l);
  }, i = (l) => {
    const c = n(l);
    if (c)
      return c;
    const d = ry(l, s);
    return r(l, d), d;
  };
  return o = a, (...l) => o(oy(...l));
}, iy = [], gt = (e) => {
  const t = (s) => s[e] || iy;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, Uu = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, Vu = /^\((?:(\w[\w-]*):)?(.+)\)$/i, ly = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, cy = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, uy = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, dy = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, fy = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, my = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, Cs = (e) => ly.test(e), Ve = (e) => !!e && !Number.isNaN(Number(e)), Ht = (e) => !!e && Number.isInteger(Number(e)), Go = (e) => e.endsWith("%") && Ve(e.slice(0, -1)), ls = (e) => cy.test(e), Fu = () => !0, py = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  uy.test(e) && !dy.test(e)
), Ya = () => !1, hy = (e) => fy.test(e), gy = (e) => my.test(e), vy = (e) => !he(e) && !ve(e), yy = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), by = (e) => Us(e, qu, Ya), he = (e) => Uu.test(e), Bs = (e) => Us(e, Gu, py), Ol = (e) => Us(e, Iy, Ve), wy = (e) => Us(e, Zu, Fu), _y = (e) => Us(e, Hu, Ya), Tl = (e) => Us(e, Wu, Ya), xy = (e) => Us(e, Bu, gy), kr = (e) => Us(e, Ku, hy), ve = (e) => Vu.test(e), On = (e) => Ys(e, Gu), ky = (e) => Ys(e, Hu), Pl = (e) => Ys(e, Wu), Sy = (e) => Ys(e, qu), Cy = (e) => Ys(e, Bu), Sr = (e) => Ys(e, Ku, !0), $y = (e) => Ys(e, Zu, !0), Us = (e, t, s) => {
  const n = Uu.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, Ys = (e, t, s = !1) => {
  const n = Vu.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, Wu = (e) => e === "position" || e === "percentage", Bu = (e) => e === "image" || e === "url", qu = (e) => e === "length" || e === "size" || e === "bg-size", Gu = (e) => e === "length", Iy = (e) => e === "number", Hu = (e) => e === "family-name", Zu = (e) => e === "number" || e === "weight", Ku = (e) => e === "shadow", Ry = () => {
  const e = gt("color"), t = gt("font"), s = gt("text"), n = gt("font-weight"), r = gt("tracking"), o = gt("leading"), a = gt("breakpoint"), i = gt("container"), l = gt("spacing"), c = gt("radius"), d = gt("shadow"), f = gt("inset-shadow"), y = gt("text-shadow"), v = gt("drop-shadow"), A = gt("blur"), b = gt("perspective"), w = gt("aspect"), O = gt("ease"), I = gt("animate"), V = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], R = () => [
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
  ], J = () => [...R(), ve, he], be = () => ["auto", "hidden", "clip", "visible", "scroll"], ee = () => ["auto", "contain", "none"], M = () => [ve, he, l], C = () => [Cs, "full", "auto", ...M()], F = () => [Ht, "none", "subgrid", ve, he], Se = () => ["auto", {
    span: ["full", Ht, ve, he]
  }, Ht, ve, he], Ce = () => [Ht, "auto", ve, he], Me = () => ["auto", "min", "max", "fr", ve, he], He = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], ue = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], W = () => ["auto", ...M()], E = () => [Cs, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...M()], _ = () => [i, Cs, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...M()], X = () => [Cs, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...M()], ne = () => [e, ve, he], Xe = () => [...R(), Pl, Tl, {
    position: [ve, he]
  }], qe = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], mt = () => ["auto", "cover", "contain", Sy, by, {
    size: [ve, he]
  }], at = () => [Go, On, Bs], We = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    ve,
    he
  ], Oe = () => ["", Ve, On, Bs], q = () => ["solid", "dashed", "dotted", "double"], j = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], D = () => [Ve, Go, Pl, Tl], le = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    A,
    ve,
    he
  ], g = () => ["none", Ve, ve, he], x = () => ["none", Ve, ve, he], P = () => [Ve, ve, he], z = () => [Cs, "full", ...M()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [ls],
      breakpoint: [ls],
      color: [Fu],
      container: [ls],
      "drop-shadow": [ls],
      ease: ["in", "out", "in-out"],
      font: [vy],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [ls],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [ls],
      shadow: [ls],
      spacing: ["px", Ve],
      text: [ls],
      "text-shadow": [ls],
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
        aspect: ["auto", "square", Cs, he, ve, w]
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
        "@container": ["", "normal", "size", ve, he]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [yy],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [Ve, "auto", he, ve, i]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": V()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": V()
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
        overscroll: ee()
      }],
      /**
       * Overscroll Behavior X
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-x": [{
        "overscroll-x": ee()
      }],
      /**
       * Overscroll Behavior Y
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-y": [{
        "overscroll-y": ee()
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
        inset: C()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": C()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": C()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": C(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: C()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": C(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: C()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": C()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": C()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: C()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: C()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: C()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: C()
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
        z: [Ht, "auto", ve, he]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [Cs, "full", "auto", i, ...M()]
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
        flex: [Ve, Cs, "auto", "initial", "none", he]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", Ve, ve, he]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", Ve, ve, he]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [Ht, "first", "last", "none", ve, he]
      }],
      /**
       * Grid Template Columns
       * @see https://tailwindcss.com/docs/grid-template-columns
       */
      "grid-cols": [{
        "grid-cols": F()
      }],
      /**
       * Grid Column Start / End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start-end": [{
        col: Se()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": Ce()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": Ce()
      }],
      /**
       * Grid Template Rows
       * @see https://tailwindcss.com/docs/grid-template-rows
       */
      "grid-rows": [{
        "grid-rows": F()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: Se()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": Ce()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": Ce()
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
        "auto-cols": Me()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": Me()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: M()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": M()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": M()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...He(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...ue(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...ue()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...He()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...ue(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...ue(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": He()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...ue(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...ue()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: M()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: M()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: M()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: M()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: M()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: M()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: M()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: M()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: M()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: M()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: M()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: W()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: W()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: W()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: W()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: W()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: W()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: W()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: W()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: W()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: W()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: W()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": M()
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
        "space-y": M()
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
        size: E()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ..._()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ..._()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ..._()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...X()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...X()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...X()]
      }],
      /**
       * Width
       * @see https://tailwindcss.com/docs/width
       */
      w: [{
        w: [i, "screen", ...E()]
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
          ...E()
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
          ...E()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...E()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...E()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...E()]
      }],
      // ------------------
      // --- Typography ---
      // ------------------
      /**
       * Font Size
       * @see https://tailwindcss.com/docs/font-size
       */
      "font-size": [{
        text: ["base", s, On, Bs]
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
        font: [n, $y, wy]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", Go, he]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [ky, _y, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [he]
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
        tracking: [r, ve, he]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [Ve, "none", ve, Ol]
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
          ...M()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", ve, he]
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
        list: ["disc", "decimal", "none", ve, he]
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
        placeholder: ne()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: ne()
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
        decoration: [...q(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [Ve, "from-font", "auto", ve, Bs]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: ne()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [Ve, "auto", ve, he]
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
        indent: M()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [Ht, ve, he]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", ve, he]
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
        content: ["none", ve, he]
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
        bg: Xe()
      }],
      /**
       * Background Repeat
       * @see https://tailwindcss.com/docs/background-repeat
       */
      "bg-repeat": [{
        bg: qe()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: mt()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, Ht, ve, he],
          radial: ["", ve, he],
          conic: ["", Ht, ve, he]
        }, Cy, xy]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: ne()
      }],
      /**
       * Gradient Color Stops From Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from-pos": [{
        from: at()
      }],
      /**
       * Gradient Color Stops Via Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via-pos": [{
        via: at()
      }],
      /**
       * Gradient Color Stops To Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to-pos": [{
        to: at()
      }],
      /**
       * Gradient Color Stops From
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from": [{
        from: ne()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: ne()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: ne()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: We()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": We()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": We()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": We()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": We()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": We()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": We()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": We()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": We()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": We()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": We()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": We()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": We()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": We()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": We()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: Oe()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": Oe()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": Oe()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": Oe()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": Oe()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": Oe()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": Oe()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": Oe()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": Oe()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": Oe()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": Oe()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": Oe()
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
        "divide-y": Oe()
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
        border: [...q(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...q(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: ne()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": ne()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": ne()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": ne()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": ne()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": ne()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": ne()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": ne()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": ne()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": ne()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": ne()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: ne()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [...q(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [Ve, ve, he]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", Ve, On, Bs]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: ne()
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
          Sr,
          kr
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: ne()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", f, Sr, kr]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": ne()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: Oe()
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
        ring: ne()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [Ve, Bs]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": ne()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": Oe()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": ne()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", y, Sr, kr]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": ne()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [Ve, ve, he]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...j(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": j()
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
        "mask-linear": [Ve]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": D()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": D()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": ne()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": ne()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": D()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": D()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": ne()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": ne()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": D()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": D()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": ne()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": ne()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": D()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": D()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": ne()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": ne()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": D()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": D()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": ne()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": ne()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": D()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": D()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": ne()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": ne()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": D()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": D()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": ne()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": ne()
      }],
      "mask-image-radial": [{
        "mask-radial": [ve, he]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": D()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": D()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": ne()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": ne()
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
        "mask-conic": [Ve]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": D()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": D()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": ne()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": ne()
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
        mask: Xe()
      }],
      /**
       * Mask Repeat
       * @see https://tailwindcss.com/docs/mask-repeat
       */
      "mask-repeat": [{
        mask: qe()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: mt()
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
        mask: ["none", ve, he]
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
          ve,
          he
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: le()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [Ve, ve, he]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [Ve, ve, he]
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
          v,
          Sr,
          kr
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": ne()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", Ve, ve, he]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [Ve, ve, he]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", Ve, ve, he]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [Ve, ve, he]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", Ve, ve, he]
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
          ve,
          he
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": le()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [Ve, ve, he]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [Ve, ve, he]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", Ve, ve, he]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [Ve, ve, he]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", Ve, ve, he]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [Ve, ve, he]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [Ve, ve, he]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", Ve, ve, he]
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
        "border-spacing": M()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": M()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": M()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", ve, he]
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
        duration: [Ve, "initial", ve, he]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", O, ve, he]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [Ve, ve, he]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", I, ve, he]
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
        perspective: [b, ve, he]
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
        rotate: g()
      }],
      /**
       * Rotate X
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-x": [{
        "rotate-x": g()
      }],
      /**
       * Rotate Y
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-y": [{
        "rotate-y": g()
      }],
      /**
       * Rotate Z
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-z": [{
        "rotate-z": g()
      }],
      /**
       * Scale
       * @see https://tailwindcss.com/docs/scale
       */
      scale: [{
        scale: x()
      }],
      /**
       * Scale X
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-x": [{
        "scale-x": x()
      }],
      /**
       * Scale Y
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-y": [{
        "scale-y": x()
      }],
      /**
       * Scale Z
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-z": [{
        "scale-z": x()
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
        transform: [ve, he, "", "none", "gpu", "cpu"]
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
        translate: z()
      }],
      /**
       * Translate X
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-x": [{
        "translate-x": z()
      }],
      /**
       * Translate Y
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-y": [{
        "translate-y": z()
      }],
      /**
       * Translate Z
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-z": [{
        "translate-z": z()
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
        zoom: [Ht, ve, he]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: ne()
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
        caret: ne()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", ve, he]
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
        "scrollbar-thumb": ne()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": ne()
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
        "scroll-m": M()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": M()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": M()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": M()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": M()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": M()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": M()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": M()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": M()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": M()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": M()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": M()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": M()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": M()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": M()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": M()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": M()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": M()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": M()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": M()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": M()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": M()
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
        "will-change": ["auto", "scroll", "contents", "transform", ve, he]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...ne()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [Ve, On, Bs, Ol]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...ne()]
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
}, Ay = /* @__PURE__ */ ay(Ry);
function Xa(...e) {
  return Ay(Mu(e));
}
const Ey = { class: "cmst:flex cmst:h-14 cmst:items-center cmst:gap-3 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:pl-3 cmst:pr-14" }, Oy = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:text-cmst-muted" }, Ty = { class: "cmst:flex-1 cmst:min-w-0" }, Py = ["onKeydown"], Ny = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:px-4 cmst:py-3" }, My = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-1 cmst:flex-col cmst:gap-0.5 cmst:overflow-y-auto cmst:px-3 cmst:pb-4"
}, zy = {
  key: 0,
  class: "cmst-drawer-hint"
}, jy = {
  key: 1,
  class: "cmst-drawer-hint"
}, Dy = {
  key: 2,
  class: "cmst-drawer-hint"
}, Ly = /* @__PURE__ */ xt({
  __name: "StudioApp",
  setup(e) {
    const t = yu(), s = ur(), n = bo(), r = Ja(), o = /* @__PURE__ */ T(!1), a = /* @__PURE__ */ T(null);
    xs(() => {
      s.initialize(), n.initialize();
    });
    const i = {
      playground: bu,
      history: fh,
      workflows: wu,
      backend: vh,
      settings: bh
    }, l = ["playground", "history"], c = ["workflows", "backend", "settings"], d = ye(() => String(t.name ?? "playground")), f = ye(
      () => Uo[d.value ?? "playground"] ?? "Studio"
    ), y = ye(() => r.wizardOpen);
    function v() {
      o.value = !0;
    }
    function A() {
      o.value = !1;
    }
    Wt(
      () => t.fullPath,
      () => {
        o.value = !1;
      }
    ), Wt(o, (w) => {
      w && lr(() => {
        a.value?.focus();
      });
    });
    function b() {
      window.dispatchEvent(new CustomEvent("comfymodal:close-vue-studio")), window.__comfymodalCloseVueStudio?.();
    }
    return (w, O) => (k(), S("div", {
      "data-testid": "vue-studio-root",
      class: Ae(["cmst:relative cmst:flex cmst:flex-col cmst:bg-cmst-bg cmst:text-cmst-fg", y.value ? "cmst:min-h-0" : "cmst:min-h-[60vh]"])
    }, [
      u("header", Ey, [
        u("button", {
          type: "button",
          "aria-label": "Open navigation",
          "data-testid": "vue-nav-drawer-open",
          class: "cmst:shrink-0 cmst:rounded-md cmst:p-2 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg",
          onClick: v
        }, [
          H(p(ih), {
            class: "cmst:size-4",
            "aria-hidden": "true"
          })
        ]),
        O[0] || (O[0] = u("span", { class: "cmst:shrink-0 cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg" }, " Modal Studio ", -1)),
        O[1] || (O[1] = u("span", {
          "aria-hidden": "true",
          class: "cmst:shrink-0 cmst:text-cmst-muted"
        }, "/", -1)),
        u("span", Oy, L(f.value), 1),
        u("button", {
          type: "button",
          "data-testid": "vue-studio-close",
          "aria-label": "Close Studio",
          class: "cmst:shrink-0 cmst:rounded-md cmst:p-1.5 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg",
          onClick: b
        }, [
          H(p(ya), {
            class: "cmst:size-4",
            "aria-hidden": "true"
          })
        ])
      ]),
      u("main", Ty, [
        H(p(gu))
      ]),
      o.value ? (k(), S(fe, { key: 0 }, [
        u("button", {
          type: "button",
          "aria-label": "Close navigation",
          class: "cmst-drawer-backdrop",
          "data-testid": "vue-nav-drawer-backdrop",
          onClick: A
        }),
        u("div", {
          ref_key: "drawerPanel",
          ref: a,
          class: "cmst-drawer",
          role: "dialog",
          "aria-modal": "true",
          "aria-label": "Studio navigation",
          "data-testid": "vue-nav-drawer",
          tabindex: "-1",
          onKeydown: zs(er(A, ["stop"]), ["esc"])
        }, [
          u("div", Ny, [
            O[2] || (O[2] = u("span", { class: "cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg" }, " Modal Studio ", -1)),
            u("button", {
              type: "button",
              "aria-label": "Close navigation",
              class: "cmst-close-btn",
              onClick: A
            }, [
              H(p(ya), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })
            ])
          ]),
          u("nav", My, [
            (k(), S(fe, null, ze(l, (I) => H(p(va), {
              key: I,
              to: { name: I },
              class: "cmst-drawer-row",
              "data-active": d.value === I,
              "data-testid": `vue-nav-${I}`,
              "aria-current": d.value === I ? "page" : void 0
            }, {
              default: se(() => [
                (k(), ut(fi(i[I]), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                })),
                K(" " + L(p(Uo)[I]), 1)
              ]),
              _: 2
            }, 1032, ["to", "data-active", "data-testid", "aria-current"])), 64)),
            O[3] || (O[3] = u("p", { class: "cmst-micro cmst:px-3 cmst:pb-1 cmst:pt-4" }, "Studio", -1)),
            (k(), S(fe, null, ze(c, (I) => H(p(va), {
              key: I,
              to: { name: I },
              class: Ae(["cmst-drawer-row", p(Xa)(d.value === I && "cmst:text-cmst-fg")]),
              "data-active": d.value === I,
              "data-testid": `vue-nav-${I}`,
              "aria-current": d.value === I ? "page" : void 0
            }, {
              default: se(() => [
                (k(), ut(fi(i[I]), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                })),
                K(" " + L(p(Uo)[I]) + " ", 1),
                I === "workflows" ? (k(), S("span", zy, "Library + setup")) : I === "backend" ? (k(), S("span", jy, "Deployment + models")) : I === "settings" ? (k(), S("span", Dy, "Preferences")) : te("", !0)
              ]),
              _: 2
            }, 1032, ["to", "data-active", "data-testid", "aria-current", "class"])), 64))
          ])
        ], 40, Py)
      ], 64)) : te("", !0)
    ], 2));
  }
}), Uy = "/", Ju = { page: "playground", focus: null };
function Cr(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function Ho(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = js(n) ? n : Ju.page;
  let o = null;
  if (s)
    for (const a of s.split("&")) {
      const i = a.indexOf("=");
      if (i !== -1 && decodeURIComponent(a.slice(0, i)) === "focus") {
        try {
          const l = decodeURIComponent(a.slice(i + 1));
          o = l === "" ? null : l;
        } catch {
          o = null;
        }
        break;
      }
    }
  return { page: r, focus: o };
}
function Zo(e) {
  const t = Su(e.location.hash);
  return !t.matched || !js(t.page) ? null : { page: t.page, focus: t.focus };
}
function Ko(e, t, s) {
  const n = Cu(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function Vy(e, t) {
  let s = Sh(t, e.location.hash), n = Cr(s), r = {};
  const o = n, a = /* @__PURE__ */ new Set();
  let i = !1;
  const l = () => {
    const d = n;
    s = Zo(e) ?? { ...Ju }, n = Cr(s), a.forEach((y) => y(n, d));
  }, c = (d, f) => d === null && f === o;
  return {
    get base() {
      return Uy;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (d) => {
      const f = Cu(Ho(d));
      return f === "" ? "#" + d : f;
    },
    replace: (d, f) => {
      const y = Zo(e), v = Ho(d), A = Cr(v);
      s = v, f !== void 0 && (r = f), n = A, !c(y, A) && tl(y, v) !== "none" && Ko(e, v, "replace");
    },
    push: (d, f) => {
      const y = Zo(e), v = Ho(d), A = Cr(v);
      if (s = v, f !== void 0 && (r = f), n = A, c(y, A)) return;
      const b = tl(y, v);
      b === "push" ? Ko(e, v, "push") : b === "replace" && Ko(e, v, "replace");
    },
    go: (d) => {
      e.history.go(d);
    },
    listen: (d) => {
      const f = (y, v) => {
        d(y, v, { type: "pop", direction: "unknown", delta: 0 });
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
const Nl = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, Ml = Mu, Fy = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return Ml(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, a = Object.keys(r).map((c) => {
    const d = s?.[c], f = o?.[c];
    if (d === null) return null;
    const y = Nl(d) || Nl(f);
    return r[c][y];
  }), i = s && Object.entries(s).reduce((c, d) => {
    let [f, y] = d;
    return y === void 0 || (c[f] = y), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, d) => {
    let { class: f, className: y, ...v } = d;
    return Object.entries(v).every((A) => {
      let [b, w] = A;
      return Array.isArray(w) ? w.includes({
        ...o,
        ...i
      }[b]) : {
        ...o,
        ...i
      }[b] === w;
    }) ? [
      ...c,
      f,
      y
    ] : c;
  }, []);
  return Ml(e, a, l, s?.class, s?.className);
}, Wy = Fy(
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
), By = ["type", "disabled"], re = /* @__PURE__ */ xt({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (k(), S("button", {
      type: e.type,
      disabled: e.disabled,
      class: Ae(p(Wy)({ variant: e.variant, size: e.size }))
    }, [
      Ac(t.$slots, "default")
    ], 10, By));
  }
});
function fr(e) {
  return Xa(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-6 cmst:sm:p-8",
    e
  );
}
const qy = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-danger",
  role: "alert"
}, Gy = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, Hy = {
  key: 1,
  class: "cmst-type-meta",
  "data-testid": "vue-backend-progress",
  role: "status"
}, Zy = {
  class: "cmst-seg",
  role: "tablist",
  "aria-label": "Backend sections"
}, Ky = ["data-active", "aria-selected", "data-testid", "onClick"], Jy = {
  role: "listbox",
  "aria-label": "Workspaces",
  class: "cmst:min-w-0"
}, Qy = ["aria-selected", "data-testid", "onClick"], Yy = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, Xy = { class: "cmst-type-object cmst:truncate" }, eb = { class: "cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate" }, tb = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, sb = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1.5" }, nb = {
  key: 0,
  "aria-label": "Workspace form",
  class: "cmst:mt-3 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3",
  "data-testid": "vue-workspace-form"
}, rb = { class: "cmst-type-section" }, ob = { class: "cmst:mt-3 cmst:flex cmst:max-w-md cmst:flex-col cmst:gap-2.5" }, ab = { class: "cmst-field-label" }, ib = { class: "cmst-field-label" }, lb = { class: "cmst-field-label" }, cb = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, ub = { class: "cmst:mt-3 cmst:flex cmst:gap-1.5" }, db = {
  key: 1,
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3",
  "data-testid": "vue-swap-confirm"
}, fb = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, mb = {
  key: 2,
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3",
  "data-testid": "vue-swap-review"
}, pb = { class: "cmst:text-[13px]" }, hb = ["value"], gb = { class: "cmst-type-meta" }, vb = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, yb = {
  "aria-label": "Accounts and tokens",
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4"
}, bb = { class: "cmst:mt-1 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-[13px]" }, wb = { "data-testid": "vue-auth-status" }, _b = { class: "cmst:mt-1" }, xb = { class: "cmst-setting-row" }, kb = { class: "cmst:min-w-0" }, Sb = { class: "cmst:text-[13px] cmst:font-medium" }, Cb = { "data-testid": "vue-cred-hf-state" }, $b = { class: "cmst:flex cmst:gap-1.5" }, Ib = { class: "cmst-setting-row" }, Rb = { class: "cmst:min-w-0" }, Ab = { class: "cmst:text-[13px] cmst:font-medium" }, Eb = { "data-testid": "vue-cred-civitai-state" }, Ob = { class: "cmst:flex cmst:gap-1.5" }, Tb = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted",
  role: "status"
}, Pb = {
  "aria-label": "Manifest repair",
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4"
}, Nb = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Mb = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, zb = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted",
  role: "status"
}, jb = { "aria-label": "Deployment readiness" }, Db = { class: "cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3" }, Lb = { class: "cmst:min-w-0" }, Ub = { class: "cmst:mt-1.5 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-[13px]" }, Vb = { "data-testid": "vue-deploy-state" }, Fb = {
  key: 0,
  class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted"
}, Wb = {
  key: 1,
  class: "cmst:mt-2 cmst:w-56 cmst:max-w-full"
}, Bb = ["aria-valuenow"], qb = { class: "cmst:flex cmst:flex-wrap cmst:gap-1.5" }, Gb = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, Hb = {
  key: 1,
  class: "cmst:mt-2"
}, Zb = {
  "aria-label": "Custom-node sync",
  class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4"
}, Kb = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Jb = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, Qb = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-1.5" }, Yb = {
  key: 4,
  "aria-label": "Models"
}, Xb = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, ew = { class: "cmst-type-meta cmst:mt-0.5" }, tw = { class: "cmst:flex cmst:gap-1.5" }, sw = {
  class: "cmst:mt-2 cmst:max-h-64 cmst:overflow-auto",
  "data-testid": "vue-models-list"
}, nw = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, rw = { class: "cmst-type-meta cmst:truncate" }, ow = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, aw = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-1.5" }, iw = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "vue-model-install-message",
  role: "status"
}, lw = {
  key: 5,
  "aria-label": "Custom nodes"
}, cw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, uw = { class: "cmst-type-meta cmst:mt-0.5" }, dw = { class: "cmst:flex cmst:gap-1.5" }, fw = {
  class: "cmst:mt-2 cmst:max-h-64 cmst:overflow-auto",
  "data-testid": "vue-nodes-list"
}, mw = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, pw = { class: "cmst-type-meta cmst:truncate" }, hw = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, gw = /* @__PURE__ */ xt({
  __name: "BackendView",
  setup(e) {
    const t = bo(), s = /* @__PURE__ */ T("workspaces"), n = /* @__PURE__ */ T(""), r = /* @__PURE__ */ T(!1), o = /* @__PURE__ */ T(""), a = /* @__PURE__ */ T(""), i = /* @__PURE__ */ T(""), l = /* @__PURE__ */ T(""), c = /* @__PURE__ */ T(""), d = /* @__PURE__ */ T([]), f = /* @__PURE__ */ T(""), y = /* @__PURE__ */ T(""), v = /* @__PURE__ */ T(""), A = /* @__PURE__ */ T(""), b = /* @__PURE__ */ T(""), w = /* @__PURE__ */ T(""), O = /* @__PURE__ */ T("diffusion_models"), I = /* @__PURE__ */ T(""), V = /* @__PURE__ */ T(!1), R = ["workspaces", "deployment", "models", "nodes"];
    xs(async () => {
      await t.initialize().catch(() => {
      }), await Promise.all([
        t.loadCredentials().catch(() => {
        }),
        t.loadSyncStatus().catch(() => {
        })
      ]);
    });
    function J(E) {
      const _ = E.toLowerCase();
      return _ === "ready" || _ === "deployed" || _ === "deployed_unwarmed" || _ === "complete" || _ === "completed" || _ === "success" ? "cmst:bg-cmst-ok" : _ === "failed" || _ === "error" ? "cmst:bg-cmst-danger" : _ === "deploying" || _ === "running" || _ === "pending" || _ === "syncing" || _ === "warming" || _ === "unknown" ? "cmst:bg-cmst-warn" : "cmst:bg-cmst-muted";
    }
    const be = ye(() => {
      const E = t.deployStatus?.progress;
      return typeof E != "number" || Number.isNaN(E) ? null : Math.min(100, Math.max(0, Math.round(E <= 1 ? E * 100 : E)));
    }), ee = ye(() => {
      const E = b.value.trim().toLowerCase();
      return E ? t.customNodes.filter(
        (_) => String(_.title || _.id || _.name || "").toLowerCase().includes(E)
      ) : t.customNodes;
    });
    async function M() {
      n.value && await t.selectWorkspace(n.value).catch(() => {
      });
    }
    function C() {
      c.value = "", o.value = "", a.value = "", i.value = "", l.value = "", r.value = !0;
    }
    function F() {
      const E = t.workspaces.find((_) => _.id === n.value);
      E && (c.value = E.id, o.value = E.label, a.value = "", i.value = "", l.value = "", r.value = !0);
    }
    async function Se() {
      if (l.value = "", !o.value.trim()) {
        l.value = "Workspace label required.";
        return;
      }
      if (!c.value && (!a.value.trim() || !i.value.trim())) {
        l.value = "Token ID and Token Secret are required.";
        return;
      }
      try {
        await t.saveWorkspace(
          c.value ? { workspace_id: c.value, label: o.value.trim(), token_id: a.value.trim(), token_secret: i.value.trim(), set_active: !1 } : { label: o.value.trim(), token_id: a.value.trim(), token_secret: i.value.trim(), set_active: !1 }
        ), r.value = !1;
      } catch (E) {
        l.value = E instanceof Error ? E.message : "Save failed.";
      }
    }
    async function Ce() {
      n.value && await t.startSwap(n.value).catch(() => {
      });
    }
    async function Me() {
      await t.confirmSwapReview(n.value, d.value).catch(() => {
      });
    }
    async function He() {
      await t.deploy().catch(() => {
      });
    }
    async function ue(E) {
      v.value = "";
      try {
        const _ = await t.saveCredential(E, E === "hf" ? f.value : y.value);
        v.value = _, f.value = "", y.value = "";
      } catch (_) {
        v.value = _ instanceof Error ? _.message : "Save failed.";
      }
    }
    async function W() {
      if (w.value.trim()) {
        I.value = "Installing…";
        try {
          const E = w.value.trim();
          await t.installModel({ url: E, filename: Lg(E), save_path: O.value }), I.value = "Install request accepted.";
        } catch (E) {
          I.value = E instanceof Error ? E.message : "Install failed.";
        }
        w.value = "";
      }
    }
    return (E, _) => (k(), S("section", {
      class: Ae(p(fr)()),
      "data-testid": "vue-page-backend"
    }, [
      p(t).error ? (k(), S("div", qy, L(p(t).error), 1)) : te("", !0),
      u("div", Gy, [
        _[27] || (_[27] = u("div", null, [
          u("h1", { class: "cmst-type-view" }, "Manage Modal")
        ], -1)),
        H(re, {
          variant: "ghost",
          size: "icon",
          "aria-label": "Reload infrastructure",
          disabled: p(t).loading,
          onClick: _[0] || (_[0] = (X) => p(t).load())
        }, {
          default: se(() => [
            H(p(vo), {
              class: Ae(["cmst:size-4", p(t).loading ? "cmst:animate-spin" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ]),
          _: 1
        }, 8, ["disabled"])
      ]),
      p(t).progress ? (k(), S("p", Hy, L(p(t).progress), 1)) : te("", !0),
      u("div", Zy, [
        (k(), S(fe, null, ze(R, (X) => u("button", {
          key: X,
          type: "button",
          role: "tab",
          class: "cmst-seg-btn cmst:capitalize",
          "data-active": s.value === X,
          "aria-selected": s.value === X,
          "data-testid": `vue-backend-tab-${X}`,
          onClick: (ne) => s.value = X
        }, L(X), 9, Ky)), 64))
      ]),
      s.value === "workspaces" ? (k(), S(fe, { key: 2 }, [
        u("div", Jy, [
          (k(!0), S(fe, null, ze(p(t).workspaces, (X) => (k(), S("button", {
            key: X.id,
            type: "button",
            role: "option",
            class: "cmst-object-row",
            "aria-selected": n.value === X.id,
            "data-testid": `vue-workspace-${X.id}`,
            onClick: (ne) => n.value = X.id
          }, [
            u("span", Yy, [
              u("span", {
                class: Ae(["cmst-status-dot", X.isActive ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
                "aria-hidden": "true"
              }, null, 2),
              u("strong", Xy, L(X.label), 1)
            ]),
            u("span", eb, L(X.isActive ? "Active" : "Idle") + " · last deploy: " + L(X.lastDeployStatus), 1)
          ], 8, Qy))), 128)),
          p(t).workspaces.length ? te("", !0) : (k(), S("p", tb, " No workspaces returned by the server. "))
        ]),
        u("div", sb, [
          H(re, {
            size: "sm",
            variant: "secondary",
            disabled: !n.value || p(t).busy,
            "data-testid": "vue-workspace-activate",
            onClick: M
          }, {
            default: se(() => [..._[28] || (_[28] = [
              K("Set Active", -1)
            ])]),
            _: 1
          }, 8, ["disabled"]),
          H(re, {
            size: "sm",
            variant: "outline",
            disabled: p(t).busy,
            onClick: C
          }, {
            default: se(() => [..._[29] || (_[29] = [
              K("Add workspace", -1)
            ])]),
            _: 1
          }, 8, ["disabled"]),
          H(re, {
            size: "sm",
            variant: "ghost",
            disabled: !n.value || p(t).busy,
            onClick: F
          }, {
            default: se(() => [..._[30] || (_[30] = [
              K("Edit", -1)
            ])]),
            _: 1
          }, 8, ["disabled"]),
          H(re, {
            size: "sm",
            variant: "ghost",
            disabled: !n.value || p(t).busy,
            "data-testid": "vue-workspace-swap",
            onClick: Ce
          }, {
            default: se(() => [..._[31] || (_[31] = [
              K("Swap", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ]),
        r.value ? (k(), S("section", nb, [
          u("h3", rb, L(c.value ? "Edit workspace" : "Add workspace"), 1),
          u("div", ob, [
            u("label", ab, [
              _[32] || (_[32] = K("Label", -1)),
              Fe(u("input", {
                "onUpdate:modelValue": _[1] || (_[1] = (X) => o.value = X),
                class: "cmst-field"
              }, null, 512), [
                [lt, o.value]
              ])
            ]),
            u("label", ib, [
              _[33] || (_[33] = K("Token ID", -1)),
              Fe(u("input", {
                "onUpdate:modelValue": _[2] || (_[2] = (X) => a.value = X),
                class: "cmst-field cmst:font-mono",
                placeholder: "ak-…"
              }, null, 512), [
                [lt, a.value]
              ])
            ]),
            u("label", lb, [
              _[34] || (_[34] = K("Token Secret", -1)),
              Fe(u("input", {
                "onUpdate:modelValue": _[3] || (_[3] = (X) => i.value = X),
                type: "password",
                class: "cmst-field cmst:font-mono",
                placeholder: "as-…"
              }, null, 512), [
                [lt, i.value]
              ])
            ])
          ]),
          l.value ? (k(), S("p", cb, L(l.value), 1)) : te("", !0),
          u("div", ub, [
            H(re, {
              size: "sm",
              "data-testid": "vue-workspace-save",
              onClick: Se
            }, {
              default: se(() => [..._[35] || (_[35] = [
                K("Save workspace", -1)
              ])]),
              _: 1
            }),
            H(re, {
              size: "sm",
              variant: "ghost",
              onClick: _[4] || (_[4] = (X) => r.value = !1)
            }, {
              default: se(() => [..._[36] || (_[36] = [
                K("Cancel", -1)
              ])]),
              _: 1
            })
          ])
        ])) : te("", !0),
        p(t).swapConfirmRequired ? (k(), S("div", db, [
          _[39] || (_[39] = u("p", { class: "cmst:text-[13px]" }, "A prompt is still running. Switch workspaces anyway?", -1)),
          u("div", fb, [
            H(re, {
              size: "sm",
              "data-testid": "vue-swap-confirm-yes",
              onClick: _[5] || (_[5] = (X) => p(t).confirmSwapInterrupt(n.value))
            }, {
              default: se(() => [..._[37] || (_[37] = [
                K("Interrupt and switch", -1)
              ])]),
              _: 1
            }),
            H(re, {
              size: "sm",
              variant: "ghost",
              onClick: _[6] || (_[6] = (X) => p(t).cancelSwapDialog())
            }, {
              default: se(() => [..._[38] || (_[38] = [
                K("Cancel", -1)
              ])]),
              _: 1
            })
          ])
        ])) : te("", !0),
        p(t).swapReview ? (k(), S("div", mb, [
          u("p", pb, "Select models to download to " + L(p(t).swapReview.workspaceLabel) + ":", 1),
          (k(!0), S(fe, null, ze(p(t).swapReview.toInstall, (X) => (k(), S("label", {
            key: X.key,
            class: "cmst:mt-1 cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:text-[13px]"
          }, [
            Fe(u("input", {
              "onUpdate:modelValue": _[7] || (_[7] = (ne) => d.value = ne),
              type: "checkbox",
              value: X.key
            }, null, 8, hb), [
              [ln, d.value]
            ]),
            u("span", gb, L(X.filename) + " · " + L(X.folder), 1)
          ]))), 128)),
          u("div", vb, [
            H(re, {
              size: "sm",
              "data-testid": "vue-swap-review-go",
              onClick: Me
            }, {
              default: se(() => [..._[40] || (_[40] = [
                K("Start swap", -1)
              ])]),
              _: 1
            }),
            H(re, {
              size: "sm",
              variant: "ghost",
              onClick: _[8] || (_[8] = (X) => p(t).cancelSwapDialog())
            }, {
              default: se(() => [..._[41] || (_[41] = [
                K("Cancel", -1)
              ])]),
              _: 1
            })
          ])
        ])) : te("", !0),
        u("section", yb, [
          _[47] || (_[47] = u("h3", { class: "cmst-type-section" }, "Accounts & tokens", -1)),
          u("p", bb, [
            u("span", {
              class: Ae(["cmst-status-dot", p(t).authConnected ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
              "aria-hidden": "true"
            }, null, 2),
            _[42] || (_[42] = K(" Modal connection: ", -1)),
            u("strong", wb, L(p(t).authConnected === null ? "unknown" : p(t).authConnected ? "connected" : "not configured"), 1)
          ]),
          u("div", _b, [
            u("div", xb, [
              u("div", kb, [
                u("p", Sb, [
                  _[43] || (_[43] = K("HuggingFace · ", -1)),
                  u("span", Cb, L(p(t).hfConfigured ? "configured" : "not configured"), 1)
                ])
              ]),
              u("div", $b, [
                Fe(u("input", {
                  "onUpdate:modelValue": _[9] || (_[9] = (X) => f.value = X),
                  type: "password",
                  placeholder: "hf_...",
                  "aria-label": "HuggingFace token",
                  class: "cmst-field cmst:w-44",
                  "data-testid": "vue-cred-hf-input"
                }, null, 512), [
                  [lt, f.value]
                ]),
                H(re, {
                  size: "sm",
                  variant: "secondary",
                  "data-testid": "vue-cred-hf-save",
                  onClick: _[10] || (_[10] = (X) => ue("hf"))
                }, {
                  default: se(() => [..._[44] || (_[44] = [
                    K("Save", -1)
                  ])]),
                  _: 1
                })
              ])
            ]),
            u("div", Ib, [
              u("div", Rb, [
                u("p", Ab, [
                  _[45] || (_[45] = K("Civitai · ", -1)),
                  u("span", Eb, L(p(t).civitaiConfigured ? "configured" : "not configured"), 1)
                ])
              ]),
              u("div", Ob, [
                Fe(u("input", {
                  "onUpdate:modelValue": _[11] || (_[11] = (X) => y.value = X),
                  type: "password",
                  placeholder: "Civitai API key",
                  "aria-label": "Civitai token",
                  class: "cmst-field cmst:w-44",
                  "data-testid": "vue-cred-civitai-input"
                }, null, 512), [
                  [lt, y.value]
                ]),
                H(re, {
                  size: "sm",
                  variant: "secondary",
                  "data-testid": "vue-cred-civitai-save",
                  onClick: _[12] || (_[12] = (X) => ue("civitai"))
                }, {
                  default: se(() => [..._[46] || (_[46] = [
                    K("Save", -1)
                  ])]),
                  _: 1
                })
              ])
            ])
          ]),
          v.value ? (k(), S("p", Tb, L(v.value), 1)) : te("", !0)
        ]),
        u("section", Pb, [
          u("div", Nb, [
            _[49] || (_[49] = u("h3", { class: "cmst-type-section" }, "Manifest repair", -1)),
            H(re, {
              size: "sm",
              variant: "ghost",
              "data-testid": "vue-repair-scan",
              onClick: _[13] || (_[13] = (X) => p(t).scanRepair())
            }, {
              default: se(() => [..._[48] || (_[48] = [
                K("Scan issues", -1)
              ])]),
              _: 1
            })
          ]),
          p(t).repairIssues ? (k(), S("pre", Mb, L(JSON.stringify(p(t).repairIssues, null, 2)), 1)) : te("", !0),
          p(t).repairMessage ? (k(), S("p", zb, L(p(t).repairMessage), 1)) : te("", !0)
        ])
      ], 64)) : te("", !0),
      s.value === "deployment" ? (k(), S(fe, { key: 3 }, [
        u("section", jb, [
          u("div", Db, [
            u("div", Lb, [
              _[50] || (_[50] = u("h3", { class: "cmst-type-section" }, "Deployment readiness", -1)),
              u("p", Ub, [
                u("span", {
                  class: Ae(["cmst-status-dot", J(p(t).deployStatus.state)]),
                  "aria-hidden": "true"
                }, null, 2),
                u("strong", Vb, L(p(t).deployStatus.state), 1)
              ]),
              p(t).deployMessage ? (k(), S("p", Fb, L(p(t).deployMessage), 1)) : te("", !0),
              be.value !== null ? (k(), S("div", Wb, [
                u("div", {
                  class: "cmst-progress-track",
                  role: "progressbar",
                  "aria-valuenow": be.value,
                  "aria-valuemin": "0",
                  "aria-valuemax": "100"
                }, [
                  u("div", {
                    class: "cmst-progress-fill",
                    style: wn({ width: `${be.value}%` })
                  }, null, 4)
                ], 8, Bb)
              ])) : te("", !0)
            ]),
            u("div", qb, [
              H(re, {
                size: "sm",
                disabled: p(t).loading || !!p(t).deploymentOperationId,
                "data-testid": "vue-deploy",
                onClick: He
              }, {
                default: se(() => [..._[51] || (_[51] = [
                  K("Deploy", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              H(re, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-deploy-refresh",
                onClick: _[14] || (_[14] = (X) => p(t).loadDeployment())
              }, {
                default: se(() => [..._[52] || (_[52] = [
                  K("Refresh status", -1)
                ])]),
                _: 1
              }),
              H(re, {
                size: "sm",
                variant: "ghost",
                onClick: _[15] || (_[15] = (X) => V.value = !V.value)
              }, {
                default: se(() => [
                  K(L(V.value ? "Hide" : "Show") + " log", 1)
                ]),
                _: 1
              })
            ])
          ]),
          V.value ? (k(), S("pre", Gb, L(p(t).deployLog ?? "Loading…"), 1)) : te("", !0),
          V.value && !p(t).deployLog ? (k(), S("div", Hb, [
            H(re, {
              size: "sm",
              variant: "ghost",
              onClick: _[16] || (_[16] = (X) => p(t).loadLog())
            }, {
              default: se(() => [..._[53] || (_[53] = [
                K("Load deployment log", -1)
              ])]),
              _: 1
            })
          ])) : te("", !0)
        ]),
        u("section", Zb, [
          u("div", Kb, [
            _[55] || (_[55] = u("h3", { class: "cmst-type-section" }, "Custom-node sync", -1)),
            H(re, {
              size: "sm",
              variant: "ghost",
              onClick: _[17] || (_[17] = (X) => p(t).loadSyncStatus())
            }, {
              default: se(() => [..._[54] || (_[54] = [
                K("Refresh status", -1)
              ])]),
              _: 1
            })
          ]),
          p(t).customNodeSync ? (k(), S("pre", Jb, L(JSON.stringify(p(t).customNodeSync, null, 2)), 1)) : te("", !0),
          u("div", Qb, [
            H(re, {
              size: "sm",
              variant: "outline",
              "data-testid": "vue-node-push",
              onClick: _[18] || (_[18] = (X) => p(t).pushPlugins())
            }, {
              default: se(() => [..._[56] || (_[56] = [
                K("Push plugins (fast)", -1)
              ])]),
              _: 1
            }),
            H(re, {
              size: "sm",
              variant: "outline",
              "data-testid": "vue-node-rebuild",
              onClick: _[19] || (_[19] = (X) => p(t).rebuildDependencies())
            }, {
              default: se(() => [..._[57] || (_[57] = [
                K("Rebuild dependencies (slow)", -1)
              ])]),
              _: 1
            })
          ])
        ])
      ], 64)) : te("", !0),
      s.value === "models" ? (k(), S("section", Yb, [
        u("div", Xb, [
          u("div", null, [
            _[58] || (_[58] = u("h3", { class: "cmst-type-section" }, "Models", -1)),
            u("p", ew, L(p(t).models.length) + " installed", 1)
          ]),
          u("div", tw, [
            Fe(u("input", {
              "onUpdate:modelValue": _[20] || (_[20] = (X) => A.value = X),
              class: "cmst-field cmst:w-48",
              placeholder: "Search models",
              "aria-label": "Search models",
              onKeyup: _[21] || (_[21] = zs((X) => p(t).loadInventory(), ["enter"]))
            }, null, 544), [
              [lt, A.value]
            ]),
            H(re, {
              size: "sm",
              variant: "outline",
              onClick: _[22] || (_[22] = (X) => p(t).rescanModelsNow(!0))
            }, {
              default: se(() => [..._[59] || (_[59] = [
                K("Rescan", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        u("div", sw, [
          (k(!0), S(fe, null, ze(p(t).models, (X, ne) => (k(), S("div", {
            key: ne,
            class: "cmst-data-row"
          }, [
            _[60] || (_[60] = u("span", {
              class: "cmst-status-dot cmst:bg-cmst-muted",
              "aria-hidden": "true"
            }, null, -1)),
            u("span", nw, L(String(X.filename || X.name || X.id || `model ${ne}`)), 1),
            u("span", rw, L(String(X.folder || X.type || "")), 1)
          ]))), 128)),
          p(t).models.length ? te("", !0) : (k(), S("p", ow, "No models installed."))
        ]),
        u("div", aw, [
          Fe(u("input", {
            "onUpdate:modelValue": _[23] || (_[23] = (X) => w.value = X),
            class: "cmst-field cmst:min-w-0 cmst:flex-1",
            placeholder: "Paste a direct model link",
            "aria-label": "Model URL",
            "data-testid": "vue-model-url"
          }, null, 512), [
            [lt, w.value]
          ]),
          Fe(u("select", {
            "onUpdate:modelValue": _[24] || (_[24] = (X) => O.value = X),
            class: "cmst-field",
            "aria-label": "Model folder"
          }, [..._[61] || (_[61] = [
            Ur('<option value="diffusion_models">diffusion_models</option><option value="vae">vae</option><option value="clip">clip</option><option value="loras">loras</option><option value="upscale_models">upscale_models</option>', 5)
          ])], 512), [
            [ps, O.value]
          ]),
          H(re, {
            size: "sm",
            "data-testid": "vue-model-install",
            onClick: W
          }, {
            default: se(() => [..._[62] || (_[62] = [
              K("Install", -1)
            ])]),
            _: 1
          })
        ]),
        I.value ? (k(), S("p", iw, L(I.value), 1)) : te("", !0)
      ])) : te("", !0),
      s.value === "nodes" ? (k(), S("section", lw, [
        u("div", cw, [
          u("div", null, [
            _[63] || (_[63] = u("h3", { class: "cmst-type-section" }, "Custom nodes", -1)),
            u("p", uw, L(ee.value.length) + " registered", 1)
          ]),
          u("div", dw, [
            Fe(u("input", {
              "onUpdate:modelValue": _[25] || (_[25] = (X) => b.value = X),
              class: "cmst-field cmst:w-48",
              placeholder: "Search nodes",
              "aria-label": "Search nodes"
            }, null, 512), [
              [lt, b.value]
            ]),
            H(re, {
              size: "sm",
              variant: "outline",
              onClick: _[26] || (_[26] = (X) => p(t).refreshCustomNodesNow())
            }, {
              default: se(() => [..._[64] || (_[64] = [
                K("Refresh registry", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        u("div", fw, [
          (k(!0), S(fe, null, ze(ee.value, (X, ne) => (k(), S("div", {
            key: ne,
            class: "cmst-data-row"
          }, [
            _[65] || (_[65] = u("span", {
              class: "cmst-status-dot cmst:bg-cmst-muted",
              "aria-hidden": "true"
            }, null, -1)),
            u("span", mw, L(String(X.title || X.id || X.name || `node ${ne}`)), 1),
            u("span", pw, L(String(X.version || X.id || "")), 1)
          ]))), 128)),
          ee.value.length ? te("", !0) : (k(), S("p", hw, "No custom nodes match."))
        ])
      ])) : te("", !0)
    ], 2));
  }
});
function Qu(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return t.item ?? t.generation ?? t.experiment ?? e;
}
function ot(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function vw(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = ot(s, "asset_id", "assetId"), r = () => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: ot(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: ot(s, "logical_key", "logicalKey"),
    thumbUrl: ot(s, "thumb_url", "thumbnail_url") || r(),
    previewUrl: ot(s, "preview_url", "data_saver_url") || r(),
    dataSaverUrl: ot(s, "data_saver_url", "preview_url") || r(),
    originalUrl: ot(s, "original_url") || r(),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: ot(s, "filename", "name"),
    exportState: ot(s, "export_state", "exportState") || "not_exported"
  };
}
function yw(e, t) {
  const s = e && typeof e == "object" ? e : {};
  return {
    index: t,
    status: ot(s, "status", "outcome") || "unknown",
    error: ot(s, "error", "message") || null,
    ...s
  };
}
function rr(e) {
  return e.dataSaverUrl || e.thumbUrl || e.originalUrl;
}
function Yu(e) {
  return e.originalAvailable && e.originalUrl ? e.originalUrl : e.dataSaverUrl || e.originalUrl || e.thumbUrl;
}
function Xu(e) {
  return e.originalUrl || e.dataSaverUrl || e.thumbUrl;
}
function bw(e, t) {
  const s = e.featured_output_index;
  if (typeof s == "number" && t[s]) return s;
  const n = e.featured_output;
  if (n && typeof n == "object") {
    const r = n.index;
    if (typeof r == "number" && t[r]) return r;
  }
  return 0;
}
function Qr(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((c, d) => vw(c, d)), r = bw(t, n), o = Array.isArray(t.cells) ? t.cells : [], a = Array.isArray(t.cover) ? t.cover : [], i = Array.isArray(t.attempts) ? t.attempts : [], l = Array.isArray(t.errors) ? t.errors : [];
  return {
    id: ot(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: ot(t, "status", "outcome") || "unknown",
    workflow: ot(t, "workflow", "workflow_name"),
    workflowVersion: ot(t, "workflow_version", "workflowVersion", "version_id"),
    preset: ot(t, "preset", "preset_name"),
    prompt: ot(t, "prompt", "positive_prompt"),
    startedAt: ot(t, "started_at", "created_at") || null,
    completedAt: ot(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: ot(t, "note"),
    outputs: n,
    featuredOutput: n[r] ?? n[0] ?? null,
    featuredOutputIndex: r,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    replayReason: ot(t, "replay_reason", "replayReason"),
    attempts: i.map((c, d) => yw(c, d)),
    errors: l.filter((c) => !!c && typeof c == "object").map((c) => ({ code: ot(c, "code") || "error", message: ot(c, "message") || "Unknown error" })),
    params: t.params && typeof t.params == "object" ? t.params : {},
    timing: t.timing && typeof t.timing == "object" ? t.timing : {},
    cells: o.map((c) => Qr(c)),
    cover: a.map((c) => c ? Qr(c) : null),
    axisLabels: {
      x: ot(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "x"),
      y: ot(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "y")
    },
    counts: {
      cells: typeof t.true_cell_count == "number" ? t.true_cell_count : o.length,
      results: typeof t.result_count == "number" ? t.result_count : 0,
      failed: typeof t.failed_count == "number" ? t.failed_count : 0,
      interrupted: typeof t.interrupted_count == "number" ? t.interrupted_count : 0
    },
    raw: t
  };
}
async function ww(e = {}) {
  const t = new URLSearchParams(), s = { limit: 24, ...e };
  s.sort !== void 0 && (s.order = s.sort, delete s.sort), s.favorite_only !== void 0 && (s.favorite = s.favorite_only, delete s.favorite_only);
  for (const [n, r] of Object.entries(s))
    r !== void 0 && String(r) !== "" && t.set(n, String(r));
  return oe(`/history-v2/feed?${t}`);
}
async function _w(e) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}`).then(Qu);
}
async function xw(e) {
  return oe(`/history-v2/experiments/${encodeURIComponent(e)}`).then(Qu);
}
async function kw(e, t) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function Sw(e, t) {
  return oe(`/history-v2/experiments/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function Cw(e, t) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function $w(e, t) {
  return oe(`/history-v2/experiments/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function Iw(e, t) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}/featured`, { method: "PATCH", body: { output_index: t } });
}
async function Rw(e, t = {}) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}/original`, { method: "POST", body: t });
}
async function Aw(e) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}/original/retry`, { method: "POST" });
}
async function Ew(e) {
  return oe(`/history-v2/generations/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function Ow(e) {
  return oe(`/history-v2/experiments/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function Tw(e) {
  return oe(`/history-v2/experiments/${encodeURIComponent(e)}/cancel`, { method: "POST" });
}
async function Pw(e, t) {
  return oe(`/history-v2/experiments/${encodeURIComponent(e)}/cells/${encodeURIComponent(t)}/retry`, { method: "POST" });
}
async function Nw(e, t) {
  return oe("/history-v2/bulk-delete", { method: "POST", body: { generation_ids: e, experiment_ids: t } });
}
async function Mw(e) {
  return oe(`/history-v2/assets/${encodeURIComponent(e)}/export`, { method: "POST" });
}
async function zw(e) {
  return oe(`/history-v2/assets/${encodeURIComponent(e)}/open`, { method: "POST" });
}
async function jw(e) {
  return oe(`/history-v2/assets/${encodeURIComponent(e)}/reveal`, { method: "POST" });
}
function Dw(e) {
  const t = e.split(";")[0].trim().toLowerCase();
  return t === "image/png" ? "png" : t === "image/jpeg" ? "jpg" : t === "image/webp" ? "webp" : t === "image/gif" ? "gif" : t === "image/bmp" ? "bmp" : "png";
}
function Lw(e, t, s) {
  return `${[e.workflow || "generation", e.id, `output-${t.index}`].map((r) => r.replace(/[^a-zA-Z0-9-_]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48)).filter(Boolean).join("-") || "history-output"}.${s}`;
}
async function Uw(e, t, s = "original") {
  const n = s === "original" ? t.originalUrl : s === "dataSaver" ? t.dataSaverUrl : t.thumbUrl, r = await fetch(n);
  if (!r.ok) throw new Error(`Download failed with status ${r.status}`);
  const o = await r.blob(), a = Lw(e, t, Dw(o.type)), i = URL.createObjectURL(o);
  try {
    const l = document.createElement("a");
    l.href = i, l.download = a, document.body.appendChild(l), l.click(), l.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(i), 1e3);
  }
}
async function Vw(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return oe(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const tn = gs("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1, kind: "mixed", status: "" }), xn = /* @__PURE__ */ _n("studio-history", () => {
  const e = /* @__PURE__ */ T([]), t = /* @__PURE__ */ T(null), s = /* @__PURE__ */ T(null), n = /* @__PURE__ */ T(tn.read().query), r = /* @__PURE__ */ T(tn.read().sort), o = /* @__PURE__ */ T(tn.read().favoriteOnly), a = /* @__PURE__ */ T(tn.read().kind), i = /* @__PURE__ */ T(tn.read().status), l = /* @__PURE__ */ T(null), c = /* @__PURE__ */ T(!1), d = /* @__PURE__ */ T(!1), f = /* @__PURE__ */ T(null), y = /* @__PURE__ */ T(null), v = /* @__PURE__ */ T(null), A = /* @__PURE__ */ T(null), b = /* @__PURE__ */ T(/* @__PURE__ */ new Set()), w = /* @__PURE__ */ T(!1), O = /* @__PURE__ */ T(null), I = bn(), V = bn();
  let R = !1, J = null;
  const be = ye(() => e.value.find((h) => h.id === t.value) ?? null), ee = ye(() => e.value.find((h) => h.id === s.value) ?? be.value), M = ye(() => ({
    a: e.value.find((h) => h.id === v.value) ?? null,
    b: e.value.find((h) => h.id === A.value) ?? null
  })), C = ye(() => [...b.value]);
  function F() {
    tn.write({ query: n.value, sort: r.value, favoriteOnly: o.value, kind: a.value, status: i.value });
  }
  function Se(h) {
    s.value = h, h && (t.value = h);
  }
  function Ce(h) {
    n.value = h, F();
  }
  function Me(h) {
    r.value = h, F();
  }
  function He(h) {
    o.value = h, F();
  }
  function ue(h) {
    a.value = h, F();
  }
  function W(h) {
    i.value = h, F();
  }
  function E(h) {
    const N = e.value.findIndex((U) => U.id === h.id && U.kind === h.kind);
    N >= 0 ? e.value[N] = h : e.value.unshift(h);
  }
  function _(h, N) {
    e.value = e.value.filter((U) => !(U.id === N && U.kind === h)), t.value === N && (t.value = null), s.value === N && (s.value = null), v.value === N && (v.value = null), A.value === N && (A.value = null), b.value.delete(`${h}:${N}`);
  }
  async function X(h = !1) {
    d.value = !0, f.value = null;
    try {
      const N = await I.run(async (ge) => {
        const ie = await ww({
          search: n.value,
          order: r.value,
          favorite: o.value ? !0 : void 0,
          kind: a.value === "mixed" ? void 0 : a.value,
          status: i.value || void 0,
          cursor: h ? l.value ?? void 0 : void 0
        });
        return ge.aborted ? null : ie;
      });
      if (N.stale || !N.value) return;
      const U = N.value, G = (U.items ?? U.records ?? []).map(Qr);
      e.value = h ? e.value.concat(G) : G, l.value = U.next_cursor ?? null, c.value = U.has_more === !0 || !!l.value;
    } catch (N) {
      throw f.value = N instanceof Error ? N.message : "Could not load History V2", N;
    } finally {
      d.value = !1, R && (R = !1, X());
    }
  }
  async function ne(h, N = "generation") {
    y.value = null;
    try {
      const U = await V.run(async (G) => {
        const ge = N === "experiment" ? await xw(h) : await _w(h);
        return G.aborted ? null : ge;
      });
      if (U.stale || !U.value) return;
      E(Qr(U.value)), t.value = h;
    } catch (U) {
      throw y.value = U instanceof Error ? U.message : "Could not load History detail", U;
    }
  }
  async function Xe(h) {
    if (Se(h), !h) return;
    const N = e.value.find((U) => U.id === h);
    await ne(h, N?.kind ?? "generation");
  }
  async function qe(h, N) {
    const U = h.favorite;
    h.favorite = N;
    try {
      h.kind === "experiment" ? await Sw(h.id, N) : await kw(h.id, N), tt("history");
    } catch (G) {
      throw h.favorite = U, G;
    }
  }
  async function mt(h, N) {
    const U = h.note;
    h.note = N;
    try {
      h.kind === "experiment" ? await $w(h.id, N) : await Cw(h.id, N), tt("history");
    } catch (G) {
      throw h.note = U, G;
    }
  }
  async function at(h, N) {
    await Iw(h.id, N), await ne(h.id, h.kind), tt("history");
  }
  async function We(h) {
    await Vw(h), _(h.kind, h.id), tt("history");
  }
  function Oe(h) {
    const N = `${h.kind}:${h.id}`, U = new Set(b.value);
    U.has(N) ? U.delete(N) : U.add(N), b.value = U;
  }
  function q() {
    b.value = /* @__PURE__ */ new Set();
  }
  async function j() {
    const h = [], N = [];
    for (const U of b.value) {
      const G = U.indexOf(":"), ge = U.slice(0, G), ie = U.slice(G + 1);
      ge === "experiment" ? N.push(ie) : h.push(ie);
    }
    if (!(!h.length && !N.length)) {
      await Nw(h, N);
      for (const U of h) _("generation", U);
      for (const U of N) _("experiment", U);
      q(), tt("history");
    }
  }
  async function D(h, N) {
    let U;
    return N === "original" ? U = await Rw(h.id) : N === "retry" ? U = await Aw(h.id) : U = await Ew(h.id), O.value = `${N} accepted for ${h.id}`, tt("history"), U;
  }
  async function le(h, N, U) {
    let G;
    return N === "resume" ? G = await Ow(h.id) : U ? G = await Pw(h.id, U) : G = await Tw(h.id), await ne(h.id, "experiment"), tt("history"), G;
  }
  async function g(h) {
    const N = await Mw(h.assetId);
    return h.exportState = "exported", N;
  }
  function x(h, N) {
    h === "a" ? v.value = N : A.value = N;
  }
  function P() {
    const h = v.value;
    v.value = A.value, A.value = h;
  }
  function z() {
    v.value = null, A.value = null;
  }
  async function $() {
    J || (J = yo((h) => {
      if (h === "history") {
        if (d.value) {
          R = !0;
          return;
        }
        X();
      }
    })), e.value.length || await X();
  }
  function m() {
    e.value = [], t.value = null, s.value = null, l.value = null, v.value = null, A.value = null, b.value = /* @__PURE__ */ new Set();
  }
  return {
    records: e,
    selected: be,
    selectedId: t,
    focused: ee,
    focusId: s,
    query: n,
    sort: r,
    favoriteOnly: o,
    kindFilter: a,
    statusFilter: i,
    cursor: l,
    hasMore: c,
    loading: d,
    error: f,
    detailError: y,
    compareA: v,
    compareB: A,
    compareRecords: M,
    selection: C,
    viewerOpen: w,
    actionMessage: O,
    setFocus: Se,
    setQuery: Ce,
    setSort: Me,
    setFavoriteOnly: He,
    setKindFilter: ue,
    setStatusFilter: W,
    loadFeed: X,
    loadDetail: ne,
    applyRouteFocus: Xe,
    setFavorite: qe,
    setNote: mt,
    setFeatured: at,
    remove: We,
    toggleSelection: Oe,
    clearSelection: q,
    removeSelected: j,
    runReplayAction: D,
    runExperimentAction: le,
    exportAsset: g,
    openHistoryAsset: zw,
    revealHistoryAsset: jw,
    downloadHistoryAsset: Uw,
    selectCompare: x,
    swapCompare: P,
    clearCompare: z,
    selectFeedAsset: rr,
    selectDetailAsset: Yu,
    selectCompareAsset: Xu,
    initialize: $,
    clear: m
  };
}), Fw = { class: "cmst-media-well cmst:relative" }, Ww = ["aria-label", "data-testid"], Bw = ["src", "alt"], qw = {
  key: 1,
  class: "cmst:flex cmst:aspect-square cmst:w-full cmst:items-center cmst:justify-center cmst:text-cmst-muted",
  "aria-hidden": "true"
}, Gw = ["aria-pressed", "aria-label", "data-testid"], Hw = ["aria-pressed", "aria-label", "data-testid"], Zw = ["aria-label"], Kw = { class: "cmst-type-object cmst:block cmst:truncate" }, Jw = { class: "cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate" }, Qw = /* @__PURE__ */ xt({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = e, n = t, r = xn(), o = ye(() => `${s.record.kind}:${s.record.id}`), a = ye(() => r.selection.includes(o.value)), i = ye(() => {
      const v = s.record.featuredOutput;
      return !v || typeof v.width != "number" || typeof v.height != "number" ? null : `${v.width}×${v.height}`;
    }), l = ye(() => {
      const v = s.record.prompt?.trim();
      return v && !/^[{[]/.test(v) ? v.length > 80 ? `${v.slice(0, 80)}…` : v : s.record.workflow ? s.record.workflow : s.record.kind === "experiment" ? "Experiment" : "Generation";
    });
    function c(v) {
      if (!v) return null;
      const A = Date.parse(v);
      if (Number.isNaN(A)) return null;
      const b = Math.max(0, Math.round((Date.now() - A) / 6e4));
      if (b < 1) return "just now";
      if (b < 60) return `${b}m ago`;
      const w = Math.round(b / 60);
      if (w < 24) return `${w}h ago`;
      const O = Math.round(w / 24);
      return O < 30 ? `${O}d ago` : new Date(A).toLocaleDateString();
    }
    const d = ye(() => c(s.record.completedAt ?? s.record.startedAt));
    async function f(v) {
      v.stopPropagation(), await r.setFavorite(s.record, !s.record.favorite).catch(() => {
      });
    }
    function y(v) {
      v.stopPropagation(), r.toggleSelection(s.record);
    }
    return (v, A) => (k(), S("div", {
      class: Ae(["cmst:group cmst:overflow-hidden cmst:rounded cmst:bg-cmst-matte", a.value ? "cmst:ring-2 cmst:ring-cmst-primary cmst:ring-inset" : ""])
    }, [
      u("div", Fw, [
        u("button", {
          type: "button",
          class: "cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:p-0 cmst:text-left",
          "aria-label": `Open ${e.record.workflow || e.record.id}`,
          "data-testid": `vue-history-card-${e.record.id}`,
          onClick: A[0] || (A[0] = (b) => n("select", e.record)),
          onKeydown: A[1] || (A[1] = zs((b) => n("select", e.record), ["enter"]))
        }, [
          e.record.featuredOutput ? (k(), S("img", {
            key: 0,
            src: p(rr)(e.record.featuredOutput),
            alt: e.record.workflow || e.record.id,
            class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
            loading: "lazy"
          }, null, 8, Bw)) : (k(), S("span", qw, [
            H(p(Yp), { class: "cmst:size-[18px]" })
          ]))
        ], 40, Ww),
        u("div", {
          class: Ae(["cmst-hover-actions cmst:absolute cmst:right-1.5 cmst:top-1.5 cmst:flex cmst:gap-1", e.record.favorite || a.value ? "cmst-hover-actions-pinned" : ""])
        }, [
          u("button", {
            type: "button",
            class: "cmst-icon-btn cmst:bg-cmst-raised/90",
            "aria-pressed": e.record.favorite ? "true" : "false",
            "aria-label": e.record.favorite ? `Remove ${e.record.id} from favorites` : `Add ${e.record.id} to favorites`,
            "data-testid": `vue-history-favorite-${e.record.id}`,
            onClick: A[2] || (A[2] = (b) => f(b))
          }, [
            H(p(Wr), {
              class: Ae(["cmst:size-3.5", e.record.favorite ? "cmst:fill-cmst-primary cmst:text-cmst-primary" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ], 8, Gw),
          u("button", {
            type: "button",
            class: "cmst-icon-btn cmst:bg-cmst-raised/90",
            "aria-pressed": a.value ? "true" : "false",
            "aria-label": a.value ? `Deselect ${e.record.id}` : `Select ${e.record.id}`,
            "data-testid": `vue-history-select-${e.record.id}`,
            onClick: A[3] || (A[3] = (b) => y(b))
          }, [
            H(p(qp), {
              class: Ae(["cmst:size-3.5", a.value ? "cmst:text-cmst-primary" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ], 8, Hw)
        ], 2)
      ]),
      u("button", {
        type: "button",
        class: "cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:px-2.5 cmst:py-2 cmst:text-left",
        "aria-label": `Open ${e.record.workflow || e.record.id}`,
        onClick: A[4] || (A[4] = (b) => n("select", e.record))
      }, [
        u("span", Kw, L(l.value), 1),
        u("span", Jw, [
          K(L(e.record.status), 1),
          i.value ? (k(), S(fe, { key: 0 }, [
            K(" · " + L(i.value), 1)
          ], 64)) : te("", !0),
          d.value ? (k(), S(fe, { key: 1 }, [
            K(" · " + L(d.value), 1)
          ], 64)) : te("", !0)
        ])
      ], 8, Zw)
    ], 2));
  }
}), Yw = /* @__PURE__ */ xt({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = e, n = t, r = ur(), o = ye(() => {
      const a = Number.parseInt(String(r.columnsPreference ?? "4"), 10);
      return Number.isNaN(a) ? 4 : Math.min(8, Math.max(2, a));
    });
    return (a, i) => (k(), S("div", {
      class: "cmst:grid cmst:gap-0.5",
      style: wn({ gridTemplateColumns: `repeat(${o.value}, minmax(0, 1fr))` }),
      "data-testid": "vue-history-grid"
    }, [
      (k(!0), S(fe, null, ze(s.records, (l) => (k(), ut(Qw, {
        key: `${l.kind}:${l.id}`,
        record: l,
        onSelect: i[0] || (i[0] = (c) => n("select", c))
      }, null, 8, ["record"]))), 128))
    ], 4));
  }
}), Xw = ["aria-label", "onKeydown"], e_ = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, t_ = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, s_ = { class: "cmst:text-lg cmst:font-semibold" }, n_ = { class: "cmst:text-xs cmst:opacity-70" }, r_ = {
  key: 0,
  class: "cmst:mt-2 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, o_ = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70",
  role: "status"
}, a_ = ["src", "alt", "data-testid"], i_ = {
  key: 3,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, l_ = {
  key: 4,
  class: "cmst:mt-3 cmst:text-sm cmst:text-red-300"
}, c_ = {
  key: 5,
  class: "cmst:mt-3 cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-viewer-params"
}, u_ = { class: "cmst:mt-1" }, d_ = { class: "cmst:opacity-70" }, f_ = {
  key: 6,
  class: "cmst:mt-3 cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-viewer-attempts"
}, m_ = { class: "cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, p_ = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, h_ = { class: "cmst:mt-2 cmst:flex cmst:items-center cmst:gap-2" }, g_ = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-xs" }, v_ = ["data-testid"], y_ = {
  key: 0,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, b_ = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, w_ = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:opacity-70"
}, __ = { class: "cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1" }, x_ = {
  key: 1,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, k_ = { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, S_ = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, C_ = ["data-testid"], $_ = ["data-testid", "aria-label", "onClick", "onKeydown"], I_ = ["data-testid"], R_ = {
  key: 0,
  class: "cmst:opacity-70"
}, A_ = { class: "cmst:mt-4 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, E_ = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, O_ = { key: 0 }, T_ = {
  key: 1,
  class: "cmst:flex cmst:items-center cmst:gap-2"
}, P_ = { class: "cmst:text-xs" }, N_ = /* @__PURE__ */ xt({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = e, n = t, r = xn(), o = /* @__PURE__ */ T(s.record?.note ?? ""), a = /* @__PURE__ */ T(!1), i = /* @__PURE__ */ T(null), l = /* @__PURE__ */ T(null), c = /* @__PURE__ */ T(null), d = /* @__PURE__ */ T(null), f = (b) => b ? Object.entries(b.params).map(([w, O]) => [w, String(O ?? "")]) : [], y = (b) => b && b.charAt(0).toUpperCase() + b.slice(1);
    xs(() => {
      c.value = document.activeElement, o.value = s.record?.note ?? "", l.value?.focus();
    }), uo(() => {
      c.value?.focus?.();
    });
    async function v(b, w) {
      i.value = b;
      try {
        await w();
      } catch {
      } finally {
        i.value = null;
      }
    }
    function A() {
      n("close");
    }
    return (b, w) => e.record ? (k(), S("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-state": "open",
      "data-testid": "vue-history-viewer",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": `${e.record.kind} detail`,
      tabindex: "-1",
      onKeydown: zs(er(A, ["stop"]), ["esc"])
    }, [
      u("div", e_, [
        u("div", t_, [
          u("div", null, [
            u("h2", s_, L(e.record.workflow || e.record.id), 1),
            u("p", n_, L(y(e.record.status)) + " · " + L(e.record.kind) + " · " + L(e.record.id), 1)
          ]),
          H(re, {
            ref_key: "closeBtn",
            ref: l,
            variant: "outline",
            size: "sm",
            "data-testid": "vue-viewer-close",
            onClick: A
          }, {
            default: se(() => [...w[13] || (w[13] = [
              K("Close", -1)
            ])]),
            _: 1
          }, 512)
        ]),
        p(r).detailError ? (k(), S("div", r_, L(p(r).detailError), 1)) : te("", !0),
        p(r).actionMessage ? (k(), S("p", o_, L(p(r).actionMessage), 1)) : te("", !0),
        e.record.featuredOutput ? (k(), S("img", {
          key: 2,
          src: p(Yu)(e.record.featuredOutput),
          alt: e.record.workflow || e.record.id,
          class: "cmst:mx-auto cmst:mt-4 cmst:max-h-[50vh] cmst:max-w-full cmst:object-contain",
          "data-testid": `vue-viewer-image-${e.record.id}`
        }, null, 8, a_)) : (k(), S("p", i_, "No projected image asset.")),
        e.record.errors.length ? (k(), S("div", l_, [
          (k(!0), S(fe, null, ze(e.record.errors, (O, I) => (k(), S("p", { key: I }, L(O.code) + ": " + L(O.message), 1))), 128))
        ])) : te("", !0),
        f(e.record).length ? (k(), S("div", c_, [
          w[14] || (w[14] = u("h3", { class: "cmst:font-semibold" }, "Parameters", -1)),
          u("dl", u_, [
            (k(!0), S(fe, null, ze(f(e.record), ([O, I]) => (k(), S("div", {
              key: O,
              class: "cmst:flex cmst:gap-2"
            }, [
              u("dt", d_, L(O), 1),
              u("dd", null, L(I), 1)
            ]))), 128))
          ])
        ])) : te("", !0),
        e.record.attempts.length ? (k(), S("div", f_, [
          w[15] || (w[15] = u("h3", { class: "cmst:font-semibold" }, "Attempts", -1)),
          (k(!0), S(fe, null, ze(e.record.attempts, (O) => (k(), S("p", {
            key: O.index
          }, "Attempt " + L(O.index) + ": " + L(O.status), 1))), 128))
        ])) : te("", !0),
        u("div", m_, [
          u("div", p_, [
            w[18] || (w[18] = u("h3", { class: "cmst:font-semibold" }, "Annotations", -1)),
            u("div", h_, [
              H(re, {
                size: "sm",
                variant: "outline",
                "aria-pressed": e.record.favorite ? "true" : "false",
                "data-testid": `vue-viewer-favorite-${e.record.id}`,
                onClick: w[0] || (w[0] = (O) => v("favorite", () => p(r).setFavorite(e.record, !e.record.favorite)))
              }, {
                default: se(() => [
                  K(L(e.record.favorite ? "★ Favorited" : "☆ Favorite"), 1)
                ]),
                _: 1
              }, 8, ["aria-pressed", "data-testid"])
            ]),
            u("label", g_, [
              w[16] || (w[16] = K(" Note ", -1)),
              Fe(u("textarea", {
                "onUpdate:modelValue": w[1] || (w[1] = (O) => o.value = O),
                rows: "2",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-sm",
                "data-testid": `vue-viewer-note-${e.record.id}`
              }, null, 8, v_), [
                [lt, o.value]
              ])
            ]),
            H(re, {
              class: "cmst:mt-2",
              size: "sm",
              variant: "secondary",
              "data-testid": `vue-viewer-note-save-${e.record.id}`,
              onClick: w[2] || (w[2] = (O) => v("note", () => p(r).setNote(e.record, o.value)))
            }, {
              default: se(() => [...w[17] || (w[17] = [
                K("Save note", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          e.record.kind === "generation" ? (k(), S("div", y_, [
            w[27] || (w[27] = u("h3", { class: "cmst:font-semibold" }, "Replay", -1)),
            u("div", b_, [
              H(re, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || i.value !== null,
                "data-testid": `vue-viewer-original-${e.record.id}`,
                onClick: w[3] || (w[3] = (O) => v("original", () => p(r).runReplayAction(e.record, "original")))
              }, {
                default: se(() => [...w[19] || (w[19] = [
                  K("Generate Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              H(re, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || i.value !== null,
                "data-testid": `vue-viewer-retry-${e.record.id}`,
                onClick: w[4] || (w[4] = (O) => v("retry", () => p(r).runReplayAction(e.record, "retry")))
              }, {
                default: se(() => [...w[20] || (w[20] = [
                  K("Retry Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              H(re, {
                size: "sm",
                variant: "outline",
                disabled: i.value !== null,
                "data-testid": `vue-viewer-resume-${e.record.id}`,
                onClick: w[5] || (w[5] = (O) => v("resume", () => p(r).runReplayAction(e.record, "resume")))
              }, {
                default: se(() => [...w[21] || (w[21] = [
                  K("Resume", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"])
            ]),
            e.record.replayCapable ? te("", !0) : (k(), S("p", w_, L(e.record.replayReason || "Not replay-capable."), 1)),
            w[28] || (w[28] = u("h3", { class: "cmst:mt-3 cmst:font-semibold" }, "Outputs", -1)),
            (k(!0), S(fe, null, ze(e.record.outputs, (O) => (k(), S("div", {
              key: O.index,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs"
            }, [
              u("p", null, L(O.filename || `output ${O.index}`) + " · " + L(O.exportState), 1),
              u("div", __, [
                H(re, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-download-${O.assetId}`,
                  onClick: (I) => v(`download-${O.index}`, () => p(r).downloadHistoryAsset(e.record, O, "original"))
                }, {
                  default: se(() => [...w[22] || (w[22] = [
                    K("Download", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                H(re, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-export-${O.assetId}`,
                  onClick: (I) => v(`export-${O.index}`, () => p(r).exportAsset(O))
                }, {
                  default: se(() => [...w[23] || (w[23] = [
                    K("Export", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                H(re, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (I) => v(`open-${O.index}`, () => p(r).openHistoryAsset(O.assetId))
                }, {
                  default: se(() => [...w[24] || (w[24] = [
                    K("Open", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                H(re, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (I) => v(`reveal-${O.index}`, () => p(r).revealHistoryAsset(O.assetId))
                }, {
                  default: se(() => [...w[25] || (w[25] = [
                    K("Reveal", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                H(re, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-featured-${O.index}`,
                  onClick: (I) => v("featured", () => p(r).setFeatured(e.record, O.index))
                }, {
                  default: se(() => [...w[26] || (w[26] = [
                    K("Feature", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"])
              ])
            ]))), 128))
          ])) : (k(), S("div", x_, [
            w[32] || (w[32] = u("h3", { class: "cmst:font-semibold" }, "Experiment", -1)),
            u("p", k_, "Cells: " + L(e.record.counts.cells) + " · Results: " + L(e.record.counts.results) + " · Failed: " + L(e.record.counts.failed), 1),
            u("div", S_, [
              H(re, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-resume-${e.record.id}`,
                onClick: w[6] || (w[6] = (O) => v("exp-resume", () => p(r).runExperimentAction(e.record, "resume")))
              }, {
                default: se(() => [...w[29] || (w[29] = [
                  K("Resume", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"]),
              H(re, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-cancel-${e.record.id}`,
                onClick: w[7] || (w[7] = (O) => v("exp-cancel", () => p(r).runExperimentAction(e.record, "cancel")))
              }, {
                default: se(() => [...w[30] || (w[30] = [
                  K("Cancel", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"])
            ]),
            (k(!0), S(fe, null, ze(e.record.cells, (O) => (k(), S("div", {
              key: O.id,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs",
              "data-testid": `vue-cell-${O.id}`
            }, [
              u("button", {
                type: "button",
                class: "cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:text-left",
                "data-testid": `vue-cell-open-${O.id}`,
                "aria-label": `Open cell ${O.id}`,
                onClick: (I) => d.value = d.value === O.id ? null : O.id,
                onKeydown: zs(er((I) => d.value = d.value === O.id ? null : O.id, ["prevent"]), ["enter"])
              }, [
                u("p", null, L(O.id) + " · " + L(O.status), 1)
              ], 40, $_),
              d.value === O.id ? (k(), S("div", {
                key: 0,
                "data-testid": `vue-cell-detail-${O.id}`,
                tabindex: "0"
              }, [
                u("p", null, L(O.featuredOutput ? "Preview available" : "No preview projected") + " · " + L(O.status), 1),
                O.prompt ? (k(), S("p", R_, L(O.prompt), 1)) : te("", !0)
              ], 8, I_)) : te("", !0),
              O.status === "failed" ? (k(), ut(re, {
                key: 1,
                class: "cmst:mt-1",
                size: "sm",
                variant: "ghost",
                "data-testid": `vue-cell-retry-${O.id}`,
                onClick: (I) => v(`cell-${O.id}`, () => p(r).runExperimentAction(e.record, "cancel", O.id))
              }, {
                default: se(() => [...w[31] || (w[31] = [
                  K("Retry cell", -1)
                ])]),
                _: 1
              }, 8, ["data-testid", "onClick"])) : te("", !0)
            ], 8, C_))), 128))
          ]))
        ]),
        u("div", A_, [
          u("div", E_, [
            H(re, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-a-${e.record.id}`,
              onClick: w[8] || (w[8] = (O) => p(r).selectCompare("a", e.record.id))
            }, {
              default: se(() => [...w[33] || (w[33] = [
                K("Compare A", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            H(re, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-b-${e.record.id}`,
              onClick: w[9] || (w[9] = (O) => p(r).selectCompare("b", e.record.id))
            }, {
              default: se(() => [...w[34] || (w[34] = [
                K("Compare B", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          a.value ? (k(), S("div", T_, [
            u("span", P_, "Delete this " + L(e.record.kind) + "?", 1),
            H(re, {
              size: "sm",
              "data-testid": `vue-delete-confirm-${e.record.id}`,
              onClick: w[11] || (w[11] = (O) => v("delete", () => p(r).remove(e.record).then(A)))
            }, {
              default: se(() => [...w[36] || (w[36] = [
                K("Confirm delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            H(re, {
              size: "sm",
              variant: "ghost",
              onClick: w[12] || (w[12] = (O) => a.value = !1)
            }, {
              default: se(() => [...w[37] || (w[37] = [
                K("Cancel", -1)
              ])]),
              _: 1
            })
          ])) : (k(), S("div", O_, [
            H(re, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-delete-${e.record.id}`,
              onClick: w[10] || (w[10] = (O) => a.value = !0)
            }, {
              default: se(() => [...w[35] || (w[35] = [
                K("Delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]))
        ])
      ])
    ], 40, Xw)) : te("", !0);
  }
}), ed = /* @__PURE__ */ xt({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (k(), S("div", {
      class: Ae(
        p(Xa)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg"
        )
      )
    }, [
      Ac(t.$slots, "default")
    ], 2));
  }
});
function M_() {
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
const z_ = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, j_ = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70",
  "data-testid": "vue-picker-empty"
}, D_ = {
  key: 1,
  class: "cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:sm:grid-cols-3"
}, L_ = ["data-testid", "aria-label", "onClick"], U_ = ["src", "alt"], V_ = { class: "cmst:mt-1 cmst:block cmst:truncate cmst:text-xs" }, F_ = { class: "cmst:mt-3 cmst:flex cmst:justify-center" }, td = /* @__PURE__ */ xt({
  __name: "HistoryPicker",
  emits: ["select", "cancel"],
  setup(e, { emit: t }) {
    const s = xn(), n = /* @__PURE__ */ T(""), r = /* @__PURE__ */ T(null);
    xs(async () => {
      r.value = M_(), await s.initialize();
    });
    const o = t;
    let a;
    function i(c) {
      window.clearTimeout(a), a = window.setTimeout(() => {
        s.setQuery(c), s.loadFeed();
      }, 250);
    }
    function l(c) {
      o("select", c);
    }
    return (c, d) => r.value ? (k(), ut(kc, {
      key: 0,
      to: r.value
    }, [
      u("div", {
        class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
        "data-state": "open",
        "data-testid": "vue-history-picker",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": "Pick a History generation",
        tabindex: "-1",
        onKeydown: d[4] || (d[4] = zs(er((f) => o("cancel"), ["stop"]), ["esc"]))
      }, [
        H(ed, { class: "cmst:w-[min(48rem,94vw)] cmst:max-h-[86vh] cmst:overflow-auto cmst:p-4" }, {
          default: se(() => [
            u("div", z_, [
              d[6] || (d[6] = u("h2", { class: "cmst:text-base cmst:font-semibold" }, "Pick from History", -1)),
              H(re, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-picker-cancel",
                onClick: d[0] || (d[0] = (f) => o("cancel"))
              }, {
                default: se(() => [...d[5] || (d[5] = [
                  K("Cancel", -1)
                ])]),
                _: 1
              })
            ]),
            Fe(u("input", {
              "onUpdate:modelValue": d[1] || (d[1] = (f) => n.value = f),
              class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              placeholder: "Search generations",
              "aria-label": "Search generations",
              onInput: d[2] || (d[2] = (f) => i(f.target.value))
            }, null, 544), [
              [lt, n.value]
            ]),
            p(s).records.length ? (k(), S("div", D_, [
              (k(!0), S(fe, null, ze(p(s).records, (f) => (k(), S("button", {
                key: `${f.kind}:${f.id}`,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-picker-option-${f.id}`,
                "aria-label": `Select ${f.workflow || f.id}`,
                onClick: (y) => l(f)
              }, [
                f.featuredOutput ? (k(), S("img", {
                  key: 0,
                  src: p(rr)(f.featuredOutput),
                  alt: f.workflow || f.id,
                  class: "cmst:aspect-square cmst:w-full cmst:object-cover cmst:rounded",
                  loading: "lazy"
                }, null, 8, U_)) : te("", !0),
                u("span", V_, L(f.workflow || f.id), 1)
              ], 8, L_))), 128))
            ])) : (k(), S("div", j_, "No generations match.")),
            u("div", F_, [
              p(s).hasMore ? (k(), ut(re, {
                key: 0,
                variant: "outline",
                size: "sm",
                onClick: d[3] || (d[3] = (f) => p(s).loadFeed(!0))
              }, {
                default: se(() => [...d[7] || (d[7] = [
                  K("Load more", -1)
                ])]),
                _: 1
              })) : te("", !0)
            ])
          ]),
          _: 1
        })
      ], 32)
    ], 8, ["to"])) : te("", !0);
  }
}), W_ = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, B_ = { class: "cmst:flex cmst:gap-1.5" }, q_ = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, G_ = { class: "cmst-media-well cmst:flex cmst:aspect-[4/3] cmst:items-center cmst:justify-center" }, H_ = ["src", "alt", "data-testid"], Z_ = {
  key: 1,
  class: "cmst:px-3 cmst:text-center cmst:text-xs cmst:text-cmst-muted"
}, K_ = { class: "cmst-type-meta cmst:mt-1 cmst:truncate" }, J_ = /* @__PURE__ */ xt({
  __name: "CompareViewer",
  setup(e) {
    const t = xn(), s = ye(() => t.compareRecords);
    function n(a) {
      return t.records.find((i) => i.id === a) ?? null;
    }
    function r(a) {
      const i = n(a)?.featuredOutput;
      return i ? Xu(i) : null;
    }
    function o(a) {
      const i = a === "a" ? t.compareA : t.compareB, l = n(i);
      return l ? `${a.toUpperCase()} · ${l.workflow || l.id}` : `Slot ${a.toUpperCase()} empty or deleted.`;
    }
    return (a, i) => s.value.a || s.value.b ? (k(), ut(ed, {
      key: 0,
      class: "cmst:p-4",
      "data-testid": "vue-compare"
    }, {
      default: se(() => [
        u("div", W_, [
          i[4] || (i[4] = u("div", { class: "cmst:min-w-0" }, [
            u("h3", { class: "cmst-type-section" }, "Compare"),
            u("p", { class: "cmst-type-meta cmst:mt-0.5" }, "transient — never persisted")
          ], -1)),
          u("div", B_, [
            H(re, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-swap",
              onClick: i[0] || (i[0] = (l) => p(t).swapCompare())
            }, {
              default: se(() => [...i[2] || (i[2] = [
                K("Switch A/B", -1)
              ])]),
              _: 1
            }),
            H(re, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-clear",
              onClick: i[1] || (i[1] = (l) => p(t).clearCompare())
            }, {
              default: se(() => [...i[3] || (i[3] = [
                K("Clear", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        u("div", q_, [
          (k(), S(fe, null, ze(["a", "b"], (l) => u("figure", {
            key: l,
            class: "cmst:min-w-0"
          }, [
            u("div", G_, [
              r(l === "a" ? p(t).compareA : p(t).compareB) ? (k(), S("img", {
                key: 0,
                src: r(l === "a" ? p(t).compareA : p(t).compareB),
                alt: `Compare ${l.toUpperCase()}`,
                class: "cmst:max-h-full cmst:max-w-full cmst:object-contain",
                "data-testid": `vue-compare-${l}`
              }, null, 8, H_)) : (k(), S("span", Z_, "Slot " + L(l.toUpperCase()) + " empty or deleted.", 1))
            ]),
            u("figcaption", K_, L(o(l)), 1)
          ])), 64))
        ])
      ]),
      _: 1
    })) : te("", !0);
  }
}), Q_ = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, Y_ = { class: "cmst-type-meta cmst:mt-0.5" }, X_ = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, ex = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-xs cmst:text-cmst-muted" }, tx = {
  class: "cmst-type-meta",
  "aria-hidden": "true"
}, sx = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, nx = { class: "cmst:relative" }, rx = ["value"], ox = ["value"], ax = { class: "cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px] cmst:text-cmst-muted" }, ix = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-danger",
  role: "alert"
}, lx = {
  key: 1,
  class: "cmst:py-6 cmst:text-[13px] cmst:text-cmst-muted"
}, cx = {
  key: 2,
  class: "cmst:py-6 cmst:text-[13px] cmst:text-cmst-muted",
  "data-testid": "vue-history-empty"
}, ux = {
  key: 0,
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2"
}, dx = { class: "cmst-type-meta" }, fx = { class: "cmst:flex cmst:justify-center" }, mx = /* @__PURE__ */ xt({
  __name: "HistoryView",
  setup(e) {
    const t = xn(), s = ur(), n = yu(), r = vu(), o = /* @__PURE__ */ T(t.query), a = /* @__PURE__ */ T(!1), i = ye({
      get: () => {
        const A = Number.parseInt(String(s.columnsPreference ?? "4"), 10);
        return Number.isNaN(A) ? 4 : Math.min(8, Math.max(2, A));
      },
      set: (A) => s.setHistoryColumns(String(A))
    });
    function l() {
      const A = n.query.focus;
      return typeof A == "string" && A !== "" ? A : null;
    }
    xs(async () => {
      await t.initialize(), await t.applyRouteFocus(l());
    }), Wt(
      () => n.query.focus,
      (A) => {
        t.applyRouteFocus(typeof A == "string" ? A : null);
      }
    );
    let c;
    Wt(o, (A) => {
      window.clearTimeout(c), c = window.setTimeout(() => {
        t.setQuery(A), t.loadFeed();
      }, 250);
    });
    async function d(A) {
      t.setFocus(A.id), await r.replace({ name: "history", query: { focus: A.id } }), await t.loadDetail(A.id, A.kind), t.viewerOpen = !0;
    }
    async function f() {
      t.viewerOpen = !1, await r.replace({ name: "history" });
    }
    function y(A) {
      a.value = !1, d(A);
    }
    function v() {
      t.setQuery(""), o.value = "", t.setStatusFilter(""), t.setKindFilter("mixed"), t.loadFeed();
    }
    return (A, b) => (k(), S("section", {
      class: Ae(p(fr)()),
      "data-testid": "vue-page-history"
    }, [
      u("div", Q_, [
        u("div", null, [
          b[15] || (b[15] = u("h1", { class: "cmst-type-view" }, "History", -1)),
          u("p", Y_, L(p(t).records.length) + " records · " + L(p(t).selection.length) + " selected ", 1)
        ]),
        u("div", X_, [
          u("label", ex, [
            b[16] || (b[16] = u("span", { "aria-hidden": "true" }, "Tiles", -1)),
            Fe(u("input", {
              "onUpdate:modelValue": b[0] || (b[0] = (w) => i.value = w),
              type: "range",
              min: "2",
              max: "8",
              step: "1",
              "aria-label": "Thumbnail columns",
              "data-testid": "vue-history-thumb-size",
              class: "cmst:accent-cmst-primary"
            }, null, 512), [
              [
                lt,
                i.value,
                void 0,
                { number: !0 }
              ]
            ]),
            u("span", tx, L(i.value), 1)
          ]),
          H(re, {
            variant: "secondary",
            size: "sm",
            "data-testid": "vue-history-picker-open",
            onClick: b[1] || (b[1] = (w) => a.value = !0)
          }, {
            default: se(() => [...b[17] || (b[17] = [
              K("Pick generation", -1)
            ])]),
            _: 1
          }),
          H(re, {
            variant: "ghost",
            size: "icon",
            "aria-label": "Refresh history",
            disabled: p(t).loading,
            onClick: b[2] || (b[2] = (w) => p(t).loadFeed())
          }, {
            default: se(() => [
              H(p(vo), {
                class: Ae(["cmst:size-4", p(t).loading ? "cmst:animate-spin" : ""]),
                "aria-hidden": "true"
              }, null, 8, ["class"])
            ]),
            _: 1
          }, 8, ["disabled"])
        ])
      ]),
      u("div", sx, [
        u("div", nx, [
          H(p(_u), {
            class: "cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted",
            "aria-hidden": "true"
          }),
          Fe(u("input", {
            "onUpdate:modelValue": b[3] || (b[3] = (w) => o.value = w),
            class: "cmst-field cmst:w-52 cmst:pl-8",
            placeholder: "Search history",
            "aria-label": "Search history",
            "data-testid": "vue-history-search"
          }, null, 512), [
            [lt, o.value]
          ])
        ]),
        u("select", {
          value: p(t).kindFilter,
          class: "cmst-field",
          "aria-label": "Record kind",
          onChange: b[4] || (b[4] = (w) => {
            p(t).setKindFilter(w.target.value), p(t).loadFeed();
          })
        }, [...b[18] || (b[18] = [
          u("option", { value: "mixed" }, "All kinds", -1),
          u("option", { value: "generation" }, "Generations", -1),
          u("option", { value: "experiment" }, "Experiments", -1)
        ])], 40, rx),
        u("select", {
          value: p(t).statusFilter,
          class: "cmst-field",
          "aria-label": "Status filter",
          onChange: b[5] || (b[5] = (w) => {
            p(t).setStatusFilter(w.target.value), p(t).loadFeed();
          })
        }, [...b[19] || (b[19] = [
          Ur('<option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="running">Running</option><option value="canceled">Canceled</option>', 5)
        ])], 40, ox),
        Fe(u("select", {
          "onUpdate:modelValue": b[6] || (b[6] = (w) => p(t).sort = w),
          class: "cmst-field",
          "aria-label": "Sort order",
          onChange: b[7] || (b[7] = (w) => {
            p(t).setSort(p(t).sort), p(t).loadFeed();
          })
        }, [...b[20] || (b[20] = [
          u("option", { value: "newest" }, "Newest", -1),
          u("option", { value: "oldest" }, "Oldest", -1),
          u("option", { value: "fastest" }, "Fastest", -1),
          u("option", { value: "slowest" }, "Slowest", -1)
        ])], 544), [
          [ps, p(t).sort]
        ]),
        u("label", ax, [
          Fe(u("input", {
            "onUpdate:modelValue": b[8] || (b[8] = (w) => p(t).favoriteOnly = w),
            type: "checkbox",
            onChange: b[9] || (b[9] = (w) => {
              p(t).setFavoriteOnly(p(t).favoriteOnly), p(t).loadFeed();
            })
          }, null, 544), [
            [ln, p(t).favoriteOnly]
          ]),
          b[21] || (b[21] = K(" Favorites ", -1))
        ])
      ]),
      p(t).error ? (k(), S("div", ix, [
        K(L(p(t).error) + " ", 1),
        H(re, {
          class: "cmst:ml-2",
          size: "sm",
          variant: "ghost",
          onClick: b[10] || (b[10] = (w) => p(t).loadFeed())
        }, {
          default: se(() => [...b[22] || (b[22] = [
            K("Retry", -1)
          ])]),
          _: 1
        })
      ])) : te("", !0),
      p(t).loading && !p(t).records.length ? (k(), S("p", lx, " Loading history… ")) : p(t).records.length ? (k(), S(fe, { key: 3 }, [
        p(t).selection.length ? (k(), S("div", ux, [
          u("span", dx, L(p(t).selection.length) + " selected", 1),
          H(re, {
            size: "sm",
            variant: "outline",
            "data-testid": "vue-history-bulk-delete",
            onClick: b[11] || (b[11] = (w) => p(t).removeSelected())
          }, {
            default: se(() => [
              K("Delete selected (" + L(p(t).selection.length) + ")", 1)
            ]),
            _: 1
          }),
          H(re, {
            size: "sm",
            variant: "ghost",
            onClick: b[12] || (b[12] = (w) => p(t).clearSelection())
          }, {
            default: se(() => [...b[25] || (b[25] = [
              K("Clear selection", -1)
            ])]),
            _: 1
          })
        ])) : te("", !0),
        H(Yw, {
          records: p(t).records,
          onSelect: d
        }, null, 8, ["records"]),
        u("div", fx, [
          p(t).hasMore ? (k(), ut(re, {
            key: 0,
            variant: "outline",
            onClick: b[13] || (b[13] = (w) => p(t).loadFeed(!0))
          }, {
            default: se(() => [...b[26] || (b[26] = [
              K("Load more", -1)
            ])]),
            _: 1
          })) : te("", !0)
        ])
      ], 64)) : (k(), S("div", cx, [
        b[24] || (b[24] = K(" No records match this query. ", -1)),
        H(re, {
          class: "cmst:ml-2",
          size: "sm",
          variant: "ghost",
          onClick: v
        }, {
          default: se(() => [...b[23] || (b[23] = [
            K("Clear filters", -1)
          ])]),
          _: 1
        })
      ])),
      H(J_),
      p(t).viewerOpen ? (k(), ut(N_, {
        key: 4,
        record: p(t).selected,
        onClose: f
      }, null, 8, ["record"])) : te("", !0),
      a.value ? (k(), ut(td, {
        key: 5,
        onSelect: y,
        onCancel: b[14] || (b[14] = (w) => a.value = !1)
      })) : te("", !0)
    ], 2));
  }
});
async function px(e, t = "", s) {
  let n = `/studio/workflows/${encodeURIComponent(e)}/run-context`;
  return t && (n += `?version_id=${encodeURIComponent(t)}`), oe(n, {}, s);
}
async function hx(e, t) {
  return oe("/studio/run", { method: "POST", body: e }, t);
}
async function gx(e, t) {
  return oe("/studio/run_batch", { method: "POST", body: e }, t);
}
async function vx(e, t) {
  return oe(
    "/studio/experiment-v2",
    { method: "POST", body: e },
    t
  );
}
async function yx(e, t) {
  return oe(
    `/studio/experiments/${encodeURIComponent(e)}/stop-now`,
    { method: "POST", body: {} },
    t
  );
}
async function bx(e, t = fetch) {
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
    const r = await n.json(), o = r.files, a = typeof r.name == "string" ? r.name : Array.isArray(o) && typeof o[0] == "string" ? o[0] : void 0;
    return a ? { ok: !0, filename: a } : { ok: !1, message: "Upload returned no filename" };
  } catch {
    return { ok: !1, message: "Upload returned an unreadable response" };
  }
}
function Tn(e) {
  try {
    if (typeof crypto < "u" && typeof crypto.randomUUID == "function")
      return crypto.randomUUID();
  } catch {
  }
  return `${e}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
const zl = {
  generate: ["text", "references", "layout", "sketch", "guidance"],
  edit: ["text", "references", "select", "expand", "sketch"],
  post: ["adjust", "color", "detail", "effects", "crop", "heal", "upscale"]
}, Ra = ["upscale"], wx = new Set(
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
), _x = /* @__PURE__ */ new Set(["model_unet", "model", "unet", "clip", "vae", "model_clip", "model_vae"]);
function $s(e) {
  try {
    if (typeof structuredClone == "function") return structuredClone(e);
  } catch {
  }
  return JSON.parse(JSON.stringify(e));
}
function xx(e) {
  const t = {};
  for (const [s, n] of Object.entries(e))
    wx.has(s.toLowerCase()) || (t[s] = n);
  return t;
}
function kx(e, t) {
  return e === "source_image" || e === "mask" ? !0 : t?.control_kind === "image";
}
function Sx(e, t) {
  return _x.has(e) ? !0 : !t || typeof t != "object" ? !1 : t.control_kind === "file" || t.control_kind === "model";
}
function Jo(e, t) {
  const s = {};
  for (const [n, r] of Object.entries(e))
    !r || typeof r != "object" || (r.default !== void 0 ? s[n] = r.default : Array.isArray(r.enum_options) && r.enum_options.length && (s[n] = r.enum_options[0]));
  return s;
}
function Cx(e, t) {
  const s = [];
  for (const [n, r] of Object.entries(e)) {
    const o = t[n];
    if (!o) {
      s.push({ field: n, message: `unknown control '${n}'` });
      continue;
    }
    !kx(n, o) && !Sx(n, o) && Array.isArray(o.enum_options) && o.enum_options.length && r !== void 0 && r !== null && !o.enum_options.some((a) => a === r) && s.push({ field: n, message: "must be one of the available options" }), typeof r == "number" && (typeof o.minimum == "number" && r < o.minimum && s.push({ field: n, message: `must be >= ${o.minimum}` }), typeof o.maximum == "number" && r > o.maximum && s.push({ field: n, message: `must be <= ${o.maximum}` })), o.required && (r == null || typeof r == "string" && r.trim() === "") && s.push({ field: n, message: "required" });
  }
  for (const [n, r] of Object.entries(t))
    r?.required && !Object.prototype.hasOwnProperty.call(e, n) && s.push({ field: n, message: `missing required control '${n}'` });
  return s;
}
const jl = (e, t) => gs(
  `playground.draft.${e}.${t}`,
  {}
), Qo = gs(
  "playground.selection.v1",
  { workflowId: "", versionId: "" }
), Dl = gs(
  "playground.current-generation.v1",
  { key: "", generationId: "" }
), $x = /* @__PURE__ */ _n("studio-playground", () => {
  const e = /* @__PURE__ */ T("txt2img"), t = /* @__PURE__ */ T(!1), s = /* @__PURE__ */ T(!1), n = /* @__PURE__ */ T("generate"), r = /* @__PURE__ */ T("text"), o = /* @__PURE__ */ T(Qo.read().workflowId), a = /* @__PURE__ */ T(Qo.read().versionId), i = /* @__PURE__ */ T(null), l = /* @__PURE__ */ T({}), c = /* @__PURE__ */ T({}), d = /* @__PURE__ */ T("idle"), f = /* @__PURE__ */ T(""), y = /* @__PURE__ */ T([]), v = /* @__PURE__ */ T(!1), A = /* @__PURE__ */ T(0), b = /* @__PURE__ */ T(""), w = /* @__PURE__ */ T(0), O = /* @__PURE__ */ T(!1), I = /* @__PURE__ */ T(""), V = /* @__PURE__ */ T([]), R = /* @__PURE__ */ T({}), J = /* @__PURE__ */ T({}), be = /* @__PURE__ */ T(null), ee = /* @__PURE__ */ T(!1), M = /* @__PURE__ */ T({
    status: "idle",
    message: "",
    runId: "",
    experimentId: ""
  }), C = /* @__PURE__ */ T(null), F = /* @__PURE__ */ T(null), Se = /* @__PURE__ */ T(""), Ce = /* @__PURE__ */ T([]), Me = /* @__PURE__ */ T({}), He = bn(), ue = ye(() => `${o.value}::${a.value}`), W = ye(() => Cx(c.value, l.value)), E = ye(() => {
    if (d.value === "loading") return "Loading workflow…";
    if (d.value === "error") return f.value || "Workflow unavailable";
    if (!o.value) return "Select a workflow to begin";
    if (!v.value)
      return y.value[0] || "This workflow is not runnable yet";
    const Z = W.value.find((pe) => pe.message === "required" || pe.message.startsWith("missing"));
    return Z ? `Fill in ${Z.field} to generate` : Ra.includes(r.value) ? "This tool arrives in a later phase — execution is disabled" : _.value ? "A run is already in flight" : null;
  }), _ = ye(() => M.value.status === "submitting" || M.value.status === "running"), X = ye(() => Ce.value.length), ne = ye(
    () => Object.entries(Me.value).filter(([, Z]) => Z.enabled && Z.values.length > 0)
  );
  function Xe() {
    Qo.write({ workflowId: o.value, versionId: a.value });
  }
  function qe() {
    if (!(!o.value || !a.value))
      try {
        jl(o.value, a.value).write({ ...c.value });
      } catch {
      }
  }
  function mt(Z) {
    e.value = Z;
  }
  function at(Z) {
    t.value = Z, Z && (s.value = !1);
  }
  function We(Z) {
    s.value = Z, Z && (t.value = !1);
  }
  function Oe(Z, pe) {
    n.value = Z, r.value = pe;
  }
  function q(Z, pe) {
    c.value = { ...c.value, [Z]: pe }, ee.value = !0, qe();
  }
  function j() {
    c.value = Jo(l.value), V.value = [], R.value = {}, J.value = {}, ee.value = !1, D(), qe();
  }
  function D() {
    b.value = "", w.value += 1, O.value = !1, I.value = "";
  }
  function le(Z, pe) {
    b.value = pe, c.value = { ...c.value, source_image: Z }, ee.value = !0, qe();
  }
  function g() {
    const Z = { ...c.value };
    delete Z.source_image, delete Z.mask, c.value = Z, D(), qe();
  }
  function x(Z) {
    return b.value = Z, w.value += 1, O.value = !0, I.value = "", w.value;
  }
  function P(Z, pe, Be) {
    return Z !== w.value || pe !== b.value ? !1 : (O.value = !1, c.value = { ...c.value, source_image: Be }, ee.value = !0, qe(), !0);
  }
  function z(Z, pe, Be) {
    Z !== w.value || pe !== b.value || (O.value = !1, I.value = Be);
  }
  async function $(Z) {
    const pe = ue.value, Be = x(pe), it = await bx(Z);
    return !it.ok || !it.filename ? (z(Be, pe, it.message || "Upload failed"), !1) : P(Be, pe, it.filename);
  }
  function m(Z) {
    V.value = [...V.value, { id: Tn("ref"), filename: Z }], ee.value = !0;
  }
  function h(Z) {
    V.value = V.value.filter((pe) => pe.id !== Z), ee.value = !0;
  }
  function N(Z) {
    J.value = { ...J.value, ...Z }, ee.value = !0;
  }
  function U() {
    J.value = {}, ee.value = !0;
  }
  function G(Z, pe) {
    const Be = Z && typeof Z.controls == "object" ? Z.controls : {}, it = xx(Be);
    c.value = { ...Jo(l.value), ...it }, V.value = [], J.value = {}, D(), B(null), be.value = pe, ee.value = !1, qe();
  }
  async function ge(Z, pe = "", Be) {
    const it = A.value += 1;
    o.value = Z, a.value = pe, i.value = null, l.value = {}, c.value = {}, y.value = [], f.value = "", v.value = !1, D(), V.value = [], d.value = "loading", Xe();
    const kt = await He.run(async (ks) => {
      const _o = await px(Z, pe, Be);
      return ks.aborted ? null : _o;
    });
    if (kt.stale || !kt.value) return { ok: !1, error: "superseded" };
    if (it !== A.value) return { ok: !1, error: "superseded" };
    const Ue = kt.value;
    if (!Ue || Ue.status !== "ok")
      return d.value = "error", f.value = "Could not load workflow", { ok: !1, error: f.value };
    const Ke = Ue.control_schema ?? {}, Tt = Ue.version?.workflow_version_id;
    typeof Tt == "string" && Tt && (a.value = Tt, Xe()), i.value = Ue, l.value = Ke;
    const kn = Array.isArray(
      Ue.version?.reasons
    ) ? Ue.version.reasons : [];
    Ue.version?.runnable !== !0 && !kn.length && kn.push("This workflow is not runnable yet"), Ue.mapping || kn.push("missing mapping"), y.value = kn, v.value = kn.length === 0, d.value = "ready";
    let wo = {};
    try {
      wo = jl(o.value, a.value).read();
    } catch {
      wo = {};
    }
    const ei = { ...Jo(Ke) };
    for (const [ks, _o] of Object.entries(wo))
      Object.prototype.hasOwnProperty.call(Ke, ks) && (ei[ks] = _o);
    c.value = ei, f.value = "";
    try {
      const ks = Dl.read();
      C.value = ks.key === ue.value && ks.generationId ? ks.generationId : null;
    } catch {
      C.value = null;
    }
    return { ok: !0 };
  }
  function ie(Z) {
    return {
      workflow_id: o.value,
      workflow_version_id: a.value,
      featureId: e.value,
      workflow_type: String(
        i.value?.workflow?.workflow_type ?? "t2i"
      ),
      controls: $s({ ...c.value }),
      modal_options: Z ? $s({ ...Z }) : void 0,
      profile_name: null,
      request_id: Tn("req"),
      metadata: {
        source: "studio_playground_vue",
        workflow_id: o.value,
        workflow_version_id: a.value
      },
      trace: {}
    };
  }
  function xe(Z, pe) {
    if (pe.method && (Z.studio_method = pe.method), pe.references && (Z.studio_references = pe.references), pe.guidance && (Z.guidance = pe.guidance), pe.style) {
      Z.studio_style = pe.style;
      const Be = pe.style.composed;
      typeof Be == "string" && (Z.controls = { ...Z.controls, prompt: Be });
    }
  }
  async function Ie(Z = {}) {
    const pe = E.value;
    if (pe) return { ok: !1, error: pe };
    const Be = ie(Z.modalOptions);
    xe(Be, {
      method: Z.method,
      references: Z.references ?? (V.value.length ? { items: $s(V.value.map((Ue) => Ue.filename)), methods: R.value } : void 0),
      guidance: Z.guidance,
      style: Z.style
    }), F.value = $s(Be), Se.value = String(Be.controls.source_image ?? "");
    const it = Pt(), kt = it.start({
      kind: "generation",
      label: "Generation",
      status: "running",
      message: "Submitting…"
    });
    M.value = { status: "submitting", message: "Submitting…", runId: "", experimentId: "" };
    try {
      const Ue = await hx(Be, Z.fetchImpl), Ke = String(Ue.runId ?? Ue.run_id ?? Ue.id ?? "");
      return B(Ke || null), M.value = {
        status: "running",
        message: "Running…",
        runId: Ke,
        experimentId: "",
        detail: Ue
      }, it.patch(kt, { message: "Running…" }), Ue.status === "ok" || Ue.direct_run ? (M.value = { status: "succeeded", message: "Run completed", runId: Ke, experimentId: "", detail: Ue }, it.finish(kt, "Run completed"), Ke && Z.onDone?.({ id: Ke }), { ok: !0 }) : (M.value = { status: "running", message: "Running…", runId: Ke, experimentId: "", detail: Ue }, { ok: !0 });
    } catch (Ue) {
      const Ke = Ue instanceof Error ? Ue.message : "Submission failed";
      return M.value = { status: "failed", message: Ke, runId: "", experimentId: "" }, it.fail(kt, Ke), { ok: !1, error: Ke };
    }
  }
  function Le(Z) {
    return o.value ? (Ce.value = [
      ...Ce.value,
      {
        id: Tn("q"),
        label: Z || `Variant ${Ce.value.length + 1}`,
        workflowId: o.value,
        workflowVersionId: a.value,
        controlValues: $s({ ...c.value })
      }
    ], { ok: !0 }) : { ok: !1, error: "Select a workflow first" };
  }
  function Ze(Z) {
    Ce.value = Ce.value.filter((pe) => pe.id !== Z);
  }
  function Q() {
    Ce.value = [];
  }
  async function de(Z = {}) {
    if (!Ce.value.length) return { ok: !1, error: "Queue is empty" };
    if (_.value) return { ok: !1, error: "A run is already in flight" };
    const pe = Ce.value.filter(
      (Ue) => Ue.workflowId === Ce.value[0].workflowId
    ), Be = Ce.value.filter((Ue) => Ue.workflowId !== Ce.value[0].workflowId);
    if (Ce.value = Be, pe.length === 1) {
      const Ue = pe[0];
      return c.value = { ...Ue.controlValues }, Ie({ modalOptions: Z.modalOptions, fetchImpl: Z.fetchImpl });
    }
    const it = Pt(), kt = it.start({
      kind: "generation",
      label: `Batch (${pe.length})`,
      status: "running",
      message: `Batch running: 0 of ${pe.length} complete`
    });
    M.value = {
      status: "running",
      message: `Batch running: 0 of ${pe.length} complete`,
      runId: "",
      experimentId: ""
    };
    try {
      const Ue = pe.map((Ke) => ({
        request_id: Tn("variant"),
        controls: $s(Ke.controlValues)
      }));
      return await gx(
        {
          profile: null,
          workflow_id: pe[0].workflowId,
          workflow_version_id: pe[0].workflowVersionId,
          request_id: Tn("batch"),
          modal_options: Z.modalOptions ? $s({ ...Z.modalOptions }) : null,
          variants: Ue
        },
        Z.fetchImpl
      ), M.value = { status: "succeeded", message: "Batch submitted", runId: "", experimentId: "" }, it.finish(kt, "Batch submitted"), { ok: !0 };
    } catch (Ue) {
      const Ke = Ue instanceof Error ? Ue.message : "Batch failed";
      return M.value = { status: "failed", message: Ke, runId: "", experimentId: "" }, it.fail(kt, Ke), { ok: !1, error: Ke };
    }
  }
  function ce(Z, pe) {
    const Be = Me.value[Z] ?? { enabled: !1, values: [] };
    Me.value = { ...Me.value, [Z]: { ...Be, ...pe } };
  }
  function Ee() {
    Me.value = {};
  }
  async function je(Z = {}) {
    if (ne.value.length === 0) return { ok: !1, error: "Enable at least one sweep axis" };
    const pe = E.value;
    if (pe && pe !== "A run is already in flight") return { ok: !1, error: pe };
    const Be = ie(Z.modalOptions), it = $s({
      ...Be,
      axes: Object.fromEntries(ne.value.map(([Ke, Tt]) => [Ke, Tt.values]))
    });
    F.value = it;
    const kt = Pt(), Ue = kt.start({ kind: "experiment", label: "Experiment", status: "running" });
    M.value = { status: "submitting", message: "Submitting experiment…", runId: "", experimentId: "" };
    try {
      const Ke = await vx(it, Z.fetchImpl), Tt = String(Ke.experiment_id ?? Ke.experimentId ?? Ke.id ?? "");
      return B(Tt || null), M.value = { status: "running", message: "Experiment running…", runId: "", experimentId: Tt, detail: Ke }, kt.patch(Ue, { message: "Experiment running…" }), { ok: !0 };
    } catch (Ke) {
      const Tt = Ke instanceof Error ? Ke.message : "Experiment submission failed";
      return M.value = { status: "failed", message: Tt, runId: "", experimentId: "" }, kt.fail(Ue, Tt), { ok: !1, error: Tt };
    }
  }
  async function Re(Z) {
    const pe = M.value.experimentId || M.value.runId;
    if (M.value = { ...M.value, status: "canceled", message: "Run canceled" }, pe)
      try {
        await yx(pe, Z);
      } catch {
      }
  }
  function B(Z) {
    C.value = Z;
    try {
      Dl.write({ key: ue.value, generationId: Z ?? "" });
    } catch {
    }
  }
  function Y(Z) {
    B(Z), M.value = { ...M.value, status: "succeeded", message: "Run completed" };
  }
  function _e(Z) {
    M.value = { ...M.value, status: "failed", message: Z };
  }
  return {
    featureId: e,
    experimentMode: t,
    queueMode: s,
    activeMode: n,
    activeSubtool: r,
    workflowId: o,
    versionId: a,
    runContext: i,
    schema: l,
    controlValues: c,
    contextStatus: d,
    contextError: f,
    contextReasons: y,
    runnable: v,
    sourceOwnerKey: b,
    sourceUploading: O,
    sourceError: I,
    references: V,
    workflowMethods: R,
    outputOverride: J,
    presetId: be,
    presetDirty: ee,
    runState: M,
    currentGenerationId: C,
    lastSubmitted: F,
    submittedSource: Se,
    queue: Ce,
    experimentAxes: Me,
    contextKey: ue,
    draftErrors: W,
    gateReason: E,
    isBusy: _,
    queueCount: X,
    enabledAxes: ne,
    setFeature: mt,
    setExperimentMode: at,
    setQueueMode: We,
    setTool: Oe,
    setControl: q,
    resetDraft: j,
    setSource: le,
    clearSource: g,
    beginUpload: x,
    commitUpload: P,
    failUpload: z,
    uploadSource: $,
    addReference: m,
    removeReference: h,
    setOutputOverride: N,
    clearOutputOverride: U,
    applyPreset: G,
    selectWorkflow: ge,
    buildPayload: ie,
    submitRun: Ie,
    enqueueCurrent: Le,
    removeQueued: Ze,
    clearQueue: Q,
    drainQueue: de,
    setAxis: ce,
    clearAxes: Ee,
    submitExperimentDef: je,
    cancelRun: Re,
    noteSucceeded: Y,
    noteFailed: _e
  };
}), Ix = { "data-testid": "vue-playground-controls" }, Rx = {
  key: 0,
  class: "cmst:py-4 cmst:text-sm cmst:opacity-70"
}, Ax = ["for"], Ex = ["id", "value", "data-testid", "onInput"], Ox = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-2 cmst:py-2"
}, Tx = { class: "cmst:flex cmst:items-center cmst:gap-2" }, Px = ["data-testid"], Nx = ["data-testid", "onClick"], Mx = { class: "cmst:cursor-pointer cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover" }, zx = ["onChange"], jx = ["data-testid", "onClick"], Dx = {
  key: 2,
  class: "cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:py-2"
}, Lx = ["for"], Ux = ["id", "value", "min", "max", "step", "data-testid", "onInput"], Vx = ["for"], Fx = {
  key: 1,
  class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]"
}, Wx = ["id", "checked", "data-testid", "onChange"], Bx = ["id", "value", "data-testid", "onChange"], qx = ["value"], Gx = {
  key: 3,
  class: "cmst:flex cmst:items-center cmst:gap-2"
}, Hx = ["id", "value", "data-testid", "onInput"], Zx = ["data-testid", "onClick"], Kx = ["id", "value", "min", "max", "step", "data-testid", "onInput"], Jx = ["id", "value", "data-testid", "onInput"], sn = "cmst:h-9 cmst:w-full cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm cmst:text-cmst-fg", $r = "cmst:flex cmst:flex-col cmst:gap-1.5 cmst:py-2", Ir = "cmst:text-[13px] cmst:font-medium cmst:text-cmst-secondary-text", Qx = /* @__PURE__ */ xt({
  __name: "PlaygroundControls",
  props: {
    schema: {},
    values: {},
    hideRoles: {}
  },
  emits: ["update", "pickImage", "uploadImage", "clearImage"],
  setup(e, { emit: t }) {
    const s = e, n = t;
    function r(I) {
      return s.schema[I] ?? {};
    }
    function o(I) {
      const V = r(I);
      return typeof V.label == "string" && V.label ? V.label : I.split("_").map((R) => R && R[0].toUpperCase() + R.slice(1)).join(" ");
    }
    function a(I) {
      return I === "prompt" || I === "negative_prompt" || I.endsWith("_prompt");
    }
    function i(I, V) {
      return I === "source_image" || I === "mask" ? !0 : V.control_kind === "image";
    }
    function l(I) {
      return I === "seed";
    }
    function c(I) {
      return I === "width" || I === "height";
    }
    function d(I, V) {
      return i(I, V) ? "image" : l(I) ? "seed" : typeof V.default == "boolean" || V.data_type === "BOOLEAN" ? "toggle" : Array.isArray(V.enum_options) && V.enum_options.length ? "select" : typeof V.default == "number" || V.data_type === "INT" || V.data_type === "FLOAT" ? "number" : a(I) ? "prompt" : "text";
    }
    const f = ye(() => {
      const I = new Set(s.hideRoles ?? []), V = Object.keys(s.schema).filter(
        (J) => s.schema[J]?.enabled !== !1 && !I.has(J)
      ), R = (J) => J === "prompt" ? 0 : J === "negative_prompt" ? 1 : a(J) ? 2 : J === "source_image" || J === "mask" ? 3 : c(J) ? 4 : l(J) ? 5 : 10;
      return V.sort((J, be) => R(J) - R(be) || J.localeCompare(be));
    }), y = ye(() => f.value.filter((I) => d(I, r(I)) === "prompt")), v = ye(() => f.value.filter((I) => c(I))), A = ye(
      () => f.value.filter((I) => d(I, r(I)) === "image")
    ), b = ye(
      () => f.value.filter(
        (I) => !a(I) && !c(I) && d(I, r(I)) !== "image" && d(I, r(I)) !== "prompt"
      )
    );
    function w(I, V) {
      const R = V.target, J = R.files?.[0];
      J && n("uploadImage", I, J), R.value = "";
    }
    function O(I) {
      n("update", I, Math.floor(Math.random() * 2 ** 31));
    }
    return (I, V) => (k(), S("div", Ix, [
      f.value.length ? te("", !0) : (k(), S("div", Rx, " This workflow exposes no controls yet. Map them in Workflows first. ")),
      (k(!0), S(fe, null, ze(y.value, (R) => (k(), S("div", {
        key: R,
        class: Ae($r)
      }, [
        u("label", {
          for: `pg-ctl-${R}`,
          class: Ae(Ir)
        }, L(o(R)), 9, Ax),
        u("textarea", {
          id: `pg-ctl-${R}`,
          value: String(s.values[R] ?? ""),
          rows: "3",
          class: Ae(`${sn} cmst:h-auto cmst:py-2`),
          "data-testid": `vue-playground-control-${R}`,
          onInput: (J) => n("update", R, J.target.value)
        }, null, 42, Ex)
      ]))), 128)),
      A.value.length ? (k(), S("div", Ox, [
        (k(!0), S(fe, null, ze(A.value, (R) => (k(), S("div", {
          key: R,
          class: Ae($r)
        }, [
          u("span", {
            class: Ae(Ir)
          }, L(o(R)), 1),
          u("div", Tx, [
            u("span", {
              class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]",
              "data-testid": `vue-playground-control-${R}`
            }, L(String(s.values[R] ?? "No image selected")), 9, Px),
            u("button", {
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
              "data-testid": `vue-playground-pick-${R}`,
              onClick: (J) => n("pickImage", R)
            }, " Browse ", 8, Nx),
            u("label", Mx, [
              V[0] || (V[0] = K(" Upload ", -1)),
              u("input", {
                type: "file",
                accept: "image/*",
                class: "cmst:hidden",
                onChange: (J) => w(R, J)
              }, null, 40, zx)
            ]),
            s.values[R] ? (k(), S("button", {
              key: 0,
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:opacity-70 cmst:hover:bg-cmst-hover",
              "data-testid": `vue-playground-clear-${R}`,
              onClick: (J) => n("clearImage", R)
            }, " Clear ", 8, jx)) : te("", !0)
          ])
        ]))), 128))
      ])) : te("", !0),
      v.value.length ? (k(), S("div", Dx, [
        (k(!0), S(fe, null, ze(v.value, (R) => (k(), S("div", {
          key: R,
          class: Ae($r)
        }, [
          u("label", {
            for: `pg-ctl-${R}`,
            class: Ae(Ir)
          }, L(o(R)), 9, Lx),
          u("input", {
            id: `pg-ctl-${R}`,
            type: "number",
            value: Number(s.values[R] ?? r(R).default ?? 0),
            min: r(R).minimum,
            max: r(R).maximum,
            step: r(R).step ?? 1,
            class: Ae(sn),
            "data-testid": `vue-playground-control-${R}`,
            onInput: (J) => n("update", R, Number(J.target.value))
          }, null, 40, Ux)
        ]))), 128))
      ])) : te("", !0),
      (k(!0), S(fe, null, ze(b.value, (R) => (k(), S("div", {
        key: R,
        class: Ae($r)
      }, [
        d(R, r(R)) !== "toggle" ? (k(), S("label", {
          key: 0,
          for: `pg-ctl-${R}`,
          class: Ae(Ir)
        }, L(o(R)), 9, Vx)) : te("", !0),
        d(R, r(R)) === "toggle" ? (k(), S("label", Fx, [
          u("input", {
            id: `pg-ctl-${R}`,
            type: "checkbox",
            checked: !!(s.values[R] ?? r(R).default ?? !1),
            "data-testid": `vue-playground-control-${R}`,
            onChange: (J) => n("update", R, J.target.checked)
          }, null, 40, Wx),
          K(" " + L(o(R)), 1)
        ])) : d(R, r(R)) === "select" ? (k(), S("select", {
          key: 2,
          id: `pg-ctl-${R}`,
          value: String(s.values[R] ?? ""),
          class: Ae(sn),
          "data-testid": `vue-playground-control-${R}`,
          onChange: (J) => n("update", R, J.target.value)
        }, [
          (k(!0), S(fe, null, ze(r(R).enum_options ?? [], (J) => (k(), S("option", {
            key: String(J),
            value: String(J)
          }, L(String(J)), 9, qx))), 128))
        ], 40, Bx)) : d(R, r(R)) === "seed" ? (k(), S("div", Gx, [
          u("input", {
            id: `pg-ctl-${R}`,
            type: "number",
            value: Number(s.values[R] ?? 0),
            class: Ae(sn),
            "data-testid": `vue-playground-control-${R}`,
            onInput: (J) => n("update", R, Number(J.target.value))
          }, null, 40, Hx),
          u("button", {
            type: "button",
            class: "cmst:shrink-0 cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
            "data-testid": `vue-playground-randomize-${R}`,
            onClick: (J) => O(R)
          }, " Random ", 8, Zx)
        ])) : d(R, r(R)) === "number" ? (k(), S("input", {
          key: 4,
          id: `pg-ctl-${R}`,
          type: "number",
          value: Number(s.values[R] ?? r(R).default ?? 0),
          min: r(R).minimum,
          max: r(R).maximum,
          step: r(R).step ?? 1,
          class: Ae(sn),
          "data-testid": `vue-playground-control-${R}`,
          onInput: (J) => n("update", R, Number(J.target.value))
        }, null, 40, Kx)) : (k(), S("input", {
          key: 5,
          id: `pg-ctl-${R}`,
          type: "text",
          value: String(s.values[R] ?? ""),
          class: Ae(sn),
          "data-testid": `vue-playground-control-${R}`,
          onInput: (J) => n("update", R, J.target.value)
        }, null, 40, Jx))
      ]))), 128))
    ]));
  }
}), Yx = {
  class: "cmst:flex cmst:flex-col cmst:gap-1",
  "data-testid": "vue-generate-bar"
}, Xx = { class: "cmst:flex cmst:items-stretch cmst:justify-center" }, e1 = { class: "cmst:flex cmst:overflow-hidden cmst:rounded-full cmst:bg-gradient-to-r cmst:from-cmst-primary cmst:to-[#7a5cff] cmst:p-[1.5px]" }, t1 = ["disabled", "aria-label"], s1 = ["disabled", "aria-expanded"], n1 = {
  key: 0,
  class: "cmst:flex cmst:justify-center",
  role: "menu",
  "aria-label": "Generation intent",
  "data-testid": "vue-generate-menu"
}, r1 = { class: "cmst:flex cmst:flex-col cmst:gap-0.5 cmst:rounded-xl cmst:bg-cmst-raised cmst:p-1.5 cmst:shadow-xl" }, o1 = {
  key: 1,
  class: "cmst:text-center cmst:text-[13px] cmst:text-cmst-muted",
  "data-testid": "vue-generate-gate-reason"
}, a1 = /* @__PURE__ */ xt({
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
    const s = e, n = t, r = /* @__PURE__ */ T(!1), o = ye(() => s.busy ? s.busyLabel ?? "Running…" : s.experimentMode ? "Run experiment" : s.queueMode ? s.queueCount > 0 ? `Queue (${s.queueCount})` : "Queue" : "Generate");
    function a(l) {
      r.value = !1, n("submit", l);
    }
    function i(l) {
      l.key === "Escape" && (r.value = !1), (l.key === "ArrowDown" || l.key === "Enter") && document.activeElement?.getAttribute("data-testid") === "vue-generate-menu-button" && (r.value = !0);
    }
    return window.addEventListener("keydown", i), Ic(() => window.removeEventListener("keydown", i)), (l, c) => (k(), S("div", Yx, [
      u("div", Xx, [
        u("div", e1, [
          u("button", {
            type: "button",
            disabled: e.disabled,
            class: "cmst:flex cmst:h-11 cmst:min-w-52 cmst:items-center cmst:justify-center cmst:gap-2 cmst:rounded-l-full cmst:bg-cmst-primary cmst:px-6 cmst:text-[15px] cmst:font-semibold cmst:text-white cmst:hover:bg-cmst-primary-hover cmst:disabled:cursor-not-allowed cmst:disabled:opacity-50",
            "data-testid": "vue-generate-submit",
            "aria-label": o.value,
            onClick: c[0] || (c[0] = (d) => a(e.experimentMode ? "experiment" : e.queueMode ? "queue" : "generate"))
          }, [
            e.experimentMode ? (k(), ut(p(bu), {
              key: 0,
              class: "cmst:size-4",
              "aria-hidden": "true"
            })) : e.queueMode ? (k(), ut(p(oh), {
              key: 1,
              class: "cmst:size-4",
              "aria-hidden": "true"
            })) : (k(), ut(p(ch), {
              key: 2,
              class: "cmst:size-4",
              "aria-hidden": "true"
            })),
            K(" " + L(o.value), 1)
          ], 8, t1),
          u("button", {
            type: "button",
            disabled: e.disabled && !r.value,
            class: "cmst:flex cmst:h-11 cmst:w-11 cmst:items-center cmst:justify-center cmst:rounded-r-full cmst:bg-cmst-primary cmst:text-white cmst:hover:bg-cmst-primary-hover",
            "data-testid": "vue-generate-menu-button",
            "aria-label": "More generation options",
            "aria-haspopup": "menu",
            "aria-expanded": r.value ? "true" : "false",
            onClick: c[1] || (c[1] = (d) => r.value = !r.value)
          }, [
            H(p(Hp), {
              class: "cmst:size-4",
              "aria-hidden": "true"
            })
          ], 8, s1)
        ])
      ]),
      r.value ? (k(), S("div", n1, [
        u("div", r1, [
          u("button", {
            type: "button",
            role: "menuitem",
            class: "cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover",
            "data-testid": "vue-generate-intent-generate",
            onClick: c[2] || (c[2] = (d) => a("generate"))
          }, " Generate — run now "),
          u("button", {
            type: "button",
            role: "menuitem",
            class: "cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover",
            "data-testid": "vue-generate-intent-queue",
            onClick: c[3] || (c[3] = (d) => a("queue"))
          }, " Queue — collect, then drain as a batch "),
          u("button", {
            type: "button",
            role: "menuitem",
            class: "cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover",
            "data-testid": "vue-generate-intent-experiment",
            onClick: c[4] || (c[4] = (d) => a("experiment"))
          }, " Experiment — sweep parameter axes ")
        ])
      ])) : te("", !0),
      e.reason ? (k(), S("p", o1, L(e.reason), 1)) : te("", !0)
    ]));
  }
}), i1 = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2",
  "data-testid": "vue-playground-topbar"
}, l1 = ["value"], c1 = ["value"], u1 = ["value"], d1 = ["value"], f1 = ["value"], m1 = ["value"], p1 = {
  key: 2,
  class: "cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "vue-playground-preset-dirty"
}, h1 = {
  class: "cmst:ml-auto cmst:flex cmst:items-center cmst:gap-1",
  role: "tablist",
  "aria-label": "Tool"
}, g1 = ["aria-selected", "data-testid", "onClick"], v1 = {
  class: "cmst:flex cmst:flex-wrap cmst:gap-1",
  role: "tablist",
  "aria-label": "Subtool",
  "data-testid": "vue-playground-subtools"
}, y1 = ["aria-selected", "disabled", "title", "data-testid", "onClick"], b1 = { class: "cmst:grid cmst:flex-1 cmst:grid-cols-1 cmst:gap-4 cmst:lg:grid-cols-[minmax(0,1fr)_320px]" }, w1 = {
  class: "cmst:flex cmst:min-w-0 cmst:flex-col cmst:gap-3",
  "data-testid": "vue-playground-workspace"
}, _1 = {
  class: "cmst:flex cmst:min-h-64 cmst:flex-1 cmst:items-center cmst:justify-center cmst:overflow-hidden cmst:rounded-xl cmst:bg-cmst-matte",
  "data-testid": "vue-playground-canvas"
}, x1 = ["src"], k1 = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:items-center cmst:gap-2 cmst:p-4"
}, S1 = ["src"], C1 = {
  key: 2,
  class: "cmst:flex cmst:flex-col cmst:items-center cmst:gap-2 cmst:p-8 cmst:text-center"
}, $1 = { class: "cmst:max-w-80 cmst:text-sm cmst:text-cmst-muted" }, I1 = {
  key: 0,
  class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]",
  "data-testid": "vue-playground-run-status",
  role: "status"
}, R1 = { class: "cmst:text-cmst-secondary-text" }, A1 = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-playground-prompt-zone"
}, E1 = ["for"], O1 = ["id", "value", "rows", "data-testid", "onInput"], T1 = {
  key: 2,
  class: "cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-playground-references"
}, P1 = { class: "cmst:flex cmst:items-center cmst:justify-between" }, N1 = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-muted"
}, M1 = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-1.5"
}, z1 = ["data-testid"], j1 = ["src", "alt"], D1 = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, L1 = ["aria-label", "onClick"], U1 = {
  key: 3,
  class: "cmst:flex cmst:flex-col cmst:gap-2",
  "data-testid": "vue-playground-sketch"
}, V1 = { class: "cmst:flex cmst:items-center cmst:gap-2" }, F1 = {
  key: 0,
  class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]"
}, W1 = {
  key: 1,
  class: "cmst:text-xs cmst:text-cmst-muted"
}, B1 = {
  key: 4,
  class: "cmst:flex cmst:flex-col cmst:gap-1.5",
  "data-testid": "vue-playground-queue"
}, q1 = { class: "cmst:text-sm cmst:font-semibold" }, G1 = { class: "cmst:flex cmst:flex-col cmst:gap-1" }, H1 = ["data-testid"], Z1 = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, K1 = ["aria-label", "onClick"], J1 = { class: "cmst:flex cmst:gap-2" }, Q1 = {
  class: "cmst:min-w-0 cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4",
  "data-testid": "vue-playground-inspector",
  "aria-label": "Workflow controls"
}, Y1 = {
  key: 0,
  role: "status",
  class: "cmst:py-4 cmst:text-sm cmst:opacity-70"
}, X1 = {
  key: 1,
  class: "cmst:flex cmst:flex-col cmst:gap-2 cmst:py-4",
  role: "alert"
}, ek = { class: "cmst:text-sm" }, tk = {
  key: 3,
  class: "cmst:py-1 cmst:text-[13px] cmst:opacity-70",
  role: "status"
}, sk = {
  key: 4,
  class: "cmst:py-1 cmst:text-[13px]",
  role: "alert"
}, nk = {
  key: 0,
  class: "cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4",
  "data-testid": "vue-playground-composer",
  role: "dialog",
  "aria-label": "Experiment composer"
}, rk = { class: "cmst:flex cmst:items-center cmst:justify-between" }, ok = { class: "cmst:flex cmst:gap-2" }, ak = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-2" }, ik = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]" }, lk = ["id", "checked", "data-testid", "onChange"], ck = ["id", "value", "data-testid", "onInput"], uk = {
  class: "cmst:bg-cmst-bg cmst:py-3",
  "data-testid": "vue-playground-action-zone"
}, dk = /* @__PURE__ */ xt({
  __name: "PlaygroundView",
  setup(e) {
    const t = $x(), s = Ja(), n = xn(), r = ur(), o = vu(), a = /* @__PURE__ */ T(!1), i = /* @__PURE__ */ T("source_image"), l = /* @__PURE__ */ T(!1), c = /* @__PURE__ */ T({}), d = /* @__PURE__ */ T([]), f = ye(() => zl[t.activeMode]), y = ye(() => t.schema.prompt ? "prompt" : Object.keys(t.schema).find((ue) => ue.endsWith("_prompt")) ?? null), v = ye(() => t.activeSubtool !== "text" || !y.value ? [] : [y.value, "negative_prompt"].filter((ue) => t.schema[ue])), A = ye(
      () => t.currentGenerationId ? n.records.find((ue) => ue.id === t.currentGenerationId) ?? null : null
    ), b = ye(() => {
      const W = A.value?.featuredOutput;
      if (!W) return null;
      try {
        return rr(W);
      } catch {
        return null;
      }
    }), w = ye(() => {
      const ue = t.controlValues.source_image;
      return typeof ue == "string" && ue ? ue : null;
    });
    function O() {
      return {
        ...r.outputPreferences ?? {},
        ...t.outputOverride
      };
    }
    async function I() {
      await s.initialize();
      const ue = t.workflowId, E = s.workflows.find((_) => _.workflow_id === ue) ?? s.workflows[0];
      E && await V(String(E.workflow_id));
    }
    async function V(ue) {
      try {
        await s.selectWorkflow(ue);
      } catch {
      }
      const W = s.versions.find(
        (E) => E.workflow_version_id === s.selectedWorkflow?.latest_version_id
      ) ?? s.versions[s.versions.length - 1] ?? null;
      await t.selectWorkflow(ue, W?.workflow_version_id ?? ""), d.value = [];
    }
    async function R(ue) {
      try {
        await s.selectVersion(ue);
      } catch {
      }
      await t.selectWorkflow(t.workflowId, ue), d.value = [];
    }
    function J(ue) {
      const E = s.presets.find(
        (_) => String(_.preset_id ?? _.id) === ue
      )?.state ?? null;
      t.applyPreset(E, ue);
    }
    async function be(ue) {
      if (ue === "generate") {
        (await t.submitRun({ modalOptions: O() })).ok && await n.loadFeed();
        return;
      }
      if (ue === "queue") {
        t.setQueueMode(!0), t.enqueueCurrent();
        return;
      }
      t.setExperimentMode(!0), l.value = !0;
    }
    async function ee() {
      (await t.drainQueue({ modalOptions: O() })).ok && await n.loadFeed();
    }
    async function M() {
      (await t.submitExperimentDef({ modalOptions: O() })).ok && (l.value = !1, await n.loadFeed());
    }
    function C(ue) {
      i.value = ue, a.value = !0;
    }
    function F(ue) {
      const W = i.value;
      a.value = !1;
      const E = ue.featuredOutput, _ = E ? rr(E) : ue.id;
      W === "source_image" ? (t.setSource(String(_), t.contextKey), d.value = []) : t.addReference(String(_));
    }
    function Se(ue, W) {
      t.setAxis(ue, { enabled: W });
    }
    function Ce(ue) {
      return c.value[ue] ?? "";
    }
    function Me(ue, W) {
      c.value = { ...c.value, [ue]: W };
      const E = W.split(/[\n,]+/).map((_) => _.trim()).filter((_) => _ !== "");
      t.setAxis(ue, { enabled: !0, values: E });
    }
    function He() {
      t.currentGenerationId ? o.push({ name: "history", query: { focus: t.currentGenerationId } }) : o.push({ name: "history" });
    }
    return xs(async () => {
      await r.initialize().catch(() => {
      }), await n.initialize().catch(() => {
      }), await I();
    }), Wt(
      () => t.controlValues.source_image,
      () => {
        d.value = [];
      }
    ), (ue, W) => (k(), S("section", {
      class: Ae(p(fr)("cmst:h-full")),
      "data-testid": "vue-page-playground"
    }, [
      W[27] || (W[27] = u("h2", {
        class: "cmst:sr-only",
        "data-testid": "vue-playground-title"
      }, "Playground", -1)),
      u("div", i1, [
        u("select", {
          id: "pg-workflow",
          value: p(t).workflowId,
          class: "cmst:h-9 cmst:max-w-64 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
          "aria-label": "Workflow",
          "data-testid": "vue-playground-workflow",
          onChange: W[0] || (W[0] = (E) => V(E.target.value))
        }, [
          W[12] || (W[12] = u("option", {
            value: "",
            disabled: ""
          }, "Select a workflow…", -1)),
          (k(!0), S(fe, null, ze(p(s).workflows, (E) => (k(), S("option", {
            key: String(E.workflow_id),
            value: String(E.workflow_id)
          }, L(String(E.name || E.workflow_id)), 9, c1))), 128))
        ], 40, l1),
        p(s).versions.length ? (k(), S("select", {
          key: 0,
          id: "pg-version",
          value: p(t).versionId,
          class: "cmst:h-9 cmst:max-w-44 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
          "aria-label": "Version",
          "data-testid": "vue-playground-version",
          onChange: W[1] || (W[1] = (E) => R(E.target.value))
        }, [
          (k(!0), S(fe, null, ze(p(s).versions, (E) => (k(), S("option", {
            key: String(E.workflow_version_id),
            value: String(E.workflow_version_id)
          }, " v" + L(String(E.version ?? E.workflow_version_id).slice(0, 8)), 9, d1))), 128))
        ], 40, u1)) : te("", !0),
        p(s).presets.length ? (k(), S("select", {
          key: 1,
          id: "pg-preset",
          value: p(t).presetId ?? "",
          class: "cmst:h-9 cmst:max-w-44 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
          "aria-label": "Preset",
          "data-testid": "vue-playground-preset",
          onChange: W[2] || (W[2] = (E) => J(E.target.value))
        }, [
          W[13] || (W[13] = u("option", { value: "" }, "No preset", -1)),
          (k(!0), S(fe, null, ze(p(s).presets, (E) => (k(), S("option", {
            key: String(E.preset_id ?? E.id),
            value: String(E.preset_id ?? E.id)
          }, L(String(E.name ?? E.preset_id ?? E.id)), 9, m1))), 128))
        ], 40, f1)) : te("", !0),
        p(t).presetDirty ? (k(), S("span", p1, " Modified ")) : te("", !0),
        u("div", h1, [
          (k(), S(fe, null, ze(["generate", "edit", "post"], (E) => u("button", {
            key: E,
            type: "button",
            role: "tab",
            "aria-selected": p(t).activeMode === E ? "true" : "false",
            class: Ae(["cmst:rounded-lg cmst:px-2.5 cmst:py-1.5 cmst:text-[13px] cmst:capitalize", p(t).activeMode === E ? "cmst:bg-cmst-raised cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-hover"]),
            "data-testid": `vue-playground-mode-${E}`,
            onClick: (_) => p(t).setTool(E, p(zl)[E][0])
          }, L(E), 11, g1)), 64))
        ])
      ]),
      u("div", v1, [
        (k(!0), S(fe, null, ze(f.value, (E) => (k(), S("button", {
          key: E,
          type: "button",
          role: "tab",
          "aria-selected": p(t).activeSubtool === E ? "true" : "false",
          disabled: p(Ra).includes(E),
          title: p(Ra).includes(E) ? "Arrives in a later phase — execution is disabled" : "",
          class: Ae(["cmst:rounded-lg cmst:px-2.5 cmst:py-1.5 cmst:text-[13px] cmst:capitalize cmst:disabled:cursor-not-allowed cmst:disabled:opacity-40", p(t).activeSubtool === E ? "cmst:bg-cmst-raised cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-hover"]),
          "data-testid": `vue-playground-subtool-${E}`,
          onClick: (_) => p(t).setTool(p(t).activeMode, E)
        }, L(E), 11, y1))), 128))
      ]),
      u("div", b1, [
        u("div", w1, [
          u("div", _1, [
            b.value ? (k(), S("img", {
              key: 0,
              src: b.value,
              alt: "Current generation result",
              class: "cmst:max-h-[52vh] cmst:w-full cmst:object-contain",
              "data-testid": "vue-playground-result"
            }, null, 8, x1)) : w.value ? (k(), S("div", k1, [
              u("img", {
                src: w.value,
                alt: "Source image",
                class: "cmst:max-h-[44vh] cmst:rounded cmst:object-contain",
                "data-testid": "vue-playground-source-preview"
              }, null, 8, S1),
              W[14] || (W[14] = u("span", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Source image", -1))
            ])) : (k(), S("div", C1, [
              H(p(eh), {
                class: "cmst:size-6 cmst:opacity-40",
                "aria-hidden": "true"
              }),
              u("p", $1, L(p(t).contextStatus === "loading" ? "Loading workflow…" : p(t).workflowId ? "No output yet. Describe the image, then Generate." : "Select a workflow to begin."), 1)
            ]))
          ]),
          p(t).runState.message ? (k(), S("div", I1, [
            u("span", R1, L(p(t).runState.message), 1),
            p(t).isBusy ? (k(), S("button", {
              key: 0,
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
              "data-testid": "vue-playground-cancel",
              onClick: W[3] || (W[3] = (E) => p(t).cancelRun())
            }, " Cancel ")) : te("", !0),
            p(t).currentGenerationId && p(t).runState.status === "succeeded" ? (k(), S("button", {
              key: 1,
              type: "button",
              class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover",
              "data-testid": "vue-playground-open-history",
              onClick: He
            }, " Open in History ")) : te("", !0)
          ])) : te("", !0),
          v.value.length ? (k(), S("div", A1, [
            (k(!0), S(fe, null, ze(v.value, (E) => (k(), S("div", {
              key: E,
              class: "cmst:flex cmst:flex-col cmst:gap-1.5"
            }, [
              u("label", {
                for: `pg-center-${E}`,
                class: "cmst:text-[13px] cmst:font-medium cmst:text-cmst-secondary-text"
              }, L(E === "prompt" ? "Prompt" : "Negative prompt"), 9, E1),
              u("textarea", {
                id: `pg-center-${E}`,
                value: String(p(t).controlValues[E] ?? ""),
                rows: E === "prompt" ? 4 : 2,
                class: "cmst:w-full cmst:rounded-xl cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-3 cmst:py-2.5 cmst:text-[15px]",
                "data-testid": `vue-playground-prompt-${E}`,
                onInput: (_) => p(t).setControl(E, _.target.value)
              }, null, 40, O1)
            ]))), 128))
          ])) : te("", !0),
          p(t).activeSubtool === "references" ? (k(), S("div", T1, [
            u("div", P1, [
              W[16] || (W[16] = u("h3", { class: "cmst:text-sm cmst:font-semibold" }, "References", -1)),
              H(re, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-playground-add-reference",
                onClick: W[4] || (W[4] = (E) => C("references"))
              }, {
                default: se(() => [...W[15] || (W[15] = [
                  K(" Add from History ", -1)
                ])]),
                _: 1
              })
            ]),
            p(t).references.length ? (k(), S("ul", M1, [
              (k(!0), S(fe, null, ze(p(t).references, (E) => (k(), S("li", {
                key: E.id,
                class: "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-lg cmst:bg-cmst-surface cmst:px-2.5 cmst:py-2 cmst:text-[13px]",
                "data-testid": `vue-playground-reference-${E.id}`
              }, [
                u("img", {
                  src: E.filename,
                  alt: E.filename,
                  class: "cmst:size-10 cmst:rounded cmst:object-cover",
                  loading: "lazy"
                }, null, 8, j1),
                u("span", D1, L(E.filename), 1),
                u("button", {
                  type: "button",
                  class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:hover:bg-cmst-hover",
                  "aria-label": `Remove ${E.filename}`,
                  onClick: (_) => p(t).removeReference(E.id)
                }, " Remove ", 8, L1)
              ], 8, z1))), 128))
            ])) : (k(), S("p", N1, " No reference images. They ride alongside the run without entering control values. "))
          ])) : te("", !0),
          p(t).activeSubtool === "sketch" ? (k(), S("div", U1, [
            W[18] || (W[18] = u("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Sketch base", -1)),
            W[19] || (W[19] = u("p", { class: "cmst:text-[13px] cmst:text-cmst-muted" }, " Changing the base clears overlay strokes. The flattened sketch commits to the source image on save. ", -1)),
            u("div", V1, [
              H(re, {
                variant: "outline",
                size: "sm",
                "data-testid": "vue-playground-sketch-history",
                onClick: W[5] || (W[5] = (E) => C("source_image"))
              }, {
                default: se(() => [...W[17] || (W[17] = [
                  K(" Use History image as base ", -1)
                ])]),
                _: 1
              }),
              w.value ? (k(), S("span", F1, L(w.value), 1)) : te("", !0),
              d.value.length ? (k(), S("span", W1, L(d.value.length) + " strokes ", 1)) : te("", !0)
            ])
          ])) : te("", !0),
          p(t).queueMode && p(t).queueCount > 0 ? (k(), S("div", B1, [
            u("h3", q1, "Queue (" + L(p(t).queueCount) + ")", 1),
            u("ul", G1, [
              (k(!0), S(fe, null, ze(p(t).queue, (E) => (k(), S("li", {
                key: E.id,
                class: "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-lg cmst:bg-cmst-surface cmst:px-2.5 cmst:py-1.5 cmst:text-[13px]",
                "data-testid": `vue-playground-queued-${E.id}`
              }, [
                u("span", Z1, L(E.label), 1),
                u("button", {
                  type: "button",
                  class: "cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:hover:bg-cmst-hover",
                  "aria-label": `Remove ${E.label}`,
                  onClick: (_) => p(t).removeQueued(E.id)
                }, " Remove ", 8, K1)
              ], 8, H1))), 128))
            ]),
            u("div", J1, [
              H(re, {
                variant: "default",
                size: "sm",
                "data-testid": "vue-playground-drain",
                onClick: ee
              }, {
                default: se(() => [...W[20] || (W[20] = [
                  K(" Drain queue ", -1)
                ])]),
                _: 1
              }),
              H(re, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-playground-clear-queue",
                onClick: W[6] || (W[6] = (E) => p(t).clearQueue())
              }, {
                default: se(() => [...W[21] || (W[21] = [
                  K(" Clear ", -1)
                ])]),
                _: 1
              })
            ])
          ])) : te("", !0)
        ]),
        u("aside", Q1, [
          p(t).contextStatus === "loading" ? (k(), S("div", Y1, " Loading workflow… ")) : p(t).contextStatus === "error" ? (k(), S("div", X1, [
            u("p", ek, L(p(t).contextError || "Workflow unavailable"), 1),
            H(re, {
              variant: "outline",
              size: "sm",
              onClick: I
            }, {
              default: se(() => [
                H(p(ph), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                }),
                W[22] || (W[22] = K(" Retry ", -1))
              ]),
              _: 1
            })
          ])) : (k(), ut(Qx, {
            key: 2,
            schema: p(t).schema,
            values: p(t).controlValues,
            "hide-roles": v.value,
            onUpdate: W[7] || (W[7] = (E, _) => p(t).setControl(E, _)),
            onPickImage: C,
            onUploadImage: W[8] || (W[8] = (E, _) => {
              p(t).uploadSource(_);
            }),
            onClearImage: W[9] || (W[9] = () => p(t).clearSource())
          }, null, 8, ["schema", "values", "hide-roles"])),
          p(t).sourceUploading ? (k(), S("div", tk, " Uploading… ")) : te("", !0),
          p(t).sourceError ? (k(), S("div", sk, L(p(t).sourceError), 1)) : te("", !0)
        ])
      ]),
      l.value ? (k(), S("div", nk, [
        u("div", rk, [
          W[25] || (W[25] = u("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Experiment axes", -1)),
          u("div", ok, [
            H(re, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-playground-composer-close",
              onClick: W[10] || (W[10] = (E) => l.value = !1)
            }, {
              default: se(() => [...W[23] || (W[23] = [
                K(" Close ", -1)
              ])]),
              _: 1
            }),
            H(re, {
              variant: "default",
              size: "sm",
              "data-testid": "vue-playground-composer-submit",
              onClick: M
            }, {
              default: se(() => [...W[24] || (W[24] = [
                K(" Submit experiment ", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        W[26] || (W[26] = u("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, " One value per line or comma-separated. The experiment entity itself lives in History once submitted. ", -1)),
        u("div", ak, [
          (k(!0), S(fe, null, ze(Object.keys(p(t).schema), (E) => (k(), S("div", {
            key: E,
            class: "cmst:flex cmst:flex-col cmst:gap-1"
          }, [
            u("label", ik, [
              u("input", {
                id: `pg-axis-${E}`,
                type: "checkbox",
                checked: !!p(t).experimentAxes[E]?.enabled,
                "data-testid": `vue-playground-axis-${E}`,
                onChange: (_) => Se(E, _.target.checked)
              }, null, 40, lk),
              K(" " + L(E), 1)
            ]),
            p(t).experimentAxes[E]?.enabled ? (k(), S("textarea", {
              key: 0,
              id: `pg-axis-values-${E}`,
              value: Ce(E),
              rows: "2",
              class: "cmst:w-full cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:py-1.5 cmst:text-sm",
              "data-testid": `vue-playground-axis-values-${E}`,
              placeholder: "one value per line",
              onInput: (_) => Me(E, _.target.value)
            }, null, 40, ck)) : te("", !0)
          ]))), 128))
        ])
      ])) : te("", !0),
      u("footer", uk, [
        H(a1, {
          disabled: p(t).gateReason !== null,
          reason: p(t).gateReason,
          busy: p(t).isBusy,
          "busy-label": p(t).runState.status === "submitting" ? "Submitting…" : "Running…",
          "queue-count": p(t).queueCount,
          "experiment-mode": p(t).experimentMode,
          "queue-mode": p(t).queueMode,
          onSubmit: be
        }, null, 8, ["disabled", "reason", "busy", "busy-label", "queue-count", "experiment-mode", "queue-mode"])
      ]),
      a.value ? (k(), ut(td, {
        key: 1,
        onSelect: F,
        onCancel: W[11] || (W[11] = (E) => a.value = !1)
      })) : te("", !0)
    ], 2));
  }
}), fk = {
  key: 0,
  class: "cmst:text-[13px] cmst:text-cmst-danger",
  role: "alert"
}, mk = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, pk = { class: "cmst:grid cmst:grid-cols-1 cmst:gap-6 cmst:lg:grid-cols-[180px_minmax(0,1fr)]" }, hk = {
  "aria-label": "Settings sections",
  class: "cmst-side-nav cmst:min-w-0 cmst:lg:pr-2"
}, gk = ["aria-selected", "aria-current", "data-testid", "onClick"], vk = { class: "cmst:capitalize" }, yk = { class: "cmst:min-w-0 cmst:max-w-3xl" }, bk = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, wk = { class: "cmst:mt-1" }, _k = { class: "cmst-setting-row" }, xk = ["value"], kk = { class: "cmst-setting-row" }, Sk = { class: "cmst-setting-row" }, Ck = { class: "cmst-setting-row" }, $k = ["value"], Ik = ["value"], Rk = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-muted"
}, Ak = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Ek = { class: "cmst:mt-1" }, Ok = { class: "cmst-setting-row" }, Tk = { class: "cmst-setting-row" }, Pk = { class: "cmst-setting-row" }, Nk = { class: "cmst-setting-row" }, Mk = { class: "cmst-setting-row" }, zk = { class: "cmst-setting-row" }, jk = { class: "cmst:mt-3" }, Dk = { class: "cmst:mt-1" }, Lk = ["aria-pressed", "aria-label", "data-testid", "onClick"], Uk = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]" }, Vk = {
  key: 0,
  class: "cmst:py-3 cmst:text-xs cmst:text-cmst-muted"
}, Fk = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Wk = { class: "cmst:mt-1" }, Bk = { class: "cmst-setting-row" }, qk = ["value"], Gk = ["value"], Hk = { class: "cmst-setting-row" }, Zk = ["value"], Kk = { class: "cmst-setting-row" }, Jk = ["value"], Qk = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Yk = { class: "cmst:mt-1" }, Xk = { class: "cmst-setting-row" }, e0 = { class: "cmst:min-w-0" }, t0 = { class: "cmst:text-xs cmst:text-cmst-muted" }, s0 = {
  key: 0,
  "data-testid": "vue-settings-restart-banner"
}, n0 = { class: "cmst-setting-row" }, r0 = { class: "cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" }, o0 = /* @__PURE__ */ xt({
  __name: "SettingsView",
  setup(e) {
    const t = ur(), s = /* @__PURE__ */ T(75), n = /* @__PURE__ */ T(""), r = /* @__PURE__ */ T("original"), o = /* @__PURE__ */ T("balanced"), a = /* @__PURE__ */ T(!1), i = /* @__PURE__ */ T(!0), l = /* @__PURE__ */ T("off"), c = /* @__PURE__ */ T(70), d = /* @__PURE__ */ T("off"), f = /* @__PURE__ */ T(""), y = /* @__PURE__ */ T(!1), v = /* @__PURE__ */ T(!1), A = ye(() => t.config), b = ye(() => A.value?.available_gpus ?? []);
    function w() {
      const M = A.value;
      M && (s.value = M.quality, n.value = M.save_folder, r.value = M.output_format, o.value = M.webp_lossless_compression, a.value = M.auto_save_local, i.value = M.save_metadata_sidecar, l.value = M.data_saver_default, c.value = M.data_saver_quality, d.value = t.profileLevel, f.value = M.gpu, y.value = M.skip_plan_validation);
    }
    xs(async () => {
      await t.initialize().catch(() => {
      }), await t.loadGolden().catch(() => {
      }), w();
    });
    async function O() {
      await t.save({
        output_format: r.value,
        quality: Number(s.value),
        webp_lossless_compression: o.value,
        auto_save_local: a.value,
        save_folder: n.value,
        save_metadata_sidecar: i.value,
        data_saver_default: l.value,
        data_saver_quality: Number(c.value)
      }).catch(() => {
      }), w();
    }
    async function I() {
      await t.save({ gpu: f.value }).catch(() => {
      }), w();
    }
    async function V() {
      await t.save({
        data_saver_default: l.value,
        data_saver_quality: Number(c.value)
      }).catch(() => {
      }), w();
    }
    async function R() {
      await t.setSkipPlanValidation(y.value).catch(() => {
      }), w();
    }
    async function J() {
      await t.setProfile(d.value).catch(() => {
      }), w();
    }
    async function be(M) {
      await t.resetSection(M), w();
    }
    async function ee() {
      if (!v.value) {
        v.value = !0;
        return;
      }
      v.value = !1, await t.resetAll(), w();
    }
    return (M, C) => (k(), S("section", {
      class: Ae(p(fr)()),
      "data-testid": "vue-page-settings"
    }, [
      p(t).error ? (k(), S("div", fk, L(p(t).error), 1)) : te("", !0),
      u("div", mk, [
        C[20] || (C[20] = u("div", null, [
          u("h1", { class: "cmst-type-view" }, "Settings")
        ], -1)),
        H(re, {
          variant: "ghost",
          size: "icon",
          "aria-label": "Reload settings",
          disabled: p(t).loading,
          onClick: C[0] || (C[0] = (F) => p(t).load().then(w).catch(() => {
          }))
        }, {
          default: se(() => [
            H(p(vo), {
              class: Ae(["cmst:size-4", p(t).loading ? "cmst:animate-spin" : ""]),
              "aria-hidden": "true"
            }, null, 8, ["class"])
          ]),
          _: 1
        }, 8, ["disabled"])
      ]),
      u("div", pk, [
        u("nav", hk, [
          (k(!0), S(fe, null, ze(p(Ou), (F) => (k(), S("button", {
            key: F,
            type: "button",
            class: "cmst-quiet-tab",
            "aria-selected": p(t).activeSection === F,
            "aria-current": p(t).activeSection === F ? "true" : void 0,
            "data-testid": `vue-settings-tab-${F}`,
            onClick: (Se) => p(t).setSection(F)
          }, [
            u("span", vk, L(F), 1)
          ], 8, gk))), 128))
        ]),
        u("div", yk, [
          p(t).activeSection === "generation" ? (k(), S(fe, { key: 0 }, [
            u("div", bk, [
              C[22] || (C[22] = u("h2", { class: "cmst-type-section" }, "Generation", -1)),
              H(re, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-settings-reset-generation",
                onClick: C[1] || (C[1] = (F) => be("generation"))
              }, {
                default: se(() => [...C[21] || (C[21] = [
                  K("Reset section", -1)
                ])]),
                _: 1
              })
            ]),
            u("div", wk, [
              u("div", _k, [
                C[23] || (C[23] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "GPU"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Execution device for this workspace.")
                ], -1)),
                Fe(u("select", {
                  "onUpdate:modelValue": C[2] || (C[2] = (F) => f.value = F),
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "data-testid": "vue-settings-gpu",
                  "aria-label": "GPU",
                  onChange: I
                }, [
                  (k(!0), S(fe, null, ze(b.value, (F) => (k(), S("option", {
                    key: F.value,
                    value: F.value
                  }, L(F.label), 9, xk))), 128))
                ], 544), [
                  [ps, f.value]
                ])
              ]),
              u("div", kk, [
                C[25] || (C[25] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Data Saver default"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Serve bandwidth-saving variants unless asked otherwise.")
                ], -1)),
                Fe(u("select", {
                  "onUpdate:modelValue": C[3] || (C[3] = (F) => l.value = F),
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "Data Saver default",
                  onChange: V
                }, [...C[24] || (C[24] = [
                  u("option", { value: "off" }, "Off", -1),
                  u("option", { value: "on" }, "On", -1)
                ])], 544), [
                  [ps, l.value]
                ])
              ]),
              u("div", Sk, [
                C[26] || (C[26] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Data Saver quality"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Quality level for Data Saver variants, 1–100.")
                ], -1)),
                Fe(u("input", {
                  "onUpdate:modelValue": C[4] || (C[4] = (F) => c.value = F),
                  type: "number",
                  min: "1",
                  max: "100",
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "Data Saver quality",
                  onChange: V
                }, null, 544), [
                  [
                    lt,
                    c.value,
                    void 0,
                    { number: !0 }
                  ]
                ])
              ]),
              u("div", Ck, [
                C[28] || (C[28] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Golden profile"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Pinned known-good deployment profile.")
                ], -1)),
                u("select", {
                  value: p(t).selectedGoldenProfile,
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "data-testid": "vue-settings-golden-profile",
                  "aria-label": "Golden profile",
                  onChange: C[5] || (C[5] = (F) => p(t).selectGoldenProfile(F.target.value))
                }, [
                  C[27] || (C[27] = u("option", { value: "" }, "None", -1)),
                  (k(!0), S(fe, null, ze(p(t).goldenProfiles, (F) => (k(), S("option", {
                    key: F.name,
                    value: F.name
                  }, L(F.name), 9, Ik))), 128))
                ], 40, $k)
              ])
            ]),
            A.value?.engine_migration_notice ? (k(), S("p", Rk, L(A.value.engine_migration_notice), 1)) : te("", !0)
          ], 64)) : te("", !0),
          p(t).activeSection === "outputs" ? (k(), S(fe, { key: 1 }, [
            u("div", Ak, [
              C[30] || (C[30] = u("h2", { class: "cmst-type-section" }, "Outputs", -1)),
              H(re, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-settings-reset-outputs",
                onClick: C[6] || (C[6] = (F) => be("outputs"))
              }, {
                default: se(() => [...C[29] || (C[29] = [
                  K("Reset section", -1)
                ])]),
                _: 1
              })
            ]),
            u("div", Ek, [
              u("div", Ok, [
                C[32] || (C[32] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Output format"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Saved image format. Original keeps the engine default.")
                ], -1)),
                Fe(u("select", {
                  "onUpdate:modelValue": C[7] || (C[7] = (F) => r.value = F),
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "Output format"
                }, [...C[31] || (C[31] = [
                  u("option", { value: "original" }, "Original", -1),
                  u("option", { value: "png" }, "PNG", -1),
                  u("option", { value: "jpeg" }, "JPEG", -1),
                  u("option", { value: "webp" }, "WebP", -1)
                ])], 512), [
                  [ps, r.value]
                ])
              ]),
              u("div", Tk, [
                C[33] || (C[33] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Quality"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Compression quality for lossy formats, 1–100.")
                ], -1)),
                Fe(u("input", {
                  "onUpdate:modelValue": C[8] || (C[8] = (F) => s.value = F),
                  type: "number",
                  min: "1",
                  max: "100",
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "Quality"
                }, null, 512), [
                  [
                    lt,
                    s.value,
                    void 0,
                    { number: !0 }
                  ]
                ])
              ]),
              u("div", Pk, [
                C[35] || (C[35] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "WebP lossless compression"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Effort spent on lossless WebP encodes.")
                ], -1)),
                Fe(u("select", {
                  "onUpdate:modelValue": C[9] || (C[9] = (F) => o.value = F),
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "WebP lossless compression"
                }, [...C[34] || (C[34] = [
                  u("option", { value: "balanced" }, "Balanced", -1),
                  u("option", { value: "fast" }, "Fast", -1),
                  u("option", { value: "best" }, "Best", -1)
                ])], 512), [
                  [ps, o.value]
                ])
              ]),
              u("div", Nk, [
                C[36] || (C[36] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Save folder"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Local destination for saved outputs.")
                ], -1)),
                Fe(u("input", {
                  "onUpdate:modelValue": C[10] || (C[10] = (F) => n.value = F),
                  type: "text",
                  class: "cmst-field cmst:w-56 cmst:max-w-full cmst:font-mono",
                  "aria-label": "Save folder"
                }, null, 512), [
                  [lt, n.value]
                ])
              ]),
              u("div", Mk, [
                C[37] || (C[37] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Auto-save local"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Write a local copy of every output automatically.")
                ], -1)),
                Fe(u("input", {
                  "onUpdate:modelValue": C[11] || (C[11] = (F) => a.value = F),
                  type: "checkbox",
                  "aria-label": "Auto-save local"
                }, null, 512), [
                  [ln, a.value]
                ])
              ]),
              u("div", zk, [
                C[38] || (C[38] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Save metadata sidecar"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Keep generation parameters alongside each file.")
                ], -1)),
                Fe(u("input", {
                  "onUpdate:modelValue": C[12] || (C[12] = (F) => i.value = F),
                  type: "checkbox",
                  "aria-label": "Save metadata sidecar"
                }, null, 512), [
                  [ln, i.value]
                ])
              ])
            ]),
            u("div", jk, [
              H(re, {
                size: "sm",
                variant: "secondary",
                disabled: p(t).saving,
                "data-testid": "vue-settings-save-output",
                onClick: O
              }, {
                default: se(() => [
                  K(L(p(t).saving ? "Saving…" : "Save outputs"), 1)
                ]),
                _: 1
              }, 8, ["disabled"])
            ])
          ], 64)) : te("", !0),
          p(t).activeSection === "accounts" ? (k(), S(fe, { key: 2 }, [
            C[39] || (C[39] = u("h2", { class: "cmst-type-section" }, "Accounts & tokens", -1)),
            C[40] || (C[40] = u("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, "Sign-in status lives in Manage Modal.", -1)),
            u("div", Dk, [
              (k(!0), S(fe, null, ze(p(t).goldenProfiles, (F) => (k(), S("div", {
                key: F.name,
                class: "cmst-data-row"
              }, [
                u("button", {
                  type: "button",
                  class: "cmst-icon-btn",
                  "aria-pressed": p(t).favoriteGoldenProfiles.includes(F.name) ? "true" : "false",
                  "aria-label": `Toggle favorite for ${F.name}`,
                  "data-testid": `vue-golden-favorite-${F.name}`,
                  onClick: (Se) => p(t).toggleGoldenFavorite(F.name)
                }, [
                  H(p(Wr), {
                    class: Ae(["cmst:size-3.5", p(t).favoriteGoldenProfiles.includes(F.name) ? "cmst:fill-cmst-primary cmst:text-cmst-primary" : ""]),
                    "aria-hidden": "true"
                  }, null, 8, ["class"])
                ], 8, Lk),
                u("span", Uk, L(F.name), 1)
              ]))), 128)),
              p(t).goldenProfiles.length ? te("", !0) : (k(), S("p", Vk, "Golden catalog not loaded yet."))
            ])
          ], 64)) : te("", !0),
          p(t).activeSection === "interface" ? (k(), S(fe, { key: 3 }, [
            u("div", Fk, [
              C[42] || (C[42] = u("h2", { class: "cmst-type-section" }, "Interface", -1)),
              H(re, {
                variant: "ghost",
                size: "sm",
                onClick: C[13] || (C[13] = (F) => be("interface"))
              }, {
                default: se(() => [...C[41] || (C[41] = [
                  K("Reset section", -1)
                ])]),
                _: 1
              })
            ]),
            u("div", Wk, [
              u("div", Bk, [
                C[43] || (C[43] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "History grid columns"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Media grid density on the History page.")
                ], -1)),
                u("select", {
                  value: p(t).columnsPreference,
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "History grid columns",
                  onChange: C[14] || (C[14] = (F) => p(t).setHistoryColumns(F.target.value))
                }, [
                  (k(), S(fe, null, ze([2, 3, 4, 5, 6, 7, 8], (F) => u("option", {
                    key: F,
                    value: String(F)
                  }, L(F), 9, Gk)), 64))
                ], 40, qk)
              ]),
              u("div", Hk, [
                C[45] || (C[45] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Remote inventory refresh"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "How often shared inventory re-syncs in the background.")
                ], -1)),
                u("select", {
                  value: p(t).refreshIntervalPreference,
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "Remote inventory refresh",
                  onChange: C[15] || (C[15] = (F) => p(t).setInventoryInterval(F.target.value))
                }, [...C[44] || (C[44] = [
                  Ur('<option value="0">Off</option><option value="60">1 minute</option><option value="300">5 minutes</option><option value="900">15 minutes</option><option value="1800">30 minutes</option>', 5)
                ])], 40, Zk)
              ]),
              u("div", Kk, [
                C[47] || (C[47] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Shell density"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Spacing rhythm for the Studio shell.")
                ], -1)),
                u("select", {
                  value: p(t).density,
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "data-testid": "vue-density-toggle",
                  "aria-label": "Shell density",
                  onChange: C[16] || (C[16] = (F) => p(t).setDensity(F.target.value))
                }, [...C[46] || (C[46] = [
                  u("option", { value: "comfortable" }, "Comfortable", -1),
                  u("option", { value: "compact" }, "Compact", -1)
                ])], 40, Jk)
              ])
            ])
          ], 64)) : te("", !0),
          p(t).activeSection === "advanced" ? (k(), S(fe, { key: 4 }, [
            u("div", Qk, [
              C[49] || (C[49] = u("h2", { class: "cmst-type-section" }, "Advanced", -1)),
              H(re, {
                variant: "ghost",
                size: "sm",
                onClick: C[17] || (C[17] = (F) => be("advanced"))
              }, {
                default: se(() => [...C[48] || (C[48] = [
                  K("Reset section", -1)
                ])]),
                _: 1
              })
            ]),
            u("div", Yk, [
              u("div", Xk, [
                u("div", e0, [
                  C[51] || (C[51] = u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Heavy tracing", -1)),
                  u("p", t0, [
                    C[50] || (C[50] = K(" Requires ComfyUI restart. ", -1)),
                    p(t).profileLevel !== p(t).effectiveProfileLevel ? (k(), S("span", s0, " Restart pending: selected " + L(p(t).profileLevel) + ", effective " + L(p(t).effectiveProfileLevel) + ". ", 1)) : te("", !0)
                  ])
                ]),
                Fe(u("select", {
                  "onUpdate:modelValue": C[18] || (C[18] = (F) => d.value = F),
                  class: "cmst-field cmst:w-56 cmst:max-w-full",
                  "aria-label": "Heavy tracing",
                  onChange: J
                }, [...C[52] || (C[52] = [
                  Ur('<option value="off">Off</option><option value="summary">Summary</option><option value="detailed">Detailed</option><option value="trace">Trace</option><option value="trace_verbose">Verbose trace</option>', 5)
                ])], 544), [
                  [ps, d.value]
                ])
              ]),
              u("div", n0, [
                C[53] || (C[53] = u("div", { class: "cmst:min-w-0" }, [
                  u("p", { class: "cmst:text-[13px] cmst:font-medium" }, "Skip plan validation"),
                  u("p", { class: "cmst:text-xs cmst:text-cmst-muted" }, "Temporary triage only. Re-enable after debugging.")
                ], -1)),
                Fe(u("input", {
                  "onUpdate:modelValue": C[19] || (C[19] = (F) => y.value = F),
                  type: "checkbox",
                  "data-testid": "vue-settings-skip-validation",
                  "aria-label": "Skip plan validation",
                  onChange: R
                }, null, 544), [
                  [ln, y.value]
                ])
              ])
            ]),
            u("div", r0, [
              H(re, {
                variant: "outline",
                size: "sm",
                class: "cmst:text-cmst-danger",
                "data-testid": "vue-settings-reset-all",
                onClick: ee
              }, {
                default: se(() => [
                  K(L(v.value ? "Confirm reset all settings" : "Reset all settings"), 1)
                ]),
                _: 1
              }),
              C[54] || (C[54] = u("p", { class: "cmst:mt-1 cmst:text-xs cmst:text-cmst-muted" }, "Resets only Settings-owned keys. Credentials and user data are not affected.", -1))
            ])
          ], 64)) : te("", !0)
        ])
      ])
    ], 2));
  }
}), a0 = { class: "cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3" }, i0 = { class: "cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted" }, l0 = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, c0 = { class: "cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px] cmst:text-cmst-muted" }, u0 = {
  key: 0,
  class: "cmst:flex cmst:flex-col cmst:gap-2 cmst:border-y cmst:border-solid cmst:border-cmst-border cmst:py-3"
}, d0 = {
  key: 0,
  class: "cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, f0 = { class: "cmst:grid cmst:grid-cols-1 cmst:gap-6 cmst:lg:grid-cols-[300px_minmax(0,1fr)]" }, m0 = { class: "cmst:min-w-0" }, p0 = { class: "cmst:relative" }, h0 = { class: "cmst:mt-2 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, g0 = {
  class: "cmst-seg",
  role: "tablist",
  "aria-label": "Workflows or shared inventory"
}, v0 = ["data-active", "aria-selected"], y0 = ["data-active", "aria-selected"], b0 = {
  key: 0,
  role: "listbox",
  "aria-label": "Workflows",
  class: "cmst:mt-2 cmst:min-w-0"
}, w0 = ["aria-selected", "data-testid", "onClick"], _0 = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, x0 = { class: "cmst-type-object cmst:truncate" }, k0 = {
  key: 0,
  class: "cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate"
}, S0 = {
  key: 0,
  class: "cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted"
}, C0 = {
  key: 0,
  class: "cmst:min-w-0"
}, $0 = { class: "cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3" }, I0 = { class: "cmst:min-w-0" }, R0 = { class: "cmst-type-view cmst:truncate" }, A0 = {
  key: 0,
  class: "cmst-type-meta cmst:mt-0.5"
}, E0 = { class: "cmst:flex cmst:items-center cmst:gap-1.5" }, O0 = ["data-testid", "aria-pressed"], T0 = { class: "cmst:relative" }, P0 = { class: "cmst:absolute cmst:right-0 cmst:z-20 cmst:mt-1 cmst:flex cmst:w-52 cmst:flex-col cmst:gap-2 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-raised cmst:p-3 cmst:shadow-[var(--cmst-shadow-overlay)]" }, N0 = { class: "cmst-field-label" }, M0 = ["value"], z0 = ["value"], j0 = { class: "cmst:mt-3 cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4" }, D0 = { class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, L0 = { class: "cmst-field-label" }, U0 = { class: "cmst-field-label" }, V0 = { class: "cmst:mt-3" }, F0 = {
  "aria-label": "Mapping",
  class: "cmst:mt-6"
}, W0 = { class: "cmst-type-meta cmst:mt-0.5" }, B0 = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, q0 = {
  key: 0,
  class: "cmst:mt-2"
}, G0 = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text"
}, H0 = { class: "cmst:mt-1.5" }, Z0 = {
  "aria-label": "Dependencies",
  class: "cmst:mt-6",
  "data-testid": "vue-dependencies"
}, K0 = { class: "cmst-type-meta cmst:mt-0.5" }, J0 = { class: "cmst:mt-2 cmst:flex cmst:max-h-56 cmst:flex-col cmst:gap-1 cmst:overflow-auto" }, Q0 = { class: "cmst:min-w-0 cmst:flex-1" }, Y0 = { class: "cmst:text-cmst-muted" }, X0 = {
  class: "cmst-type-meta",
  "data-testid": "dependency-model-state"
}, eS = {
  class: "cmst:flex cmst:items-center cmst:gap-1 cmst:text-xs cmst:text-cmst-muted",
  title: "Optional: skip this file when checking or installing requirements"
}, tS = ["checked", "onChange"], sS = {
  key: 1,
  class: "cmst:w-full cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "dependency-model-install-note"
}, nS = { class: "cmst:min-w-0 cmst:flex-1" }, rS = {
  key: 1,
  class: "cmst:w-full cmst:text-xs cmst:text-cmst-muted",
  "data-testid": "dependency-node-install-note"
}, oS = {
  "aria-label": "Portability",
  class: "cmst:mt-6"
}, aS = { class: "cmst-type-meta cmst:mt-0.5" }, iS = { class: "cmst:mt-2 cmst:flex cmst:gap-1.5" }, lS = {
  "aria-label": "Presets",
  class: "cmst:mt-6"
}, cS = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, uS = { class: "cmst:mt-1" }, dS = { class: "cmst:truncate" }, fS = {
  "aria-label": "Guidance mapping",
  class: "cmst:mt-6"
}, mS = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, pS = {
  key: 1,
  class: "cmst:py-8 cmst:text-[13px] cmst:text-cmst-muted"
}, hS = {
  key: 1,
  class: "cmst:min-w-0"
}, gS = { class: "cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted" }, vS = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, yS = {
  key: 1,
  "data-state": "open",
  "aria-hidden": "true",
  style: { display: "none" }
}, bS = { "data-studio-app": "" }, wS = ["onKeydown"], _S = { class: "cmst-inspector-head" }, xS = { class: "cmst:flex cmst:items-start cmst:justify-between cmst:gap-3" }, kS = { class: "cmst:min-w-0" }, SS = { class: "cmst-type-meta cmst:mt-0.5" }, CS = {
  class: "cmst-progress-thin cmst:mt-2",
  "aria-hidden": "true"
}, $S = { class: "cmst-inspector-body" }, IS = { class: "cmst-field-label cmst:mt-3" }, RS = ["value"], AS = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, ES = {
  key: 0,
  class: "cmst:mt-3"
}, OS = { class: "cmst:min-w-0 cmst:flex-1 cmst:truncate" }, TS = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text",
  role: "status"
}, PS = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, NS = { class: "cmst:mt-2 cmst:text-[13px]" }, MS = { class: "cmst:mt-3 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" }, zS = { class: "cmst:text-[13px] cmst:text-cmst-muted" }, jS = { class: "cmst:mt-2" }, DS = { class: "cmst:mt-2 cmst:max-h-40 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text" }, LS = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-danger",
  role: "alert"
}, US = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text",
  role: "status"
}, VS = { class: "cmst:mt-3" }, FS = { class: "cmst-inspector-foot" }, WS = {
  key: 1,
  class: "cmst-type-meta"
}, BS = /* @__PURE__ */ xt({
  __name: "WorkflowsView",
  setup(e) {
    const t = Ja(), s = bo(), n = /* @__PURE__ */ T(""), r = /* @__PURE__ */ T("workflows"), o = /* @__PURE__ */ T(""), a = /* @__PURE__ */ T(""), i = /* @__PURE__ */ T(""), l = /* @__PURE__ */ T(""), c = /* @__PURE__ */ T(""), d = /* @__PURE__ */ T(""), f = /* @__PURE__ */ T(""), y = /* @__PURE__ */ T(!1), v = /* @__PURE__ */ T(""), A = /* @__PURE__ */ T(""), b = /* @__PURE__ */ T("txt2img"), w = /* @__PURE__ */ T(""), O = ye(() => Math.max(0, cs.indexOf(t.wizardDraft?.step ?? "feature-type"))), I = ye(() => cs[O.value]);
    function V($) {
      return $.folder ? $.folder : ($.tags ?? []).find((h) => !!h) ?? "";
    }
    const R = ye(() => {
      const m = t.selectedVersion?.version;
      return typeof m == "number" ? `Version ${m}` : "";
    }), J = /* @__PURE__ */ new Set(["output", "outputBinding", "controls", "featureType", "step", "version"]), be = ye(() => {
      const $ = t.mapping;
      if (!$) return { configured: !1, bindings: 0, controls: 0 };
      const m = $.bindings, h = m && typeof m == "object" ? Object.keys(m).length : Object.keys($).filter((U) => !J.has(U)).length, N = $.controls;
      return {
        configured: !0,
        bindings: h,
        controls: Array.isArray(N) ? N.length : 0
      };
    }), ee = /* @__PURE__ */ T(!1), M = {
      "feature-type": "Feature",
      "required-bindings": "Bindings",
      "exposed-controls": "Controls",
      details: "Review"
    }, C = ye(() => M[I.value] ?? I.value);
    function F($) {
      if (!$ || typeof $ != "object") return "graph target";
      const m = $;
      return String(m.nodeTitle ?? m.target ?? m.nodeId ?? "graph target");
    }
    function Se($) {
      return !$ || typeof $ != "object" ? !1 : $.confirmed === !0;
    }
    xs(async () => {
      await Promise.all([t.initialize(), s.initialize()]), await t.maybeResumeWizard().catch(() => !1);
    });
    async function Ce() {
      t.query = n.value, await t.loadList();
    }
    async function Me($) {
      await t.selectWorkflow($);
      const m = t.selectedWorkflow;
      l.value = String(m?.name ?? ""), c.value = String(m?.folder ?? "");
    }
    function He() {
      t.openWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!0);
    }
    function ue() {
      window.__comfymodalCancelStudioGraphBinding?.(), t.closeWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
    }
    function W($) {
      $.key !== "Escape" || $.defaultPrevented || t.wizardOpen && ($.stopPropagation(), ue());
    }
    Wt(
      () => t.wizardOpen,
      ($) => {
        $ ? document.addEventListener("keydown", W) : document.removeEventListener("keydown", W);
      }
    ), uo(() => {
      document.removeEventListener("keydown", W);
    });
    async function E() {
      if (!o.value.trim()) return;
      const $ = o.value.trim();
      if (window.__comfymodalBeginStudioGraphBinding) {
        i.value = "Click a node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "prompt",
          label: "prompt",
          allowOutput: !1,
          onCapture: (m) => {
            t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { ...m, confirmed: !0 } } }), i.value = `Confirmed ${String(m.nodeTitle ?? m.nodeId ?? "graph target")}`;
          },
          onCancel: (m) => {
            i.value = m;
          }
        });
        return;
      }
      t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { target: $, confirmed: !0 } } }), i.value = `Confirmed graph target ${$}`;
    }
    async function _() {
      if (window.__comfymodalBeginStudioGraphBinding) {
        i.value = "Click the output node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "output",
          label: "output",
          allowOutput: !0,
          onCapture: ($) => {
            t.updateWizard({ outputBinding: { ...$, confirmed: !0 } }), i.value = `Output bound to ${String($.nodeTitle ?? $.nodeId ?? "graph target")}`;
          },
          onCancel: ($) => {
            i.value = $;
          }
        });
        return;
      }
      t.updateWizard({ outputBinding: { target: "SaveImage.images", confirmed: !0 } }), i.value = "Output binding recorded";
    }
    async function X() {
      i.value = "";
      try {
        await t.saveWizardMapping(), i.value = "Mapping saved", window.__comfymodalCancelStudioGraphBinding?.(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
      } catch ($) {
        i.value = $ instanceof Error ? $.message : "Save failed";
      }
    }
    function ne() {
      const $ = cs[Math.min(cs.length - 1, O.value + 1)];
      t.setWizardStep($);
    }
    function Xe() {
      const $ = cs[Math.max(0, O.value - 1)];
      t.setWizardStep($);
    }
    function qe() {
      if (!a.value.trim()) return;
      const $ = [...t.wizardDraft?.controls ?? [], { label: a.value.trim(), enabled: !0 }];
      t.updateWizard({ controls: $ }), a.value = "";
    }
    async function mt() {
      f.value = "";
      try {
        const $ = JSON.parse(d.value);
        await t.importNewWorkflow($), d.value = "";
      } catch ($) {
        f.value = $ instanceof Error ? $.message : "Import failed";
      }
    }
    async function at() {
      await t.updateMetadata({ name: l.value, folder: c.value }).catch(() => {
      });
    }
    async function We() {
      try {
        await t.saveMapping(JSON.parse(w.value || "{}"));
      } catch {
      }
    }
    const Oe = ye(() => t.dependencies ?? {}), q = ye(() => {
      const $ = Oe.value.models;
      if (!Array.isArray($)) return [];
      const m = new Set(
        Array.isArray(Oe.value.nonessential_keys ?? Oe.value.nonessential) ? (Oe.value.nonessential_keys ?? Oe.value.nonessential).map(String) : []
      );
      return $.filter((h) => !!h && typeof h == "object").map((h, N) => {
        const U = String(h.key || h.filename || `model-${N}`), G = Array.isArray(h.source_urls) ? h.source_urls : [];
        return {
          key: U,
          filename: String(h.filename || U),
          folder: String(h.folder || ""),
          state: String(h.state || "unknown"),
          nonessential: m.has(U),
          hasSource: G.length > 0 || typeof h.remote_model == "object",
          message: t.dependencyInstallMessage[U] ?? "",
          raw: h
        };
      }).sort((h, N) => (h.state === "missing" ? 0 : 1) - (N.state === "missing" ? 0 : 1));
    }), j = ye(() => {
      const $ = Oe.value.custom_nodes;
      return Array.isArray($) ? $.filter((m) => !!m && typeof m == "object").map((m, h) => {
        const N = String(m.name || m.cnr_id || `node-${h}`);
        return {
          key: N,
          name: String(m.name || N),
          state: String(m.state || "unknown"),
          message: t.dependencyInstallMessage[N] ?? "",
          raw: m
        };
      }) : [];
    }), D = ye(() => {
      const $ = Oe.value.summary;
      if ($ && typeof $ == "object") {
        const m = $, h = Number(m.installed ?? 0), N = Number(m.missing ?? 0);
        return `${h} installed · ${N} missing · ${N === 0 ? "ready" : "attention"}`;
      }
      return t.dependencies ? `${q.value.length + j.value.length} requirements` : "not loaded";
    }), le = ye(() => {
      const $ = t.versionState;
      if ($ && typeof $.runnable == "boolean")
        return $.runnable ? "Runnable" : "Not runnable — resolve dependencies";
      const m = t.selectedVersion;
      return m && typeof m.runnable == "boolean" ? m.runnable ? "Runnable" : "Not runnable — resolve dependencies" : "";
    }), g = ye(() => le.value === "Runnable");
    async function x($, m) {
      const h = new Set(
        q.value.filter((N) => N.nonessential).map((N) => N.key)
      );
      m ? h.add($) : h.delete($), await t.markNonessential([...h]).catch(() => {
      });
    }
    async function P($) {
      const m = $.raw.remote_model && typeof $.raw.remote_model == "object" ? $.raw.remote_model : $.raw, h = String(m.url || m.download_url || ""), N = h ? { url: h, filename: $.filename, save_path: $.folder } : { filename: $.filename, folder: $.folder };
      try {
        await s.installModel(N);
      } catch {
      }
    }
    async function z($) {
      await t.installDependencyNode($.raw);
    }
    return ($, m) => (k(), S("section", {
      class: Ae(p(fr)()),
      "data-testid": "vue-page-workflows"
    }, [
      p(t).wizardOpen ? te("", !0) : (k(), S(fe, { key: 0 }, [
        u("div", a0, [
          u("div", null, [
            m[31] || (m[31] = u("h1", { class: "cmst-type-view" }, "Workflows", -1)),
            u("p", i0, L(p(t).workflows.length) + " workflows ", 1)
          ]),
          u("div", l0, [
            Fe(u("select", {
              "onUpdate:modelValue": m[0] || (m[0] = (h) => p(t).tagFilter = h),
              class: "cmst-field",
              "aria-label": "Filter by tag",
              onChange: m[1] || (m[1] = (h) => p(t).loadList())
            }, [...m[32] || (m[32] = [
              u("option", { value: "" }, "All tags", -1)
            ])], 544), [
              [ps, p(t).tagFilter]
            ]),
            u("label", c0, [
              Fe(u("input", {
                "onUpdate:modelValue": m[2] || (m[2] = (h) => p(t).favoritesOnly = h),
                type: "checkbox",
                onChange: m[3] || (m[3] = (h) => p(t).loadList())
              }, null, 544), [
                [ln, p(t).favoritesOnly]
              ]),
              m[33] || (m[33] = K(" Favorites ", -1))
            ]),
            H(re, {
              size: "sm",
              variant: "outline",
              "data-testid": "vue-workflow-import-toggle",
              onClick: m[4] || (m[4] = (h) => y.value = !y.value)
            }, {
              default: se(() => [
                H(p(sh), {
                  class: "cmst:size-4",
                  "aria-hidden": "true"
                }),
                m[34] || (m[34] = K("Import ", -1))
              ]),
              _: 1
            })
          ])
        ]),
        y.value ? (k(), S("div", u0, [
          m[36] || (m[36] = u("label", {
            class: "cmst:text-[13px] cmst:font-medium",
            for: "vue-workflow-import-text"
          }, "Import workflow JSON", -1)),
          Fe(u("textarea", {
            id: "vue-workflow-import-text",
            "onUpdate:modelValue": m[5] || (m[5] = (h) => d.value = h),
            rows: "3",
            class: "cmst-field cmst:font-mono cmst:text-xs",
            placeholder: '{"name": "...", "static_graph": {...}}',
            "data-testid": "vue-workflow-import-input"
          }, null, 512), [
            [lt, d.value]
          ]),
          f.value ? (k(), S("p", d0, L(f.value), 1)) : te("", !0),
          u("div", null, [
            H(re, {
              size: "sm",
              "data-testid": "vue-workflow-import",
              onClick: mt
            }, {
              default: se(() => [...m[35] || (m[35] = [
                K("Import", -1)
              ])]),
              _: 1
            })
          ])
        ])) : te("", !0),
        u("div", f0, [
          u("div", m0, [
            u("div", p0, [
              H(p(_u), {
                class: "cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted",
                "aria-hidden": "true"
              }),
              Fe(u("input", {
                "onUpdate:modelValue": m[6] || (m[6] = (h) => n.value = h),
                class: "cmst-field cmst:w-full cmst:pl-8",
                placeholder: "Search workflows",
                "aria-label": "Search workflows",
                onKeyup: zs(Ce, ["enter"])
              }, null, 544), [
                [lt, n.value]
              ])
            ]),
            u("div", h0, [
              u("div", g0, [
                u("button", {
                  type: "button",
                  role: "tab",
                  class: "cmst-seg-btn",
                  "data-active": r.value === "workflows",
                  "aria-selected": r.value === "workflows",
                  onClick: m[7] || (m[7] = (h) => r.value = "workflows")
                }, [
                  H(p(wu), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  }),
                  m[37] || (m[37] = K("Workflows ", -1))
                ], 8, v0),
                u("button", {
                  type: "button",
                  role: "tab",
                  class: "cmst-seg-btn",
                  "data-active": r.value === "models",
                  "aria-selected": r.value === "models",
                  onClick: m[8] || (m[8] = (h) => r.value = "models")
                }, [
                  H(p(Kp), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  }),
                  m[38] || (m[38] = K("Models / Nodes ", -1))
                ], 8, y0)
              ]),
              H(re, {
                size: "sm",
                variant: "ghost",
                "aria-label": "Refresh workflows",
                onClick: m[9] || (m[9] = (h) => p(t).loadList())
              }, {
                default: se(() => [
                  H(p(vo), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  })
                ]),
                _: 1
              })
            ]),
            r.value === "workflows" ? (k(), S("div", b0, [
              (k(!0), S(fe, null, ze(p(t).workflows, (h) => (k(), S("button", {
                key: h.workflow_id,
                type: "button",
                role: "option",
                class: "cmst-object-row",
                "aria-selected": p(t).selectedWorkflow?.workflow_id === h.workflow_id,
                "data-testid": `vue-workflow-${h.workflow_id}`,
                onClick: (N) => Me(h.workflow_id)
              }, [
                u("span", _0, [
                  h.favorite ? (k(), ut(p(Wr), {
                    key: 0,
                    class: "cmst:size-3.5 cmst:shrink-0 cmst:fill-cmst-primary cmst:text-cmst-primary",
                    "aria-label": "Favorite"
                  })) : te("", !0),
                  u("strong", x0, L(h.name || "Untitled workflow"), 1)
                ]),
                V(h) ? (k(), S("span", k0, L(V(h)), 1)) : te("", !0)
              ], 8, w0))), 128)),
              p(t).workflows.length ? te("", !0) : (k(), S("p", S0, " No workflows returned by the server. "))
            ])) : te("", !0)
          ]),
          r.value === "workflows" ? (k(), S(fe, { key: 0 }, [
            p(t).selectedWorkflow ? (k(), S("div", C0, [
              u("div", $0, [
                u("div", I0, [
                  u("h2", R0, L(p(t).selectedWorkflow.name), 1),
                  R.value ? (k(), S("p", A0, L(R.value), 1)) : te("", !0),
                  le.value ? (k(), S("p", {
                    key: 1,
                    class: Ae(["cmst:mt-1.5 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-xs", g.value ? "cmst:text-cmst-ok" : "cmst:text-cmst-warn"]),
                    "data-testid": "vue-version-runnable"
                  }, [
                    u("span", {
                      class: Ae(["cmst:inline-block cmst:size-1.5 cmst:rounded-full", g.value ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-warn"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    K(" " + L(le.value), 1)
                  ], 2)) : te("", !0)
                ]),
                u("div", E0, [
                  u("button", {
                    type: "button",
                    "data-testid": `vue-workflow-favorite-${p(t).selectedWorkflow.workflow_id}`,
                    "aria-pressed": !!p(t).selectedWorkflow.favorite,
                    "aria-label": "Toggle favorite",
                    class: Ae(["cmst:rounded-md cmst:p-1.5 cmst:hover:bg-cmst-hover", p(t).selectedWorkflow.favorite ? "cmst:text-cmst-primary" : "cmst:text-cmst-muted"]),
                    onClick: m[10] || (m[10] = (h) => p(t).toggleFavorite(p(t).selectedWorkflow.workflow_id, !p(t).selectedWorkflow.favorite))
                  }, [
                    H(p(Wr), {
                      class: Ae(["cmst:size-4", p(t).selectedWorkflow.favorite ? "cmst:fill-cmst-primary" : ""]),
                      "aria-hidden": "true"
                    }, null, 8, ["class"])
                  ], 10, O0),
                  H(re, {
                    size: "sm",
                    onClick: He
                  }, {
                    default: se(() => [
                      H(p(xh), {
                        class: "cmst:size-4",
                        "aria-hidden": "true"
                      }),
                      m[39] || (m[39] = K("Setup workflow ", -1))
                    ]),
                    _: 1
                  }),
                  u("details", T0, [
                    m[43] || (m[43] = u("summary", {
                      class: "cmst:cursor-pointer cmst:list-none cmst:rounded-md cmst:px-2 cmst:py-1.5 cmst:text-[13px] cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg [&::-webkit-details-marker]:cmst:hidden",
                      "aria-label": "More workflow actions"
                    }, " ··· ", -1)),
                    u("div", P0, [
                      u("label", N0, [
                        m[40] || (m[40] = K("Version ", -1)),
                        u("select", {
                          value: p(t).selectedVersion?.workflow_version_id ?? "",
                          class: "cmst-field cmst:w-full",
                          "aria-label": "Select version",
                          "data-testid": "vue-version-select",
                          onChange: m[11] || (m[11] = (h) => p(t).selectVersion(h.target.value))
                        }, [
                          (k(!0), S(fe, null, ze(p(t).versions, (h) => (k(), S("option", {
                            key: h.workflow_version_id,
                            value: h.workflow_version_id
                          }, " v" + L(h.version ?? h.workflow_version_id), 9, z0))), 128))
                        ], 40, M0)
                      ]),
                      H(re, {
                        size: "sm",
                        variant: "outline",
                        "data-testid": "vue-version-capture",
                        onClick: m[12] || (m[12] = (h) => p(t).captureVersion({}))
                      }, {
                        default: se(() => [...m[41] || (m[41] = [
                          K(" Capture version ", -1)
                        ])]),
                        _: 1
                      }),
                      H(re, {
                        size: "sm",
                        variant: "outline",
                        "data-testid": "vue-workflow-delete",
                        onClick: m[13] || (m[13] = (h) => p(t).deleteSelectedWorkflow())
                      }, {
                        default: se(() => [...m[42] || (m[42] = [
                          K(" Delete workflow ", -1)
                        ])]),
                        _: 1
                      })
                    ])
                  ])
                ])
              ]),
              u("div", j0, [
                u("div", D0, [
                  u("label", L0, [
                    m[44] || (m[44] = K("Name", -1)),
                    Fe(u("input", {
                      "onUpdate:modelValue": m[14] || (m[14] = (h) => l.value = h),
                      class: "cmst-field"
                    }, null, 512), [
                      [lt, l.value]
                    ])
                  ]),
                  u("label", U0, [
                    m[45] || (m[45] = K("Folder", -1)),
                    Fe(u("input", {
                      "onUpdate:modelValue": m[15] || (m[15] = (h) => c.value = h),
                      class: "cmst-field"
                    }, null, 512), [
                      [lt, c.value]
                    ])
                  ])
                ]),
                u("div", V0, [
                  H(re, {
                    size: "sm",
                    variant: "secondary",
                    "data-testid": "vue-workflow-save-meta",
                    onClick: at
                  }, {
                    default: se(() => [...m[46] || (m[46] = [
                      K(" Save metadata ", -1)
                    ])]),
                    _: 1
                  })
                ])
              ]),
              u("section", F0, [
                m[49] || (m[49] = u("h3", { class: "cmst-type-section" }, "Mapping", -1)),
                u("p", W0, L(be.value.configured ? `${be.value.bindings} bindings · ${be.value.controls} controls` : "not configured"), 1),
                u("div", B0, [
                  H(re, {
                    size: "sm",
                    variant: "ghost",
                    onClick: m[16] || (m[16] = (h) => p(t).loadMappingCandidates())
                  }, {
                    default: se(() => [...m[47] || (m[47] = [
                      K("Load candidates", -1)
                    ])]),
                    _: 1
                  }),
                  H(re, {
                    size: "sm",
                    variant: "ghost",
                    onClick: m[17] || (m[17] = (h) => ee.value = !ee.value)
                  }, {
                    default: se(() => [
                      K(L(ee.value ? "Hide raw mapping" : "Edit raw mapping"), 1)
                    ]),
                    _: 1
                  })
                ]),
                ee.value ? (k(), S("div", q0, [
                  p(t).mappingCandidates ? (k(), S("pre", G0, L(JSON.stringify(p(t).mappingCandidates, null, 1).slice(0, 800)), 1)) : te("", !0),
                  Fe(u("textarea", {
                    "onUpdate:modelValue": m[18] || (m[18] = (h) => w.value = h),
                    rows: "3",
                    class: "cmst-field cmst:mt-2 cmst:w-full cmst:font-mono cmst:text-xs",
                    placeholder: '{"bindings": {...}}'
                  }, null, 512), [
                    [lt, w.value]
                  ]),
                  u("div", H0, [
                    H(re, {
                      size: "sm",
                      variant: "secondary",
                      "data-testid": "vue-mapping-save",
                      onClick: We
                    }, {
                      default: se(() => [...m[48] || (m[48] = [
                        K("Save mapping", -1)
                      ])]),
                      _: 1
                    })
                  ])
                ])) : te("", !0)
              ]),
              u("section", Z0, [
                m[53] || (m[53] = u("h3", { class: "cmst-type-section" }, "Dependencies", -1)),
                u("p", K0, L(D.value), 1),
                u("ul", J0, [
                  (k(!0), S(fe, null, ze(q.value, (h) => (k(), S("li", {
                    key: `model-${h.key}`,
                    class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:rounded-md cmst:px-2 cmst:py-2 cmst:text-[13px] cmst:hover:bg-cmst-hover",
                    "data-testid": "dependency-model-row"
                  }, [
                    u("span", {
                      class: Ae(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", h.state === "missing" ? "cmst:bg-cmst-danger" : h.state === "ready" || h.state === "installed" ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-muted"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    u("span", Q0, [
                      K(L(h.filename) + " ", 1),
                      u("span", Y0, "(" + L(h.folder) + ")", 1)
                    ]),
                    u("span", X0, L(h.state), 1),
                    u("label", eS, [
                      u("input", {
                        type: "checkbox",
                        checked: h.nonessential,
                        onChange: (N) => x(h.key, N.target.checked)
                      }, null, 40, tS),
                      m[50] || (m[50] = K(" Optional ", -1))
                    ]),
                    h.state === "missing" && h.hasSource ? (k(), ut(re, {
                      key: 0,
                      size: "sm",
                      variant: "ghost",
                      "data-testid": "dependency-model-install-now",
                      onClick: (N) => P(h)
                    }, {
                      default: se(() => [...m[51] || (m[51] = [
                        K("Install now", -1)
                      ])]),
                      _: 1
                    }, 8, ["onClick"])) : te("", !0),
                    h.message ? (k(), S("span", sS, L(h.message), 1)) : te("", !0)
                  ]))), 128)),
                  (k(!0), S(fe, null, ze(j.value, (h) => (k(), S("li", {
                    key: `node-${h.key}`,
                    class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:rounded-md cmst:px-2 cmst:py-2 cmst:text-[13px] cmst:hover:bg-cmst-hover",
                    "data-testid": "dependency-node-row"
                  }, [
                    u("span", {
                      class: Ae(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", h.state === "missing" ? "cmst:bg-cmst-danger" : "cmst:bg-cmst-ok"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    u("span", nS, L(h.name) + " · " + L(h.state), 1),
                    h.state === "missing" ? (k(), ut(re, {
                      key: 0,
                      size: "sm",
                      variant: "ghost",
                      "data-testid": "dependency-node-install-now",
                      onClick: (N) => z(h)
                    }, {
                      default: se(() => [...m[52] || (m[52] = [
                        K("Install now", -1)
                      ])]),
                      _: 1
                    }, 8, ["onClick"])) : te("", !0),
                    h.message ? (k(), S("span", rS, L(h.message), 1)) : te("", !0)
                  ]))), 128))
                ])
              ]),
              u("section", oS, [
                m[56] || (m[56] = u("h3", { class: "cmst-type-section" }, "Portability", -1)),
                u("p", aS, L(p(t).portability ? "analyzed" : "not analyzed"), 1),
                u("div", iS, [
                  H(re, {
                    size: "sm",
                    variant: "ghost",
                    onClick: m[19] || (m[19] = (h) => p(t).recheckPortability())
                  }, {
                    default: se(() => [...m[54] || (m[54] = [
                      K("Recheck", -1)
                    ])]),
                    _: 1
                  }),
                  H(re, {
                    size: "sm",
                    variant: "ghost",
                    "data-testid": "vue-manifest-export",
                    onClick: m[20] || (m[20] = (h) => p(t).exportManifest())
                  }, {
                    default: se(() => [...m[55] || (m[55] = [
                      K("Export manifest", -1)
                    ])]),
                    _: 1
                  })
                ])
              ]),
              u("section", lS, [
                m[59] || (m[59] = u("h3", { class: "cmst-type-section" }, "Presets", -1)),
                m[60] || (m[60] = u("p", { class: "cmst-type-meta cmst:mt-0.5" }, "image-free configuration only", -1)),
                u("div", cS, [
                  Fe(u("input", {
                    "onUpdate:modelValue": m[21] || (m[21] = (h) => v.value = h),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "Preset name",
                    "aria-label": "Preset name"
                  }, null, 512), [
                    [lt, v.value]
                  ]),
                  H(re, {
                    size: "sm",
                    variant: "secondary",
                    "data-testid": "vue-preset-create",
                    onClick: m[22] || (m[22] = (h) => {
                      p(t).createPreset({ name: v.value || "Untitled", studio_state: {} }), v.value = "";
                    })
                  }, {
                    default: se(() => [...m[57] || (m[57] = [
                      K("Create preset", -1)
                    ])]),
                    _: 1
                  })
                ]),
                u("ul", uS, [
                  (k(!0), S(fe, null, ze(p(t).presets, (h, N) => (k(), S("li", {
                    key: N,
                    class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:rounded-md cmst:px-2 cmst:py-1.5 cmst:text-[13px] cmst:hover:bg-cmst-hover"
                  }, [
                    u("span", dS, L(String(h.name || `preset ${N}`)), 1),
                    H(re, {
                      size: "sm",
                      variant: "ghost",
                      onClick: (U) => p(t).removePreset(String(h.preset_id || h.id || ""))
                    }, {
                      default: se(() => [...m[58] || (m[58] = [
                        K("Delete", -1)
                      ])]),
                      _: 1
                    }, 8, ["onClick"])
                  ]))), 128))
                ])
              ]),
              u("section", fS, [
                m[63] || (m[63] = u("h3", { class: "cmst-type-section" }, "Guidance mapping", -1)),
                u("div", mS, [
                  Fe(u("input", {
                    "onUpdate:modelValue": m[23] || (m[23] = (h) => A.value = h),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "model sha256",
                    "aria-label": "Model sha256"
                  }, null, 512), [
                    [lt, A.value]
                  ]),
                  Fe(u("select", {
                    "onUpdate:modelValue": m[24] || (m[24] = (h) => b.value = h),
                    class: "cmst-field",
                    "aria-label": "Guidance mode"
                  }, [...m[61] || (m[61] = [
                    u("option", { value: "txt2img" }, "txt2img", -1),
                    u("option", { value: "i2i" }, "i2i", -1)
                  ])], 512), [
                    [ps, b.value]
                  ]),
                  H(re, {
                    size: "sm",
                    variant: "outline",
                    onClick: m[25] || (m[25] = (h) => p(t).loadGuidance(A.value, b.value))
                  }, {
                    default: se(() => [...m[62] || (m[62] = [
                      K("Load", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ])) : (k(), S("p", pS, " Select a workflow to inspect its versions, mapping, and dependencies. "))
          ], 64)) : (k(), S("div", hS, [
            m[66] || (m[66] = u("h2", { class: "cmst-type-view" }, "Shared models & nodes", -1)),
            u("p", gS, "Models: " + L(p(s).models.length) + " · Custom nodes: " + L(p(s).customNodes.length), 1),
            u("div", vS, [
              H(re, {
                size: "sm",
                variant: "outline",
                onClick: m[26] || (m[26] = (h) => p(s).rescanModelsNow(!0))
              }, {
                default: se(() => [...m[64] || (m[64] = [
                  K("Rescan models", -1)
                ])]),
                _: 1
              }),
              H(re, {
                size: "sm",
                variant: "outline",
                onClick: m[27] || (m[27] = (h) => p(s).refreshCustomNodesNow())
              }, {
                default: se(() => [...m[65] || (m[65] = [
                  K("Refresh nodes", -1)
                ])]),
                _: 1
              })
            ])
          ]))
        ])
      ], 64)),
      p(t).wizardOpen ? (k(), S("div", yS)) : te("", !0),
      (k(), ut(kc, { to: "body" }, [
        u("div", bS, [
          p(t).wizardOpen ? (k(), S("aside", {
            key: 0,
            class: "cmst-inspector",
            "data-state": "open",
            "data-testid": "vue-workflow-wizard",
            role: "complementary",
            "aria-label": "Setup workflow",
            tabindex: "-1",
            onKeydown: zs(er(ue, ["stop"]), ["esc"])
          }, [
            u("div", _S, [
              u("div", xS, [
                u("div", kS, [
                  m[67] || (m[67] = u("h2", { class: "cmst-type-section cmst:truncate" }, "Setup workflow", -1)),
                  u("p", SS, "Step " + L(O.value + 1) + " of " + L(p(cs).length) + " · " + L(C.value), 1)
                ]),
                u("button", {
                  type: "button",
                  "aria-label": "Close wizard",
                  class: "cmst-close-btn",
                  onClick: ue
                }, [
                  H(p(ya), {
                    class: "cmst:size-4",
                    "aria-hidden": "true"
                  })
                ])
              ]),
              u("div", CS, [
                u("span", {
                  style: wn({ width: `${Math.round((O.value + 1) / p(cs).length * 100)}%` })
                }, null, 4)
              ])
            ]),
            u("div", $S, [
              I.value === "feature-type" ? (k(), S(fe, { key: 0 }, [
                m[70] || (m[70] = u("h3", { class: "cmst-type-object" }, "1 · Feature", -1)),
                m[71] || (m[71] = u("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, "Choose what this workflow does. This decides which bindings and controls the next steps ask for.", -1)),
                u("label", IS, [
                  m[69] || (m[69] = K("Feature type ", -1)),
                  u("select", {
                    class: "cmst-field cmst:w-full",
                    value: p(t).wizardDraft?.featureType,
                    onChange: m[28] || (m[28] = (h) => p(t).updateWizard({ featureType: h.target.value }))
                  }, [...m[68] || (m[68] = [
                    u("option", { value: "t2i" }, "Text to Image", -1),
                    u("option", { value: "i2i" }, "Image to Image", -1),
                    u("option", { value: "inpaint" }, "Inpaint", -1),
                    u("option", { value: "sketch" }, "Sketch", -1),
                    u("option", { value: "outpaint" }, "Outpaint", -1)
                  ])], 40, RS)
                ])
              ], 64)) : I.value === "required-bindings" ? (k(), S(fe, { key: 1 }, [
                m[73] || (m[73] = u("h3", { class: "cmst-type-object" }, "2 · Bindings", -1)),
                m[74] || (m[74] = u("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, " Select the prompt control in the ComfyUI graph — click the node input (for example, the Steps control on a KSampler node) — then confirm the binding here. ", -1)),
                u("div", AS, [
                  Fe(u("input", {
                    "onUpdate:modelValue": m[29] || (m[29] = (h) => o.value = h),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "Node input target",
                    "aria-label": "Node input target"
                  }, null, 512), [
                    [lt, o.value]
                  ]),
                  H(re, {
                    size: "sm",
                    variant: "secondary",
                    onClick: E
                  }, {
                    default: se(() => [...m[72] || (m[72] = [
                      K("Confirm binding", -1)
                    ])]),
                    _: 1
                  })
                ]),
                Object.keys(p(t).wizardDraft?.bindings ?? {}).length ? (k(), S("ul", ES, [
                  (k(!0), S(fe, null, ze(p(t).wizardDraft?.bindings ?? {}, (h, N) => (k(), S("li", {
                    key: String(N),
                    class: "cmst:flex cmst:items-center cmst:gap-2 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-1.5 cmst:text-[13px] first:cmst:border-t-0"
                  }, [
                    u("span", {
                      class: Ae(["cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full", Se(h) ? "cmst:bg-cmst-ok" : "cmst:bg-cmst-warn"]),
                      "aria-hidden": "true"
                    }, null, 2),
                    u("span", OS, L(String(N)) + " → " + L(F(h)), 1),
                    u("span", {
                      class: Ae(["cmst:rounded cmst:px-1.5 cmst:py-0.5 cmst:text-[11px] cmst:font-medium", Se(h) ? "cmst:bg-cmst-ok/15 cmst:text-cmst-ok" : "cmst:bg-cmst-warn/15 cmst:text-cmst-warn"])
                    }, L(Se(h) ? "Bound" : "Pending"), 3)
                  ]))), 128))
                ])) : te("", !0),
                i.value ? (k(), S("p", TS, L(i.value), 1)) : te("", !0)
              ], 64)) : I.value === "exposed-controls" ? (k(), S(fe, { key: 2 }, [
                m[78] || (m[78] = u("h3", { class: "cmst-type-object" }, "3 · Controls", -1)),
                m[79] || (m[79] = u("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, " Add the controls this workflow exposes. Each control becomes one field (Steps, CFG, Seed) — not a generic form builder. ", -1)),
                u("div", PS, [
                  Fe(u("input", {
                    "onUpdate:modelValue": m[30] || (m[30] = (h) => a.value = h),
                    class: "cmst-field cmst:flex-1",
                    placeholder: "Control label, e.g. Steps",
                    "aria-label": "Control label"
                  }, null, 512), [
                    [lt, a.value]
                  ]),
                  H(re, {
                    size: "sm",
                    variant: "secondary",
                    onClick: qe
                  }, {
                    default: se(() => [...m[75] || (m[75] = [
                      K("Add control", -1)
                    ])]),
                    _: 1
                  })
                ]),
                u("ul", NS, [
                  (k(!0), S(fe, null, ze(p(t).wizardDraft?.controls ?? [], (h, N) => (k(), S("li", {
                    key: N,
                    class: "cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-1.5 first:cmst:border-t-0"
                  }, " · " + L(String(h.label ?? h)), 1))), 128))
                ]),
                u("div", MS, [
                  u("p", zS, [
                    m[76] || (m[76] = K(" Select the output node in the ComfyUI graph so runs know where images land. ", -1)),
                    p(t).wizardDraft?.outputBinding ? (k(), S("span", {
                      key: 0,
                      class: Ae(["cmst:ml-1 cmst:rounded cmst:px-1.5 cmst:py-0.5 cmst:text-[11px] cmst:font-medium", Se(p(t).wizardDraft?.outputBinding) ? "cmst:bg-cmst-ok/15 cmst:text-cmst-ok" : "cmst:bg-cmst-warn/15 cmst:text-cmst-warn"])
                    }, L(Se(p(t).wizardDraft?.outputBinding) ? "Bound" : "Pending"), 3)) : te("", !0)
                  ]),
                  u("div", jS, [
                    H(re, {
                      size: "sm",
                      variant: "outline",
                      onClick: _
                    }, {
                      default: se(() => [...m[77] || (m[77] = [
                        K("Capture output binding", -1)
                      ])]),
                      _: 1
                    })
                  ])
                ])
              ], 64)) : (k(), S(fe, { key: 3 }, [
                m[80] || (m[80] = u("h3", { class: "cmst-type-object" }, "4 · Review", -1)),
                m[81] || (m[81] = u("p", { class: "cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted" }, "Review the explicit bindings before saving the version mapping.", -1)),
                u("pre", DS, L(JSON.stringify({ bindings: p(t).wizardDraft?.bindings, output: p(t).wizardDraft?.outputBinding, controls: p(t).wizardDraft?.controls }, null, 1)), 1),
                p(t).wizardError ? (k(), S("p", LS, L(p(t).wizardError), 1)) : i.value ? (k(), S("p", US, L(i.value), 1)) : te("", !0),
                u("div", VS, [
                  H(re, {
                    size: "sm",
                    disabled: p(t).wizardSaving,
                    "data-testid": "vue-wizard-save",
                    onClick: X
                  }, {
                    default: se(() => [
                      K(L(p(t).wizardSaving ? "Saving…" : "Save mapping"), 1)
                    ]),
                    _: 1
                  }, 8, ["disabled"])
                ])
              ], 64))
            ]),
            u("div", FS, [
              H(re, {
                variant: "ghost",
                size: "sm",
                disabled: O.value === 0,
                onClick: Xe
              }, {
                default: se(() => [...m[82] || (m[82] = [
                  K("Back", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              O.value < p(cs).length - 1 ? (k(), ut(re, {
                key: 0,
                size: "sm",
                onClick: ne
              }, {
                default: se(() => [...m[83] || (m[83] = [
                  K("Next", -1)
                ])]),
                _: 1
              })) : (k(), S("span", WS, "Review → Save mapping"))
            ])
          ], 40, wS)) : te("", !0)
        ])
      ]))
    ], 2));
  }
}), qS = {
  playground: dk,
  history: mx,
  workflows: BS,
  backend: gw,
  settings: o0
};
function GS(e = {}) {
  let t;
  return e.memory || !e.win ? t = vp() : t = Vy(e.win, e.initial), jp({
    history: t,
    routes: ku.map((n) => ({
      path: `/${n}`,
      name: n,
      component: qS[n]
    }))
  });
}
function ZS(e, t = {}) {
  const s = Em(), n = GS({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = Im(Ly);
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
  ZS as mountStudioPreview
};

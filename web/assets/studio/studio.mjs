/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function di(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const Ye = {}, Ls = [], Zt = () => {
}, kl = () => !1, zr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), jr = (e) => e.startsWith("onUpdate:"), ht = Object.assign, fi = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, Vu = Object.prototype.hasOwnProperty, qe = (e, t) => Vu.call(e, t), Se = Array.isArray, Cs = (e) => Zn(e) === "[object Map]", ds = (e) => Zn(e) === "[object Set]", Fi = (e) => Zn(e) === "[object Date]", Pe = (e) => typeof e == "function", ot = (e) => typeof e == "string", $t = (e) => typeof e == "symbol", Ke = (e) => e !== null && typeof e == "object", Sl = (e) => (Ke(e) || Pe(e)) && Pe(e.then) && Pe(e.catch), Cl = Object.prototype.toString, Zn = (e) => Cl.call(e), Uu = (e) => Zn(e).slice(8, -1), Al = (e) => Zn(e) === "[object Object]", Dr = (e) => ot(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, In = /* @__PURE__ */ di(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), Lr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, Fu = /-\w/g, xt = Lr(
  (e) => e.replace(Fu, (t) => t.slice(1).toUpperCase())
), Wu = /\B([A-Z])/g, Os = Lr(
  (e) => e.replace(Wu, "-$1").toLowerCase()
), Vr = Lr((e) => e.charAt(0).toUpperCase() + e.slice(1)), oo = Lr(
  (e) => e ? `on${Vr(e)}` : ""
), Ht = (e, t) => !Object.is(e, t), pr = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Rl = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, Ur = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let Wi;
const Fr = () => Wi || (Wi = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function mi(e) {
  if (Se(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = ot(n) ? qu(n) : mi(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (ot(e) || Ke(e))
    return e;
}
const Bu = /;(?![^(]*\))/g, Gu = /:([^]+)/, Hu = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function qu(e) {
  const t = {};
  return e.replace(Hu, (s) => s.startsWith("/*") ? "" : s).split(Bu).forEach((s) => {
    if (s) {
      const n = s.split(Gu);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function kt(e) {
  let t = "";
  if (ot(e))
    t = e;
  else if (Se(e))
    for (let s = 0; s < e.length; s++) {
      const n = kt(e[s]);
      n && (t += n + " ");
    }
  else if (Ke(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const Zu = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", Ku = /* @__PURE__ */ di(Zu);
function Il(e) {
  return !!e || e === "";
}
function Ju(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = fs(e[r], t[r], s);
  return n;
}
function Bi(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < n.length; a++)
      if (!r[a] && fs(o, n[a], s)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function Qu(e, t, s) {
  let n = Cs(e), r = Cs(t);
  if (n || r || (n = ds(e), r = ds(t), n || r))
    return n && r ? Bi(e, t, s) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !fs(e[a], t[a], s))
      return !1;
  }
  return String(e) === String(t);
}
function Gi(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = n(e, t, s);
  return r.delete(e), o.delete(t), i;
}
function fs(e, t, s) {
  if (e === t) return !0;
  let n = Fi(e), r = Fi(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = $t(e), r = $t(t), n || r ? e === t : (n = Se(e), r = Se(t), n || r ? n && r ? Gi(e, t, s, Ju) : !1 : (n = Ke(e), r = Ke(t), n || r ? !n || !r ? !1 : Gi(e, t, s, Qu) : String(e) === String(t))));
}
function pi(e, t) {
  return e.findIndex((s) => fs(s, t));
}
const El = (e) => !!(e && e.__v_isRef === !0), G = (e) => ot(e) ? e : e == null ? "" : Se(e) || Ke(e) && (e.toString === Cl || !Pe(e.toString)) ? El(e) ? G(e.value) : JSON.stringify(e, $l, 2) : String(e), $l = (e, t) => El(t) ? $l(e, t.value) : Cs(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[io(n, o) + " =>"] = r, s),
    {}
  )
} : ds(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => io(s))
} : $t(t) ? io(t) : Ke(t) && !Se(t) && !Al(t) ? String(t) : t, io = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    $t(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let ft;
class Ol {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && ft && (ft.active ? (this.parent = ft, this.index = (ft.scopes || (ft.scopes = [])).push(
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
      const s = ft;
      try {
        return ft = this, t();
      } finally {
        ft = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = ft, ft = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (ft === this)
        ft = this.prevScope;
      else {
        let t = ft;
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
function Tl(e) {
  return new Ol(e);
}
function hi() {
  return ft;
}
function Pl(e, t = !1) {
  ft && ft.cleanups.push(e);
}
let st;
const ao = /* @__PURE__ */ new WeakSet();
class Nl {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, ft && (ft.active ? ft.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, ao.has(this) && (ao.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || zl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, Hi(this), jl(this);
    const t = st, s = jt;
    st = this, jt = !0;
    try {
      return this.fn();
    } finally {
      Dl(this), st = t, jt = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        yi(t);
      this.deps = this.depsTail = void 0, Hi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? ao.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    zo(this) && this.run();
  }
  get dirty() {
    return zo(this);
  }
}
let Ml = 0, En, $n;
function zl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = $n, $n = e;
    return;
  }
  e.next = En, En = e;
}
function gi() {
  Ml++;
}
function vi() {
  if (--Ml > 0)
    return;
  if ($n) {
    let t = $n;
    for ($n = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; En; ) {
    let t = En;
    for (En = void 0; t; ) {
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
function jl(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function Dl(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), yi(n), Yu(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function zo(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (Ll(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function Ll(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === zn) || (e.globalVersion = zn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !zo(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = st, n = jt;
  st = e, jt = !0;
  try {
    jl(e);
    const r = e.fn(e._value);
    (t.version === 0 || Ht(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    st = s, jt = n, Dl(e), e.flags &= -3;
  }
}
function yi(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      yi(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function Yu(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let jt = !0;
const Vl = [];
function Qt() {
  Vl.push(jt), jt = !1;
}
function Yt() {
  const e = Vl.pop();
  jt = e === void 0 ? !0 : e;
}
function Hi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = st;
    st = void 0;
    try {
      t();
    } finally {
      st = s;
    }
  }
}
let zn = 0;
class Xu {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class bi {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!st || !jt || st === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== st)
      s = this.activeLink = new Xu(st, this), st.deps ? (s.prevDep = st.depsTail, st.depsTail.nextDep = s, st.depsTail = s) : st.deps = st.depsTail = s, Ul(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = st.depsTail, s.nextDep = void 0, st.depsTail.nextDep = s, st.depsTail = s, st.deps === s && (st.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, zn++, this.notify(t);
  }
  notify(t) {
    gi();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      vi();
    }
  }
}
function Ul(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        Ul(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const vr = /* @__PURE__ */ new WeakMap(), Us = /* @__PURE__ */ Symbol(
  ""
), jo = /* @__PURE__ */ Symbol(
  ""
), jn = /* @__PURE__ */ Symbol(
  ""
);
function gt(e, t, s) {
  if (jt && st) {
    let n = vr.get(e);
    n || vr.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new bi()), r.map = n, r.key = s), r.track();
  }
}
function is(e, t, s, n, r, o) {
  const i = vr.get(e);
  if (!i) {
    zn++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (gi(), t === "clear")
    i.forEach(a);
  else {
    const l = Se(e), c = l && Dr(s);
    if (l && s === "length") {
      const u = Number(n);
      i.forEach((d, h) => {
        (h === "length" || h === jn || !$t(h) && h >= u) && a(d);
      });
    } else
      switch ((s !== void 0 || i.has(void 0)) && a(i.get(s)), c && a(i.get(jn)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(Us)), Cs(e) && a(i.get(jo)));
          break;
        case "delete":
          l || (a(i.get(Us)), Cs(e) && a(i.get(jo)));
          break;
        case "set":
          Cs(e) && a(i.get(Us));
          break;
      }
  }
  vi();
}
function ed(e, t) {
  const s = vr.get(e);
  return s && s.get(t);
}
function Hs(e) {
  const t = /* @__PURE__ */ Be(e);
  return t === e || (gt(t, "iterate", jn), /* @__PURE__ */ Et(e)) ? t : /* @__PURE__ */ Xt(e) ? /* @__PURE__ */ Kt(e) ? t.map((s) => Is(Tt(s))) : t.map(Is) : t.map(Tt);
}
function Wr(e) {
  return gt(e = /* @__PURE__ */ Be(e), "iterate", jn), e;
}
function Wt(e, t) {
  return /* @__PURE__ */ Xt(e) ? Is(/* @__PURE__ */ Kt(e) ? Tt(t) : t) : Tt(t);
}
const td = {
  __proto__: null,
  [Symbol.iterator]() {
    return lo(this, Symbol.iterator, (e) => Wt(this, e));
  },
  concat(...e) {
    return Hs(this).concat(
      ...e.map((t) => Se(t) ? Hs(t) : t)
    );
  },
  entries() {
    return lo(this, "entries", (e) => (e[1] = Wt(this, e[1]), e));
  },
  every(e, t) {
    return ts(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return ts(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => Wt(this, n)),
      arguments
    );
  },
  find(e, t) {
    return ts(
      this,
      "find",
      e,
      t,
      (s) => Wt(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return ts(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return ts(
      this,
      "findLast",
      e,
      t,
      (s) => Wt(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return ts(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return ts(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return co(this, "includes", e);
  },
  indexOf(...e) {
    return co(this, "indexOf", e);
  },
  join(e) {
    return Hs(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return co(this, "lastIndexOf", e);
  },
  map(e, t) {
    return ts(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return pn(this, "pop");
  },
  push(...e) {
    return pn(this, "push", e);
  },
  reduce(e, ...t) {
    return Zi(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return Zi(this, "reduceRight", e, t);
  },
  shift() {
    return pn(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return ts(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return pn(this, "splice", e);
  },
  toReversed() {
    return Hs(this).toReversed();
  },
  toSorted(e) {
    return Hs(this).toSorted(e);
  },
  toSpliced(...e) {
    return Hs(this).toSpliced(...e);
  },
  unshift(...e) {
    return pn(this, "unshift", e);
  },
  values() {
    return lo(this, "values", (e) => Wt(this, e));
  }
};
function lo(e, t, s) {
  const n = Wr(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ Et(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => qi(o.next(), s), r !== Fl[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => qi(o._next(), s);
  }
  return o;
}
function qi(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const Fl = Array.prototype;
function ts(e, t, s, n, r, o) {
  const i = Wr(e), a = i !== e && !/* @__PURE__ */ Et(e), l = i[t];
  if (l !== Fl[t]) {
    const d = l.apply(e, o);
    return a ? Tt(d) : d;
  }
  let c = s;
  i !== e && (a ? c = function(d, h) {
    return s.call(this, Wt(e, d), h, e);
  } : s.length > 2 && (c = function(d, h) {
    return s.call(this, d, h, e);
  }));
  const u = l.call(i, c, n);
  return a && r ? r(u) : u;
}
function Zi(e, t, s, n) {
  const r = Wr(e), o = r !== e && !/* @__PURE__ */ Et(e);
  let i = s, a = !1;
  r !== e && (o ? (a = n.length === 0, i = function(c, u, d) {
    return a && (a = !1, c = Wt(e, c)), s.call(this, c, Wt(e, u), d, e);
  }) : s.length > 3 && (i = function(c, u, d) {
    return s.call(this, c, u, d, e);
  }));
  const l = r[t](i, ...n);
  return a ? Wt(e, l) : l;
}
function co(e, t, s) {
  const n = /* @__PURE__ */ Be(e);
  gt(n, "iterate", jn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ Br(s[0]) ? (s[0] = /* @__PURE__ */ Be(s[0]), n[t](...s)) : r;
}
function pn(e, t, s = []) {
  Qt(), gi();
  const n = (/* @__PURE__ */ Be(e))[t].apply(e, s);
  return vi(), Yt(), n;
}
const sd = /* @__PURE__ */ di("__proto__,__v_isRef,__isVue"), Wl = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter($t)
);
function nd(e) {
  $t(e) || (e = String(e));
  const t = /* @__PURE__ */ Be(this);
  return gt(t, "has", e), t.hasOwnProperty(e);
}
class Bl {
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
      return n === (r ? o ? md : Zl : o ? ql : Hl).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const i = Se(t);
    if (!r) {
      let l;
      if (i && (l = td[s]))
        return l;
      if (s === "hasOwnProperty")
        return nd;
    }
    const a = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ lt(t) ? t : n
    );
    if (($t(s) ? Wl.has(s) : sd(s)) || (r || gt(t, "get", s), o))
      return a;
    if (/* @__PURE__ */ lt(a)) {
      const l = i && Dr(s) ? a : a.value;
      return r && Ke(l) ? /* @__PURE__ */ Lo(l) : l;
    }
    return Ke(a) ? r ? /* @__PURE__ */ Lo(a) : /* @__PURE__ */ Kn(a) : a;
  }
}
class Gl extends Bl {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const i = Se(t) && Dr(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ Xt(o);
      if (!/* @__PURE__ */ Et(n) && !/* @__PURE__ */ Xt(n) && (o = /* @__PURE__ */ Be(o), n = /* @__PURE__ */ Be(n)), !i && /* @__PURE__ */ lt(o) && !/* @__PURE__ */ lt(n))
        return c || (o.value = n), !0;
    }
    const a = i ? Number(s) < t.length : qe(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ lt(t) ? t : r
    );
    return t === /* @__PURE__ */ Be(r) && l && (a ? Ht(n, o) && is(t, "set", s, n) : is(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = qe(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && is(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!$t(s) || !Wl.has(s)) && gt(t, "has", s), n;
  }
  ownKeys(t) {
    return gt(
      t,
      "iterate",
      Se(t) ? "length" : Us
    ), Reflect.ownKeys(t);
  }
}
class rd extends Bl {
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
const od = /* @__PURE__ */ new Gl(), id = /* @__PURE__ */ new rd(), ad = /* @__PURE__ */ new Gl(!0);
const Do = (e) => e, tr = (e) => Reflect.getPrototypeOf(e);
function ld(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ Be(r), i = Cs(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...n), u = s ? Do : t ? Is : Tt;
    return !t && gt(
      o,
      "iterate",
      l ? jo : Us
    ), ht(
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
function sr(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function cd(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ Be(o), a = /* @__PURE__ */ Be(r);
      e || (Ht(r, a) && gt(i, "get", r), gt(i, "get", a));
      const { has: l } = tr(i), c = t ? Do : e ? Is : Tt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && gt(/* @__PURE__ */ Be(r), "iterate", Us), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ Be(o), a = /* @__PURE__ */ Be(r);
      return e || (Ht(r, a) && gt(i, "has", r), gt(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ Be(a), c = t ? Do : e ? Is : Tt;
      return !e && gt(l, "iterate", Us), a.forEach((u, d) => r.call(o, c(u), c(d), i));
    }
  };
  return ht(
    s,
    e ? {
      add: sr("add"),
      set: sr("set"),
      delete: sr("delete"),
      clear: sr("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ Be(this), i = tr(o), a = /* @__PURE__ */ Be(r), l = !t && !/* @__PURE__ */ Et(r) && !/* @__PURE__ */ Xt(r) ? a : r;
        return i.has.call(o, l) || Ht(r, l) && i.has.call(o, r) || Ht(a, l) && i.has.call(o, a) || (o.add(l), is(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ Et(o) && !/* @__PURE__ */ Xt(o) && (o = /* @__PURE__ */ Be(o));
        const i = /* @__PURE__ */ Be(this), { has: a, get: l } = tr(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ Be(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? Ht(o, u) && is(i, "set", r, o) : is(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ Be(this), { has: i, get: a } = tr(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ Be(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && is(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ Be(this), o = r.size !== 0, i = r.clear();
        return o && is(
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
    s[r] = ld(r, e, t);
  }), s;
}
function wi(e, t) {
  const s = cd(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    qe(s, r) && r in n ? s : n,
    r,
    o
  );
}
const ud = {
  get: /* @__PURE__ */ wi(!1, !1)
}, dd = {
  get: /* @__PURE__ */ wi(!1, !0)
}, fd = {
  get: /* @__PURE__ */ wi(!0, !1)
};
const Hl = /* @__PURE__ */ new WeakMap(), ql = /* @__PURE__ */ new WeakMap(), Zl = /* @__PURE__ */ new WeakMap(), md = /* @__PURE__ */ new WeakMap();
function pd(e) {
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
function Kn(e) {
  return /* @__PURE__ */ Xt(e) ? e : _i(
    e,
    !1,
    od,
    ud,
    Hl
  );
}
// @__NO_SIDE_EFFECTS__
function Kl(e) {
  return _i(
    e,
    !1,
    ad,
    dd,
    ql
  );
}
// @__NO_SIDE_EFFECTS__
function Lo(e) {
  return _i(
    e,
    !0,
    id,
    fd,
    Zl
  );
}
function _i(e, t, s, n, r) {
  if (!Ke(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = pd(Uu(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? n : s
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Kt(e) {
  return /* @__PURE__ */ Xt(e) ? /* @__PURE__ */ Kt(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function Xt(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function Et(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function Br(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function Be(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ Be(t) : e;
}
function xi(e) {
  return !qe(e, "__v_skip") && Object.isExtensible(e) && Rl(e, "__v_skip", !0), e;
}
const Tt = (e) => Ke(e) ? /* @__PURE__ */ Kn(e) : e, Is = (e) => Ke(e) ? /* @__PURE__ */ Lo(e) : e;
// @__NO_SIDE_EFFECTS__
function lt(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function R(e) {
  return Jl(e, !1);
}
// @__NO_SIDE_EFFECTS__
function On(e) {
  return Jl(e, !0);
}
function Jl(e, t) {
  return /* @__PURE__ */ lt(e) ? e : new hd(e, t);
}
class hd {
  constructor(t, s) {
    this.dep = new bi(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ Be(t), this._value = s ? t : Tt(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ Et(t) || /* @__PURE__ */ Xt(t);
    t = n ? t : /* @__PURE__ */ Be(t), Ht(t, s) && (this._rawValue = t, this._value = n ? t : Tt(t), this.dep.trigger());
  }
}
function g(e) {
  return /* @__PURE__ */ lt(e) ? e.value : e;
}
function Xs(e) {
  return Pe(e) ? e() : g(e);
}
const gd = {
  get: (e, t, s) => t === "__v_raw" ? e : g(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ lt(r) && !/* @__PURE__ */ lt(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function Ql(e) {
  return /* @__PURE__ */ Kt(e) ? e : new Proxy(e, gd);
}
// @__NO_SIDE_EFFECTS__
function vd(e) {
  const t = Se(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = bd(e, s);
  return t;
}
class yd {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = $t(s) ? s : String(s), this._raw = /* @__PURE__ */ Be(t);
    let r = !0, o = t;
    if (!Se(t) || $t(this._key) || !Dr(this._key))
      do
        r = !/* @__PURE__ */ Br(o) || /* @__PURE__ */ Et(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = g(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ lt(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ lt(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return ed(this._raw, this._key);
  }
}
function bd(e, t, s) {
  return new yd(e, t, s);
}
class wd {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new bi(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = zn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    st !== this)
      return zl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return Ll(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function _d(e, t, s = !1) {
  let n, r;
  return Pe(e) ? n = e : (n = e.get, r = e.set), new wd(n, r, s);
}
const nr = {}, yr = /* @__PURE__ */ new WeakMap();
let js;
function xd(e, t = !1, s = js) {
  if (s) {
    let n = yr.get(s);
    n || yr.set(s, n = []), n.push(e);
  }
}
function kd(e, t, s = Ye) {
  const { immediate: n, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = s, c = (J) => r ? J : /* @__PURE__ */ Et(J) || r === !1 || r === 0 ? as(J, 1) : as(J);
  let u, d, h, m, _ = !1, S = !1;
  if (/* @__PURE__ */ lt(e) ? (d = () => e.value, _ = /* @__PURE__ */ Et(e)) : /* @__PURE__ */ Kt(e) ? (d = () => c(e), _ = !0) : Se(e) ? (S = !0, _ = e.some((J) => /* @__PURE__ */ Kt(J) || /* @__PURE__ */ Et(J)), d = () => e.map((J) => {
    if (/* @__PURE__ */ lt(J))
      return J.value;
    if (/* @__PURE__ */ Kt(J))
      return c(J);
    if (Pe(J))
      return l ? l(J, 2) : J();
  })) : Pe(e) ? t ? d = l ? () => l(e, 2) : e : d = () => {
    if (h) {
      Qt();
      try {
        h();
      } finally {
        Yt();
      }
    }
    const J = js;
    js = u;
    try {
      return l ? l(e, 3, [m]) : e(m);
    } finally {
      js = J;
    }
  } : d = Zt, t && r) {
    const J = d, ce = r === !0 ? 1 / 0 : r;
    d = () => as(J(), ce);
  }
  const b = hi(), A = () => {
    u.stop(), b && b.active && fi(b.effects, u);
  };
  if (o && t) {
    const J = t;
    t = (...ce) => {
      try {
        return J(...ce);
      } finally {
        A();
      }
    };
  }
  let M = S ? new Array(e.length).fill(nr) : nr;
  const Y = (J) => {
    if (!(!(u.flags & 1) || !u.dirty && !J))
      if (t) {
        const ce = u.run();
        if (J || r || _ || (S ? ce.some((Ae, re) => Ht(Ae, M[re])) : Ht(ce, M))) {
          const Ae = js;
          Qt();
          try {
            h && h(), js = u;
            const re = [
              ce,
              // pass undefined as the old value when it's changed for the first time
              M === nr ? void 0 : S && M[0] === nr ? [] : M,
              m
            ];
            M = ce, l ? l(t, 3, re) : (
              // @ts-expect-error
              t(...re)
            );
          } finally {
            js = Ae, Yt();
          }
        }
      } else
        u.run();
  };
  return a && a(Y), u = new Nl(d), u.scheduler = i ? () => i(Y, !1) : Y, m = (J) => xd(J, !1, u), h = u.onStop = () => {
    const J = yr.get(u);
    if (J) {
      if (l)
        l(J, 4);
      else
        for (const ce of J) ce();
      yr.delete(u);
    }
  }, t ? n ? Y(!0) : M = u.run() : i ? i(Y.bind(null, !0), !0) : u.run(), A.pause = u.pause.bind(u), A.resume = u.resume.bind(u), A.stop = A, A;
}
function as(e, t = 1 / 0, s) {
  if (t <= 0 || !Ke(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ lt(e))
    as(e.value, t, s);
  else if (Se(e))
    for (let n = 0; n < e.length; n++)
      as(e[n], t, s);
  else if (ds(e) || Cs(e))
    e.forEach((n) => {
      as(n, t, s);
    });
  else if (Al(e)) {
    for (const n in e)
      as(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && as(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function Jn(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (r) {
    Gr(r, t, s);
  }
}
function Dt(e, t, s, n) {
  if (Pe(e)) {
    const r = Jn(e, t, s, n);
    return r && Sl(r) && r.catch((o) => {
      Gr(o, t, s);
    }), r;
  }
  if (Se(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(Dt(e[o], t, s, n));
    return r;
  }
}
function Gr(e, t, s, n = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || Ye;
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
      Qt(), Jn(o, null, 10, [
        e,
        l,
        c
      ]), Yt();
      return;
    }
  }
  Sd(e, s, r, n, i);
}
function Sd(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const _t = [];
let zt = -1;
const Bt = [];
let _s = null, Ks = 0;
const Yl = /* @__PURE__ */ Promise.resolve();
let br = null;
function Hr(e) {
  const t = br || Yl;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function Cd(e) {
  let t = zt + 1, s = _t.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = _t[n], o = Dn(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function ki(e) {
  if (!(e.flags & 1)) {
    const t = Dn(e), s = _t[_t.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= Dn(s) ? _t.push(e) : _t.splice(Cd(t), 0, e), e.flags |= 1, Xl();
  }
}
function Xl() {
  br || (br = Yl.then(sc));
}
function Ad(e) {
  if (!Se(e))
    _s && e.id === -1 ? _s.splice(Ks + 1, 0, e) : e.flags & 1 || (Bt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Bt.push(e[t]);
  Xl();
}
function ec(e, t, s, n = zt + 1) {
  for (; n < _t.length; n++) {
    const r = _t[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      _t.splice(n, 1), n = e ? n - 1 : zt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function tc(e, t, s = 0) {
  if (Bt.length) {
    let n = Bt, r = 0;
    if (t) {
      n = [];
      for (let i = 0; i < Bt.length; i++) {
        const a = Bt[i];
        (a.i !== void 0 ? !a.i || a.i.uid < s : t.has(a)) ? Bt[r++] = a : n.push(a);
      }
    }
    const o = [...new Set(n)].sort((i, a) => Dn(i) - Dn(a));
    if (Bt.length = r, _s) {
      for (let i = 0; i < o.length; i++)
        _s.push(o[i]);
      return;
    }
    for (_s = o, Ks = 0; Ks < _s.length; Ks++) {
      const i = _s[Ks];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    _s = null, Ks = 0;
  }
}
let uo = !1;
function Rd(e, t) {
  if (uo) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Bt);
  e(), uo = !0;
  try {
    ec(void 0, t), tc(void 0, s, t);
  } finally {
    uo = !1;
  }
}
const Dn = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function sc(e) {
  try {
    for (zt = 0; zt < _t.length; zt++) {
      const t = _t[zt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), Jn(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; zt < _t.length; zt++) {
      const t = _t[zt];
      t && (t.flags &= -2);
    }
    zt = -1, _t.length = 0, tc(), br = null, (_t.length || Bt.length) && sc();
  }
}
let pt = null, nc = null;
function wr(e) {
  const t = pt;
  return pt = e, nc = e && e.type.__scopeId || null, t;
}
function W(e, t = pt, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && Sr(-1);
    const o = wr(t), i = us.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = us.length; l > i; l--) Oi();
      wr(o), n._d && Sr(1);
    }
    return a;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Ve(e, t) {
  if (pt === null)
    return e;
  const s = Yr(pt), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = Ye] = t[r];
    o && (Pe(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && as(i), n.push({
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
function Ps(e, t, s, n) {
  const r = e.dirs, o = t && t.dirs;
  for (let i = 0; i < r.length; i++) {
    const a = r[i];
    o && (a.oldValue = o[i].value);
    let l = a.dir[n];
    l && (Qt(), Dt(l, s, 8, [
      e.el,
      a,
      e,
      t
    ]), Yt());
  }
}
function hr(e, t) {
  if (vt) {
    let s = vt.provides;
    const n = vt.parent && vt.parent.provides;
    n === s && (s = vt.provides = Object.create(n)), s[e] = t;
  }
}
function At(e, t, s = !1) {
  const n = Qr();
  if (n || Fs) {
    let r = Fs ? Fs._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && Pe(t) ? t.call(n && n.proxy) : t;
  }
}
function Si() {
  return !!(Qr() || Fs);
}
const Id = /* @__PURE__ */ Symbol.for("v-scx"), Ed = () => At(Id);
function $d(e, t) {
  return Ci(e, null, t);
}
function As(e, t, s) {
  return Ci(e, t, s);
}
function Ci(e, t, s = Ye) {
  const { immediate: n, deep: r, flush: o, once: i } = s, a = ht({}, s), l = t && n || !t && o !== "post";
  let c;
  if (Un) {
    if (o === "sync") {
      const m = Ed();
      c = m.__watcherHandles || (m.__watcherHandles = []);
    } else if (!l) {
      const m = () => {
      };
      return m.stop = Zt, m.resume = Zt, m.pause = Zt, m;
    }
  }
  const u = vt;
  a.call = (m, _, S) => Dt(m, u, _, S);
  let d = !1;
  o === "post" ? a.scheduler = (m) => {
    m.i = u, bt(m, u && u.suspense);
  } : o !== "sync" && (d = !0, a.scheduler = (m, _) => {
    _ ? m() : ki(m);
  }), a.augmentJob = (m) => {
    t && (m.flags |= 4), d && (m.flags |= 2, u && (m.id = u.uid, m.i = u));
  };
  const h = kd(e, t, a);
  return Un && (c ? c.push(h) : l && h()), h;
}
function Od(e, t, s) {
  const n = this.proxy, r = ot(e) ? e.includes(".") ? rc(n, e) : () => n[e] : e.bind(n, n);
  let o;
  Pe(t) ? o = t : (o = t.handler, s = t);
  const i = Qn(this), a = Ci(r, o.bind(n), s);
  return i(), a;
}
function rc(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const ys = /* @__PURE__ */ new WeakMap(), oc = /* @__PURE__ */ Symbol("_vte"), qr = (e) => e.__isTeleport, Ds = (e) => e && (e.disabled || e.disabled === ""), Td = (e) => e && (e.defer || e.defer === ""), Ki = (e) => typeof SVGElement < "u" && e instanceof SVGElement, Ji = (e) => typeof MathMLElement == "function" && e instanceof MathMLElement, Vo = (e, t) => {
  const s = e && e.to;
  return ot(s) ? t ? t(s) : null : s;
}, Pd = {
  name: "Teleport",
  __isTeleport: !0,
  process(e, t, s, n, r, o, i, a, l, c) {
    const {
      mc: u,
      pc: d,
      pbc: h,
      o: { insert: m, querySelector: _, createText: S, createComment: b, parentNode: A }
    } = c, M = Ds(t.props);
    let { dynamicChildren: Y } = t;
    const J = (re, U, q) => {
      re.shapeFlag & 16 && u(
        re.children,
        U,
        q,
        r,
        o,
        i,
        a,
        l
      );
    }, ce = (re = t) => {
      const U = Ds(re.props), q = re.target = Vo(re.props, _), x = Uo(q, re, S, m);
      q && (i !== "svg" && Ki(q) ? i = "svg" : i !== "mathml" && Ji(q) && (i = "mathml"), r && r.isCE && (r.ce._teleportTargets || (r.ce._teleportTargets = /* @__PURE__ */ new Set())).add(q), U || (J(re, q, x), xn(re, !1)));
    }, Ae = (re) => {
      const U = () => {
        if (ys.get(re) === U) {
          if (ys.delete(re), Ds(re.props)) {
            const q = A(re.el) || s;
            J(re, q, re.anchor), xn(re, !0);
          }
          ce(re);
        }
      };
      ys.set(re, U), bt(U, o);
    };
    if (e == null) {
      const re = t.el = S(""), U = t.anchor = S("");
      if (m(re, s, n), m(U, s, n), Td(t.props) || o && o.pendingBranch) {
        Ae(t);
        return;
      }
      M && (J(t, s, U), xn(t, !0)), ce();
    } else {
      t.el = e.el;
      const re = t.anchor = e.anchor, U = ys.get(e);
      if (U) {
        U.flags |= 8, ys.delete(e), Ae(t);
        return;
      }
      t.targetStart = e.targetStart;
      const q = t.target = e.target, x = t.targetAnchor = e.targetAnchor, Q = Ds(e.props), xe = Q ? s : q, C = Q ? re : x;
      if (i === "svg" || Ki(q) ? i = "svg" : (i === "mathml" || Ji(q)) && (i = "mathml"), Y ? (h(
        e.dynamicChildren,
        Y,
        xe,
        r,
        o,
        i,
        a
      ), $i(e, t, !0)) : l || d(
        e,
        t,
        xe,
        C,
        r,
        o,
        i,
        a,
        !1
      ), M)
        Q ? t.props && e.props && t.props.to !== e.props.to && (t.props.to = e.props.to) : rr(
          t,
          s,
          re,
          c,
          1
        );
      else if ((t.props && t.props.to) !== (e.props && e.props.to)) {
        const te = Vo(t.props, _);
        te && (t.target = te, rr(
          t,
          te,
          null,
          c,
          0
        ));
      } else Q && rr(
        t,
        q,
        x,
        c,
        1
      );
      xn(t, M);
    }
  },
  remove(e, t, s, { um: n, o: { remove: r } }, o) {
    const {
      shapeFlag: i,
      children: a,
      anchor: l,
      targetStart: c,
      targetAnchor: u,
      target: d,
      props: h
    } = e, m = Ds(h), _ = o || !m, S = ys.get(e);
    if (S && (S.flags |= 8, ys.delete(e)), d && (r(c), r(u)), o && r(l), !S && (m || d) && i & 16)
      for (let b = 0; b < a.length; b++) {
        const A = a[b];
        n(
          A,
          t,
          s,
          _,
          !!A.dynamicChildren
        );
      }
  },
  move: rr,
  hydrate: Nd
};
function rr(e, t, s, { o: { insert: n }, m: r }, o = 2) {
  o === 0 && (e.targetStart && n(e.targetStart, t, s), n(e.targetAnchor, t, s), s = e.targetAnchor);
  const { el: i, anchor: a, shapeFlag: l, children: c, props: u } = e, d = o === 2;
  if (d && n(i, t, s), !ys.has(e) && (!d || Ds(u)) && l & 16)
    for (let h = 0; h < c.length; h++)
      r(
        c[h],
        t,
        s,
        2
      );
  d && n(a, t, s);
}
function Nd(e, t, s, n, r, o, {
  o: { nextSibling: i, parentNode: a, querySelector: l, insert: c, createText: u }
}, d) {
  function h(b, A) {
    let M = A;
    for (; M; ) {
      if (M && M.nodeType === 8) {
        if (M.data === "teleport start anchor")
          t.targetStart = M;
        else if (M.data === "teleport anchor") {
          t.targetAnchor = M, b._lpa = t.targetAnchor && i(t.targetAnchor);
          break;
        }
      }
      M = i(M);
    }
  }
  function m(b, A) {
    A.anchor = d(
      i(b),
      A,
      a(b),
      s,
      n,
      r,
      o
    );
  }
  const _ = t.target = Vo(
    t.props,
    l
  ), S = Ds(t.props);
  if (_) {
    const b = _._lpa || _.firstChild;
    t.shapeFlag & 16 && (S ? (m(e, t), h(_, b), t.targetAnchor || Uo(
      _,
      t,
      u,
      c,
      // if target is the same as the main view, insert anchors before current node
      // to avoid hydrating mismatch
      a(e) === _ ? e : null
    )) : (t.anchor = i(e), h(_, b), t.targetAnchor || Uo(_, t, u, c), d(
      b && i(b),
      t,
      _,
      s,
      n,
      r,
      o
    ))), xn(t, S);
  } else S && t.shapeFlag & 16 && (m(e, t), t.targetStart = e, t.targetAnchor = i(e));
  return t.anchor && i(t.anchor);
}
const Md = Pd;
function xn(e, t) {
  const s = e.ctx;
  if (s && s.ut) {
    let n, r;
    for (t ? (n = e.el, r = e.anchor) : (n = e.targetStart, r = e.targetAnchor); n && n !== r; )
      n.nodeType === 1 && n.setAttribute("data-v-owner", s.uid), n = n.nextSibling;
    s.ut();
  }
}
function Uo(e, t, s, n, r = null) {
  const o = t.targetStart = s(""), i = t.targetAnchor = s("");
  return o[oc] = i, e && (n(o, e, r), n(i, e, r)), i;
}
const fo = /* @__PURE__ */ Symbol("_leaveCb");
function zd(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const s of e)
      if (s.type !== Pt) {
        t = s;
        break;
      }
  }
  return t;
}
function ic(e) {
  if (!Ai(e))
    return qr(e.type) && e.children ? zd(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && Pe(s.default))
      return s.default();
  }
}
function _r(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    _r(
      qr(s.type) && ic(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === Ee && Se(e.children)) {
    const s = gc(e.children, !1);
    s && _r(s, t);
  }
}
function Fo(e) {
  if (e.component)
    return Fo(e.component.subTree);
  if (e.type === Ee) {
    const t = Se(e.children) && gc(e.children, !1);
    return t ? Fo(t) : void 0;
  }
  if (e.type !== Pt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function Ct(e, t) {
  return Pe(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    ht({ name: e.name }, t, { setup: e })
  ) : e;
}
function ac(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function Qi(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const xr = /* @__PURE__ */ new WeakMap();
function Tn(e, t, s, n, r = !1) {
  if (Se(e)) {
    e.forEach(
      (S, b) => Tn(
        S,
        t && (Se(t) ? t[b] : t),
        s,
        n,
        r
      )
    );
    return;
  }
  if (en(n) && !r) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && Tn(e, t, s, n.component.subTree);
    return;
  }
  const o = n.shapeFlag & 4 ? Yr(n.component) : n.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === Ye ? a.refs = {} : a.refs, d = a.setupState, h = /* @__PURE__ */ Be(d), m = d === Ye ? kl : (S) => Qi(u, S) ? !1 : qe(h, S), _ = (S, b) => !(b && Qi(u, b));
  if (c != null && c !== l) {
    if (Yi(t), ot(c))
      u[c] = null, m(c) && (d[c] = null);
    else if (/* @__PURE__ */ lt(c)) {
      const S = t;
      _(c, S.k) && (c.value = null), S.k && (u[S.k] = null);
    }
  }
  if (Pe(l))
    Jn(l, a, 12, [i, u]);
  else {
    const S = ot(l), b = /* @__PURE__ */ lt(l);
    if (S || b) {
      const A = () => {
        if (e.f) {
          const M = S ? m(l) ? d[l] : u[l] : _() || !e.k ? l.value : u[e.k];
          if (r)
            Se(M) && fi(M, o);
          else if (Se(M))
            M.includes(o) || M.push(o);
          else if (S)
            u[l] = [o], m(l) && (d[l] = u[l]);
          else {
            const Y = [o];
            _(l, e.k) && (l.value = Y), e.k && (u[e.k] = Y);
          }
        } else S ? (u[l] = i, m(l) && (d[l] = i)) : b && (_(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const M = () => {
          A(), xr.delete(e);
        };
        M.id = -1, xr.set(e, M), bt(M, s);
      } else
        Yi(e), A();
    }
  }
}
function Yi(e) {
  const t = xr.get(e);
  t && (t.flags |= 8, xr.delete(e));
}
Fr().requestIdleCallback;
Fr().cancelIdleCallback;
const en = (e) => !!e.type.__asyncLoader, Ai = (e) => e.type.__isKeepAlive;
function jd(e, t) {
  lc(e, "a", t);
}
function Dd(e, t) {
  lc(e, "da", t);
}
function lc(e, t, s = vt) {
  const n = e.__wdc || (e.__wdc = () => {
    let r = s;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (Zr(t, n, s), s) {
    let r = s.parent;
    for (; r && r.parent; )
      Ai(r.parent.vnode) && Ld(n, t, s, r), r = r.parent;
  }
}
function Ld(e, t, s, n) {
  const r = Zr(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  Ri(() => {
    fi(n[t], r);
  }, s);
}
function Zr(e, t, s = vt, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Qt();
      const a = Qn(s), l = Dt(t, s, e, i);
      return a(), Yt(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const ps = (e) => (t, s = vt) => {
  (!Un || e === "sp") && Zr(e, (...n) => t(...n), s);
}, Vd = ps("bm"), hs = ps("m"), Ud = ps(
  "bu"
), Fd = ps("u"), Wd = ps(
  "bum"
), Ri = ps("um"), Bd = ps(
  "sp"
), Gd = ps("rtg"), Hd = ps("rtc");
function qd(e, t = vt) {
  Zr("ec", e, t);
}
const Zd = "components", cc = /* @__PURE__ */ Symbol.for("v-ndc");
function Kd(e) {
  return ot(e) ? Jd(Zd, e, !1) || e : e || cc;
}
function Jd(e, t, s = !0, n = !1) {
  const r = pt || vt;
  if (r) {
    const o = r.type;
    {
      const a = Nf(
        o,
        !1
      );
      if (a && (a === t || a === xt(t) || a === Vr(xt(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      Xi(r[e] || o[e], t) || // global registration
      Xi(r.appContext[e], t)
    );
    return !i && n ? o : i;
  }
}
function Xi(e, t) {
  return e && (e[t] || e[xt(t)] || e[Vr(xt(t))]);
}
function et(e, t, s, n) {
  let r;
  const o = s, i = Se(e);
  if (i || ot(e)) {
    const a = i && /* @__PURE__ */ Kt(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ Et(e), c = /* @__PURE__ */ Xt(e), e = Wr(e)), r = new Array(e.length);
    for (let u = 0, d = e.length; u < d; u++)
      r[u] = t(
        l ? c ? Is(Tt(e[u])) : Tt(e[u]) : e[u],
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
  else if (Ke(e))
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
function uc(e, t, s, n, r, o) {
  if (s == null && (s = {}), pt.ce || pt.parent && en(pt.parent) && pt.parent.ce) {
    const c = s, u = Object.keys(c).length > 0;
    return $(), Ze(
      Ee,
      null,
      [V("slot", c, n)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = us.length;
  $();
  let l;
  try {
    const c = i && dc(i(s)), u = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = Ze(
      Ee,
      {
        key: (u && !$t(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = us.length; u > a; u--) Oi();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function dc(e) {
  return e.some((t) => sn(t) ? !(t.type === Pt || t.type === Ee && !dc(t.children)) : !0) ? e : null;
}
const Wo = (e) => e ? Oc(e) ? Yr(e) : Wo(e.parent) : null, Pn = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ ht(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => Wo(e.parent),
    $root: (e) => Wo(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => mc(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      ki(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = Hr.bind(e.proxy)),
    $watch: (e) => Od.bind(e)
  })
), mo = (e, t) => e !== Ye && !e.__isScriptSetup && qe(e, t), Qd = {
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
        if (mo(n, t))
          return i[t] = 1, n[t];
        if (r !== Ye && qe(r, t))
          return i[t] = 2, r[t];
        if (qe(o, t))
          return i[t] = 3, o[t];
        if (s !== Ye && qe(s, t))
          return i[t] = 4, s[t];
        Bo && (i[t] = 0);
      }
    }
    const c = Pn[t];
    let u, d;
    if (c)
      return t === "$attrs" && gt(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (u = a.__cssModules) && (u = u[t])
    )
      return u;
    if (s !== Ye && qe(s, t))
      return i[t] = 4, s[t];
    if (
      // global properties
      d = l.config.globalProperties, qe(d, t)
    )
      return d[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: r, ctx: o } = e;
    return mo(r, t) ? (r[t] = s, !0) : n !== Ye && qe(n, t) ? (n[t] = s, !0) : qe(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(s[a] || e !== Ye && a[0] !== "$" && qe(e, a) || mo(t, a) || qe(o, a) || qe(n, a) || qe(Pn, a) || qe(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : qe(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function ea(e) {
  return Se(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let Bo = !0;
function Yd(e) {
  const t = mc(e), s = e.proxy, n = e.ctx;
  Bo = !1, t.beforeCreate && ta(t.beforeCreate, e, "bc");
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
    beforeUpdate: m,
    updated: _,
    activated: S,
    deactivated: b,
    beforeDestroy: A,
    beforeUnmount: M,
    destroyed: Y,
    unmounted: J,
    render: ce,
    renderTracked: Ae,
    renderTriggered: re,
    errorCaptured: U,
    serverPrefetch: q,
    // public API
    expose: x,
    inheritAttrs: Q,
    // assets
    components: xe,
    directives: C,
    filters: te
  } = t;
  if (c && Xd(c, n, null), i)
    for (const pe in i) {
      const Ce = i[pe];
      Pe(Ce) && (n[pe] = Ce.bind(s));
    }
  if (r) {
    const pe = r.call(s, s);
    Ke(pe) && (e.data = /* @__PURE__ */ Kn(pe));
  }
  if (Bo = !0, o)
    for (const pe in o) {
      const Ce = o[pe], ze = Pe(Ce) ? Ce.bind(s, s) : Pe(Ce.get) ? Ce.get.bind(s, s) : Zt, oe = !Pe(Ce) && Pe(Ce.set) ? Ce.set.bind(s) : Zt, tt = Ue({
        get: ze,
        set: oe
      });
      Object.defineProperty(n, pe, {
        enumerable: !0,
        configurable: !0,
        get: () => tt.value,
        set: (Je) => tt.value = Je
      });
    }
  if (a)
    for (const pe in a)
      fc(a[pe], n, s, pe);
  if (l) {
    const pe = Pe(l) ? l.call(s) : l;
    Reflect.ownKeys(pe).forEach((Ce) => {
      hr(Ce, pe[Ce]);
    });
  }
  u && ta(u, e, "c");
  function ke(pe, Ce) {
    Se(Ce) ? Ce.forEach((ze) => pe(ze.bind(s))) : Ce && pe(Ce.bind(s));
  }
  if (ke(Vd, d), ke(hs, h), ke(Ud, m), ke(Fd, _), ke(jd, S), ke(Dd, b), ke(qd, U), ke(Hd, Ae), ke(Gd, re), ke(Wd, M), ke(Ri, J), ke(Bd, q), Se(x))
    if (x.length) {
      const pe = e.exposed || (e.exposed = {});
      x.forEach((Ce) => {
        Object.defineProperty(pe, Ce, {
          get: () => s[Ce],
          set: (ze) => s[Ce] = ze,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  ce && e.render === Zt && (e.render = ce), Q != null && (e.inheritAttrs = Q), xe && (e.components = xe), C && (e.directives = C), q && ac(e);
}
function Xd(e, t, s = Zt) {
  Se(e) && (e = Go(e));
  for (const n in e) {
    const r = e[n];
    let o;
    Ke(r) ? "default" in r ? o = At(
      r.from || n,
      r.default,
      !0
    ) : o = At(r.from || n) : o = At(r), /* @__PURE__ */ lt(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[n] = o;
  }
}
function ta(e, t, s) {
  Dt(
    Se(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function fc(e, t, s, n) {
  let r = n.includes(".") ? rc(s, n) : () => s[n];
  if (ot(e)) {
    const o = t[e];
    Pe(o) && As(r, o);
  } else if (Pe(e))
    As(r, e.bind(s));
  else if (Ke(e))
    if (Se(e))
      e.forEach((o) => fc(o, t, s, n));
    else {
      const o = Pe(e.handler) ? e.handler.bind(s) : t[e.handler];
      Pe(o) && As(r, o, e);
    }
}
function mc(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !s && !n ? l = t : (l = {}, r.length && r.forEach(
    (c) => kr(l, c, i, !0)
  ), kr(l, t, i)), Ke(t) && o.set(t, l), l;
}
function kr(e, t, s, n = !1) {
  const { mixins: r, extends: o } = t;
  o && kr(e, o, s, !0), r && r.forEach(
    (i) => kr(e, i, s, !0)
  );
  for (const i in t)
    if (!(n && i === "expose")) {
      const a = ef[i] || s && s[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const ef = {
  data: sa,
  props: na,
  emits: na,
  // objects
  methods: kn,
  computed: kn,
  // lifecycle
  beforeCreate: yt,
  created: yt,
  beforeMount: yt,
  mounted: yt,
  beforeUpdate: yt,
  updated: yt,
  beforeDestroy: yt,
  beforeUnmount: yt,
  destroyed: yt,
  unmounted: yt,
  activated: yt,
  deactivated: yt,
  errorCaptured: yt,
  serverPrefetch: yt,
  // assets
  components: kn,
  directives: kn,
  // watch
  watch: sf,
  // provide / inject
  provide: sa,
  inject: tf
};
function sa(e, t) {
  return t ? e ? function() {
    return ht(
      Pe(e) ? e.call(this, this) : e,
      Pe(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function tf(e, t) {
  return kn(Go(e), Go(t));
}
function Go(e) {
  if (Se(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function yt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function kn(e, t) {
  return e ? ht(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function na(e, t) {
  return e ? Se(e) && Se(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : ht(
    /* @__PURE__ */ Object.create(null),
    ea(e),
    ea(t ?? {})
  ) : t;
}
function sf(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = ht(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = yt(e[n], t[n]);
  return s;
}
function pc() {
  return {
    app: null,
    config: {
      isNativeTag: kl,
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
let nf = 0;
function rf(e, t) {
  return function(n, r = null) {
    Pe(n) || (n = ht({}, n)), r != null && !Ke(r) && (r = null);
    const o = pc(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: nf++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: zf,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...d) {
        return i.has(u) || (u && Pe(u.install) ? (i.add(u), u.install(c, ...d)) : Pe(u) && (i.add(u), u(c, ...d))), c;
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
          const m = c._ceVNode || V(n, r);
          return m.appContext = o, h === !0 ? h = "svg" : h === !1 && (h = void 0), e(m, u, h), l = !0, c._container = u, u.__vue_app__ = c, Yr(m.component);
        }
      },
      onUnmount(u) {
        a.push(u);
      },
      unmount() {
        l && (Dt(
          a,
          c._instance,
          16
        ), e(null, c._container), delete c._container.__vue_app__);
      },
      provide(u, d) {
        return o.provides[u] = d, c;
      },
      runWithContext(u) {
        const d = Fs;
        Fs = c;
        try {
          return u();
        } finally {
          Fs = d;
        }
      }
    };
    return c;
  };
}
let Fs = null;
const of = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${xt(t)}Modifiers`] || e[`${Os(t)}Modifiers`];
function af(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || Ye;
  let r = s;
  const o = t.startsWith("update:"), i = o && of(n, t.slice(7));
  i && (i.trim && (r = s.map((u) => ot(u) ? u.trim() : u)), i.number && (r = r.map(Ur)));
  let a, l = n[a = oo(t)] || // also try camelCase event handler (#2249)
  n[a = oo(xt(t))];
  !l && o && (l = n[a = oo(Os(t))]), l && Dt(
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
    e.emitted[a] = !0, Dt(
      c,
      e,
      6,
      r
    );
  }
}
const lf = /* @__PURE__ */ new WeakMap();
function hc(e, t, s = !1) {
  const n = s ? lf : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!Pe(e)) {
    const l = (c) => {
      const u = hc(c, t, !0);
      u && (a = !0, ht(i, u));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (Ke(e) && n.set(e, null), null) : (Se(o) ? o.forEach((l) => i[l] = null) : ht(i, o), Ke(e) && n.set(e, i), i);
}
function Kr(e, t) {
  return !e || !zr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), qe(e, t[0].toLowerCase() + t.slice(1)) || qe(e, Os(t)) || qe(e, t));
}
function ra(e) {
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
    setupState: m,
    ctx: _,
    inheritAttrs: S
  } = e, b = wr(e);
  let A, M;
  try {
    if (s.shapeFlag & 4) {
      const J = r || n, ce = J;
      A = Gt(
        c.call(
          ce,
          J,
          u,
          d,
          m,
          h,
          _
        )
      ), M = a;
    } else {
      const J = t;
      A = Gt(
        J.length > 1 ? J(
          d,
          { attrs: a, slots: i, emit: l }
        ) : J(
          d,
          null
        )
      ), M = t.props ? a : cf(a);
    }
  } catch (J) {
    us.length = 0, Gr(J, e, 1), A = V(Pt);
  }
  let Y = A;
  if (M && S !== !1) {
    const J = Object.keys(M), { shapeFlag: ce } = Y;
    J.length && ce & 7 && (o && J.some(jr) && (M = uf(
      M,
      o
    )), Y = nn(Y, M, !1, !0));
  }
  if (s.dirs && (Y = nn(Y, null, !1, !0), Y.dirs = Y.dirs ? Y.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const J = qr(Y.type) && ic(Y) || Y;
    _r(J, s.transition);
  }
  return A = Y, wr(b), A;
}
function gc(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const r = e[n];
    if (sn(r)) {
      if (r.type !== Pt || r.children === "v-if") {
        if (s)
          return;
        s = r;
      }
    } else
      return;
  }
  return s;
}
const cf = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || zr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, uf = (e, t) => {
  const s = {};
  for (const n in e)
    (!jr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function df(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? oa(n, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let d = 0; d < u.length; d++) {
        const h = u[d];
        if (vc(i, n, h) && !Kr(c, h))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : n === i ? !1 : n ? i ? oa(n, i, c) : !0 : !!i;
  return !1;
}
function oa(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!qe(e, o) || vc(t, e, o) && !Kr(s, o))
      return !0;
  }
  return !1;
}
function vc(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && Ke(n) && Ke(r) ? !fs(n, r) : n !== r;
}
function ff({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const yc = {}, bc = () => Object.create(yc), wc = (e) => Object.getPrototypeOf(e) === yc;
function mf(e, t, s, n = !1) {
  const r = {}, o = bc();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), _c(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ Kl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function pf(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ Be(r), [l] = e.propsOptions;
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
        if (Kr(e.emitsOptions, h))
          continue;
        const m = t[h];
        if (l)
          if (qe(o, h))
            m !== o[h] && (o[h] = m, c = !0);
          else {
            const _ = xt(h);
            r[_] = Ho(
              l,
              a,
              _,
              m,
              e,
              !1
            );
          }
        else
          m !== o[h] && (o[h] = m, c = !0);
      }
    }
  } else {
    _c(e, t, r, o) && (c = !0);
    let u;
    for (const d in a)
      (!t || // for camelCase
      !qe(t, d) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = Os(d)) === d || !qe(t, u))) && (l ? s && // for camelCase
      (s[d] !== void 0 || // for kebab-case
      s[u] !== void 0) && (r[d] = Ho(
        l,
        a,
        d,
        void 0,
        e,
        !0
      )) : delete r[d]);
    if (o !== a)
      for (const d in o)
        (!t || !qe(t, d)) && (delete o[d], c = !0);
  }
  c && is(e.attrs, "set", "");
}
function _c(e, t, s, n) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (In(l))
        continue;
      const c = t[l];
      let u;
      r && qe(r, u = xt(l)) ? !o || !o.includes(u) ? s[u] = c : (a || (a = {}))[u] = c : Kr(e.emitsOptions, l) || (!(l in n) || c !== n[l]) && (n[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ Be(s), c = a || Ye;
    for (let u = 0; u < o.length; u++) {
      const d = o[u];
      s[d] = Ho(
        r,
        l,
        d,
        c[d],
        e,
        !qe(c, d)
      );
    }
  }
  return i;
}
function Ho(e, t, s, n, r, o) {
  const i = e[s];
  if (i != null) {
    const a = qe(i, "default");
    if (a && n === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && Pe(l)) {
        const { propsDefaults: c } = r;
        if (s in c)
          n = c[s];
        else {
          const u = Qn(r);
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
    ] && (n === "" || n === Os(s)) && (n = !0));
  }
  return n;
}
const hf = /* @__PURE__ */ new WeakMap();
function xc(e, t, s = !1) {
  const n = s ? hf : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!Pe(e)) {
    const u = (d) => {
      l = !0;
      const [h, m] = xc(d, t, !0);
      ht(i, h), m && a.push(...m);
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return Ke(e) && n.set(e, Ls), Ls;
  if (Se(o))
    for (let u = 0; u < o.length; u++) {
      const d = xt(o[u]);
      ia(d) && (i[d] = Ye);
    }
  else if (o)
    for (const u in o) {
      const d = xt(u);
      if (ia(d)) {
        const h = o[u], m = i[d] = Se(h) || Pe(h) ? { type: h } : ht({}, h), _ = m.type;
        let S = !1, b = !0;
        if (Se(_))
          for (let A = 0; A < _.length; ++A) {
            const M = _[A], Y = Pe(M) && M.name;
            if (Y === "Boolean") {
              S = !0;
              break;
            } else Y === "String" && (b = !1);
          }
        else
          S = Pe(_) && _.name === "Boolean";
        m[
          0
          /* shouldCast */
        ] = S, m[
          1
          /* shouldCastTrue */
        ] = b, (S || qe(m, "default")) && a.push(d);
      }
    }
  const c = [i, a];
  return Ke(e) && n.set(e, c), c;
}
function ia(e) {
  return e[0] !== "$" && !In(e);
}
const Ii = (e) => e === "_" || e === "_ctx" || e === "$stable", Ei = (e) => Se(e) ? e.map(Gt) : [Gt(e)], gf = (e, t, s) => {
  if (t._n)
    return t;
  const n = W((...r) => Ei(t(...r)), s);
  return n._c = !1, n;
}, kc = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (Ii(r)) continue;
    const o = e[r];
    if (Pe(o))
      t[r] = gf(r, o, n);
    else if (o != null) {
      const i = Ei(o);
      t[r] = () => i;
    }
  }
}, Sc = (e, t) => {
  const s = Ei(t);
  e.slots.default = () => s;
}, Cc = (e, t, s) => {
  for (const n in t)
    (s || !Ii(n)) && (e[n] = t[n]);
}, vf = (e, t, s) => {
  const n = e.slots = bc();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (Cc(n, t, s), s && Rl(n, "_", r, !0)) : kc(t, n);
  } else t && Sc(e, t);
}, yf = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, i = Ye;
  if (n.shapeFlag & 32) {
    const a = t._;
    a ? s && a === 1 ? o = !1 : Cc(r, t, s) : (o = !t.$stable, kc(t, r)), i = t;
  } else t && (Sc(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !Ii(a) && i[a] == null && delete r[a];
}, bt = kf;
function bf(e) {
  return wf(e);
}
function wf(e, t) {
  const s = Fr();
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
    setScopeId: m = Zt,
    insertStaticContent: _
  } = e, S = (p, v, k, I = null, j = null, B = null, w = void 0, N = null, D = !!v.dynamicChildren) => {
    if (p === v)
      return;
    p && !hn(p, v) && (I = z(p), Je(p, j, B, !0), p = null), v.patchFlag === -2 && (D = !1, v.dynamicChildren = null), v.dynamicChildren && p && p.dynamicChildren && p.dynamicChildren.hasOnce && (v.dynamicChildren === Ls && (v.dynamicChildren = []), v.dynamicChildren.hasOnce = !0);
    const { type: F, ref: he, shapeFlag: ne } = v;
    switch (F) {
      case Jr:
        b(p, v, k, I);
        break;
      case Pt:
        A(p, v, k, I);
        break;
      case ho:
        p == null && M(v, k, I, w);
        break;
      case Ee:
        xe(
          p,
          v,
          k,
          I,
          j,
          B,
          w,
          N,
          D
        );
        break;
      default:
        ne & 1 ? ce(
          p,
          v,
          k,
          I,
          j,
          B,
          w,
          N,
          D
        ) : ne & 6 ? C(
          p,
          v,
          k,
          I,
          j,
          B,
          w,
          N,
          D
        ) : (ne & 64 || ne & 128) && F.process(
          p,
          v,
          k,
          I,
          j,
          B,
          w,
          N,
          D,
          P
        );
    }
    he != null && j ? Tn(he, p && p.ref, B, v || p, !v) : he == null && p && p.ref != null && Tn(p.ref, null, B, p, !0);
  }, b = (p, v, k, I) => {
    if (p == null)
      n(
        v.el = a(v.children),
        k,
        I
      );
    else {
      const j = v.el = p.el;
      v.children !== p.children && c(j, v.children);
    }
  }, A = (p, v, k, I) => {
    p == null ? n(
      v.el = l(v.children || ""),
      k,
      I
    ) : v.el = p.el;
  }, M = (p, v, k, I) => {
    [p.el, p.anchor] = _(
      p.children,
      v,
      k,
      I,
      p.el,
      p.anchor
    );
  }, Y = ({ el: p, anchor: v }, k, I) => {
    let j;
    for (; p && p !== v; )
      j = h(p), n(p, k, I), p = j;
    n(v, k, I);
  }, J = ({ el: p, anchor: v }) => {
    let k;
    for (; p && p !== v; )
      k = h(p), r(p), p = k;
    r(v);
  }, ce = (p, v, k, I, j, B, w, N, D) => {
    if (v.type === "svg" ? w = "svg" : v.type === "math" && (w = "mathml"), p == null)
      Ae(
        v,
        k,
        I,
        j,
        B,
        w,
        N,
        D
      );
    else {
      const F = p.el && p.el._isVueCE ? p.el : null;
      try {
        F && F._beginPatch(), q(
          p,
          v,
          j,
          B,
          w,
          N,
          D
        );
      } finally {
        F && F._endPatch();
      }
    }
  }, Ae = (p, v, k, I, j, B, w, N) => {
    let D, F;
    const { props: he, shapeFlag: ne, transition: _e, dirs: Re } = p;
    if (D = p.el = i(
      p.type,
      B,
      he && he.is,
      he
    ), ne & 8 ? u(D, p.children) : ne & 16 && U(
      p.children,
      D,
      null,
      I,
      j,
      po(p, B),
      w,
      N
    ), Re && Ps(p, null, I, "created"), re(D, p, p.scopeId, w, I), he) {
      for (const He in he)
        He !== "value" && !In(He) && o(D, He, null, he[He], B, I);
      "value" in he && o(D, "value", null, he.value, B), (F = he.onVnodeBeforeMount) && Ut(F, I, p);
    }
    Re && Ps(p, null, I, "beforeMount");
    const Le = _f(j, _e);
    Le && _e.beforeEnter(D), n(D, v, k), ((F = he && he.onVnodeMounted) || Le || Re) && bt(() => {
      try {
        F && Ut(F, I, p), Le && _e.enter(D), Re && Ps(p, null, I, "mounted");
      } finally {
      }
    }, j);
  }, re = (p, v, k, I, j) => {
    if (k && m(p, k), I)
      for (let B = 0; B < I.length; B++)
        m(p, I[B]);
    if (j) {
      let B = j.subTree;
      if (v === B || Rc(B.type) && (B.ssContent === v || B.ssFallback === v)) {
        const w = j.vnode;
        re(
          p,
          w,
          w.scopeId,
          w.slotScopeIds,
          j.parent
        );
      }
    }
  }, U = (p, v, k, I, j, B, w, N, D = 0) => {
    for (let F = D; F < p.length; F++) {
      const he = p[F] = N ? os(p[F]) : Gt(p[F]);
      S(
        null,
        he,
        v,
        k,
        I,
        j,
        B,
        w,
        N
      );
    }
  }, q = (p, v, k, I, j, B, w) => {
    const N = v.el = p.el;
    let { patchFlag: D, dynamicChildren: F, dirs: he } = v;
    D |= p.patchFlag & 16;
    const ne = p.props || Ye, _e = v.props || Ye;
    let Re;
    if (k && Ns(k, !1), (Re = _e.onVnodeBeforeUpdate) && Ut(Re, k, v, p), he && Ps(v, p, k, "beforeUpdate"), k && Ns(k, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    F && (!p.dynamicChildren || p.dynamicChildren.length !== F.length) && (D = 0, w = !1, F = null), (ne.innerHTML && _e.innerHTML == null || ne.textContent && _e.textContent == null) && u(N, ""), F ? x(
      p.dynamicChildren,
      F,
      N,
      k,
      I,
      po(v, j),
      B
    ) : w || Ce(
      p,
      v,
      N,
      null,
      k,
      I,
      po(v, j),
      B,
      !1
    ), D > 0) {
      if (D & 16)
        Q(N, ne, _e, k, j);
      else if (D & 2 && ne.class !== _e.class && o(N, "class", null, _e.class, j), D & 4 && o(N, "style", ne.style, _e.style, j), D & 8) {
        const Le = v.dynamicProps;
        for (let He = 0; He < Le.length; He++) {
          const Z = Le[He], le = ne[Z], ae = _e[Z];
          (ae !== le || Z === "value") && o(N, Z, le, ae, j, k);
        }
      }
      D & 1 && p.children !== v.children && u(N, v.children);
    } else !w && F == null && Q(N, ne, _e, k, j);
    ((Re = _e.onVnodeUpdated) || he) && bt(() => {
      Re && Ut(Re, k, v, p), he && Ps(v, p, k, "updated");
    }, I);
  }, x = (p, v, k, I, j, B, w) => {
    for (let N = 0; N < v.length; N++) {
      const D = p[N], F = v[N], he = D.el || qo(D), ne = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        he && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (D.type === Ee || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !hn(D, F) || // - In the case of a component, it could contain anything.
        D.shapeFlag & 198) ? d(he) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          k
        )
      );
      S(
        D,
        F,
        ne,
        null,
        I,
        j,
        B,
        w,
        !0
      );
    }
  }, Q = (p, v, k, I, j) => {
    if (v !== k) {
      if (v !== Ye)
        for (const B in v)
          !In(B) && !(B in k) && o(
            p,
            B,
            v[B],
            null,
            j,
            I
          );
      for (const B in k) {
        if (In(B)) continue;
        const w = k[B], N = v[B];
        w !== N && B !== "value" && o(p, B, N, w, j, I);
      }
      "value" in k && o(p, "value", v.value, k.value, j);
    }
  }, xe = (p, v, k, I, j, B, w, N, D) => {
    const F = v.el = p ? p.el : a(""), he = v.anchor = p ? p.anchor : a("");
    let { patchFlag: ne, dynamicChildren: _e, slotScopeIds: Re } = v;
    Re && (N = N ? N.concat(Re) : Re), p == null ? (n(F, k, I), n(he, k, I), U(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      v.children || [],
      k,
      he,
      j,
      B,
      w,
      N,
      D
    )) : ne > 0 && ne & 64 && _e && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    p.dynamicChildren && p.dynamicChildren.length === _e.length ? (x(
      p.dynamicChildren,
      _e,
      k,
      j,
      B,
      w,
      N
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (v.key != null || j && v === j.subTree) && $i(
      p,
      v,
      !0
      /* shallow */
    )) : Ce(
      p,
      v,
      k,
      he,
      j,
      B,
      w,
      N,
      D
    );
  }, C = (p, v, k, I, j, B, w, N, D) => {
    v.slotScopeIds = N, p == null ? v.shapeFlag & 512 ? j.ctx.activate(
      v,
      k,
      I,
      w,
      D
    ) : te(
      v,
      k,
      I,
      j,
      B,
      w,
      D
    ) : Ne(p, v, D);
  }, te = (p, v, k, I, j, B, w) => {
    const N = p.component = Ef(
      p,
      I,
      j
    );
    if (Ai(p) && (N.ctx.renderer = P), $f(N, !1, w), N.asyncDep) {
      if (j && j.registerDep(
        N,
        ke,
        w,
        B
      ), !p.el) {
        const D = N.subTree = V(Pt);
        A(null, D, v, k), p.placeholder = D.el;
      }
    } else
      ke(
        N,
        p,
        v,
        k,
        j,
        B,
        w
      );
  }, Ne = (p, v, k) => {
    const I = v.component = p.component;
    if (df(p, v, k))
      if (I.asyncDep && !I.asyncResolved) {
        v.el = p.el, v.placeholder = p.placeholder, pe(I, v, k);
        return;
      } else
        I.next = v, I.update();
    else
      v.el = p.el, v.placeholder = p.placeholder, I.vnode = v;
  }, ke = (p, v, k, I, j, B, w) => {
    const N = () => {
      if (p.isMounted) {
        let { next: ne, bu: _e, u: Re, parent: Le, vnode: He } = p;
        {
          const De = Ac(p);
          if (De) {
            ne && (ne.el = He.el, pe(p, ne, w)), De.asyncDep.then(() => {
              bt(() => {
                p.isUnmounted || F();
              }, j);
            });
            return;
          }
        }
        let Z = ne, le;
        Ns(p, !1), ne ? (ne.el = He.el, pe(p, ne, w)) : ne = He, _e && pr(_e), (le = ne.props && ne.props.onVnodeBeforeUpdate) && Ut(le, Le, ne, He), Ns(p, !0);
        const ae = ra(p), Oe = p.subTree;
        p.subTree = ae, S(
          Oe,
          ae,
          // parent may have changed if it's in a teleport
          d(Oe.el),
          // anchor may have changed if it's in a fragment
          z(Oe),
          p,
          j,
          B
        ), ne.el = ae.el, Z === null && ff(p, ae.el), Re && bt(Re, j), (le = ne.props && ne.props.onVnodeUpdated) && bt(
          () => Ut(le, Le, ne, He),
          j
        );
      } else {
        let ne;
        const { el: _e, props: Re } = v, { bm: Le, m: He, parent: Z, root: le, type: ae } = p, Oe = en(v);
        Ns(p, !1), Le && pr(Le), !Oe && (ne = Re && Re.onVnodeBeforeMount) && Ut(ne, Z, v), Ns(p, !0);
        {
          le.ce && le.ce._hasShadowRoot() && le.ce._injectChildStyle(
            ae,
            p.parent ? p.parent.type : void 0
          );
          const De = p.subTree = ra(p);
          S(
            null,
            De,
            k,
            I,
            p,
            j,
            B
          ), v.el = De.el;
        }
        if (He && bt(He, j), !Oe && (ne = Re && Re.onVnodeMounted)) {
          const De = v;
          bt(
            () => Ut(ne, Z, De),
            j
          );
        }
        (v.shapeFlag & 256 || Z && en(Z.vnode) && Z.vnode.shapeFlag & 256) && p.a && bt(p.a, j), p.isMounted = !0, v = k = I = null;
      }
    };
    p.scope.on();
    const D = p.effect = new Nl(N);
    p.scope.off();
    const F = p.update = D.run.bind(D), he = p.job = D.runIfDirty.bind(D);
    he.i = p, he.id = p.uid, D.scheduler = () => ki(he), Ns(p, !0), F();
  }, pe = (p, v, k) => {
    v.component = p;
    const I = p.vnode.props;
    p.vnode = v, p.next = null, pf(p, v.props, I, k), yf(p, v.children, k), Qt(), ec(p), Yt();
  }, Ce = (p, v, k, I, j, B, w, N, D = !1) => {
    const F = p && p.children, he = p ? p.shapeFlag : 0, ne = v.children, { patchFlag: _e, shapeFlag: Re } = v;
    if (_e > 0) {
      if (_e & 128) {
        oe(
          F,
          ne,
          k,
          I,
          j,
          B,
          w,
          N,
          D
        );
        return;
      } else if (_e & 256) {
        ze(
          F,
          ne,
          k,
          I,
          j,
          B,
          w,
          N,
          D
        );
        return;
      }
    }
    Re & 8 ? (he & 16 && ve(F, j, B), ne !== F && u(k, ne)) : he & 16 ? Re & 16 ? oe(
      F,
      ne,
      k,
      I,
      j,
      B,
      w,
      N,
      D
    ) : ve(F, j, B, !0) : (he & 8 && u(k, ""), Re & 16 && U(
      ne,
      k,
      I,
      j,
      B,
      w,
      N,
      D
    ));
  }, ze = (p, v, k, I, j, B, w, N, D) => {
    p = p || Ls, v = v || Ls;
    const F = p.length, he = v.length, ne = Math.min(F, he);
    let _e;
    for (_e = 0; _e < ne; _e++) {
      const Re = v[_e] = D ? os(v[_e]) : Gt(v[_e]);
      S(
        p[_e],
        Re,
        k,
        null,
        j,
        B,
        w,
        N,
        D
      );
    }
    F > he ? ve(
      p,
      j,
      B,
      !0,
      !1,
      ne
    ) : U(
      v,
      k,
      I,
      j,
      B,
      w,
      N,
      D,
      ne
    );
  }, oe = (p, v, k, I, j, B, w, N, D) => {
    let F = 0;
    const he = v.length;
    let ne = p.length - 1, _e = he - 1;
    for (; F <= ne && F <= _e; ) {
      const Re = p[F], Le = v[F] = D ? os(v[F]) : Gt(v[F]);
      if (hn(Re, Le))
        S(
          Re,
          Le,
          k,
          null,
          j,
          B,
          w,
          N,
          D
        );
      else
        break;
      F++;
    }
    for (; F <= ne && F <= _e; ) {
      const Re = p[ne], Le = v[_e] = D ? os(v[_e]) : Gt(v[_e]);
      if (hn(Re, Le))
        S(
          Re,
          Le,
          k,
          null,
          j,
          B,
          w,
          N,
          D
        );
      else
        break;
      ne--, _e--;
    }
    if (F > ne) {
      if (F <= _e) {
        const Re = _e + 1, Le = Re < he ? v[Re].el : I;
        for (; F <= _e; )
          S(
            null,
            v[F] = D ? os(v[F]) : Gt(v[F]),
            k,
            Le,
            j,
            B,
            w,
            N,
            D
          ), F++;
      }
    } else if (F > _e)
      for (; F <= ne; )
        Je(p[F], j, B, !0), F++;
    else {
      const Re = F, Le = F, He = /* @__PURE__ */ new Map();
      for (F = Le; F <= _e; F++) {
        const K = v[F] = D ? os(v[F]) : Gt(v[F]);
        K.key != null && He.set(K.key, F);
      }
      let Z, le = 0;
      const ae = _e - Le + 1;
      let Oe = !1, De = 0;
      const Ie = new Array(ae);
      for (F = 0; F < ae; F++) Ie[F] = 0;
      for (F = Re; F <= ne; F++) {
        const K = p[F];
        if (le >= ae) {
          Je(K, j, B, !0);
          continue;
        }
        let ye;
        if (K.key != null)
          ye = He.get(K.key);
        else
          for (Z = Le; Z <= _e; Z++)
            if (Ie[Z - Le] === 0 && hn(K, v[Z])) {
              ye = Z;
              break;
            }
        ye === void 0 ? Je(K, j, B, !0) : (Ie[ye - Le] = F + 1, ye >= De ? De = ye : Oe = !0, S(
          K,
          v[ye],
          k,
          null,
          j,
          B,
          w,
          N,
          D
        ), le++);
      }
      const L = Oe ? xf(Ie) : Ls;
      for (Z = L.length - 1, F = ae - 1; F >= 0; F--) {
        const K = Le + F, ye = v[K], We = v[K + 1], Rt = K + 1 < he ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          We.el || qo(We)
        ) : I;
        Ie[F] === 0 ? S(
          null,
          ye,
          k,
          Rt,
          j,
          B,
          w,
          N,
          D
        ) : Oe && (Z < 0 || F !== L[Z] ? tt(ye, k, Rt, 2) : Z--);
      }
    }
  }, tt = (p, v, k, I, j = null) => {
    const { el: B, type: w, transition: N, children: D, shapeFlag: F } = p;
    if (F & 6) {
      tt(p.component.subTree, v, k, I);
      return;
    }
    if (F & 128) {
      p.suspense.move(v, k, I);
      return;
    }
    if (F & 64) {
      w.move(p, v, k, P);
      return;
    }
    if (w === Ee) {
      n(B, v, k);
      for (let ne = 0; ne < D.length; ne++)
        tt(D[ne], v, k, I);
      n(p.anchor, v, k);
      return;
    }
    if (w === ho) {
      Y(p, v, k);
      return;
    }
    if (I !== 2 && F & 1 && N)
      if (I === 0)
        N.persisted && !B[fo] ? n(B, v, k) : (N.beforeEnter(B), n(B, v, k), bt(() => N.enter(B), j));
      else {
        const { leave: ne, delayLeave: _e, afterLeave: Re } = N, Le = () => {
          p.ctx.isUnmounted ? r(B) : n(B, v, k);
        }, He = () => {
          const Z = B._isLeaving || !!B[fo];
          B._isLeaving && B[fo](
            !0
            /* cancelled */
          ), N.persisted && !Z ? Le() : ne(B, () => {
            Le(), Re && Re();
          });
        };
        _e ? _e(B, Le, He) : He();
      }
    else
      n(B, v, k);
  }, Je = (p, v, k, I = !1, j = !1) => {
    const {
      type: B,
      props: w,
      ref: N,
      children: D,
      dynamicChildren: F,
      shapeFlag: he,
      patchFlag: ne,
      dirs: _e,
      cacheIndex: Re,
      memo: Le
    } = p;
    if ((ne === -2 || F && F.hasOnce) && (j = !1), N != null && (Qt(), Tn(N, null, k, p, !0), Yt()), Re != null && (!p.ctx || p.ctx === v) && (v.renderCache[Re] = void 0), he & 256) {
      v.ctx.deactivate(p);
      return;
    }
    const He = he & 1 && _e, Z = !en(p);
    let le;
    if (Z && (le = w && w.onVnodeBeforeUnmount) && Ut(le, v, p), he & 6)
      T(p.component, k, I);
    else {
      if (he & 128) {
        p.suspense.unmount(k, I);
        return;
      }
      He && Ps(p, null, v, "beforeUnmount"), he & 64 ? p.type.remove(
        p,
        v,
        k,
        P,
        I
      ) : F && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !F.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (B !== Ee || ne > 0 && ne & 64) ? ve(
        F,
        v,
        k,
        !1,
        !0
      ) : (B === Ee && ne & 384 || !j && he & 16) && ve(D, v, k), I && ue(p);
    }
    const ae = Le != null && Re == null;
    (Z && (le = w && w.onVnodeUnmounted) || He || ae) && bt(() => {
      le && Ut(le, v, p), He && Ps(p, null, v, "unmounted"), ae && (p.el = null);
    }, k);
  }, ue = (p) => {
    const { type: v, el: k, anchor: I, transition: j } = p, B = v === Ee;
    if (B && !j) {
      y(k, I);
      return;
    }
    if (v === ho) {
      J(p), j && !j.persisted && j.afterLeave && j.afterLeave();
      return;
    }
    const w = B ? Fo(p) : p, N = () => {
      B ? d(k) && y(k, I) : r(k), j && !j.persisted && j.afterLeave && j.afterLeave();
    };
    if (w && w.shapeFlag & 1 && j && !j.persisted) {
      const { leave: D, delayLeave: F } = j, he = w.el, ne = () => D(he, N);
      F ? F(he, N, ne) : ne();
    } else
      N();
  }, y = (p, v) => {
    let k;
    for (; p !== v; )
      k = h(p), r(p), p = k;
    r(v);
  }, T = (p, v, k) => {
    const { bum: I, scope: j, job: B, subTree: w, um: N, m: D, a: F } = p;
    aa(D), aa(F), I && pr(I), j.stop(), B ? (B.flags |= 8, Je(w, p, v, k)) : p.vnode.el && w && (w.transition = p.vnode.transition, Je(w, p, v, k)), N && bt(N, v), bt(() => {
      p.isUnmounted = !0;
    }, v);
  }, ve = (p, v, k, I = !1, j = !1, B = 0) => {
    for (let w = B; w < p.length; w++)
      Je(p[w], v, k, I, j);
  }, z = (p) => {
    if (p.shapeFlag & 6)
      return z(p.component.subTree);
    if (p.shapeFlag & 128)
      return p.suspense.next();
    const v = h(p.anchor || p.el), k = v && v[oc];
    return k ? h(k) : v;
  }, E = (p, v, k) => {
    const I = p && v._vnode ? void 0 : p && p.component ? p.component.uid : If();
    Rd(() => {
      p == null ? v._vnode && Je(v._vnode, null, null, !0) : S(
        v._vnode || null,
        p,
        v,
        null,
        null,
        null,
        k
      ), v._vnode = p;
    }, I);
  }, P = {
    p: S,
    um: Je,
    m: tt,
    r: ue,
    mt: te,
    mc: U,
    pc: Ce,
    pbc: x,
    n: z,
    o: e
  };
  return {
    render: E,
    hydrate: void 0,
    createApp: rf(E)
  };
}
function po({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function Ns({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function _f(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function $i(e, t, s = !1) {
  const n = e.children, r = t.children;
  if (Se(n) && Se(r))
    for (let o = 0; o < n.length; o++) {
      const i = n[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = os(r[o]), a.el = i.el), !s && a.patchFlag !== -2 && $i(i, a)), a.type === Jr && (a.patchFlag === -1 && (a = r[o] = os(a)), a.el = i.el), a.type === Pt && !a.el && (a.el = i.el);
    }
}
function xf(e) {
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
function Ac(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : Ac(t);
}
function aa(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function qo(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? qo(t.subTree) : null;
}
const Rc = (e) => e.__isSuspense;
function kf(e, t) {
  t && t.pendingBranch ? Se(e) ? t.effects.push(...e) : t.effects.push(e) : Ad(e);
}
const Ee = /* @__PURE__ */ Symbol.for("v-fgt"), Jr = /* @__PURE__ */ Symbol.for("v-txt"), Pt = /* @__PURE__ */ Symbol.for("v-cmt"), ho = /* @__PURE__ */ Symbol.for("v-stc"), us = [];
let It = null;
function $(e = !1) {
  us.push(It = e ? null : []);
}
function Oi() {
  us.pop(), It = us[us.length - 1] || null;
}
let Ln = 1;
function Sr(e, t = !1) {
  Ln += e, e < 0 && It && t && (It.hasOnce = !0);
}
function Ic(e) {
  return e.dynamicChildren = Ln > 0 ? It || Ls : null, Oi(), Ln > 0 && It && It.push(e), e;
}
function H(e, t, s, n, r, o) {
  return Ic(
    f(
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
function Ze(e, t, s, n, r) {
  return Ic(
    V(
      e,
      t,
      s,
      n,
      r,
      !0
    )
  );
}
function sn(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function hn(e, t) {
  return e.type === t.type && e.key === t.key;
}
const Ec = ({ key: e }) => e ?? null, gr = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? ot(e) || /* @__PURE__ */ lt(e) || Pe(e) ? { i: pt, r: e, k: t, f: !!s } : e : null);
function f(e, t = null, s = null, n = 0, r = null, o = e === Ee ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Ec(t),
    ref: t && gr(t),
    scopeId: nc,
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
    ctx: pt
  };
  return a ? (Cr(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= ot(s) ? 8 : 16), Ln > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  It && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && It.push(l), l;
}
const V = Sf;
function Sf(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === cc) && (e = Pt), sn(e)) {
    const a = nn(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && Cr(a, s), Ln > 0 && !o && It && (a.shapeFlag & 6 ? It[It.indexOf(e)] = a : It.push(a)), a.patchFlag = -2, a;
  }
  if (Mf(e) && (e = e.__vccOpts), t) {
    t = Cf(t);
    let { class: a, style: l } = t;
    a && !ot(a) && (t.class = kt(a)), Ke(l) && (/* @__PURE__ */ Br(l) && !Se(l) && (l = ht({}, l)), t.style = mi(l));
  }
  const i = ot(e) ? 1 : Rc(e) ? 128 : qr(e) ? 64 : Ke(e) ? 4 : Pe(e) ? 2 : 0;
  return f(
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
function Cf(e) {
  return e ? /* @__PURE__ */ Br(e) || wc(e) ? ht({}, e) : e : null;
}
function nn(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? Af(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Ec(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? Se(o) ? o.concat(gr(t)) : [o, gr(t)] : gr(t)
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
    patchFlag: t && e.type !== Ee ? i === -1 ? 16 : i | 16 : i,
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
    ssContent: e.ssContent && nn(e.ssContent),
    ssFallback: e.ssFallback && nn(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && _r(
    u,
    l.clone(u)
  ), u;
}
function O(e = " ", t = 0) {
  return V(Jr, null, e, t);
}
function we(e = "", t = !1) {
  return t ? ($(), Ze(Pt, null, e)) : V(Pt, null, e);
}
function Gt(e) {
  return e == null || typeof e == "boolean" ? V(Pt) : Se(e) ? V(
    Ee,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : sn(e) ? os(e) : V(Jr, null, String(e));
}
function os(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : nn(e);
}
function Cr(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (Se(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), Cr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !wc(t) ? t._ctx = pt : r === 3 && pt && (pt.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (Pe(t)) {
    if (n & 65) {
      Cr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: pt }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [O(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function Af(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = kt([t.class, n.class]));
      else if (r === "style")
        t.style = mi([t.style, n.style]);
      else if (zr(r)) {
        const o = t[r], i = n[r];
        i && o !== i && !(Se(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !jr(r) && (t[r] = i);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function Ut(e, t, s, n = null) {
  Dt(e, t, 7, [
    s,
    n
  ]);
}
const Rf = pc();
let $c = 0;
function If() {
  return $c;
}
function Ef(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || Rf, o = {
    uid: $c++,
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
    scope: new Ol(
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
    propsOptions: xc(n, r),
    emitsOptions: hc(n, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: Ye,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: Ye,
    data: Ye,
    props: Ye,
    attrs: Ye,
    slots: Ye,
    refs: Ye,
    setupState: Ye,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = af.bind(null, o), e.ce && e.ce(o), o;
}
let vt = null;
const Qr = () => vt || pt;
let Ar, Vn;
{
  const e = Fr(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  Ar = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => vt = s
  ), Vn = t(
    "__VUE_SSR_SETTERS__",
    (s) => Un = s
  );
}
const Qn = (e) => {
  const t = vt;
  return Ar(e), e.scope.on(), () => {
    e.scope.off(), Ar(t);
  };
}, la = () => {
  vt && vt.scope.off(), Ar(null);
};
function Oc(e) {
  return e.vnode.shapeFlag & 4;
}
let Un = !1;
function $f(e, t = !1, s = !1) {
  t && Vn(t);
  const { props: n, children: r } = e.vnode, o = Oc(e);
  mf(e, n, o, t), vf(e, r, s || t);
  const i = o ? Of(e, t) : void 0;
  return t && Vn(!1), i;
}
function Of(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Qd);
  const { setup: n } = s;
  if (n) {
    Qt();
    const r = e.setupContext = n.length > 1 ? Pf(e) : null, o = Qn(e), i = Jn(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = Sl(i);
    if (Yt(), o(), (a || e.sp) && !en(e) && ac(e), a) {
      if (i.then(la, la), t)
        return i.then((l) => {
          Vn(!0);
          try {
            ca(e, l, t);
          } finally {
            Vn(!1);
          }
        }).catch((l) => {
          Gr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      ca(e, i);
  } else
    Tc(e);
}
function ca(e, t, s) {
  Pe(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : Ke(t) && (e.setupState = Ql(t)), Tc(e);
}
function Tc(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || Zt);
  {
    const r = Qn(e);
    Qt();
    try {
      Yd(e);
    } finally {
      Yt(), r();
    }
  }
}
const Tf = {
  get(e, t) {
    return gt(e, "get", ""), e[t];
  }
};
function Pf(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Tf),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Yr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(Ql(xi(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in Pn)
        return Pn[s](e);
    },
    has(t, s) {
      return s in t || s in Pn;
    }
  })) : e.proxy;
}
function Nf(e, t = !0) {
  return Pe(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function Mf(e) {
  return Pe(e) && "__vccOpts" in e;
}
const Ue = (e, t) => /* @__PURE__ */ _d(e, t, Un);
function Fn(e, t, s) {
  try {
    Sr(-1);
    const n = arguments.length;
    return n === 2 ? Ke(t) && !Se(t) ? sn(t) ? V(e, null, [t]) : V(e, t) : V(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && sn(s) && (s = [s]), V(e, t, s));
  } finally {
    Sr(1);
  }
}
const zf = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Zo;
const ua = typeof window < "u" && window.trustedTypes;
if (ua)
  try {
    Zo = /* @__PURE__ */ ua.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const Pc = Zo ? (e) => Zo.createHTML(e) : (e) => e, jf = "http://www.w3.org/2000/svg", Df = "http://www.w3.org/1998/Math/MathML", rs = typeof document < "u" ? document : null, da = rs && /* @__PURE__ */ rs.createElement("template"), Lf = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? rs.createElementNS(jf, e) : t === "mathml" ? rs.createElementNS(Df, e) : s ? rs.createElement(e, { is: s }) : rs.createElement(e);
    return e === "select" && n && n.multiple != null && r.setAttribute("multiple", n.multiple), r;
  },
  createText: (e) => rs.createTextNode(e),
  createComment: (e) => rs.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => rs.querySelector(e),
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
      da.innerHTML = Pc(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const a = da.content;
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
}, Vf = /* @__PURE__ */ Symbol("_vtc");
function Uf(e, t, s) {
  const n = e[Vf];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const fa = /* @__PURE__ */ Symbol("_vod"), Ff = /* @__PURE__ */ Symbol("_vsh"), Wf = /* @__PURE__ */ Symbol(""), Bf = /(?:^|;)\s*display\s*:/;
function Gf(e, t, s) {
  const n = e.style, r = ot(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (ot(t))
        for (const i of t.split(";")) {
          const a = i.slice(0, i.indexOf(":")).trim();
          s[a] == null && Sn(n, a, "");
        }
      else
        for (const i in t)
          s[i] == null && Sn(n, i, "");
    for (const i in s) {
      i === "display" && (o = !0);
      const a = s[i];
      a != null ? qf(
        e,
        i,
        !ot(t) && t ? t[i] : void 0,
        a
      ) || Sn(n, i, a) : Sn(n, i, "");
    }
  } else if (r) {
    if (t !== s) {
      const i = n[Wf];
      i && (s += ";" + i), n.cssText = s, o = Bf.test(s);
    }
  } else t && e.removeAttribute("style");
  fa in e && ((!r || t !== s) && (e[fa] = o ? n.display : ""), e[Ff] && (n.display = "none"));
}
const or = /\s*!important$/;
function Sn(e, t, s) {
  if (Se(s))
    s.forEach((n) => Sn(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    or.test(s) ? e.setProperty(t, s.replace(or, ""), "important") : e.setProperty(t, s);
  else {
    const n = Hf(e, t);
    or.test(s) ? e.setProperty(
      Os(n),
      s.replace(or, ""),
      "important"
    ) : e[n] = s;
  }
}
const ma = ["Webkit", "Moz", "ms"], go = {};
function Hf(e, t) {
  const s = go[t];
  if (s)
    return s;
  let n = xt(t);
  if (n !== "filter" && n in e)
    return go[t] = n;
  n = Vr(n);
  for (let r = 0; r < ma.length; r++) {
    const o = ma[r] + n;
    if (o in e)
      return go[t] = o;
  }
  return t;
}
function qf(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && ot(n) && s === n;
}
const pa = "http://www.w3.org/1999/xlink";
function ha(e, t, s, n, r, o = Ku(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(pa, t.slice(6, t.length)) : e.setAttributeNS(pa, t, s) : s == null || o && !Il(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : $t(s) ? String(s) : s
  );
}
function ga(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? Pc(s) : s);
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
    a === "boolean" ? s = Il(s) : s == null && a === "string" ? (s = "", i = !0) : a === "number" && (s = 0, i = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function Ss(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function Zf(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const va = /* @__PURE__ */ Symbol("_vei");
function Kf(e, t, s, n, r = null) {
  const o = e[va] || (e[va] = {}), i = o[t];
  if (n && i)
    i.value = n;
  else {
    const [a, l] = Yf(t);
    if (n) {
      const c = o[t] = tm(
        n,
        r
      );
      Ss(e, a, c, l);
    } else i && (Zf(e, a, i, l), o[t] = void 0);
  }
}
const Jf = /(Once|Passive|Capture)$/, Qf = /^on:?(?:Once|Passive|Capture)$/;
function Yf(e) {
  let t, s;
  for (; (s = e.match(Jf)) && !Qf.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Os(e.slice(2)), t];
}
let vo = 0;
const Xf = /* @__PURE__ */ Promise.resolve(), em = () => vo || (Xf.then(() => vo = 0), vo = Date.now());
function tm(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if (Se(r)) {
      const o = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        o.call(n), n._stopped = !0;
      };
      const i = r.slice(), a = [n];
      for (let l = 0; l < i.length && !n._stopped; l++) {
        const c = i[l];
        c && Dt(
          c,
          t,
          5,
          a
        );
      }
    } else
      Dt(
        r,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = em(), s;
}
const ya = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, sm = (e, t, s, n, r, o) => {
  const i = r === "svg";
  t === "class" ? Uf(e, n, i) : t === "style" ? Gf(e, s, n) : zr(t) ? jr(t) || Kf(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : nm(e, t, n, i)) ? (ga(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && ha(e, t, n, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (rm(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !ot(n))) ? ga(e, xt(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), ha(e, t, n, i));
};
function nm(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && ya(t) && Pe(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return ya(t) && ot(s) ? !1 : t in e;
}
function rm(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = xt(t);
  return Array.isArray(s) ? s.some((r) => xt(r) === n) : Object.keys(s).some((r) => xt(r) === n);
}
const rn = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return Se(t) ? (s) => pr(t, s) : t;
};
function om(e) {
  e.target.composing = !0;
}
function ba(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const qt = /* @__PURE__ */ Symbol("_assign"), ir = /* @__PURE__ */ Symbol("_initialValue");
function yo(e, t, s) {
  return t && (e = e.trim()), s && (e = Ur(e)), e;
}
const at = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[ir] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[ir] = e.defaultValue.replace(/\r\n?/g, `
`))), e[qt] = rn(r);
    const o = n || r.props && r.props.type === "number";
    Ss(e, t ? "change" : "input", (i) => {
      i.target.composing || e[qt](yo(e.value, s, o));
    }), (s || o) && Ss(e, "change", () => {
      e.value = yo(e.value, s, o);
    }), t || (Ss(e, "compositionstart", om), Ss(e, "compositionend", ba), Ss(e, "change", ba));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[ir];
    delete e[ir], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[qt](yo(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, i) {
    if (e[qt] = rn(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? Ur(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, tn = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[qt] = rn(s), Ss(e, "change", () => {
      const n = e._modelValue, r = Wn(e), o = e.checked, i = e[qt];
      if (Se(n)) {
        const a = pi(n, r), l = a !== -1;
        if (o && !l)
          i(n.concat(r));
        else if (!o && l) {
          const c = [...n];
          c.splice(a, 1), i(c);
        }
      } else if (ds(n)) {
        const a = new Set(n);
        o ? a.add(r) : a.delete(r), i(a);
      } else
        i(Nc(e, o));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: wa,
  beforeUpdate(e, t, s) {
    e[qt] = rn(s), wa(e, t, s);
  }
};
function wa(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let r;
  if (Se(t))
    r = pi(t, n.props.value) > -1;
  else if (ds(t))
    r = t.has(n.props.value);
  else {
    if (t === s) return;
    r = fs(t, Nc(e, !0));
  }
  e.checked !== r && (e.checked = r);
}
const ls = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, Ss(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? Ur(Wn(l)) : Wn(l)
      ), o = e.multiple, i = o ? ds(e._modelValue) ? new Set(r) : r : r[0], a = e._pendingValue = [
        o,
        o ? Se(i) ? r.slice() : r : i
      ];
      try {
        e[qt](i);
      } finally {
        Hr(() => {
          e._pendingValue === a && (e._pendingValue = void 0);
        });
      }
    }), e[qt] = rn(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    _a(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[qt] = rn(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !im(t, s[1], s[0])) && _a(e, t);
  }
};
function im(e, t, s) {
  if (!s || Se(e)) return fs(e, t);
  if (ds(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function _a(e, t) {
  const s = e.multiple, n = Se(t);
  if (!(s && !n && !ds(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const i = e.options[r], a = Wn(i);
      if (s)
        if (n) {
          const l = typeof a;
          l === "string" || l === "number" ? i.selected = t.some((c) => String(c) === String(a)) : i.selected = pi(t, a) > -1;
        } else
          i.selected = t.has(a);
      else if (fs(Wn(i), t)) {
        e.selectedIndex !== r && (e.selectedIndex = r);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function Wn(e) {
  return "_value" in e ? e._value : e.value;
}
function Nc(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const am = ["ctrl", "shift", "alt", "meta"], lm = {
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
  exact: (e, t) => am.some((s) => e[`${s}Key`] && !t.includes(s))
}, Rr = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = lm[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, cm = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
}, Ws = (e, t) => {
  const s = e._withKeys || (e._withKeys = {}), n = t.join(".");
  return s[n] || (s[n] = ((r) => {
    if (!("key" in r))
      return;
    const o = Os(r.key);
    if (t.some(
      (i) => i === o || cm[i] === o
    ))
      return e(r);
  }));
}, um = /* @__PURE__ */ ht({ patchProp: sm }, Lf);
let xa;
function dm() {
  return xa || (xa = bf(um));
}
const fm = ((...e) => {
  const t = dm().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = pm(n);
    if (!r) return;
    const o = t._component;
    !Pe(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = s(r, !1, mm(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function mm(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function pm(e) {
  return ot(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let Mc;
const Xr = (e) => Mc = e, zc = (
  /* istanbul ignore next */
  Symbol()
);
function Ko(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var Nn;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(Nn || (Nn = {}));
function hm() {
  const e = Tl(!0), t = e.run(() => /* @__PURE__ */ R({}));
  let s = [], n = [];
  const r = xi({
    install(o) {
      Xr(r), r._a = o, o.provide(zc, r), o.config.globalProperties.$pinia = r, n.forEach((i) => s.push(i)), n = [];
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
const jc = () => {
};
function ka(e, t, s, n = jc) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && hi() && Pl(r), r;
}
function qs(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const gm = (e) => e(), Sa = Symbol(), bo = Symbol();
function Jo(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    Ko(r) && Ko(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ lt(n) && !/* @__PURE__ */ Kt(n) ? e[s] = Jo(r, n) : e[s] = n;
  }
  return e;
}
const vm = (
  /* istanbul ignore next */
  Symbol()
);
function ym(e) {
  return !Ko(e) || !Object.prototype.hasOwnProperty.call(e, vm);
}
const { assign: bs } = Object;
function bm(e) {
  return !!(/* @__PURE__ */ lt(e) && e.effect);
}
function wm(e, t, s, n) {
  const { state: r, actions: o, getters: i } = t, a = s.state.value[e];
  let l;
  function c() {
    a || (s.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ vd(s.state.value[e]);
    return bs(u, o, Object.keys(i || {}).reduce((d, h) => (d[h] = xi(Ue(() => {
      Xr(s);
      const m = s._s.get(e);
      return i[h].call(m, m);
    })), d), {}));
  }
  return l = Dc(e, c, t, s, n, !0), l;
}
function Dc(e, t, s = {}, n, r, o) {
  let i;
  const a = bs({ actions: {} }, s), l = { deep: !0 };
  let c, u, d = /* @__PURE__ */ new Set(), h = /* @__PURE__ */ new Set(), m;
  const _ = n.state.value[e];
  !o && !_ && (n.state.value[e] = {});
  let S;
  function b(U) {
    let q;
    c = u = !1, typeof U == "function" ? (U(n.state.value[e]), q = {
      type: Nn.patchFunction,
      storeId: e,
      events: m
    }) : (Jo(n.state.value[e], U), q = {
      type: Nn.patchObject,
      payload: U,
      storeId: e,
      events: m
    });
    const x = S = Symbol();
    Hr().then(() => {
      S === x && (c = !0);
    }), u = !0, qs(d, q, n.state.value[e]);
  }
  const A = o ? function() {
    const { state: q } = s, x = q ? q() : {};
    this.$patch((Q) => {
      bs(Q, x);
    });
  } : (
    /* istanbul ignore next */
    jc
  );
  function M() {
    i.stop(), d.clear(), h.clear(), n._s.delete(e);
  }
  const Y = (U, q = "") => {
    if (Sa in U)
      return U[bo] = q, U;
    const x = function() {
      Xr(n);
      const Q = Array.from(arguments), xe = /* @__PURE__ */ new Set(), C = /* @__PURE__ */ new Set();
      function te(pe) {
        xe.add(pe);
      }
      function Ne(pe) {
        C.add(pe);
      }
      qs(h, {
        args: Q,
        name: x[bo],
        store: ce,
        after: te,
        onError: Ne
      });
      let ke;
      try {
        ke = U.apply(this && this.$id === e ? this : ce, Q);
      } catch (pe) {
        throw qs(C, pe), pe;
      }
      return ke instanceof Promise ? ke.then((pe) => (qs(xe, pe), pe)).catch((pe) => (qs(C, pe), Promise.reject(pe))) : (qs(xe, ke), ke);
    };
    return x[Sa] = !0, x[bo] = q, x;
  }, J = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: ka.bind(null, h),
    $patch: b,
    $reset: A,
    $subscribe(U, q = {}) {
      const x = ka(d, U, q.detached, () => Q()), Q = i.run(() => As(() => n.state.value[e], (xe) => {
        (q.flush === "sync" ? u : c) && U({
          storeId: e,
          type: Nn.direct,
          events: m
        }, xe);
      }, bs({}, l, q)));
      return x;
    },
    $dispose: M
  }, ce = /* @__PURE__ */ Kn(J);
  n._s.set(e, ce);
  const re = (n._a && n._a.runWithContext || gm)(() => n._e.run(() => (i = Tl()).run(() => t({ action: Y }))));
  for (const U in re) {
    const q = re[U];
    if (/* @__PURE__ */ lt(q) && !bm(q) || /* @__PURE__ */ Kt(q))
      o || (_ && ym(q) && (/* @__PURE__ */ lt(q) ? q.value = _[U] : Jo(q, _[U])), n.state.value[e][U] = q);
    else if (typeof q == "function") {
      const x = Y(q, U);
      re[U] = x, a.actions[U] = q;
    }
  }
  return bs(ce, re), bs(/* @__PURE__ */ Be(ce), re), Object.defineProperty(ce, "$state", {
    get: () => n.state.value[e],
    set: (U) => {
      b((q) => {
        bs(q, U);
      });
    }
  }), n._p.forEach((U) => {
    bs(ce, i.run(() => U({
      store: ce,
      app: n._a,
      pinia: n,
      options: a
    })));
  }), _ && o && s.hydrate && s.hydrate(ce.$state, _), c = !0, u = !0, ce;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function mn(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(i, a) {
    const l = Si();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? At(zc, null) : null), i && Xr(i), i = Mc, i._s.has(e) || (r ? Dc(e, t, n, i) : wm(e, n, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const Js = typeof document < "u";
function Lc(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function _m(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && Lc(e.default);
}
const nt = Object.assign;
function wo(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = Lt(r) ? r.map(e) : e(r);
  }
  return s;
}
const Mn = () => {
}, Lt = Array.isArray;
function Ca(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const Vc = /#/g, xm = /&/g, km = /\//g, Sm = /=/g, Cm = /\?/g, Uc = /\+/g, Am = /%5B/g, Rm = /%5D/g, Fc = /%5E/g, Im = /%60/g, Wc = /%7B/g, Em = /%7C/g, Bc = /%7D/g, $m = /%20/g;
function Ti(e) {
  return e == null ? "" : encodeURI("" + e).replace(Em, "|").replace(Am, "[").replace(Rm, "]");
}
function Om(e) {
  return Ti(e).replace(Wc, "{").replace(Bc, "}").replace(Fc, "^");
}
function Qo(e) {
  return Ti(e).replace(Uc, "%2B").replace($m, "+").replace(Vc, "%23").replace(xm, "%26").replace(Im, "`").replace(Wc, "{").replace(Bc, "}").replace(Fc, "^");
}
function Tm(e) {
  return Qo(e).replace(Sm, "%3D");
}
function Pm(e) {
  return Ti(e).replace(Vc, "%23").replace(Cm, "%3F");
}
function Nm(e) {
  return Pm(e).replace(km, "%2F");
}
function Bn(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const Mm = /\/$/, zm = (e) => e.replace(Mm, "");
function _o(e, t, s = "/") {
  let n, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (n = n || t.slice(0, a), i = t.slice(a, t.length)), n = Vm(n ?? t, s), {
    fullPath: n + o + i,
    path: n,
    query: r,
    hash: Bn(i)
  };
}
function jm(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Dm(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && on(t.matched[n], s.matched[r]) && Gc(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function on(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function Gc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!Lm(e[s], t[s])) return !1;
  return !0;
}
function Lm(e, t) {
  return Lt(e) ? Aa(e, t) : Lt(t) ? Aa(t, e) : e?.valueOf() === t?.valueOf();
}
function Aa(e, t) {
  return Lt(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function Vm(e, t) {
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
const gs = {
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
let Yo = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), Ra = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const xo = "";
function Um(e) {
  if (!e) if (Js) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), zm(e);
}
const Fm = /^[^#]+#/;
function Wm(e, t) {
  return e.replace(Fm, "#") + t;
}
function Bm(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const Gm = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function Hm(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = Bm(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function Ia(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Xo = /* @__PURE__ */ new Map();
function qm(e, t) {
  Xo.set(e, t);
}
function Zm(e) {
  const t = Xo.get(e);
  return Xo.delete(e), t;
}
function Km(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function Hc(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let it = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const qc = Symbol("");
it.MATCHER_NOT_FOUND + "", it.NAVIGATION_GUARD_REDIRECT + "", it.NAVIGATION_ABORTED + "", it.NAVIGATION_CANCELLED + "", it.NAVIGATION_DUPLICATED + "";
function an(e, t) {
  return nt(/* @__PURE__ */ new Error(), {
    type: e,
    [qc]: !0
  }, t);
}
function ss(e, t) {
  return e instanceof Error && qc in e && (t == null || !!(e.type & t));
}
const Jm = [
  "params",
  "query",
  "hash"
];
function Qm(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of Jm) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function Ym(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(Uc, " "), o = r.indexOf("="), i = Bn(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : Bn(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      Lt(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function Ea(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Tm(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (Lt(n) ? n.map((r) => r && Qo(r)) : [n && Qo(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function Xm(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = Lt(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const ep = Symbol(""), $a = Symbol(""), eo = Symbol(""), Pi = Symbol(""), ei = Symbol("");
function gn() {
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
function xs(e, t, s, n, r, o = (i) => i()) {
  const i = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (h) => {
      h === !1 ? l(an(it.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : h instanceof Error ? l(h) : Km(h) ? l(an(it.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: h
      })) : (i && n.enterCallbacks[r] === i && typeof h == "function" && i.push(h), a());
    }, u = o(() => e.call(n && n.instances[r], t, s, c));
    let d = Promise.resolve(u);
    e.length < 3 && (d = d.then(c)), d.catch((h) => l(h));
  });
}
function ko(e, t, s, n, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (Lc(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(xs(c, s, n, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const d = _m(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = d;
            const h = (d.__vccOpts || d)[t];
            return h && xs(h, s, n, i, a, r)();
          }));
        }
    }
  return o;
}
function tp(e, t) {
  const s = [], n = [], r = [], o = Math.max(t.matched.length, e.matched.length);
  for (let i = 0; i < o; i++) {
    const a = t.matched[i];
    a && (e.matched.find((c) => on(c, a)) ? n.push(a) : s.push(a));
    const l = e.matched[i];
    l && (t.matched.find((c) => on(c, l)) || r.push(l));
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
function sp(e = "") {
  let t = [], s = [[xo, {}]], n = 0;
  e = Um(e);
  function r(a, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const d = {
      direction: c,
      delta: u,
      type: Yo.pop
    };
    for (const h of t) h(a, l, d);
  }
  const i = {
    location: xo,
    state: {},
    base: e,
    createHref: Wm.bind(null, e),
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
      t = [], s = [[xo, {}]], n = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? Ra.back : Ra.forward;
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
let Vs = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var dt = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(dt || {});
const np = {
  type: Vs.Static,
  value: ""
}, rp = /[a-zA-Z0-9_]/;
function op(e) {
  if (!e) return [[]];
  if (e === "/") return [[np]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(m) {
    throw new Error(`ERR (${s})/"${c}": ${m}`);
  }
  let s = dt.Static, n = s;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function d() {
    c && (s === dt.Static ? o.push({
      type: Vs.Static,
      value: c
    }) : s === dt.Param || s === dt.ParamRegExp || s === dt.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: Vs.Param,
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
    if (l = e[a++], l === "\\" && s !== dt.ParamRegExp) {
      n = s, s = dt.EscapeNext;
      continue;
    }
    switch (s) {
      case dt.Static:
        l === "/" ? (c && d(), i()) : l === ":" ? (d(), s = dt.Param) : h();
        break;
      case dt.EscapeNext:
        h(), s = n;
        break;
      case dt.Param:
        l === "(" ? s = dt.ParamRegExp : rp.test(l) ? h() : (d(), s = dt.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case dt.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : s = dt.ParamRegExpEnd : u += l;
        break;
      case dt.ParamRegExpEnd:
        d(), s = dt.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === dt.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), d(), i(), r;
}
const Oa = "[^/]+?", ip = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var wt = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(wt || {});
const ap = /[.+*?^${}()[\]/\\]/g;
function lp(e, t) {
  const s = nt({}, ip, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [wt.Root];
    s.strict && !c.length && (r += "/");
    for (let d = 0; d < c.length; d++) {
      const h = c[d];
      let m = wt.Segment + (s.sensitive ? wt.BonusCaseSensitive : 0);
      if (h.type === Vs.Static)
        d || (r += "/"), r += h.value.replace(ap, "\\$&"), m += wt.Static;
      else if (h.type === Vs.Param) {
        const { value: _, repeatable: S, optional: b, regexp: A } = h;
        o.push({
          name: _,
          repeatable: S,
          optional: b
        });
        const M = A || Oa;
        if (M !== Oa) {
          m += wt.BonusCustomRegExp;
          try {
            `${M}`;
          } catch (J) {
            throw new Error(`Invalid custom RegExp for param "${_}" (${M}): ` + J.message);
          }
        }
        let Y = S ? `((?:${M})(?:/(?:${M}))*)` : `(${M})`;
        d || (Y = b && c.length < 2 ? `(?:/${Y})` : "/" + Y), b && (Y += "?"), r += Y, m += wt.Dynamic, b && (m += wt.BonusOptional), S && (m += wt.BonusRepeatable), M === ".*" && (m += wt.BonusWildcard);
      }
      u.push(m);
    }
    n.push(u);
  }
  if (s.strict && s.end) {
    const c = n.length - 1;
    n[c][n[c].length - 1] += wt.BonusStrict;
  }
  s.strict || (r += "/?"), s.end ? r += "$" : s.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const i = new RegExp(r, s.sensitive ? "" : "i");
  function a(c) {
    const u = c.match(i), d = {};
    if (!u) return null;
    for (let h = 1; h < u.length; h++) {
      const m = u[h] || "", _ = o[h - 1];
      d[_.name] = m && _.repeatable ? m.split("/") : m;
    }
    return d;
  }
  function l(c) {
    let u = "", d = !1;
    for (const h of e) {
      (!d || !u.endsWith("/")) && (u += "/"), d = !1;
      for (const m of h) if (m.type === Vs.Static) u += m.value;
      else if (m.type === Vs.Param) {
        const { value: _, repeatable: S, optional: b } = m, A = _ in c ? c[_] : "";
        if (Lt(A) && !S) throw new Error(`Provided param "${_}" is an array but it is not repeatable (* or + modifiers)`);
        const M = Lt(A) ? A.join("/") : A;
        if (!M) if (b)
          h.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : d = !0);
        else throw new Error(`Missing required param "${_}"`);
        u += M;
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
function cp(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === wt.Static + wt.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === wt.Static + wt.Segment ? 1 : -1 : 0;
}
function Zc(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = cp(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (Ta(n)) return 1;
    if (Ta(r)) return -1;
  }
  return r.length - n.length;
}
function Ta(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const up = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function dp(e, t, s) {
  const n = lp(op(e.path), s), r = nt(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function fp(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = Ca(up, t);
  function r(d) {
    return n.get(d);
  }
  function o(d, h, m) {
    const _ = !m, S = Na(d);
    S.aliasOf = m && m.record;
    const b = Ca(t, d), A = [S];
    if ("alias" in d) {
      const J = typeof d.alias == "string" ? [d.alias] : d.alias;
      for (const ce of J) A.push(Na(nt({}, S, {
        components: m ? m.record.components : S.components,
        path: ce,
        aliasOf: m ? m.record : S
      })));
    }
    let M, Y;
    for (const J of A) {
      const { path: ce } = J;
      if (h && ce[0] !== "/") {
        const Ae = h.record.path, re = Ae[Ae.length - 1] === "/" ? "" : "/";
        J.path = h.record.path + (ce && re + ce);
      }
      if (M = dp(J, h, b), m ? m.alias.push(M) : (Y = Y || M, Y !== M && Y.alias.push(M), _ && d.name && !Ma(M) && i(d.name)), Kc(M) && l(M), S.children) {
        const Ae = S.children;
        for (let re = 0; re < Ae.length; re++) o(Ae[re], M, m && m.children[re]);
      }
      m = m || M;
    }
    return Y ? () => {
      i(Y);
    } : Mn;
  }
  function i(d) {
    if (Hc(d)) {
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
    const h = hp(d, s);
    s.splice(h, 0, d), d.record.name && !Ma(d) && n.set(d.record.name, d);
  }
  function c(d, h) {
    let m, _ = {}, S, b;
    if ("name" in d && d.name) {
      if (m = n.get(d.name), !m) throw an(it.MATCHER_NOT_FOUND, { location: d });
      b = m.record.name, _ = nt(Pa(h.params, m.keys.filter((Y) => !Y.optional).concat(m.parent ? m.parent.keys.filter((Y) => Y.optional) : []).map((Y) => Y.name)), d.params && Pa(d.params, m.keys.map((Y) => Y.name))), S = m.stringify(_);
    } else if (d.path != null)
      S = d.path, m = s.find((Y) => Y.re.test(S)), m && (_ = m.parse(S), b = m.record.name);
    else {
      if (m = h.name ? n.get(h.name) : s.find((Y) => Y.re.test(h.path)), !m) throw an(it.MATCHER_NOT_FOUND, {
        location: d,
        currentLocation: h
      });
      b = m.record.name, _ = nt({}, h.params, d.params), S = m.stringify(_);
    }
    const A = [];
    let M = m;
    for (; M; )
      A.unshift(M.record), M = M.parent;
    return {
      name: b,
      path: S,
      params: _,
      matched: A,
      meta: pp(A)
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
function Pa(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function Na(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: mp(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function mp(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function Ma(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function pp(e) {
  return e.reduce((t, s) => nt(t, s.meta), {});
}
function hp(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    Zc(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = gp(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function gp(e) {
  let t = e;
  for (; t = t.parent; ) if (Kc(t) && Zc(e, t) === 0) return t;
}
function Kc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function za(e) {
  const t = At(eo), s = At(Pi), n = Ue(() => {
    const l = g(e.to);
    return t.resolve(l);
  }), r = Ue(() => {
    const { matched: l } = n.value, { length: c } = l, u = l[c - 1], d = s.matched;
    if (!u || !d.length) return -1;
    const h = d.findIndex(on.bind(null, u));
    if (h > -1) return h;
    const m = ja(l[c - 2]);
    return c > 1 && ja(u) === m && d[d.length - 1].path !== m ? d.findIndex(on.bind(null, l[c - 2])) : h;
  }), o = Ue(() => r.value > -1 && wp(s.params, n.value.params)), i = Ue(() => r.value > -1 && r.value === s.matched.length - 1 && Gc(s.params, n.value.params));
  function a(l = {}) {
    if (bp(l)) {
      const c = t[g(e.replace) ? "replace" : "push"](g(e.to)).catch(Mn);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: Ue(() => n.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function vp(e) {
  return e.length === 1 ? e[0] : e;
}
const yp = /* @__PURE__ */ Ct({
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
  useLink: za,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ Kn(za(e)), { options: n } = At(eo), r = Ue(() => ({
      [Da(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [Da(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && vp(t.default(s));
      return e.custom ? o : Fn("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), Jc = yp;
function bp(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function wp(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!Lt(r) || r.length !== n.length || n.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function ja(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const Da = (e, t, s) => e ?? t ?? s, _p = /* @__PURE__ */ Ct({
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
    const n = At(ei), r = Ue(() => e.route || n.value), o = At($a, 0), i = Ue(() => {
      let c = g(o);
      const { matched: u } = r.value;
      let d;
      for (; (d = u[c]) && !d.components; ) c++;
      return c;
    }), a = Ue(() => r.value.matched[i.value]);
    hr($a, Ue(() => i.value + 1)), hr(ep, a), hr(ei, r);
    const l = /* @__PURE__ */ R();
    return As(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, d], [h, m, _]) => {
      u && (u.instances[d] = c, m && m !== u && c && c === h && (u.leaveGuards.size || (u.leaveGuards = m.leaveGuards), u.updateGuards.size || (u.updateGuards = m.updateGuards))), c && u && (!m || !on(u, m) || !h) && (u.enterCallbacks[d] || []).forEach((S) => S(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, d = a.value, h = d && d.components[u];
      if (!h) return La(s.default, {
        Component: h,
        route: c
      });
      const m = d.props[u], _ = m ? m === !0 ? c.params : typeof m == "function" ? m(c) : m : null, b = Fn(h, nt({}, _, t, {
        onVnodeUnmounted: (A) => {
          A.component.isUnmounted && (d.instances[u] = null);
        },
        ref: l
      }));
      return La(s.default, {
        Component: b,
        route: c
      }) || b;
    };
  }
});
function La(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const Qc = _p;
function xp(e) {
  const t = fp(e.routes, e), s = e.parseQuery || Ym, n = e.stringifyQuery || Ea, r = e.history, o = gn(), i = gn(), a = gn(), l = /* @__PURE__ */ On(gs);
  let c = gs;
  Js && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = wo.bind(null, (z) => "" + z), d = wo.bind(null, Nm), h = wo.bind(null, Bn);
  function m(z, E) {
    let P, ie;
    return Hc(z) ? (P = t.getRecordMatcher(z), ie = E) : ie = z, t.addRoute(ie, P);
  }
  function _(z) {
    const E = t.getRecordMatcher(z);
    E && t.removeRoute(E);
  }
  function S() {
    return t.getRoutes().map((z) => z.record);
  }
  function b(z) {
    return !!t.getRecordMatcher(z);
  }
  function A(z, E) {
    if (E = nt({}, E || l.value), typeof z == "string") {
      const I = _o(s, z, E.path), j = t.resolve({ path: I.path }, E), B = r.createHref(I.fullPath);
      return nt(I, j, {
        params: h(j.params),
        hash: Bn(I.hash),
        redirectedFrom: void 0,
        href: B
      });
    }
    let P;
    if (z.path != null)
      P = nt({}, z, { path: _o(s, z.path, E.path).path });
    else {
      const I = nt({}, z.params);
      for (const j in I) I[j] == null && delete I[j];
      P = nt({}, z, { params: d(I) }), E.params = d(E.params);
    }
    const ie = t.resolve(P, E), p = z.hash || "";
    ie.params = u(h(ie.params));
    const v = jm(n, nt({}, z, {
      hash: Om(p),
      path: ie.path
    })), k = r.createHref(v);
    return nt({
      fullPath: v,
      hash: p,
      query: n === Ea ? Xm(z.query) : z.query || {}
    }, ie, {
      redirectedFrom: void 0,
      href: k
    });
  }
  function M(z) {
    return typeof z == "string" ? _o(s, z, l.value.path) : nt({}, z);
  }
  function Y(z, E) {
    if (c !== z) return an(it.NAVIGATION_CANCELLED, {
      from: E,
      to: z
    });
  }
  function J(z) {
    return re(z);
  }
  function ce(z) {
    return J(nt(M(z), { replace: !0 }));
  }
  function Ae(z, E) {
    const P = z.matched[z.matched.length - 1];
    if (P && P.redirect) {
      const { redirect: ie } = P;
      let p = typeof ie == "function" ? ie(z, E) : ie;
      return typeof p == "string" && (p = p.includes("?") || p.includes("#") ? p = M(p) : { path: p }, p.params = {}), nt({
        query: z.query,
        hash: z.hash,
        params: p.path != null ? {} : z.params
      }, p);
    }
  }
  function re(z, E) {
    const P = c = A(z), ie = l.value, p = z.state, v = z.force, k = z.replace === !0, I = Ae(P, ie);
    if (I) return re(nt(M(I), {
      state: typeof I == "object" ? nt({}, p, I.state) : p,
      force: v,
      replace: k
    }), E || P);
    const j = P;
    j.redirectedFrom = E;
    let B;
    return !v && Dm(n, ie, P) && (B = an(it.NAVIGATION_DUPLICATED, {
      to: j,
      from: ie
    }), tt(ie, ie, !0, !1)), (B ? Promise.resolve(B) : x(j, ie)).catch((w) => ss(w) ? ss(w, it.NAVIGATION_GUARD_REDIRECT) ? w : oe(w) : Ce(w, j, ie)).then((w) => {
      if (w) {
        if (ss(w, it.NAVIGATION_GUARD_REDIRECT))
          return re(nt({ replace: k }, M(w.to), {
            state: typeof w.to == "object" ? nt({}, p, w.to.state) : p,
            force: v
          }), E || j);
      } else w = xe(j, ie, !0, k, p);
      return Q(j, ie, w), w;
    });
  }
  function U(z, E) {
    const P = Y(z, E);
    return P ? Promise.reject(P) : Promise.resolve();
  }
  function q(z) {
    const E = y.values().next().value;
    return E && typeof E.runWithContext == "function" ? E.runWithContext(z) : z();
  }
  function x(z, E) {
    let P;
    const [ie, p, v] = tp(z, E);
    P = ko(ie.reverse(), "beforeRouteLeave", z, E);
    for (const I of ie) I.leaveGuards.forEach((j) => {
      P.push(xs(j, z, E));
    });
    const k = U.bind(null, z, E);
    return P.push(k), ve(P).then(() => {
      P = [];
      for (const I of o.list()) P.push(xs(I, z, E));
      return P.push(k), ve(P);
    }).then(() => {
      P = ko(p, "beforeRouteUpdate", z, E);
      for (const I of p) I.updateGuards.forEach((j) => {
        P.push(xs(j, z, E));
      });
      return P.push(k), ve(P);
    }).then(() => {
      P = [];
      for (const I of v) if (I.beforeEnter) if (Lt(I.beforeEnter)) for (const j of I.beforeEnter) P.push(xs(j, z, E));
      else P.push(xs(I.beforeEnter, z, E));
      return P.push(k), ve(P);
    }).then(() => (z.matched.forEach((I) => I.enterCallbacks = {}), P = ko(v, "beforeRouteEnter", z, E, q), P.push(k), ve(P))).then(() => {
      P = [];
      for (const I of i.list()) P.push(xs(I, z, E));
      return P.push(k), ve(P);
    }).catch((I) => ss(I, it.NAVIGATION_CANCELLED) ? I : Promise.reject(I));
  }
  function Q(z, E, P) {
    a.list().forEach((ie) => q(() => ie(z, E, P)));
  }
  function xe(z, E, P, ie, p) {
    const v = Y(z, E);
    if (v) return v;
    const k = E === gs, I = Js ? history.state : {};
    P && (ie || k ? r.replace(z.fullPath, nt({ scroll: k && I && I.scroll }, p)) : r.push(z.fullPath, p)), l.value = z, tt(z, E, P, k), oe();
  }
  let C;
  function te() {
    C || (C = r.listen((z, E, P) => {
      if (!T.listening) return;
      const ie = A(z), p = Ae(ie, T.currentRoute.value);
      if (p) {
        re(nt(p, {
          replace: !0,
          force: !0
        }), ie).catch(Mn);
        return;
      }
      c = ie;
      const v = l.value;
      Js && qm(Ia(v.fullPath, P.delta), Gm()), x(ie, v).catch((k) => ss(k, it.NAVIGATION_ABORTED | it.NAVIGATION_CANCELLED) ? k : ss(k, it.NAVIGATION_GUARD_REDIRECT) ? (re(nt(M(k.to), { force: !0 }), ie).then((I) => {
        ss(I, it.NAVIGATION_ABORTED | it.NAVIGATION_DUPLICATED) && !P.delta && P.type === Yo.pop && r.go(-1, !1);
      }).catch(Mn), Promise.reject()) : (P.delta && r.go(-P.delta, !1), Ce(k, ie, v))).then((k) => {
        k = k || xe(ie, v, !1), k && (P.delta && !ss(k, it.NAVIGATION_CANCELLED) ? r.go(-P.delta, !1) : P.type === Yo.pop && ss(k, it.NAVIGATION_ABORTED | it.NAVIGATION_DUPLICATED) && r.go(-1, !1)), Q(ie, v, k);
      }).catch(Mn);
    }));
  }
  let Ne = gn(), ke = gn(), pe;
  function Ce(z, E, P) {
    oe(z);
    const ie = ke.list();
    return ie.length ? ie.forEach((p) => p(z, E, P)) : console.error(z), Promise.reject(z);
  }
  function ze() {
    return pe && l.value !== gs ? Promise.resolve() : new Promise((z, E) => {
      Ne.add([z, E]);
    });
  }
  function oe(z) {
    return pe || (pe = !z, te(), Ne.list().forEach(([E, P]) => z ? P(z) : E()), Ne.reset()), z;
  }
  function tt(z, E, P, ie) {
    const { scrollBehavior: p } = e;
    if (!Js || !p) return Promise.resolve();
    const v = !P && Zm(Ia(z.fullPath, 0)) || (ie || !P) && history.state && history.state.scroll || null;
    return Hr().then(() => p(z, E, v)).then((k) => k && Hm(k)).catch((k) => Ce(k, z, E));
  }
  const Je = (z) => r.go(z);
  let ue;
  const y = /* @__PURE__ */ new Set(), T = {
    currentRoute: l,
    listening: !0,
    addRoute: m,
    removeRoute: _,
    clearRoutes: t.clearRoutes,
    hasRoute: b,
    getRoutes: S,
    resolve: A,
    options: e,
    push: J,
    replace: ce,
    go: Je,
    back: () => Je(-1),
    forward: () => Je(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: ke.add,
    isReady: ze,
    install(z) {
      z.component("RouterLink", Jc), z.component("RouterView", Qc), z.config.globalProperties.$router = T, Object.defineProperty(z.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => g(l)
      }), Js && !ue && l.value === gs && (ue = !0, J(r.location).catch((ie) => {
      }));
      const E = {};
      for (const ie in gs) Object.defineProperty(E, ie, {
        get: () => l.value[ie],
        enumerable: !0
      });
      z.provide(eo, T), z.provide(Pi, /* @__PURE__ */ Kl(E)), z.provide(ei, l);
      const P = z.unmount;
      y.add(z), z.unmount = function() {
        y.delete(z), y.size < 1 && (c = gs, C && C(), C = null, l.value = gs, ue = !1, pe = !1), P();
      };
    }
  };
  function ve(z) {
    return z.reduce((E, P) => E.then(() => q(P)), Promise.resolve());
  }
  return T;
}
function kp() {
  return At(eo);
}
function Yc(e) {
  return At(Pi);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ms = {
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
const Va = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function So(e) {
  return e != null;
}
function Sp(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (h) => s[h] ?? h, r = e.size ?? e.width ?? Ms.width, o = e.size ?? e.height ?? Ms.height, i = e.aliases?.filter((h) => typeof h == "string" && h.trim() !== "").map((h) => `lucide-${h}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? Va(...l) : Va("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? Ms["stroke-width"]) * Number(e.size ?? e.width ?? Ms.width) / Number(t.size ?? t.width ?? Ms.width) : t.strokeWidth ?? Ms["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(Ms).reduce((h, [m, _]) => (h[n(m)] = _, h), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && So(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && So(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && So(t.height) && {
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
      const [m, _, S] = h, b = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ..._ } : _;
      return S ? [m, b, S] : [m, b];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Cp = (e) => {
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
const ar = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ap = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Rp = /* @__PURE__ */ Symbol("lucide-icons");
function Ip() {
  return At(Rp, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ep = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && Ap(e),
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
  color: m,
  ..._
}, { slots: S }) => {
  const {
    size: b,
    color: A,
    strokeWidth: M = 2,
    absoluteStrokeWidth: Y = !1,
    nonScalingStroke: J = !1,
    class: ce = ""
  } = Ip(), Ae = ar(r) || ar(o) || r === !0 || o === !0 || Y === !0, re = ar(i) || ar(a) || i === !0 || a === !0 || J === !0;
  delete _.class;
  const U = S.default?.(), [, q, x = []] = Sp(n, {
    color: m ?? A,
    width: d ?? u ?? b,
    height: h ?? u ?? b,
    strokeWidth: l ?? c ?? M,
    absoluteStrokeWidth: Ae,
    nonScalingStroke: re,
    className: ce,
    hasA11yProp: U != null && U.length > 0 || Cp(_),
    attributes: _
  });
  return Fn("svg", q, [
    ...x.map(([Q, xe]) => Fn(Q, xe)),
    ...U ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Vt(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => Fn(
    Ep,
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
const $p = {
  name: "database",
  size: 24,
  node: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]
}, Op = Vt($p);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Tp = {
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
}, Xc = Vt(Tp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Pp = {
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
}, ti = Vt(Pp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Np = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, Mp = Vt(Np);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const zp = {
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
}, jp = Vt(zp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Dp = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, to = Vt(Dp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Lp = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, eu = Vt(Lp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Vp = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, Up = Vt(Vp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Fp = {
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
}, tu = Vt(Fp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Wp = {
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
}, su = Vt(Wp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Bp = {
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
}, Gp = Vt(Bp);
function Hp(e) {
  return hi() ? (Pl(e), !0) : !1;
}
const Co = /* @__PURE__ */ new WeakMap(), qp = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const s = e[0], n = (t = Qr()) == null ? void 0 : t.proxy;
  if (n == null && !Si())
    throw new Error("injectLocal must be called in setup");
  return n && Co.has(n) && s in Co.get(n) ? Co.get(n)[s] : At(...e);
}, Zp = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const Kp = Object.prototype.toString, Jp = (e) => Kp.call(e) === "[object Object]";
function Ua(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function Ao(e) {
  return Array.isArray(e) ? e : [e];
}
function Qp(e, t, s) {
  return As(
    e,
    t,
    {
      ...s,
      immediate: !0
    }
  );
}
const nu = Zp ? window : void 0;
function Yp(e) {
  var t;
  const s = Xs(e);
  return (t = s?.$el) != null ? t : s;
}
function Xp(...e) {
  const t = [], s = () => {
    t.forEach((a) => a()), t.length = 0;
  }, n = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = Ue(() => {
    const a = Ao(Xs(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = Qp(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => Yp(c))) != null ? l : [nu].filter((c) => c != null),
        Ao(Xs(r.value ? e[1] : e[0])),
        Ao(g(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Xs(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (s(), !a?.length || !l?.length || !c?.length)
        return;
      const d = Jp(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (h) => l.flatMap(
            (m) => c.map((_) => n(h, m, _, d))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), s();
  };
  return Hp(s), i;
}
// @__NO_SIDE_EFFECTS__
function eh() {
  const e = /* @__PURE__ */ On(!1), t = Qr();
  return t && hs(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function th(e) {
  const t = /* @__PURE__ */ eh();
  return Ue(() => (t.value, !!e()));
}
const sh = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function nh() {
  const e = Si() ? /* @__PURE__ */ qp(sh, null) : null;
  return typeof e == "number" ? e : void 0;
}
function rh(e, t = {}) {
  const { window: s = nu, ssrWidth: n = /* @__PURE__ */ nh() } = t, r = /* @__PURE__ */ th(() => s && "matchMedia" in s && typeof s.matchMedia == "function"), o = /* @__PURE__ */ On(typeof n == "number"), i = /* @__PURE__ */ On(), a = /* @__PURE__ */ On(!1), l = (c) => {
    a.value = c.matches;
  };
  return $d(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Xs(e).split(",");
      a.value = c.some((u) => {
        const d = u.includes("not all"), h = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), m = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let _ = !!(h || m);
        return h && _ && (_ = n >= Ua(h[1])), m && _ && (_ = n <= Ua(m[1])), d ? !_ : _;
      });
      return;
    }
    r.value && (i.value = s.matchMedia(Xs(e)), a.value = i.value.matches);
  }), Xp(i, "change", l, { passive: !0 }), Ue(() => a.value);
}
const ru = "comfymodal", Ni = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], oh = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function Es(e) {
  return typeof e == "string" && Ni.indexOf(e) !== -1;
}
function lr(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function ou(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || lr(r.slice(0, o)) !== ru) return t;
  const i = lr(r.slice(o + 1));
  if (!Es(i)) return t;
  let a = null;
  for (let l = 1; l < n.length; l++) {
    const c = n[l], u = c.indexOf("=");
    if (u === -1 || lr(c.slice(0, u)) !== "focus") continue;
    const d = lr(c.slice(u + 1));
    a = d === null || d === "" ? null : d;
    break;
  }
  return { matched: !0, page: i, focus: a };
}
function iu(e) {
  if (!Es(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + ru + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function Fa(e, t) {
  if (!t || !Es(t.page)) return "none";
  if (!e || !Es(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function ih(e, t) {
  if (e && Es(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = ou(t);
  return s.matched && Es(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
const ah = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function Ro(e) {
  return ah.has(e);
}
let Wa = 0;
function lh() {
  return Wa += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${Wa}`;
}
const Ot = /* @__PURE__ */ mn("studio-operations", () => {
  const e = /* @__PURE__ */ R(/* @__PURE__ */ new Map()), t = Ue(() => [...e.value.values()]), s = Ue(
    () => t.value.filter((h) => h.status === "pending" || h.status === "running")
  );
  function n(h) {
    return e.value.get(h);
  }
  function r(h) {
    const m = Date.now(), _ = lh(), S = h.status === "pending" ? "pending" : "running";
    return e.value.set(_, {
      id: _,
      kind: h.kind,
      label: h.label,
      status: S,
      progress: h.progress,
      message: h.message,
      startedAt: m,
      finishedAt: void 0,
      workspaceId: h.workspaceId
    }), _;
  }
  function o(h, m) {
    const _ = e.value.get(h);
    if (!_) return;
    const { status: S, ...b } = m, A = { ..._, ...b };
    !Ro(_.status) && S !== void 0 && !Ro(S) && (A.status = S), e.value.set(h, A);
  }
  function i(h, m, _) {
    const S = e.value.get(h);
    !S || Ro(S.status) || e.value.set(h, {
      ...S,
      status: m,
      message: _ === void 0 ? S.message : _,
      finishedAt: Date.now()
    });
  }
  function a(h, m) {
    i(h, "completed", m);
  }
  function l(h, m) {
    i(h, "failed", m);
  }
  function c(h, m) {
    i(h, "canceled", m);
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
var Ge;
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
})(Ge || (Ge = {}));
var Ba;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(Ba || (Ba = {}));
const ge = Ge.arrayToEnum([
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
]), ks = (e) => {
  switch (typeof e) {
    case "undefined":
      return ge.undefined;
    case "string":
      return ge.string;
    case "number":
      return Number.isNaN(e) ? ge.nan : ge.number;
    case "boolean":
      return ge.boolean;
    case "function":
      return ge.function;
    case "bigint":
      return ge.bigint;
    case "symbol":
      return ge.symbol;
    case "object":
      return Array.isArray(e) ? ge.array : e === null ? ge.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? ge.promise : typeof Map < "u" && e instanceof Map ? ge.map : typeof Set < "u" && e instanceof Set ? ge.set : typeof Date < "u" && e instanceof Date ? ge.date : ge.object;
    default:
      return ge.unknown;
  }
}, ee = Ge.arrayToEnum([
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
class ms extends Error {
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
    if (!(t instanceof ms))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, Ge.jsonStringifyReplacer, 2);
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
ms.create = (e) => new ms(e);
const si = (e, t) => {
  let s;
  switch (e.code) {
    case ee.invalid_type:
      e.received === ge.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case ee.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, Ge.jsonStringifyReplacer)}`;
      break;
    case ee.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${Ge.joinValues(e.keys, ", ")}`;
      break;
    case ee.invalid_union:
      s = "Invalid input";
      break;
    case ee.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${Ge.joinValues(e.options)}`;
      break;
    case ee.invalid_enum_value:
      s = `Invalid enum value. Expected ${Ge.joinValues(e.options)}, received '${e.received}'`;
      break;
    case ee.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case ee.invalid_return_type:
      s = "Invalid function return type";
      break;
    case ee.invalid_date:
      s = "Invalid date";
      break;
    case ee.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : Ge.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case ee.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case ee.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case ee.custom:
      s = "Invalid input";
      break;
    case ee.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case ee.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case ee.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, Ge.assertNever(e);
  }
  return { message: s };
};
let ch = si;
function uh() {
  return ch;
}
const dh = (e) => {
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
function de(e, t) {
  const s = uh(), n = dh({
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
      s === si ? void 0 : si
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(n);
}
class St {
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
        return Te;
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
    return St.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const r of s) {
      const { key: o, value: i } = r;
      if (o.status === "aborted" || i.status === "aborted")
        return Te;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (n[o.value] = i.value);
    }
    return { status: t.value, value: n };
  }
}
const Te = Object.freeze({
  status: "aborted"
}), Cn = (e) => ({ status: "dirty", value: e }), Nt = (e) => ({ status: "valid", value: e }), Ga = (e) => e.status === "aborted", Ha = (e) => e.status === "dirty", ln = (e) => e.status === "valid", Ir = (e) => typeof Promise < "u" && e instanceof Promise;
var be;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(be || (be = {}));
class es {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const qa = (e, t) => {
  if (ln(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new ms(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function Me(e) {
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
class Fe {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return ks(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: ks(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new St(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: ks(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (Ir(s))
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
      parsedType: ks(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return qa(n, r);
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
      parsedType: ks(t)
    };
    if (!this["~standard"].async)
      try {
        const n = this._parseSync({ data: t, path: [], parent: s });
        return ln(n) ? {
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
    return this._parseAsync({ data: t, path: [], parent: s }).then((n) => ln(n) ? {
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
      parsedType: ks(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (Ir(r) ? r : Promise.resolve(r));
    return qa(n, o);
  }
  refine(t, s) {
    const n = (r) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(r) : s;
    return this._refinement((r, o) => {
      const i = t(r), a = () => o.addIssue({
        code: ee.custom,
        ...n(r)
      });
      return typeof Promise < "u" && i instanceof Promise ? i.then((l) => l ? !0 : (a(), !1)) : i ? !0 : (a(), !1);
    });
  }
  refinement(t, s) {
    return this._refinement((n, r) => t(n) ? !0 : (r.addIssue(typeof s == "function" ? s(n, r) : s), !1));
  }
  _refinement(t) {
    return new dn({
      schema: this,
      typeName: $e.ZodEffects,
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
    return Rs.create(this, this._def);
  }
  nullable() {
    return fn.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return Jt.create(this);
  }
  promise() {
    return Pr.create(this, this._def);
  }
  or(t) {
    return $r.create([this, t], this._def);
  }
  and(t) {
    return Or.create(this, t, this._def);
  }
  transform(t) {
    return new dn({
      ...Me(this._def),
      schema: this,
      typeName: $e.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new oi({
      ...Me(this._def),
      innerType: this,
      defaultValue: s,
      typeName: $e.ZodDefault
    });
  }
  brand() {
    return new Nh({
      typeName: $e.ZodBranded,
      type: this,
      ...Me(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new ii({
      ...Me(this._def),
      innerType: this,
      catchValue: s,
      typeName: $e.ZodCatch
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
    return Mi.create(this, t);
  }
  readonly() {
    return ai.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const fh = /^c[^\s-]{8,}$/i, mh = /^[0-9a-z]+$/, ph = /^[0-9A-HJKMNP-TV-Z]{26}$/i, hh = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, gh = /^[a-z0-9_-]{21}$/i, vh = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, yh = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, bh = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, wh = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let Io;
const _h = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, xh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, kh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, Sh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, Ch = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, Ah = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, au = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", Rh = new RegExp(`^${au}$`);
function lu(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function Ih(e) {
  return new RegExp(`^${lu(e)}$`);
}
function Eh(e) {
  let t = `${au}T${lu(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function $h(e, t) {
  return !!((t === "v4" || !t) && _h.test(e) || (t === "v6" || !t) && kh.test(e));
}
function Oh(e, t) {
  if (!vh.test(e))
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
function Th(e, t) {
  return !!((t === "v4" || !t) && xh.test(e) || (t === "v6" || !t) && Sh.test(e));
}
class cs extends Fe {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== ge.string) {
      const o = this._getOrReturnCtx(t);
      return de(o, {
        code: ee.invalid_type,
        expected: ge.string,
        received: o.parsedType
      }), Te;
    }
    const n = new St();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), de(r, {
          code: ee.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), de(r, {
          code: ee.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? de(r, {
          code: ee.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && de(r, {
          code: ee.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        bh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "email",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        Io || (Io = new RegExp(wh, "u")), Io.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "emoji",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        hh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "uuid",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        gh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "nanoid",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        fh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "cuid",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        mh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "cuid2",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        ph.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
          validation: "ulid",
          code: ee.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), de(r, {
            validation: "url",
            code: ee.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "regex",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? Eh(o).test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? Rh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? Ih(o).test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? yh.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "duration",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? $h(t.data, o.version) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "ip",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? Oh(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "jwt",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Th(t.data, o.version) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "cidr",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? Ch.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "base64",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? Ah.test(t.data) || (r = this._getOrReturnCtx(t, r), de(r, {
        validation: "base64url",
        code: ee.invalid_string,
        message: o.message
      }), n.dirty()) : Ge.assertNever(o);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((r) => t.test(r), {
      validation: s,
      code: ee.invalid_string,
      ...be.errToObj(n)
    });
  }
  _addCheck(t) {
    return new cs({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...be.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...be.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...be.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...be.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...be.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...be.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...be.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...be.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...be.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...be.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...be.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...be.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...be.errToObj(t) });
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
      ...be.errToObj(t?.message)
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
      ...be.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...be.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...be.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...be.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...be.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...be.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...be.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...be.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...be.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, be.errToObj(t));
  }
  trim() {
    return new cs({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new cs({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new cs({
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
cs.create = (e) => new cs({
  checks: [],
  typeName: $e.ZodString,
  coerce: e?.coerce ?? !1,
  ...Me(e)
});
function Ph(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class cn extends Fe {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== ge.number) {
      const o = this._getOrReturnCtx(t);
      return de(o, {
        code: ee.invalid_type,
        expected: ge.number,
        received: o.parsedType
      }), Te;
    }
    let n;
    const r = new St();
    for (const o of this._def.checks)
      o.kind === "int" ? Ge.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? Ph(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.not_finite,
        message: o.message
      }), r.dirty()) : Ge.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, be.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, be.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, be.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, be.toString(s));
  }
  setLimit(t, s, n, r) {
    return new cn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: be.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new cn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: be.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: be.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: be.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: be.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: be.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: be.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: be.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: be.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: be.toString(t)
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && Ge.isInteger(t.value));
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
cn.create = (e) => new cn({
  checks: [],
  typeName: $e.ZodNumber,
  coerce: e?.coerce || !1,
  ...Me(e)
});
class Gn extends Fe {
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
    if (this._getType(t) !== ge.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new St();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), de(n, {
        code: ee.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : Ge.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return de(s, {
      code: ee.invalid_type,
      expected: ge.bigint,
      received: s.parsedType
    }), Te;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, be.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, be.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, be.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, be.toString(s));
  }
  setLimit(t, s, n, r) {
    return new Gn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: be.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Gn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: be.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: be.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: be.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: be.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: be.toString(s)
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
Gn.create = (e) => new Gn({
  checks: [],
  typeName: $e.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...Me(e)
});
class ni extends Fe {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== ge.boolean) {
      const n = this._getOrReturnCtx(t);
      return de(n, {
        code: ee.invalid_type,
        expected: ge.boolean,
        received: n.parsedType
      }), Te;
    }
    return Nt(t.data);
  }
}
ni.create = (e) => new ni({
  typeName: $e.ZodBoolean,
  coerce: e?.coerce || !1,
  ...Me(e)
});
class Er extends Fe {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== ge.date) {
      const o = this._getOrReturnCtx(t);
      return de(o, {
        code: ee.invalid_type,
        expected: ge.date,
        received: o.parsedType
      }), Te;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return de(o, {
        code: ee.invalid_date
      }), Te;
    }
    const n = new St();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), de(r, {
        code: ee.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), n.dirty()) : Ge.assertNever(o);
    return {
      status: n.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new Er({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: be.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: be.toString(s)
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
Er.create = (e) => new Er({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: $e.ZodDate,
  ...Me(e)
});
class Za extends Fe {
  _parse(t) {
    if (this._getType(t) !== ge.symbol) {
      const n = this._getOrReturnCtx(t);
      return de(n, {
        code: ee.invalid_type,
        expected: ge.symbol,
        received: n.parsedType
      }), Te;
    }
    return Nt(t.data);
  }
}
Za.create = (e) => new Za({
  typeName: $e.ZodSymbol,
  ...Me(e)
});
class Ka extends Fe {
  _parse(t) {
    if (this._getType(t) !== ge.undefined) {
      const n = this._getOrReturnCtx(t);
      return de(n, {
        code: ee.invalid_type,
        expected: ge.undefined,
        received: n.parsedType
      }), Te;
    }
    return Nt(t.data);
  }
}
Ka.create = (e) => new Ka({
  typeName: $e.ZodUndefined,
  ...Me(e)
});
class Ja extends Fe {
  _parse(t) {
    if (this._getType(t) !== ge.null) {
      const n = this._getOrReturnCtx(t);
      return de(n, {
        code: ee.invalid_type,
        expected: ge.null,
        received: n.parsedType
      }), Te;
    }
    return Nt(t.data);
  }
}
Ja.create = (e) => new Ja({
  typeName: $e.ZodNull,
  ...Me(e)
});
class Qa extends Fe {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return Nt(t.data);
  }
}
Qa.create = (e) => new Qa({
  typeName: $e.ZodAny,
  ...Me(e)
});
class Ya extends Fe {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return Nt(t.data);
  }
}
Ya.create = (e) => new Ya({
  typeName: $e.ZodUnknown,
  ...Me(e)
});
class $s extends Fe {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return de(s, {
      code: ee.invalid_type,
      expected: ge.never,
      received: s.parsedType
    }), Te;
  }
}
$s.create = (e) => new $s({
  typeName: $e.ZodNever,
  ...Me(e)
});
class Xa extends Fe {
  _parse(t) {
    if (this._getType(t) !== ge.undefined) {
      const n = this._getOrReturnCtx(t);
      return de(n, {
        code: ee.invalid_type,
        expected: ge.void,
        received: n.parsedType
      }), Te;
    }
    return Nt(t.data);
  }
}
Xa.create = (e) => new Xa({
  typeName: $e.ZodVoid,
  ...Me(e)
});
class Jt extends Fe {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== ge.array)
      return de(s, {
        code: ee.invalid_type,
        expected: ge.array,
        received: s.parsedType
      }), Te;
    if (r.exactLength !== null) {
      const i = s.data.length > r.exactLength.value, a = s.data.length < r.exactLength.value;
      (i || a) && (de(s, {
        code: i ? ee.too_big : ee.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (de(s, {
      code: ee.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (de(s, {
      code: ee.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((i, a) => r.type._parseAsync(new es(s, i, s.path, a)))).then((i) => St.mergeArray(n, i));
    const o = [...s.data].map((i, a) => r.type._parseSync(new es(s, i, s.path, a)));
    return St.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new Jt({
      ...this._def,
      minLength: { value: t, message: be.toString(s) }
    });
  }
  max(t, s) {
    return new Jt({
      ...this._def,
      maxLength: { value: t, message: be.toString(s) }
    });
  }
  length(t, s) {
    return new Jt({
      ...this._def,
      exactLength: { value: t, message: be.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Jt.create = (e, t) => new Jt({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: $e.ZodArray,
  ...Me(t)
});
function Qs(e) {
  if (e instanceof ct) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = Rs.create(Qs(n));
    }
    return new ct({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof Jt ? new Jt({
    ...e._def,
    type: Qs(e.element)
  }) : e instanceof Rs ? Rs.create(Qs(e.unwrap())) : e instanceof fn ? fn.create(Qs(e.unwrap())) : e instanceof Bs ? Bs.create(e.items.map((t) => Qs(t))) : e;
}
class ct extends Fe {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = Ge.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== ge.object) {
      const c = this._getOrReturnCtx(t);
      return de(c, {
        code: ee.invalid_type,
        expected: ge.object,
        received: c.parsedType
      }), Te;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof $s && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], d = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new es(r, d, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof $s) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && (de(r, {
          code: ee.unrecognized_keys,
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
            new es(r, d, r.path, u)
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
    }).then((c) => St.mergeObjectSync(n, c)) : St.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return be.errToObj, new ct({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: be.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new ct({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new ct({
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
    return new ct({
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
    return new ct({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: $e.ZodObject
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
    return new ct({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of Ge.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new ct({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of Ge.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new ct({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return Qs(this);
  }
  partial(t) {
    const s = {};
    for (const n of Ge.objectKeys(this.shape)) {
      const r = this.shape[n];
      t && !t[n] ? s[n] = r : s[n] = r.optional();
    }
    return new ct({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of Ge.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let o = this.shape[n];
        for (; o instanceof Rs; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new ct({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return cu(Ge.objectKeys(this.shape));
  }
}
ct.create = (e, t) => new ct({
  shape: () => e,
  unknownKeys: "strip",
  catchall: $s.create(),
  typeName: $e.ZodObject,
  ...Me(t)
});
ct.strictCreate = (e, t) => new ct({
  shape: () => e,
  unknownKeys: "strict",
  catchall: $s.create(),
  typeName: $e.ZodObject,
  ...Me(t)
});
ct.lazycreate = (e, t) => new ct({
  shape: e,
  unknownKeys: "strip",
  catchall: $s.create(),
  typeName: $e.ZodObject,
  ...Me(t)
});
class $r extends Fe {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return s.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new ms(a.ctx.common.issues));
      return de(s, {
        code: ee.invalid_union,
        unionErrors: i
      }), Te;
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
      const a = i.map((l) => new ms(l));
      return de(s, {
        code: ee.invalid_union,
        unionErrors: a
      }), Te;
    }
  }
  get options() {
    return this._def.options;
  }
}
$r.create = (e, t) => new $r({
  options: e,
  typeName: $e.ZodUnion,
  ...Me(t)
});
function ri(e, t) {
  const s = ks(e), n = ks(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === ge.object && n === ge.object) {
    const r = Ge.objectKeys(t), o = Ge.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = ri(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (s === ge.array && n === ge.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = ri(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === ge.date && n === ge.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class Or extends Fe {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, i) => {
      if (Ga(o) || Ga(i))
        return Te;
      const a = ri(o.value, i.value);
      return a.valid ? ((Ha(o) || Ha(i)) && s.dirty(), { status: s.value, value: a.data }) : (de(n, {
        code: ee.invalid_intersection_types
      }), Te);
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
Or.create = (e, t, s) => new Or({
  left: e,
  right: t,
  typeName: $e.ZodIntersection,
  ...Me(s)
});
class Bs extends Fe {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== ge.array)
      return de(n, {
        code: ee.invalid_type,
        expected: ge.array,
        received: n.parsedType
      }), Te;
    if (n.data.length < this._def.items.length)
      return de(n, {
        code: ee.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), Te;
    !this._def.rest && n.data.length > this._def.items.length && (de(n, {
      code: ee.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new es(n, i, n.path, a)) : null;
    }).filter((i) => !!i);
    return n.common.async ? Promise.all(o).then((i) => St.mergeArray(s, i)) : St.mergeArray(s, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Bs({
      ...this._def,
      rest: t
    });
  }
}
Bs.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Bs({
    items: e,
    typeName: $e.ZodTuple,
    rest: null,
    ...Me(t)
  });
};
class Tr extends Fe {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== ge.object)
      return de(n, {
        code: ee.invalid_type,
        expected: ge.object,
        received: n.parsedType
      }), Te;
    const r = [], o = this._def.keyType, i = this._def.valueType;
    for (const a in n.data)
      r.push({
        key: o._parse(new es(n, a, n.path, a)),
        value: i._parse(new es(n, n.data[a], n.path, a)),
        alwaysSet: a in n.data
      });
    return n.common.async ? St.mergeObjectAsync(s, r) : St.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof Fe ? new Tr({
      keyType: t,
      valueType: s,
      typeName: $e.ZodRecord,
      ...Me(n)
    }) : new Tr({
      keyType: cs.create(),
      valueType: t,
      typeName: $e.ZodRecord,
      ...Me(s)
    });
  }
}
class el extends Fe {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== ge.map)
      return de(n, {
        code: ee.invalid_type,
        expected: ge.map,
        received: n.parsedType
      }), Te;
    const r = this._def.keyType, o = this._def.valueType, i = [...n.data.entries()].map(([a, l], c) => ({
      key: r._parse(new es(n, a, n.path, [c, "key"])),
      value: o._parse(new es(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return Te;
          (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
        }
        return { status: s.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return Te;
        (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
      }
      return { status: s.value, value: a };
    }
  }
}
el.create = (e, t, s) => new el({
  valueType: t,
  keyType: e,
  typeName: $e.ZodMap,
  ...Me(s)
});
class Hn extends Fe {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== ge.set)
      return de(n, {
        code: ee.invalid_type,
        expected: ge.set,
        received: n.parsedType
      }), Te;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (de(n, {
      code: ee.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (de(n, {
      code: ee.too_big,
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
          return Te;
        u.status === "dirty" && s.dirty(), c.add(u.value);
      }
      return { status: s.value, value: c };
    }
    const a = [...n.data.values()].map((l, c) => o._parse(new es(n, l, n.path, c)));
    return n.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, s) {
    return new Hn({
      ...this._def,
      minSize: { value: t, message: be.toString(s) }
    });
  }
  max(t, s) {
    return new Hn({
      ...this._def,
      maxSize: { value: t, message: be.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Hn.create = (e, t) => new Hn({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: $e.ZodSet,
  ...Me(t)
});
class tl extends Fe {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
tl.create = (e, t) => new tl({
  getter: e,
  typeName: $e.ZodLazy,
  ...Me(t)
});
class sl extends Fe {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return de(s, {
        received: s.data,
        code: ee.invalid_literal,
        expected: this._def.value
      }), Te;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
sl.create = (e, t) => new sl({
  value: e,
  typeName: $e.ZodLiteral,
  ...Me(t)
});
function cu(e, t) {
  return new un({
    values: e,
    typeName: $e.ZodEnum,
    ...Me(t)
  });
}
class un extends Fe {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return de(s, {
        expected: Ge.joinValues(n),
        received: s.parsedType,
        code: ee.invalid_type
      }), Te;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return de(s, {
        received: s.data,
        code: ee.invalid_enum_value,
        options: n
      }), Te;
    }
    return Nt(t.data);
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
    return un.create(t, {
      ...this._def,
      ...s
    });
  }
  exclude(t, s = this._def) {
    return un.create(this.options.filter((n) => !t.includes(n)), {
      ...this._def,
      ...s
    });
  }
}
un.create = cu;
class nl extends Fe {
  _parse(t) {
    const s = Ge.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== ge.string && n.parsedType !== ge.number) {
      const r = Ge.objectValues(s);
      return de(n, {
        expected: Ge.joinValues(r),
        received: n.parsedType,
        code: ee.invalid_type
      }), Te;
    }
    if (this._cache || (this._cache = new Set(Ge.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = Ge.objectValues(s);
      return de(n, {
        received: n.data,
        code: ee.invalid_enum_value,
        options: r
      }), Te;
    }
    return Nt(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
nl.create = (e, t) => new nl({
  values: e,
  typeName: $e.ZodNativeEnum,
  ...Me(t)
});
class Pr extends Fe {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== ge.promise && s.common.async === !1)
      return de(s, {
        code: ee.invalid_type,
        expected: ge.promise,
        received: s.parsedType
      }), Te;
    const n = s.parsedType === ge.promise ? s.data : Promise.resolve(s.data);
    return Nt(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
Pr.create = (e, t) => new Pr({
  type: e,
  typeName: $e.ZodPromise,
  ...Me(t)
});
class dn extends Fe {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === $e.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (i) => {
        de(n, i), i.fatal ? s.abort() : s.dirty();
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
            return Te;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? Te : l.status === "dirty" || s.value === "dirty" ? Cn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return Te;
        const a = this._def.schema._parseSync({
          data: i,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? Te : a.status === "dirty" || s.value === "dirty" ? Cn(a.value) : a;
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
        return a.status === "aborted" ? Te : (a.status === "dirty" && s.dirty(), i(a.value), { status: s.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => a.status === "aborted" ? Te : (a.status === "dirty" && s.dirty(), i(a.value).then(() => ({ status: s.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!ln(i))
          return Te;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => ln(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: s.value,
          value: a
        })) : Te);
    Ge.assertNever(r);
  }
}
dn.create = (e, t, s) => new dn({
  schema: e,
  typeName: $e.ZodEffects,
  effect: t,
  ...Me(s)
});
dn.createWithPreprocess = (e, t, s) => new dn({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: $e.ZodEffects,
  ...Me(s)
});
class Rs extends Fe {
  _parse(t) {
    return this._getType(t) === ge.undefined ? Nt(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Rs.create = (e, t) => new Rs({
  innerType: e,
  typeName: $e.ZodOptional,
  ...Me(t)
});
class fn extends Fe {
  _parse(t) {
    return this._getType(t) === ge.null ? Nt(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
fn.create = (e, t) => new fn({
  innerType: e,
  typeName: $e.ZodNullable,
  ...Me(t)
});
class oi extends Fe {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === ge.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
oi.create = (e, t) => new oi({
  innerType: e,
  typeName: $e.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...Me(t)
});
class ii extends Fe {
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
    return Ir(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new ms(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new ms(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
ii.create = (e, t) => new ii({
  innerType: e,
  typeName: $e.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...Me(t)
});
class rl extends Fe {
  _parse(t) {
    if (this._getType(t) !== ge.nan) {
      const n = this._getOrReturnCtx(t);
      return de(n, {
        code: ee.invalid_type,
        expected: ge.nan,
        received: n.parsedType
      }), Te;
    }
    return { status: "valid", value: t.data };
  }
}
rl.create = (e) => new rl({
  typeName: $e.ZodNaN,
  ...Me(e)
});
class Nh extends Fe {
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
class Mi extends Fe {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? Te : o.status === "dirty" ? (s.dirty(), Cn(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? Te : r.status === "dirty" ? (s.dirty(), {
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
    return new Mi({
      in: t,
      out: s,
      typeName: $e.ZodPipeline
    });
  }
}
class ai extends Fe {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (ln(r) && (r.value = Object.freeze(r.value)), r);
    return Ir(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
ai.create = (e, t) => new ai({
  innerType: e,
  typeName: $e.ZodReadonly,
  ...Me(t)
});
var $e;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})($e || ($e = {}));
const mt = cs.create, Eo = cn.create, cr = ni.create;
$s.create;
const uu = Jt.create, zi = ct.create;
$r.create;
Or.create;
Bs.create;
const Mh = Tr.create, li = un.create;
Pr.create;
Rs.create;
fn.create;
const zh = "comfymodal.studio.vue.";
function jh() {
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
function Dh() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return jh();
}
function Ys(e, t, s, n) {
  const r = zh + e, o = Dh();
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
const Lh = "/comfymodal";
class Vh extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function Uh(e, t) {
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
function Fh(e, t) {
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
async function se(e, t = {}, s = fetch) {
  const {
    method: n = "GET",
    body: r,
    signal: o,
    timeoutMs: i,
    headers: a = {}
  } = t, { signal: l, cleanup: c } = Fh(o, i);
  try {
    if (l && l.aborted) throw l.reason;
    const u = await s(Lh + e, {
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
      throw new Vh(
        u.status,
        Uh(h, `Request failed with status ${u.status}`),
        h
      );
    return h;
  } finally {
    c();
  }
}
const Wh = zi({ value: mt(), label: mt() }).passthrough(), Bh = zi({
  gpu: mt().default(""),
  default_gpu: mt().default(""),
  available_gpus: uu(Wh).default([]),
  persisted_gpu: mt().default(""),
  output_format: mt().default("original"),
  quality: Eo().default(75),
  webp_lossless_compression: mt().default("balanced"),
  auto_save_local: cr().default(!1),
  save_folder: mt().default(""),
  save_metadata_sidecar: cr().default(!0),
  preview_default: li(["off", "on"]).default("off"),
  preview_codec: mt().default("webp"),
  preview_quality: Eo().default(70),
  data_saver_default: li(["off", "on"]).default("off"),
  data_saver_codec: mt().default("webp"),
  data_saver_quality: Eo().default(70),
  execution_mode: mt().default("v2"),
  execution_mode_source: mt().default(""),
  execution_mode_locked: cr().default(!1),
  engine_migration_notice: mt().nullable().default(null),
  skip_plan_validation: cr().default(!1),
  golden_gpu_order: Mh(mt()).default({})
}).passthrough(), Gh = zi({ status: mt().optional(), level: mt().default("off"), effective: mt().default("off") }).passthrough();
async function ur() {
  return Bh.parse(await se("/config"));
}
async function Hh(e) {
  return se("/config", { method: "POST", body: e });
}
async function ol() {
  return Gh.parse(await se("/profile/level"));
}
async function qh(e) {
  return se("/profile/level", { method: "POST", body: { level: e } });
}
async function Zh() {
  return se("/studio/golden/profiles");
}
async function Kh(e, t) {
  return se("/studio/golden/gpu-order", { method: "POST", body: { profile: e, order: t } });
}
async function Jh(e) {
  return se("/studio/golden/deploy", { method: "POST", body: { profile: e } });
}
async function il(e) {
  return se(`/studio/golden/deploy?profile=${encodeURIComponent(e)}`);
}
const vn = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function al(e) {
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
    localStorage.setItem(vn.outputFormat, s.output_format), localStorage.setItem(vn.quality, String(s.quality)), localStorage.setItem(vn.autoSaveLocal, String(s.auto_save_local)), localStorage.setItem(vn.saveFolder, s.save_folder), localStorage.setItem(vn.saveMetadataSidecar, String(s.save_metadata_sidecar));
  } catch {
  }
  return window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: s })), t;
}
const du = "comfymodal-studio";
function so(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(du), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function Qe(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(du);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
function qn() {
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
function Qh(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function Yh(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function An(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    Qh(s), i += 1, o && o(i);
    const a = await n(s, i);
    if (r(a)) return a;
    await Yh(t, s);
  }
}
const Xh = li(["comfortable", "compact"]), $o = Ys(
  "shell.density",
  "comfortable",
  Xh
), eg = [
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
], fu = [
  "generation",
  "outputs",
  "accounts",
  "interface",
  "advanced"
];
function tg(e) {
  try {
    return localStorage.getItem(e);
  } catch {
    return null;
  }
}
function yn(e, t) {
  try {
    localStorage.setItem(e, t);
  } catch {
  }
}
function bn(e) {
  for (const t of e)
    try {
      localStorage.removeItem(t);
    } catch {
    }
}
const mu = /* @__PURE__ */ mn("studio-settings", () => {
  const e = /* @__PURE__ */ R("generation"), t = /* @__PURE__ */ R($o.read()), s = /* @__PURE__ */ R(null), n = /* @__PURE__ */ R("off"), r = /* @__PURE__ */ R("off"), o = /* @__PURE__ */ R(!1), i = /* @__PURE__ */ R(!1), a = /* @__PURE__ */ R(null), l = /* @__PURE__ */ R(!1), c = /* @__PURE__ */ R([]), u = /* @__PURE__ */ R(null), d = /* @__PURE__ */ R(null), h = /* @__PURE__ */ R(!1);
  let m = !1, _ = null;
  const S = Ys("golden.profile", "", mt()), b = Ys(
    "golden.favorites",
    [],
    uu(mt())
  ), A = Ys("history.columns", "6"), M = Ys("inventory.interval", "300"), Y = /* @__PURE__ */ R(S.read()), J = /* @__PURE__ */ R(b.read()), ce = /* @__PURE__ */ R(A.read()), Ae = /* @__PURE__ */ R(M.read()), re = Ue(() => s.value?.gpu ?? ""), U = Ue(() => {
    const E = s.value?.golden_gpu_order;
    return E && typeof E == "object" ? E : {};
  });
  async function q() {
    o.value = !0, a.value = null;
    try {
      const [E, P] = await Promise.all([ur(), ol()]);
      s.value = E, n.value = P.level, r.value = P.effective || P.level, al(E), l.value = !0;
    } catch (E) {
      throw a.value = E instanceof Error ? E.message : "Could not load Settings", E;
    } finally {
      o.value = !1, m && (m = !1, q());
    }
  }
  async function x(E) {
    i.value = !0, a.value = null;
    try {
      await Hh(E);
      const P = await ur();
      s.value = P, al(P), Qe("settings");
    } catch (P) {
      try {
        s.value = await ur();
      } catch {
      }
      throw a.value = P instanceof Error ? P.message : "Could not save Settings", P;
    } finally {
      i.value = !1;
    }
  }
  async function Q(E) {
    const P = n.value;
    n.value = E, yn("comfymodal_heavy_tracing", E);
    try {
      await qh(E);
      const ie = await ol();
      r.value = ie.effective || ie.level, Qe("settings");
    } catch (ie) {
      throw n.value = P, yn("comfymodal_heavy_tracing", P), ie;
    }
  }
  async function xe(E) {
    const P = tg("comfymodal_skip_plan_validation");
    yn("comfymodal_skip_plan_validation", E ? "1" : "0");
    try {
      await x({ skip_plan_validation: E });
    } catch (ie) {
      if (P === null)
        try {
          localStorage.removeItem("comfymodal_skip_plan_validation");
        } catch {
        }
      else
        yn("comfymodal_skip_plan_validation", P);
      throw ie;
    }
  }
  async function C() {
    u.value = null;
    try {
      const E = await Zh();
      if (!E || E.status !== "ok" || !Array.isArray(E.profiles))
        throw new Error(
          E && E.message || "invalid catalog response"
        );
      const P = new Set(
        E.profiles.filter((v) => v && typeof v.name == "string").map((v) => v.name)
      );
      c.value = E.profiles.filter((v) => v && P.has(v.name));
      const ie = s.value?.golden_profile, p = typeof ie == "string" ? ie : "";
      if (P.has(p))
        Y.value = p;
      else if (!P.has(Y.value)) {
        const v = typeof E.defaultProfile == "string" && P.has(E.defaultProfile) ? E.defaultProfile : "";
        Y.value = v;
      }
      S.write(Y.value), Y.value && (d.value = await il(
        Y.value
      ));
    } catch (E) {
      throw u.value = E instanceof Error ? E.message : "Could not load Golden profiles", E;
    }
  }
  function te(E) {
    Y.value = E, S.write(E);
  }
  function Ne(E) {
    const P = J.value.includes(E) ? J.value.filter((ie) => ie !== E) : [...J.value, E];
    J.value = P, b.write(P);
  }
  async function ke(E, P) {
    await Kh(E, P);
    const ie = await ur();
    s.value = ie, Qe("settings");
  }
  async function pe(E) {
    const P = Ot(), ie = P.start({ kind: "deploy", label: `Deploy Golden ${E}` });
    h.value = !0;
    try {
      await Jh(E), await An({
        intervalMs: 2e3,
        run: async () => {
          const p = await il(E), v = String(p?.state ?? "unknown");
          return P.patch(ie, { message: `Golden deploy: ${v}` }), p;
        },
        done: (p) => p?.state === "done" || p?.state === "failed"
      }).then((p) => {
        if (p?.state === "failed")
          throw new Error(String(p.output || p.message || "Golden deploy failed"));
        d.value = p;
      }), P.finish(ie, "Golden deploy finished"), await C();
    } catch (p) {
      throw P.fail(
        ie,
        p instanceof Error ? p.message : "Golden deploy failed"
      ), p;
    } finally {
      h.value = !1;
    }
    return ie;
  }
  function Ce(E) {
    ce.value = E, A.write(E);
  }
  function ze(E) {
    Ae.value = E, M.write(E);
  }
  async function oe(E) {
    if (E === "generation") {
      bn(["comfymodal_gpu", "comfymodal_preview_default", "comfymodal_preview_codec", "comfymodal_preview_quality", "comfymodal_data_saver_default", "comfymodal_data_saver_codec", "comfymodal_data_saver_quality"]);
      const P = s.value?.default_gpu || "rtx-pro-6000";
      await x({ gpu: P, golden_profile: null }), te("");
    } else E === "outputs" ? (bn(["comfymodal_output_format", "comfymodal_quality", "comfymodal_webp_lossless_compression", "comfymodal_auto_save_local", "comfymodal_save_folder", "comfymodal_save_metadata_sidecar"]), await x({
      output_format: "original",
      quality: 75,
      webp_lossless_compression: "balanced",
      auto_save_local: !1,
      save_metadata_sidecar: !0
    })) : E === "interface" ? (bn(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1", "comfymodal_remote_inventory_refresh_interval_s", "comfymodal-studio-history-columns"]), Ce("6"), ze("300")) : E === "advanced" && (bn(["comfymodal_heavy_tracing", "comfymodal_skip_plan_validation"]), await Q("off").catch(() => {
    }), await x({ skip_plan_validation: !1 }).catch(() => {
    }));
    Qe("settings");
  }
  async function tt() {
    bn(eg), te(""), J.value = [], b.write([]), Ce("6"), ze("300");
    const E = s.value?.default_gpu || "rtx-pro-6000";
    await x({ gpu: E, golden_profile: null }).catch(() => {
    }), await Q("off").catch(() => {
    }), await x({ skip_plan_validation: !1 }).catch(() => {
    }), await q().catch(() => {
    });
  }
  async function Je() {
    _ || (_ = so((E) => {
      if (E === "settings") {
        if (o.value) {
          m = !0;
          return;
        }
        q();
      }
    })), l.value || await q(), yn("comfymodal_heavy_tracing", n.value);
  }
  function ue(E) {
    fu.includes(E) && (e.value = E);
  }
  function y(E) {
    t.value = E, $o.write(E);
  }
  function T() {
    e.value = "generation", t.value = "comfortable", $o.write("comfortable");
  }
  const ve = qn();
  async function z(E) {
    const P = await ve.run(E);
    return P.stale ? null : P.value;
  }
  return {
    activeSection: e,
    density: t,
    config: s,
    profileLevel: n,
    effectiveProfileLevel: r,
    loading: o,
    saving: i,
    error: a,
    bootstrapped: l,
    goldenProfiles: c,
    goldenError: u,
    goldenDeployState: d,
    goldenDeploying: h,
    selectedGoldenProfile: Y,
    favoriteGoldenProfiles: J,
    columnsPreference: ce,
    refreshIntervalPreference: Ae,
    gpu: re,
    goldenGpuOrder: U,
    outputPreferences: Ue(() => s.value ? {
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
    load: q,
    initialize: Je,
    save: x,
    setProfile: Q,
    setSkipPlanValidation: xe,
    loadGolden: C,
    selectGoldenProfile: te,
    toggleGoldenFavorite: Ne,
    setGoldenGpuOrder: ke,
    deployGoldenProfile: pe,
    setHistoryColumns: Ce,
    setInventoryInterval: ze,
    resetSection: oe,
    resetAll: tt,
    loadSubresource: z,
    setSection: ue,
    setDensity: y,
    reset: T
  };
});
function Oo(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const r = String(n.id ?? "");
    return { id: r, label: String(n.label ?? r), isActive: r !== "" && r === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function pu(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function sg(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function ng() {
  return se("/workspaces");
}
async function rg(e) {
  return se("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function ll() {
  return pu(await se("/deploy/status"));
}
async function og() {
  return se("/deploy", { method: "POST" });
}
async function ig() {
  return se("/deploy/log");
}
async function ag(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return se(`/studio/inventory/refresh${t}`);
}
async function lg(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return se(`/studio/models${s}`);
}
async function cg(e = !1) {
  return se("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function ug() {
  return se("/studio/custom-nodes");
}
async function dg() {
  return se("/studio/custom-nodes/refresh", { method: "POST" });
}
async function fg(e) {
  return se("/workspaces", { method: "POST", body: e });
}
async function mg(e) {
  return se("/workspaces/swap", { method: "POST", body: e });
}
async function pg(e) {
  return se(`/workspaces/swap/${encodeURIComponent(e)}`);
}
function hg(e, t) {
  return { workspace_id: e, confirm: !0, selected_keys: t.slice() };
}
function cl(e) {
  const t = String(e && e.phase || "");
  if (t === "downloading_models") {
    const s = String(e && e.download_message || ""), n = Number(e && e.download_completed || 0), r = Number(e && e.download_total || 0) + Number(e && e.download_skipped || 0);
    return s || `Preparing downloads… ${n}/${r}`;
  }
  return t === "syncing_custom_nodes" ? String(e && e.sync_message || "Syncing custom nodes to Modal…") : t === "deploying" ? String(e && e.deploy_message || "Deploying workspace…") : t ? `Phase: ${t.replace(/_/g, " ")}` : "";
}
async function gg() {
  return se("/studio/custom-nodes/sync-status");
}
async function vg() {
  return se("/studio/custom-nodes/sync", { method: "POST" });
}
async function yg() {
  return se("/studio/custom-nodes/sync/rebuild-dependencies", { method: "POST" });
}
async function bg(e) {
  return se(`/studio/custom-nodes/sync/status/${encodeURIComponent(e)}`);
}
async function wg(e) {
  return se("/model/install", { method: "POST", body: e });
}
function _g(e) {
  const s = String(e || "").split("?")[0].split("#")[0].split("/").filter(Boolean).pop() || "";
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}
async function xg(e) {
  return se(`/download/status/${encodeURIComponent(e || "")}`);
}
async function kg(e) {
  return se("/studio/models/install-request", { method: "POST", body: e });
}
async function Sg(e) {
  return se("/studio/custom-nodes/install-request", { method: "POST", body: e });
}
async function Cg() {
  return se("/manifest/repair/scan", { method: "POST" });
}
async function Ag(e) {
  return se("/manifest/repair/apply", { method: "POST", body: { updates: e } });
}
async function Rg(e, t) {
  return se("/manifest/repair/delete-placeholder", { method: "POST", body: { folder: e, filename: t } });
}
async function Ig() {
  return se("/auth/status");
}
async function ul(e) {
  return se(e === "civitai" ? "/civitai-token" : "/hf-token");
}
async function Eg(e, t) {
  return se(e === "civitai" ? "/civitai-token" : "/hf-token", { method: "POST", body: { token: t } });
}
function dl(e) {
  return !!(e && typeof e == "object" && typeof e.token == "string" && e.token !== "");
}
async function $g() {
  return se("/health?mode=deploy");
}
const no = /* @__PURE__ */ mn("studio-infrastructure", () => {
  const e = /* @__PURE__ */ R("unknown"), t = /* @__PURE__ */ R(null), s = /* @__PURE__ */ R(null), n = /* @__PURE__ */ R([]), r = /* @__PURE__ */ R(null), o = /* @__PURE__ */ R(pu(null)), i = /* @__PURE__ */ R(null), a = /* @__PURE__ */ R([]), l = /* @__PURE__ */ R([]), c = /* @__PURE__ */ R([]), u = /* @__PURE__ */ R(null), d = /* @__PURE__ */ R(!1), h = /* @__PURE__ */ R(null), m = /* @__PURE__ */ R(!1), _ = /* @__PURE__ */ R(null), S = /* @__PURE__ */ R(null), b = /* @__PURE__ */ R(!1), A = /* @__PURE__ */ R(null), M = /* @__PURE__ */ R(!1), Y = /* @__PURE__ */ R(!1), J = /* @__PURE__ */ R(null), ce = /* @__PURE__ */ R(null), Ae = /* @__PURE__ */ R(null), re = qn(), U = /* @__PURE__ */ R(null), q = /* @__PURE__ */ R(null), x = /* @__PURE__ */ R(null);
  let Q = !1, xe = null;
  const C = Ue(() => n.value.find((Z) => Z.isActive) ?? null);
  function te(Z, le) {
    e.value = Z, t.value = le ?? null;
  }
  function Ne(Z) {
    s.value = Z;
  }
  function ke() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  function pe(Z) {
    _.value = Z;
  }
  async function Ce() {
    const Z = Oo(await ng());
    n.value = Z.rows, r.value = Z.activeId;
  }
  async function ze() {
    o.value = await ll(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function oe() {
    const Z = await re.run(async (Oe) => {
      const [De, Ie] = await Promise.all([lg(), ug()]);
      return Oe.aborted ? null : { modelResult: De, nodeResult: Ie };
    });
    if (Z.stale || !Z.value) return;
    const le = Z.value.modelResult.models;
    a.value = (Array.isArray(le) ? le : []).filter(
      (Oe) => !!Oe && typeof Oe == "object"
    );
    const ae = Z.value.nodeResult.custom_nodes;
    c.value = (Array.isArray(ae) ? ae : []).filter(
      (Oe) => !!Oe && typeof Oe == "object"
    );
  }
  async function tt() {
    d.value = !0, h.value = null;
    try {
      await Promise.all([Ce(), ze(), oe()]), s.value = "server inventory loaded";
    } catch (Z) {
      throw h.value = Z instanceof Error ? Z.message : "Could not load infrastructure", Z;
    } finally {
      d.value = !1, Q && (Q = !1, tt());
    }
  }
  async function Je() {
    xe || (xe = so((Z) => {
      if (Z === "workspace") {
        if (d.value) {
          Q = !0;
          return;
        }
        tt();
      }
    })), n.value.length || await tt();
  }
  async function ue(Z) {
    m.value = !0;
    try {
      const le = await fg(Z), ae = Oo(le);
      n.value = ae.rows, r.value = ae.activeId, Qe("workspace");
    } finally {
      m.value = !1;
    }
  }
  async function y(Z) {
    if (q.value || x.value)
      throw new Error("Cannot change workspace while an operation is active");
    m.value = !0;
    const le = n.value;
    try {
      const ae = await rg(Z);
      if (!ae || ae.status !== "ok")
        throw new Error(String(ae?.message || "Activation failed"));
      const Oe = Oo(ae);
      n.value = Oe.rows, r.value = Oe.activeId, pe(`Active workspace is now ${Oe.rows.find((De) => De.isActive)?.label || Z}.`), await ze(), Qe("workspace");
    } catch (ae) {
      throw n.value = le, ae;
    } finally {
      m.value = !1;
    }
  }
  async function T(Z, le) {
    const ae = Ot();
    if (q.value || x.value)
      throw new Error("Another operation is already active");
    m.value = !0, b.value = !1, S.value = null;
    const Oe = r.value ?? void 0, De = ae.start({
      kind: "workspace-swap",
      label: "Swap workspace",
      workspaceId: Oe
    });
    x.value = De;
    const Ie = new AbortController(), L = window.setTimeout(() => Ie.abort(), 1800 * 1e3);
    try {
      const K = await mg({ workspace_id: Z, ...le || {} }), ye = String(K.status || "");
      if (ye === "busy") throw new Error(String(K.message || "Deploy already running — try again later."));
      if (ye === "error") throw new Error(String(K.message || "Workspace swap failed."));
      if (ye === "confirm_required") {
        b.value = !0, ae.patch(De, { status: "pending", message: "Confirmation required" });
        return;
      }
      if (ye === "repair_required")
        throw ae.fail(De, String(K.message || "manifest repair required")), await k(), new Error(String(K.message || "manifest repair required"));
      if (ye === "review_required") {
        const We = (Array.isArray(K.to_install) ? K.to_install : []).map((Rt) => {
          const Mt = Rt;
          return {
            key: `${String(Mt.save_path || Mt.folder || "")}/${String(Mt.filename || "")}`,
            filename: String(Mt.filename || ""),
            folder: String(Mt.folder || Mt.save_path || "")
          };
        });
        S.value = {
          workspaceLabel: String(K.workspace_label || Z),
          toInstall: We,
          installCount: Number(K.install_count || We.length),
          presentCount: Number(K.present_count || 0),
          removeCount: Array.isArray(K.to_remove) ? K.to_remove.length : 0
        }, ae.patch(De, { status: "pending", message: "Review required" });
        return;
      }
      if (ye === "started" && K.swap_id) {
        await P(String(K.swap_id), De, Ie.signal, Oe);
        return;
      }
      throw new Error(String(K.message || "Unexpected swap response."));
    } catch (K) {
      if (b.value || S.value) throw K;
      const ye = K instanceof Error ? K.message : "Workspace swap failed";
      throw ae.fail(De, ye), pe(ye), K;
    } finally {
      window.clearTimeout(L), !b.value && !S.value && (x.value = null), m.value = !1;
    }
  }
  async function ve(Z) {
    b.value = !1, x.value = null, await T(Z, { confirm_prompt_interrupt: !0 });
  }
  async function z(Z, le) {
    const ae = x.value;
    S.value = null, x.value = null, ae && Ot().cancel(ae, "Superseded by review confirmation"), await T(Z, hg(Z, le));
  }
  async function E() {
    const Z = x.value;
    b.value = !1, S.value = null, x.value = null, m.value = !1, Z && Ot().cancel(Z, "Swap cancelled."), pe("Swap cancelled.");
  }
  async function P(Z, le, ae, Oe) {
    const De = Ot();
    try {
      await An({
        intervalMs: 1e3,
        signal: ae,
        run: async () => {
          const Ie = await pg(Z);
          return De.patch(le, { message: cl(Ie) || "Working…" }), pe(cl(Ie) || "Working…"), Ie;
        },
        done: (Ie) => String(Ie.status || "") !== "running"
      }).then((Ie) => {
        const L = String(Ie.status || "");
        if (L === "ok") {
          const K = String(Ie.workspace_label || "workspace");
          De.finish(le, `Swap done — ${K}. Deploy started.`), pe(`Done — ${K}. Deploy started.`);
        } else throw L === "repair_required" ? (De.fail(le, String(Ie.message || "manifest repair required")), k(), new Error(String(Ie.message || "manifest repair required"))) : L === "not_found" ? new Error("Swap status unavailable.") : new Error(
          String(Ie.message || Ie.error || Ie.deploy_message || "Workspace swap failed")
        );
      }), Oe && r.value, await Ce(), await ze(), Qe("workspace");
    } catch (Ie) {
      if (!b.value && !S.value) {
        const L = Ie instanceof Error ? Ie.message : "Workspace swap failed";
        try {
          De.fail(le, L);
        } catch {
        }
        pe(L);
      }
      throw Ie;
    } finally {
      x.value = null;
    }
  }
  async function ie() {
    const Z = Ot();
    if (q.value) return q.value;
    if (x.value) throw new Error("Cannot deploy while a swap is active");
    const le = r.value ?? void 0, ae = Z.start({
      kind: "deploy",
      label: "Deploy workspace",
      workspaceId: le
    });
    q.value = ae;
    const Oe = new AbortController();
    U.value = Oe;
    const De = window.setTimeout(() => Oe.abort(new DOMException("Deployment polling timed out", "TimeoutError")), 600 * 1e3);
    try {
      await og(), Z.patch(ae, { status: "running", message: "Deployment started" });
      const Ie = await An({
        intervalMs: 3e3,
        signal: Oe.signal,
        run: async () => {
          const L = await ll();
          return o.value = L, e.value = L.state, t.value = L.message || null, Z.patch(ae, { message: L.message || `Deployment: ${L.state}` }), L;
        },
        done: (L) => L.state === "ready" || L.state === "deployed_unwarmed" || L.state !== "deploying" && L.state !== "starting" && L.state !== "unknown"
      });
      if (!sg(Ie.state)) throw new Error(Ie.message || `Deployment ended in ${Ie.state}`);
      if (le && r.value !== le) throw new Error("Deployment target workspace changed");
      Z.finish(ae, Ie.message || "Deployment completed");
    } catch (Ie) {
      const L = Ie instanceof Error ? Ie.message : "Deployment failed";
      throw Z.fail(ae, L), Ie;
    } finally {
      window.clearTimeout(De), U.value = null, q.value = null;
    }
    return ae;
  }
  async function p() {
    const [Z, le, ae] = await Promise.all([
      Ig().catch(() => null),
      ul("hf").catch(() => null),
      ul("civitai").catch(() => null)
    ]);
    A.value = !!(Z && Z.connected === !0), M.value = dl(le), Y.value = dl(ae);
  }
  async function v(Z, le) {
    const ae = await Eg(Z, le);
    if (!ae || ae.status !== "ok")
      throw new Error(String(ae?.message || ae?.error || "Save failed."));
    return await p(), le ? "Saved." : "Cleared.";
  }
  async function k() {
    ce.value = null;
    const Z = await Cg();
    J.value = Z;
  }
  async function I(Z) {
    ce.value = null;
    const le = await Ag(Z);
    ce.value = String(le.message || "Repairs applied."), J.value = le;
  }
  async function j(Z, le) {
    await Rg(Z, le), await k();
  }
  async function B() {
    u.value = await gg();
  }
  async function w() {
    const Z = Ot(), le = Z.start({ kind: "node-sync", label: "Push custom-node plugins" });
    try {
      await vg(), Z.finish(le, "Plugins pushed"), await B(), Qe("workspace");
    } catch (ae) {
      throw Z.fail(le, ae instanceof Error ? ae.message : "Push failed"), ae;
    }
  }
  async function N() {
    const Z = Ot(), le = Z.start({ kind: "node-sync", label: "Rebuild custom-node dependencies" });
    try {
      const ae = await yg(), Oe = String(ae.sync_id || ae.syncId || "");
      Oe && await An({
        intervalMs: 3e3,
        run: async () => {
          const De = await bg(Oe);
          return Z.patch(le, { message: String(De.message || "Rebuilding…") }), De;
        },
        done: (De) => String(De.status || "") !== "running"
      }), Z.finish(le, "Dependencies rebuilt"), await B(), Qe("workspace");
    } catch (ae) {
      throw Z.fail(le, ae instanceof Error ? ae.message : "Rebuild failed"), ae;
    }
  }
  async function D(Z) {
    const le = Ot(), ae = le.start({ kind: "model-download", label: `Download ${String(Z.filename || Z.url || "model")}` });
    try {
      const Oe = await wg(Z), De = String(Oe.download_id || Oe.downloadId || "");
      if (!De) {
        le.finish(ae, "Install request accepted"), await oe();
        return;
      }
      await An({
        intervalMs: 2e3,
        run: async () => {
          const Ie = await xg(De);
          return le.patch(ae, {
            progress: typeof Ie.progress == "number" ? Ie.progress : void 0,
            message: String(Ie.message || "Downloading…")
          }), Ie;
        },
        done: (Ie) => String(Ie.status || "") !== "running"
      }).then((Ie) => {
        if (String(Ie.status || "") === "error")
          throw new Error(String(Ie.message || "Download failed"));
      }), le.finish(ae, "Download complete"), await oe(), Qe("workspace");
    } catch (Oe) {
      throw le.fail(ae, Oe instanceof Error ? Oe.message : "Download failed"), Oe;
    }
  }
  async function F(Z) {
    await kg(Z), await oe();
  }
  async function he(Z) {
    await Sg(Z), await oe();
  }
  async function ne() {
    await ag(0), await oe(), s.value = "inventory refreshed", Qe("workspace");
  }
  async function _e(Z = !0) {
    const le = await cg(Z);
    a.value = Array.isArray(le.models) ? le.models.filter((ae) => !!ae && typeof ae == "object") : a.value, await oe();
  }
  async function Re() {
    const Z = await dg();
    c.value = Array.isArray(Z.custom_nodes) ? Z.custom_nodes.filter((le) => !!le && typeof le == "object") : c.value, await oe();
  }
  async function Le() {
    i.value = await ig();
  }
  async function He() {
    Ae.value = await $g();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: r,
    activeWorkspace: C,
    deployStatus: o,
    deployLog: i,
    models: a,
    modelTypes: l,
    customNodes: c,
    customNodeSync: u,
    loading: d,
    error: h,
    busy: m,
    progress: _,
    swapReview: S,
    swapConfirmRequired: b,
    authConnected: A,
    hfConfigured: M,
    civitaiConfigured: Y,
    repairIssues: J,
    repairMessage: ce,
    health: Ae,
    deploymentOperationId: q,
    swapOperationId: x,
    setDeploy: te,
    setSyncSummary: Ne,
    reset: ke,
    load: tt,
    initialize: Je,
    loadWorkspaces: Ce,
    loadDeployment: ze,
    loadInventory: oe,
    saveWorkspace: ue,
    selectWorkspace: y,
    startSwap: T,
    confirmSwapInterrupt: ve,
    confirmSwapReview: z,
    cancelSwapDialog: E,
    deploy: ie,
    loadCredentials: p,
    saveCredential: v,
    scanRepair: k,
    applyRepair: I,
    deletePlaceholder: j,
    loadSyncStatus: B,
    pushPlugins: w,
    rebuildDependencies: N,
    installModel: D,
    installModelRequest: F,
    installCustomNode: he,
    refreshRemoteInventoryNow: ne,
    rescanModelsNow: _e,
    refreshCustomNodesNow: Re,
    loadLog: Le,
    loadHealth: He
  };
});
function hu(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = hu(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function gu() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = hu(e)) && (n && (n += " "), n += t);
  return n;
}
const Og = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, Tg = (e, t) => ({
  classGroupId: e,
  validator: t
}), vu = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), Nr = "-", fl = [], Pg = "arbitrary..", Ng = (e) => {
  const t = zg(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return Mg(i);
      const a = i.split(Nr), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return yu(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = n[i], c = s[i];
        return l ? c ? Og(c, l) : l : c || fl;
      }
      return s[i] || fl;
    }
  };
}, yu = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const r = e[t], o = s.nextPart.get(r);
  if (o) {
    const c = yu(e, t + 1, o);
    if (c) return c;
  }
  const i = s.validators;
  if (i === null)
    return;
  const a = t === 0 ? e.join(Nr) : e.slice(t).join(Nr), l = i.length;
  for (let c = 0; c < l; c++) {
    const u = i[c];
    if (u.validator(a))
      return u.classGroupId;
  }
}, Mg = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? Pg + n : void 0;
})(), zg = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return jg(s, t);
}, jg = (e, t) => {
  const s = vu();
  for (const n in e) {
    const r = e[n];
    ji(r, s, n, t);
  }
  return s;
}, ji = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    Dg(i, t, s, n);
  }
}, Dg = (e, t, s, n) => {
  if (typeof e == "string") {
    Lg(e, t, s);
    return;
  }
  if (typeof e == "function") {
    Vg(e, t, s, n);
    return;
  }
  Ug(e, t, s, n);
}, Lg = (e, t, s) => {
  const n = e === "" ? t : bu(t, e);
  n.classGroupId = s;
}, Vg = (e, t, s, n) => {
  if (Fg(e)) {
    ji(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(Tg(s, e));
}, Ug = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    ji(l, bu(t, a), s, n);
  }
}, bu = (e, t) => {
  let s = e;
  const n = t.split(Nr), r = n.length;
  for (let o = 0; o < r; o++) {
    const i = n[o];
    let a = s.nextPart.get(i);
    a || (a = vu(), s.nextPart.set(i, a)), s = a;
  }
  return s;
}, Fg = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Wg = (e) => {
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
}, ci = "!", ml = ":", Bg = [], pl = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), Gg = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let S = 0; S < u; S++) {
      const b = r[S];
      if (i === 0 && a === 0) {
        if (b === ml) {
          o.push(r.slice(l, S)), l = S + 1;
          continue;
        }
        if (b === "/") {
          c = S;
          continue;
        }
      }
      b === "[" ? i++ : b === "]" ? i-- : b === "(" ? a++ : b === ")" && a--;
    }
    const d = o.length === 0 ? r : r.slice(l);
    let h = d, m = !1;
    d.endsWith(ci) ? (h = d.slice(0, -1), m = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      d.startsWith(ci) && (h = d.slice(1), m = !0)
    );
    const _ = c && c > l ? c - l : void 0;
    return pl(o, m, h, _);
  };
  if (t) {
    const r = t + ml, o = n;
    n = (i) => i.startsWith(r) ? o(i.slice(r.length)) : pl(Bg, !1, i, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, Hg = (e) => {
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
}, qg = (e) => ({
  cache: Wg(e.cacheSize),
  parseClassName: Gg(e),
  sortModifiers: Hg(e),
  postfixLookupClassGroupIds: Zg(e),
  ...Ng(e)
}), Zg = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, Kg = /\s+/, Jg = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Kg);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const d = l[u], {
      isExternal: h,
      modifiers: m,
      hasImportantModifier: _,
      baseClassName: S,
      maybePostfixModifierPosition: b
    } = s(d);
    if (h) {
      c = d + (c.length > 0 ? " " + c : c);
      continue;
    }
    let A = !!b, M;
    if (A) {
      const re = S.substring(0, b);
      M = n(re);
      const U = M && i[M] ? n(S) : void 0;
      U && U !== M && (M = U, A = !1);
    } else
      M = n(S);
    if (!M) {
      if (!A) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (M = n(S), !M) {
        c = d + (c.length > 0 ? " " + c : c);
        continue;
      }
      A = !1;
    }
    const Y = m.length === 0 ? "" : m.length === 1 ? m[0] : o(m).join(":"), J = _ ? Y + ci : Y, ce = J + M;
    if (a.indexOf(ce) > -1)
      continue;
    a.push(ce);
    const Ae = r(M, A);
    for (let re = 0; re < Ae.length; ++re) {
      const U = Ae[re];
      a.push(J + U);
    }
    c = d + (c.length > 0 ? " " + c : c);
  }
  return c;
}, Qg = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = wu(s)) && (r && (r += " "), r += n);
  return r;
}, wu = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = wu(e[n])) && (s && (s += " "), s += t);
  return s;
}, Yg = (e, ...t) => {
  let s, n, r, o;
  const i = (l) => {
    const c = t.reduce((u, d) => d(u), e());
    return s = qg(c), n = s.cache.get, r = s.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = n(l);
    if (c)
      return c;
    const u = Jg(l, s);
    return r(l, u), u;
  };
  return o = i, (...l) => o(Qg(...l));
}, Xg = [], ut = (e) => {
  const t = (s) => s[e] || Xg;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, _u = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, xu = /^\((?:(\w[\w-]*):)?(.+)\)$/i, ev = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, tv = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, sv = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, nv = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, rv = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, ov = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, vs = (e) => ev.test(e), je = (e) => !!e && !Number.isNaN(Number(e)), Ft = (e) => !!e && Number.isInteger(Number(e)), To = (e) => e.endsWith("%") && je(e.slice(0, -1)), ns = (e) => tv.test(e), ku = () => !0, iv = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  sv.test(e) && !nv.test(e)
), Di = () => !1, av = (e) => rv.test(e), lv = (e) => ov.test(e), cv = (e) => !fe(e) && !me(e), uv = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), dv = (e) => Ts(e, Au, Di), fe = (e) => _u.test(e), zs = (e) => Ts(e, Ru, iv), hl = (e) => Ts(e, bv, je), fv = (e) => Ts(e, Eu, ku), mv = (e) => Ts(e, Iu, Di), gl = (e) => Ts(e, Su, Di), pv = (e) => Ts(e, Cu, lv), dr = (e) => Ts(e, $u, av), me = (e) => xu.test(e), wn = (e) => Gs(e, Ru), hv = (e) => Gs(e, Iu), vl = (e) => Gs(e, Su), gv = (e) => Gs(e, Au), vv = (e) => Gs(e, Cu), fr = (e) => Gs(e, $u, !0), yv = (e) => Gs(e, Eu, !0), Ts = (e, t, s) => {
  const n = _u.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, Gs = (e, t, s = !1) => {
  const n = xu.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, Su = (e) => e === "position" || e === "percentage", Cu = (e) => e === "image" || e === "url", Au = (e) => e === "length" || e === "size" || e === "bg-size", Ru = (e) => e === "length", bv = (e) => e === "number", Iu = (e) => e === "family-name", Eu = (e) => e === "number" || e === "weight", $u = (e) => e === "shadow", wv = () => {
  const e = ut("color"), t = ut("font"), s = ut("text"), n = ut("font-weight"), r = ut("tracking"), o = ut("leading"), i = ut("breakpoint"), a = ut("container"), l = ut("spacing"), c = ut("radius"), u = ut("shadow"), d = ut("inset-shadow"), h = ut("text-shadow"), m = ut("drop-shadow"), _ = ut("blur"), S = ut("perspective"), b = ut("aspect"), A = ut("ease"), M = ut("animate"), Y = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], J = () => [
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
  ], ce = () => [...J(), me, fe], Ae = () => ["auto", "hidden", "clip", "visible", "scroll"], re = () => ["auto", "contain", "none"], U = () => [me, fe, l], q = () => [vs, "full", "auto", ...U()], x = () => [Ft, "none", "subgrid", me, fe], Q = () => ["auto", {
    span: ["full", Ft, me, fe]
  }, Ft, me, fe], xe = () => [Ft, "auto", me, fe], C = () => ["auto", "min", "max", "fr", me, fe], te = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], Ne = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], ke = () => ["auto", ...U()], pe = () => [vs, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...U()], Ce = () => [a, vs, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...U()], ze = () => [vs, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...U()], oe = () => [e, me, fe], tt = () => [...J(), vl, gl, {
    position: [me, fe]
  }], Je = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], ue = () => ["auto", "cover", "contain", gv, dv, {
    size: [me, fe]
  }], y = () => [To, wn, zs], T = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    me,
    fe
  ], ve = () => ["", je, wn, zs], z = () => ["solid", "dashed", "dotted", "double"], E = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], P = () => [je, To, vl, gl], ie = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    _,
    me,
    fe
  ], p = () => ["none", je, me, fe], v = () => ["none", je, me, fe], k = () => [je, me, fe], I = () => [vs, "full", ...U()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [ns],
      breakpoint: [ns],
      color: [ku],
      container: [ns],
      "drop-shadow": [ns],
      ease: ["in", "out", "in-out"],
      font: [cv],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [ns],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [ns],
      shadow: [ns],
      spacing: ["px", je],
      text: [ns],
      "text-shadow": [ns],
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
        aspect: ["auto", "square", vs, fe, me, b]
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
        "@container": ["", "normal", "size", me, fe]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [uv],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [je, "auto", fe, me, a]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": Y()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": Y()
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
        object: ce()
      }],
      /**
       * Overflow
       * @see https://tailwindcss.com/docs/overflow
       */
      overflow: [{
        overflow: Ae()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": Ae()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": Ae()
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
        inset: q()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": q()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": q()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": q(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: q()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": q(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: q()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": q()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": q()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: q()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: q()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: q()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: q()
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
        z: [Ft, "auto", me, fe]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [vs, "full", "auto", a, ...U()]
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
        flex: [je, vs, "auto", "initial", "none", fe]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", je, me, fe]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", je, me, fe]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [Ft, "first", "last", "none", me, fe]
      }],
      /**
       * Grid Template Columns
       * @see https://tailwindcss.com/docs/grid-template-columns
       */
      "grid-cols": [{
        "grid-cols": x()
      }],
      /**
       * Grid Column Start / End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start-end": [{
        col: Q()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": xe()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": xe()
      }],
      /**
       * Grid Template Rows
       * @see https://tailwindcss.com/docs/grid-template-rows
       */
      "grid-rows": [{
        "grid-rows": x()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: Q()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": xe()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": xe()
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
        "auto-cols": C()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": C()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: U()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": U()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": U()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...te(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...Ne(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...Ne()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...te()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...Ne(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...Ne(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": te()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...Ne(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...Ne()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: U()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: U()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: U()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: U()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: U()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: U()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: U()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: U()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: U()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: U()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: U()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: ke()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: ke()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: ke()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: ke()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: ke()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: ke()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: ke()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: ke()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: ke()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: ke()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: ke()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": U()
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
        "space-y": U()
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
        size: pe()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ...Ce()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...Ce()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...Ce()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...ze()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...ze()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...ze()]
      }],
      /**
       * Width
       * @see https://tailwindcss.com/docs/width
       */
      w: [{
        w: [a, "screen", ...pe()]
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
          ...pe()
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
          ...pe()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...pe()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...pe()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...pe()]
      }],
      // ------------------
      // --- Typography ---
      // ------------------
      /**
       * Font Size
       * @see https://tailwindcss.com/docs/font-size
       */
      "font-size": [{
        text: ["base", s, wn, zs]
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
        font: [n, yv, fv]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", To, fe]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [hv, mv, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [fe]
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
        tracking: [r, me, fe]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [je, "none", me, hl]
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
          ...U()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", me, fe]
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
        list: ["disc", "decimal", "none", me, fe]
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
        placeholder: oe()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: oe()
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
        decoration: [...z(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [je, "from-font", "auto", me, zs]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: oe()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [je, "auto", me, fe]
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
        indent: U()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [Ft, me, fe]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", me, fe]
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
        content: ["none", me, fe]
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
        bg: Je()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: ue()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, Ft, me, fe],
          radial: ["", me, fe],
          conic: ["", Ft, me, fe]
        }, vv, pv]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: oe()
      }],
      /**
       * Gradient Color Stops From Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from-pos": [{
        from: y()
      }],
      /**
       * Gradient Color Stops Via Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via-pos": [{
        via: y()
      }],
      /**
       * Gradient Color Stops To Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to-pos": [{
        to: y()
      }],
      /**
       * Gradient Color Stops From
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from": [{
        from: oe()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: oe()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: oe()
      }],
      // ---------------
      // --- Borders ---
      // ---------------
      /**
       * Border Radius
       * @see https://tailwindcss.com/docs/border-radius
       */
      rounded: [{
        rounded: T()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": T()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": T()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": T()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": T()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": T()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": T()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": T()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": T()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": T()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": T()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": T()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": T()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": T()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": T()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: ve()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": ve()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": ve()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": ve()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": ve()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": ve()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": ve()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": ve()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": ve()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": ve()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": ve()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": ve()
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
        "divide-y": ve()
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
        border: [...z(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...z(), "hidden", "none"]
      }],
      /**
       * Border Color
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color": [{
        border: oe()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": oe()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": oe()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": oe()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": oe()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": oe()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": oe()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": oe()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": oe()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": oe()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": oe()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: oe()
      }],
      /**
       * Outline Style
       * @see https://tailwindcss.com/docs/outline-style
       */
      "outline-style": [{
        outline: [...z(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [je, me, fe]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", je, wn, zs]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: oe()
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
          fr,
          dr
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: oe()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", d, fr, dr]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": oe()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: ve()
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
        ring: oe()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [je, zs]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": oe()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": ve()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": oe()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", h, fr, dr]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": oe()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [je, me, fe]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...E(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": E()
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
        "mask-linear": [je]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": P()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": P()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": oe()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": oe()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": P()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": P()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": oe()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": oe()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": P()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": P()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": oe()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": oe()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": P()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": P()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": oe()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": oe()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": P()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": P()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": oe()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": oe()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": P()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": P()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": oe()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": oe()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": P()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": P()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": oe()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": oe()
      }],
      "mask-image-radial": [{
        "mask-radial": [me, fe]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": P()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": P()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": oe()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": oe()
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
        "mask-radial-at": J()
      }],
      "mask-image-conic-pos": [{
        "mask-conic": [je]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": P()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": P()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": oe()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": oe()
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
        mask: Je()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: ue()
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
        mask: ["none", me, fe]
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
          me,
          fe
        ]
      }],
      /**
       * Blur
       * @see https://tailwindcss.com/docs/blur
       */
      blur: [{
        blur: ie()
      }],
      /**
       * Brightness
       * @see https://tailwindcss.com/docs/brightness
       */
      brightness: [{
        brightness: [je, me, fe]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [je, me, fe]
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
          m,
          fr,
          dr
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": oe()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", je, me, fe]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [je, me, fe]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", je, me, fe]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [je, me, fe]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", je, me, fe]
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
          me,
          fe
        ]
      }],
      /**
       * Backdrop Blur
       * @see https://tailwindcss.com/docs/backdrop-blur
       */
      "backdrop-blur": [{
        "backdrop-blur": ie()
      }],
      /**
       * Backdrop Brightness
       * @see https://tailwindcss.com/docs/backdrop-brightness
       */
      "backdrop-brightness": [{
        "backdrop-brightness": [je, me, fe]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [je, me, fe]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", je, me, fe]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [je, me, fe]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", je, me, fe]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [je, me, fe]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [je, me, fe]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", je, me, fe]
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
        "border-spacing": U()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": U()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": U()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", me, fe]
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
        duration: [je, "initial", me, fe]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", A, me, fe]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [je, me, fe]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", M, me, fe]
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
        perspective: [S, me, fe]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": ce()
      }],
      /**
       * Rotate
       * @see https://tailwindcss.com/docs/rotate
       */
      rotate: [{
        rotate: p()
      }],
      /**
       * Rotate X
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-x": [{
        "rotate-x": p()
      }],
      /**
       * Rotate Y
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-y": [{
        "rotate-y": p()
      }],
      /**
       * Rotate Z
       * @see https://tailwindcss.com/docs/rotate
       */
      "rotate-z": [{
        "rotate-z": p()
      }],
      /**
       * Scale
       * @see https://tailwindcss.com/docs/scale
       */
      scale: [{
        scale: v()
      }],
      /**
       * Scale X
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-x": [{
        "scale-x": v()
      }],
      /**
       * Scale Y
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-y": [{
        "scale-y": v()
      }],
      /**
       * Scale Z
       * @see https://tailwindcss.com/docs/scale
       */
      "scale-z": [{
        "scale-z": v()
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
        skew: k()
      }],
      /**
       * Skew X
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-x": [{
        "skew-x": k()
      }],
      /**
       * Skew Y
       * @see https://tailwindcss.com/docs/skew
       */
      "skew-y": [{
        "skew-y": k()
      }],
      /**
       * Transform
       * @see https://tailwindcss.com/docs/transform
       */
      transform: [{
        transform: [me, fe, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: ce()
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
        translate: I()
      }],
      /**
       * Translate X
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-x": [{
        "translate-x": I()
      }],
      /**
       * Translate Y
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-y": [{
        "translate-y": I()
      }],
      /**
       * Translate Z
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-z": [{
        "translate-z": I()
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
        zoom: [Ft, me, fe]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: oe()
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
        caret: oe()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", me, fe]
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
        "scrollbar-thumb": oe()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": oe()
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
        "scroll-m": U()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": U()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": U()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": U()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": U()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": U()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": U()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": U()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": U()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": U()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": U()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": U()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": U()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": U()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": U()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": U()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": U()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": U()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": U()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": U()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": U()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": U()
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
        "will-change": ["auto", "scroll", "contents", "transform", me, fe]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...oe()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [je, wn, zs, hl]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...oe()]
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
}, _v = /* @__PURE__ */ Yg(wv);
function Li(...e) {
  return _v(gu(e));
}
const xv = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, kv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, Sv = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, Cv = { class: "cmst:flex-1" }, Av = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, Rv = { "data-testid": "vue-status-route" }, Iv = { "data-testid": "vue-status-ops" }, Ev = { "data-testid": "vue-status-density" }, $v = { class: "cmst:flex cmst:items-center cmst:gap-1" }, Ov = /* @__PURE__ */ Ct({
  __name: "StudioApp",
  setup(e) {
    const t = Yc(), s = Ot(), n = mu(), r = no();
    hs(() => {
      n.initialize(), r.initialize();
    });
    const o = rh("(min-width: 768px)"), i = {
      playground: Xc,
      history: eu,
      workflows: ti,
      backend: tu,
      settings: su
    }, a = Ue(() => String(t.name ?? "playground"));
    function l(c) {
      const u = a.value === c;
      return Li(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        u ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (c, u) => ($(), H("div", xv, [
      f("header", kv, [
        u[0] || (u[0] = f("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          O(" Modal Studio "),
          f("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        f("nav", Sv, [
          ($(!0), H(Ee, null, et(g(Ni), (d) => ($(), Ze(g(Jc), {
            key: d,
            to: { name: d },
            class: kt(l(d)),
            "data-testid": `vue-nav-${d}`
          }, {
            default: W(() => [
              ($(), Ze(Kd(i[d]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              O(" " + G(g(oh)[d]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      f("main", Cv, [
        V(g(Qc))
      ]),
      f("footer", Av, [
        f("span", null, [
          u[1] || (u[1] = O("route: ", -1)),
          f("strong", Rv, G(a.value), 1)
        ]),
        f("span", null, [
          u[2] || (u[2] = O(" operations: ", -1)),
          f("strong", Iv, G(g(s).active.length) + " active", 1),
          O(" / " + G(g(s).all.length) + " total ", 1)
        ]),
        f("span", null, [
          u[3] || (u[3] = O(" density: ", -1)),
          f("strong", Ev, G(g(n).density), 1)
        ]),
        f("span", $v, [
          V(g(Mp), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          u[4] || (u[4] = O(" viewport: ", -1)),
          f("strong", null, G(g(o) ? "wide" : "narrow"), 1),
          u[5] || (u[5] = O(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), Tv = "/", Ou = { page: "playground", focus: null };
function mr(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function Po(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = Es(n) ? n : Ou.page;
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
function No(e) {
  const t = ou(e.location.hash);
  return !t.matched || !Es(t.page) ? null : { page: t.page, focus: t.focus };
}
function Mo(e, t, s) {
  const n = iu(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function Pv(e, t) {
  let s = ih(t, e.location.hash), n = mr(s), r = {};
  const o = n, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = n;
    s = No(e) ?? { ...Ou }, n = mr(s), i.forEach((h) => h(n, u));
  }, c = (u, d) => u === null && d === o;
  return {
    get base() {
      return Tv;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const d = iu(Po(u));
      return d === "" ? "#" + u : d;
    },
    replace: (u, d) => {
      const h = No(e), m = Po(u), _ = mr(m);
      s = m, d !== void 0 && (r = d), n = _, !c(h, _) && Fa(h, m) !== "none" && Mo(e, m, "replace");
    },
    push: (u, d) => {
      const h = No(e), m = Po(u), _ = mr(m);
      if (s = m, d !== void 0 && (r = d), n = _, c(h, _)) return;
      const S = Fa(h, m);
      S === "push" ? Mo(e, m, "push") : S === "replace" && Mo(e, m, "replace");
    },
    go: (u) => {
      e.history.go(u);
    },
    listen: (u) => {
      const d = (h, m) => {
        u(h, m, { type: "pop", direction: "unknown", delta: 0 });
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
const yl = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, bl = gu, Nv = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return bl(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = s?.[c], d = o?.[c];
    if (u === null) return null;
    const h = yl(u) || yl(d);
    return r[c][h];
  }), a = s && Object.entries(s).reduce((c, u) => {
    let [d, h] = u;
    return h === void 0 || (c[d] = h), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, u) => {
    let { class: d, className: h, ...m } = u;
    return Object.entries(m).every((_) => {
      let [S, b] = _;
      return Array.isArray(b) ? b.includes({
        ...o,
        ...a
      }[S]) : {
        ...o,
        ...a
      }[S] === b;
    }) ? [
      ...c,
      d,
      h
    ] : c;
  }, []);
  return bl(e, i, l, s?.class, s?.className);
}, Mv = Nv(
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
), zv = ["type", "disabled"], X = /* @__PURE__ */ Ct({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => ($(), H("button", {
      type: e.type,
      disabled: e.disabled,
      class: kt(g(Mv)({ variant: e.variant, size: e.size }))
    }, [
      uc(t.$slots, "default")
    ], 10, zv));
  }
}), Xe = /* @__PURE__ */ Ct({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => ($(), H("div", {
      class: kt(
        g(Li)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      uc(t.$slots, "default")
    ], 2));
  }
});
function Yn(e) {
  return Li(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const jv = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Dv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Lv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Vv = { class: "cmst:flex cmst:gap-2" }, Uv = {
  key: 0,
  class: "cmst:mt-2 cmst:text-sm",
  "data-testid": "vue-backend-progress"
}, Fv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, Wv = ["data-testid", "onClick"], Bv = { class: "cmst:block cmst:text-xs cmst:opacity-70" }, Gv = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Hv = {
  key: 0,
  class: "cmst:mt-3 cmst:max-w-md cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3",
  "data-testid": "vue-workspace-form"
}, qv = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Zv = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Kv = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Jv = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-red-300",
  role: "alert"
}, Qv = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, Yv = {
  key: 1,
  class: "cmst:mt-3 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3",
  "data-testid": "vue-swap-confirm"
}, Xv = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, ey = {
  key: 2,
  class: "cmst:mt-3 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3",
  "data-testid": "vue-swap-review"
}, ty = { class: "cmst:text-sm" }, sy = ["value"], ny = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, ry = { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, oy = { "data-testid": "vue-auth-status" }, iy = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, ay = { class: "cmst:text-sm" }, ly = { "data-testid": "vue-cred-hf-state" }, cy = { class: "cmst:mt-1 cmst:flex cmst:gap-2" }, uy = { class: "cmst:text-sm" }, dy = { "data-testid": "vue-cred-civitai-state" }, fy = { class: "cmst:mt-1 cmst:flex cmst:gap-2" }, my = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs"
}, py = { class: "cmst:flex cmst:items-center cmst:justify-between" }, hy = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, gy = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs"
}, vy = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, yy = { class: "cmst:mt-1 cmst:text-sm" }, by = { "data-testid": "vue-deploy-state" }, wy = {
  key: 0,
  class: "cmst:text-sm cmst:opacity-80"
}, _y = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, xy = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, ky = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Sy = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, Cy = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, Ay = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, Ry = { class: "cmst:text-sm cmst:font-semibold" }, Iy = { class: "cmst:flex cmst:gap-2" }, Ey = {
  class: "cmst:mt-3 cmst:flex cmst:max-h-64 cmst:flex-col cmst:gap-1 cmst:overflow-auto cmst:text-sm",
  "data-testid": "vue-models-list"
}, $y = { class: "cmst:opacity-60" }, Oy = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Ty = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs",
  "data-testid": "vue-model-install-message",
  role: "status"
}, Py = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Ny = { class: "cmst:text-sm cmst:font-semibold" }, My = {
  class: "cmst:mt-3 cmst:flex cmst:max-h-64 cmst:flex-col cmst:gap-1 cmst:overflow-auto cmst:text-sm",
  "data-testid": "vue-nodes-list"
}, zy = /* @__PURE__ */ Ct({
  __name: "BackendView",
  setup(e) {
    const t = no(), s = /* @__PURE__ */ R("workspaces"), n = /* @__PURE__ */ R(""), r = /* @__PURE__ */ R(!1), o = /* @__PURE__ */ R(""), i = /* @__PURE__ */ R(""), a = /* @__PURE__ */ R(""), l = /* @__PURE__ */ R(""), c = /* @__PURE__ */ R(""), u = /* @__PURE__ */ R([]), d = /* @__PURE__ */ R(""), h = /* @__PURE__ */ R(""), m = /* @__PURE__ */ R(""), _ = /* @__PURE__ */ R(""), S = /* @__PURE__ */ R(""), b = /* @__PURE__ */ R("diffusion_models"), A = /* @__PURE__ */ R(""), M = /* @__PURE__ */ R(!1);
    hs(async () => {
      await t.initialize().catch(() => {
      }), await Promise.all([
        t.loadCredentials().catch(() => {
        }),
        t.loadSyncStatus().catch(() => {
        })
      ]);
    });
    async function Y() {
      n.value && await t.selectWorkspace(n.value).catch(() => {
      });
    }
    function J() {
      c.value = "", o.value = "", i.value = "", a.value = "", l.value = "", r.value = !0;
    }
    function ce() {
      const xe = t.workspaces.find((C) => C.id === n.value);
      xe && (c.value = xe.id, o.value = xe.label, i.value = "", a.value = "", l.value = "", r.value = !0);
    }
    async function Ae() {
      if (l.value = "", !o.value.trim()) {
        l.value = "Workspace label required.";
        return;
      }
      if (!c.value && (!i.value.trim() || !a.value.trim())) {
        l.value = "Token ID and Token Secret are required.";
        return;
      }
      try {
        await t.saveWorkspace(
          c.value ? { workspace_id: c.value, label: o.value.trim(), token_id: i.value.trim(), token_secret: a.value.trim(), set_active: !1 } : { label: o.value.trim(), token_id: i.value.trim(), token_secret: a.value.trim(), set_active: !1 }
        ), r.value = !1;
      } catch (xe) {
        l.value = xe instanceof Error ? xe.message : "Save failed.";
      }
    }
    async function re() {
      n.value && await t.startSwap(n.value).catch(() => {
      });
    }
    async function U() {
      await t.confirmSwapReview(n.value, u.value).catch(() => {
      });
    }
    async function q() {
      await t.deploy().catch(() => {
      });
    }
    async function x(xe) {
      m.value = "";
      try {
        const C = await t.saveCredential(xe, xe === "hf" ? d.value : h.value);
        m.value = C, d.value = "", h.value = "";
      } catch (C) {
        m.value = C instanceof Error ? C.message : "Save failed.";
      }
    }
    async function Q() {
      if (S.value.trim()) {
        A.value = "Installing…";
        try {
          const xe = S.value.trim();
          await t.installModel({ url: xe, filename: _g(xe), save_path: b.value }), A.value = "Install request accepted.";
        } catch (xe) {
          A.value = xe instanceof Error ? xe.message : "Install failed.";
        }
        S.value = "";
      }
    }
    return (xe, C) => ($(), H("section", {
      class: kt(g(Yn)()),
      "data-testid": "vue-page-backend"
    }, [
      g(t).error ? ($(), H("div", jv, G(g(t).error), 1)) : we("", !0),
      V(Xe, { class: "cmst:p-4" }, {
        default: W(() => [
          f("div", Dv, [
            f("div", null, [
              f("h2", Lv, [
                V(g(tu), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                C[26] || (C[26] = O(" Manage Modal ", -1))
              ]),
              C[27] || (C[27] = f("p", { class: "cmst:text-sm cmst:opacity-80" }, [
                O("Route key remains "),
                f("code", null, "backend"),
                O(". Server truth only.")
              ], -1))
            ]),
            f("div", Vv, [
              ($(), H(Ee, null, et(["workspaces", "deployment", "models", "nodes"], (te) => V(X, {
                key: te,
                variant: s.value === te ? "default" : "outline",
                size: "sm",
                "data-testid": `vue-backend-tab-${te}`,
                onClick: (Ne) => s.value = te
              }, {
                default: W(() => [
                  O(G(te), 1)
                ]),
                _: 2
              }, 1032, ["variant", "data-testid", "onClick"])), 64)),
              V(X, {
                variant: "outline",
                size: "icon",
                "aria-label": "Reload infrastructure",
                disabled: g(t).loading,
                onClick: C[0] || (C[0] = (te) => g(t).load())
              }, {
                default: W(() => [
                  V(g(to), {
                    class: kt(["cmst:size-4", g(t).loading ? "cmst:animate-spin" : ""]),
                    "aria-hidden": "true"
                  }, null, 8, ["class"])
                ]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          g(t).progress ? ($(), H("p", Uv, G(g(t).progress), 1)) : we("", !0)
        ]),
        _: 1
      }),
      s.value === "workspaces" ? ($(), H(Ee, { key: 1 }, [
        V(Xe, { class: "cmst:p-4" }, {
          default: W(() => [
            C[42] || (C[42] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Workspaces", -1)),
            f("div", Fv, [
              ($(!0), H(Ee, null, et(g(t).workspaces, (te) => ($(), H("button", {
                key: te.id,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-workspace-${te.id}`,
                onClick: (Ne) => n.value = te.id
              }, [
                f("strong", null, G(te.label), 1),
                f("span", Bv, G(te.isActive ? "Active workspace" : `Idle · last deploy: ${te.lastDeployStatus}`), 1)
              ], 8, Wv))), 128))
            ]),
            f("div", Gv, [
              V(X, {
                size: "sm",
                variant: "secondary",
                disabled: !n.value || g(t).busy,
                "data-testid": "vue-workspace-activate",
                onClick: Y
              }, {
                default: W(() => [...C[28] || (C[28] = [
                  O("Set Active", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              V(X, {
                size: "sm",
                variant: "outline",
                disabled: g(t).busy,
                onClick: J
              }, {
                default: W(() => [...C[29] || (C[29] = [
                  O("+ Add Workspace", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              V(X, {
                size: "sm",
                variant: "outline",
                disabled: !n.value || g(t).busy,
                onClick: ce
              }, {
                default: W(() => [...C[30] || (C[30] = [
                  O("Edit Workspace", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              V(X, {
                size: "sm",
                disabled: !n.value || g(t).busy,
                "data-testid": "vue-workspace-swap",
                onClick: re
              }, {
                default: W(() => [...C[31] || (C[31] = [
                  O("Swap Workspace", -1)
                ])]),
                _: 1
              }, 8, ["disabled"])
            ]),
            r.value ? ($(), H("div", Hv, [
              f("label", qv, [
                C[32] || (C[32] = O("Label", -1)),
                Ve(f("input", {
                  "onUpdate:modelValue": C[1] || (C[1] = (te) => o.value = te),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2"
                }, null, 512), [
                  [at, o.value]
                ])
              ]),
              f("label", Zv, [
                C[33] || (C[33] = O("Token ID", -1)),
                Ve(f("input", {
                  "onUpdate:modelValue": C[2] || (C[2] = (te) => i.value = te),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  placeholder: "ak-…"
                }, null, 512), [
                  [at, i.value]
                ])
              ]),
              f("label", Kv, [
                C[34] || (C[34] = O("Token Secret", -1)),
                Ve(f("input", {
                  "onUpdate:modelValue": C[3] || (C[3] = (te) => a.value = te),
                  type: "password",
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  placeholder: "as-…"
                }, null, 512), [
                  [at, a.value]
                ])
              ]),
              l.value ? ($(), H("p", Jv, G(l.value), 1)) : we("", !0),
              f("div", Qv, [
                V(X, {
                  size: "sm",
                  "data-testid": "vue-workspace-save",
                  onClick: Ae
                }, {
                  default: W(() => [...C[35] || (C[35] = [
                    O("Save Workspace", -1)
                  ])]),
                  _: 1
                }),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  onClick: C[4] || (C[4] = (te) => r.value = !1)
                }, {
                  default: W(() => [...C[36] || (C[36] = [
                    O("Cancel", -1)
                  ])]),
                  _: 1
                })
              ])
            ])) : we("", !0),
            g(t).swapConfirmRequired ? ($(), H("div", Yv, [
              C[39] || (C[39] = f("p", { class: "cmst:text-sm" }, "A prompt is still running. Switch workspaces anyway?", -1)),
              f("div", Xv, [
                V(X, {
                  size: "sm",
                  "data-testid": "vue-swap-confirm-yes",
                  onClick: C[5] || (C[5] = (te) => g(t).confirmSwapInterrupt(n.value))
                }, {
                  default: W(() => [...C[37] || (C[37] = [
                    O("Interrupt and Switch", -1)
                  ])]),
                  _: 1
                }),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  onClick: C[6] || (C[6] = (te) => g(t).cancelSwapDialog())
                }, {
                  default: W(() => [...C[38] || (C[38] = [
                    O("Cancel", -1)
                  ])]),
                  _: 1
                })
              ])
            ])) : we("", !0),
            g(t).swapReview ? ($(), H("div", ey, [
              f("p", ty, "Select models to download to " + G(g(t).swapReview.workspaceLabel) + ":", 1),
              ($(!0), H(Ee, null, et(g(t).swapReview.toInstall, (te) => ($(), H("label", {
                key: te.key,
                class: "cmst:mt-1 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm"
              }, [
                Ve(f("input", {
                  "onUpdate:modelValue": C[7] || (C[7] = (Ne) => u.value = Ne),
                  type: "checkbox",
                  value: te.key
                }, null, 8, sy), [
                  [tn, u.value]
                ]),
                O(" " + G(te.filename) + " (" + G(te.folder) + ") ", 1)
              ]))), 128)),
              f("div", ny, [
                V(X, {
                  size: "sm",
                  "data-testid": "vue-swap-review-go",
                  onClick: U
                }, {
                  default: W(() => [...C[40] || (C[40] = [
                    O("Start Swap", -1)
                  ])]),
                  _: 1
                }),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  onClick: C[8] || (C[8] = (te) => g(t).cancelSwapDialog())
                }, {
                  default: W(() => [...C[41] || (C[41] = [
                    O("Cancel", -1)
                  ])]),
                  _: 1
                })
              ])
            ])) : we("", !0)
          ]),
          _: 1
        }),
        V(Xe, { class: "cmst:p-4" }, {
          default: W(() => [
            C[48] || (C[48] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Accounts & Tokens", -1)),
            f("p", ry, [
              C[43] || (C[43] = O(" Modal connection: ", -1)),
              f("strong", oy, G(g(t).authConnected === null ? "unknown" : g(t).authConnected ? "connected" : "not configured"), 1)
            ]),
            f("div", iy, [
              f("div", null, [
                f("p", ay, [
                  C[44] || (C[44] = O("HuggingFace: ", -1)),
                  f("strong", ly, G(g(t).hfConfigured ? "configured" : "not configured"), 1)
                ]),
                f("div", cy, [
                  Ve(f("input", {
                    "onUpdate:modelValue": C[9] || (C[9] = (te) => d.value = te),
                    type: "password",
                    placeholder: "hf_...",
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                    "data-testid": "vue-cred-hf-input"
                  }, null, 512), [
                    [at, d.value]
                  ]),
                  V(X, {
                    size: "sm",
                    "data-testid": "vue-cred-hf-save",
                    onClick: C[10] || (C[10] = (te) => x("hf"))
                  }, {
                    default: W(() => [...C[45] || (C[45] = [
                      O("Save", -1)
                    ])]),
                    _: 1
                  })
                ])
              ]),
              f("div", null, [
                f("p", uy, [
                  C[46] || (C[46] = O("Civitai: ", -1)),
                  f("strong", dy, G(g(t).civitaiConfigured ? "configured" : "not configured"), 1)
                ]),
                f("div", fy, [
                  Ve(f("input", {
                    "onUpdate:modelValue": C[11] || (C[11] = (te) => h.value = te),
                    type: "password",
                    placeholder: "Civitai API Key",
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                    "data-testid": "vue-cred-civitai-input"
                  }, null, 512), [
                    [at, h.value]
                  ]),
                  V(X, {
                    size: "sm",
                    "data-testid": "vue-cred-civitai-save",
                    onClick: C[12] || (C[12] = (te) => x("civitai"))
                  }, {
                    default: W(() => [...C[47] || (C[47] = [
                      O("Save", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ]),
            m.value ? ($(), H("p", my, G(m.value), 1)) : we("", !0)
          ]),
          _: 1
        }),
        V(Xe, { class: "cmst:p-4" }, {
          default: W(() => [
            f("div", py, [
              C[50] || (C[50] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Manifest repair", -1)),
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-repair-scan",
                onClick: C[13] || (C[13] = (te) => g(t).scanRepair())
              }, {
                default: W(() => [...C[49] || (C[49] = [
                  O("Scan issues", -1)
                ])]),
                _: 1
              })
            ]),
            g(t).repairIssues ? ($(), H("pre", hy, G(JSON.stringify(g(t).repairIssues, null, 2)), 1)) : we("", !0),
            g(t).repairMessage ? ($(), H("p", gy, G(g(t).repairMessage), 1)) : we("", !0)
          ]),
          _: 1
        })
      ], 64)) : we("", !0),
      s.value === "deployment" ? ($(), H(Ee, { key: 2 }, [
        V(Xe, { class: "cmst:p-4" }, {
          default: W(() => [
            f("div", vy, [
              f("div", null, [
                C[52] || (C[52] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Deployment readiness", -1)),
                f("p", yy, [
                  C[51] || (C[51] = O("State: ", -1)),
                  f("strong", by, G(g(t).deployStatus.state), 1)
                ]),
                g(t).deployMessage ? ($(), H("p", wy, G(g(t).deployMessage), 1)) : we("", !0)
              ]),
              f("div", _y, [
                V(X, {
                  size: "sm",
                  disabled: g(t).loading || !!g(t).deploymentOperationId,
                  "data-testid": "vue-deploy",
                  onClick: q
                }, {
                  default: W(() => [...C[53] || (C[53] = [
                    O("Deploy", -1)
                  ])]),
                  _: 1
                }, 8, ["disabled"]),
                V(X, {
                  size: "sm",
                  variant: "outline",
                  "data-testid": "vue-deploy-refresh",
                  onClick: C[14] || (C[14] = (te) => g(t).loadDeployment())
                }, {
                  default: W(() => [...C[54] || (C[54] = [
                    O("Refresh Status", -1)
                  ])]),
                  _: 1
                }),
                V(X, {
                  size: "sm",
                  variant: "outline",
                  onClick: C[15] || (C[15] = (te) => M.value = !M.value)
                }, {
                  default: W(() => [
                    O(G(M.value ? "Hide" : "Show") + " Log", 1)
                  ]),
                  _: 1
                })
              ])
            ]),
            M.value ? ($(), H("pre", xy, G(g(t).deployLog ?? "Loading…"), 1)) : we("", !0),
            M.value && !g(t).deployLog ? ($(), Ze(X, {
              key: 1,
              class: "cmst:mt-2",
              size: "sm",
              variant: "ghost",
              onClick: C[16] || (C[16] = (te) => g(t).loadLog())
            }, {
              default: W(() => [...C[55] || (C[55] = [
                O("Load deployment log", -1)
              ])]),
              _: 1
            })) : we("", !0)
          ]),
          _: 1
        }),
        V(Xe, { class: "cmst:p-4" }, {
          default: W(() => [
            f("div", ky, [
              C[57] || (C[57] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Custom-node sync", -1)),
              V(X, {
                size: "sm",
                variant: "outline",
                onClick: C[17] || (C[17] = (te) => g(t).loadSyncStatus())
              }, {
                default: W(() => [...C[56] || (C[56] = [
                  O("Refresh status", -1)
                ])]),
                _: 1
              })
            ]),
            g(t).customNodeSync ? ($(), H("pre", Sy, G(JSON.stringify(g(t).customNodeSync, null, 2)), 1)) : we("", !0),
            f("div", Cy, [
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-node-push",
                onClick: C[18] || (C[18] = (te) => g(t).pushPlugins())
              }, {
                default: W(() => [...C[58] || (C[58] = [
                  O("Push plugins (FAST)", -1)
                ])]),
                _: 1
              }),
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-node-rebuild",
                onClick: C[19] || (C[19] = (te) => g(t).rebuildDependencies())
              }, {
                default: W(() => [...C[59] || (C[59] = [
                  O("Rebuild dependencies (SLOW)", -1)
                ])]),
                _: 1
              })
            ])
          ]),
          _: 1
        })
      ], 64)) : we("", !0),
      s.value === "models" ? ($(), Ze(Xe, {
        key: 3,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          f("div", Ay, [
            f("h3", Ry, "Models (" + G(g(t).models.length) + ")", 1),
            f("div", Iy, [
              Ve(f("input", {
                "onUpdate:modelValue": C[20] || (C[20] = (te) => _.value = te),
                class: "cmst:h-9 cmst:w-48 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                placeholder: "Search models",
                onKeyup: C[21] || (C[21] = Ws((te) => g(t).loadInventory(), ["enter"]))
              }, null, 544), [
                [at, _.value]
              ]),
              V(X, {
                size: "sm",
                variant: "outline",
                onClick: C[22] || (C[22] = (te) => g(t).rescanModelsNow(!0))
              }, {
                default: W(() => [...C[60] || (C[60] = [
                  O("Rescan", -1)
                ])]),
                _: 1
              })
            ])
          ]),
          f("ul", Ey, [
            ($(!0), H(Ee, null, et(g(t).models, (te, Ne) => ($(), H("li", {
              key: Ne,
              class: "cmst:rounded cmst:bg-cmst-bg cmst:px-2 cmst:py-1 cmst:text-xs"
            }, [
              O(G(String(te.filename || te.name || te.id || `model ${Ne}`)) + " ", 1),
              f("span", $y, " · " + G(String(te.folder || te.type || "")), 1)
            ]))), 128))
          ]),
          f("div", Oy, [
            Ve(f("input", {
              "onUpdate:modelValue": C[23] || (C[23] = (te) => S.value = te),
              class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              placeholder: "Paste a direct model link",
              "data-testid": "vue-model-url"
            }, null, 512), [
              [at, S.value]
            ]),
            Ve(f("select", {
              "onUpdate:modelValue": C[24] || (C[24] = (te) => b.value = te),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
            }, [...C[61] || (C[61] = [
              f("option", { value: "diffusion_models" }, "diffusion_models", -1),
              f("option", { value: "vae" }, "vae", -1),
              f("option", { value: "clip" }, "clip", -1),
              f("option", { value: "loras" }, "loras", -1),
              f("option", { value: "upscale_models" }, "upscale_models", -1)
            ])], 512), [
              [ls, b.value]
            ]),
            V(X, {
              size: "sm",
              "data-testid": "vue-model-install",
              onClick: Q
            }, {
              default: W(() => [...C[62] || (C[62] = [
                O("Install", -1)
              ])]),
              _: 1
            })
          ]),
          A.value ? ($(), H("p", Ty, G(A.value), 1)) : we("", !0)
        ]),
        _: 1
      })) : we("", !0),
      s.value === "nodes" ? ($(), Ze(Xe, {
        key: 4,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          f("div", Py, [
            f("h3", Ny, "Custom nodes (" + G(g(t).customNodes.length) + ")", 1),
            V(X, {
              size: "sm",
              variant: "outline",
              onClick: C[25] || (C[25] = (te) => g(t).refreshCustomNodesNow())
            }, {
              default: W(() => [...C[63] || (C[63] = [
                O("Refresh registry", -1)
              ])]),
              _: 1
            })
          ]),
          f("ul", My, [
            ($(!0), H(Ee, null, et(g(t).customNodes, (te, Ne) => ($(), H("li", {
              key: Ne,
              class: "cmst:rounded cmst:bg-cmst-bg cmst:px-2 cmst:py-1 cmst:text-xs"
            }, G(String(te.title || te.id || te.name || `node ${Ne}`)), 1))), 128))
          ])
        ]),
        _: 1
      })) : we("", !0)
    ], 2));
  }
});
function Tu(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return t.item ?? t.generation ?? t.experiment ?? e;
}
function rt(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function jy(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = rt(s, "asset_id", "assetId"), r = () => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: rt(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: rt(s, "logical_key", "logicalKey"),
    thumbUrl: rt(s, "thumb_url", "thumbnail_url") || r(),
    previewUrl: rt(s, "preview_url", "data_saver_url") || r(),
    dataSaverUrl: rt(s, "data_saver_url", "preview_url") || r(),
    originalUrl: rt(s, "original_url") || r(),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: rt(s, "filename", "name"),
    exportState: rt(s, "export_state", "exportState") || "not_exported"
  };
}
function Dy(e, t) {
  const s = e && typeof e == "object" ? e : {};
  return {
    index: t,
    status: rt(s, "status", "outcome") || "unknown",
    error: rt(s, "error", "message") || null,
    ...s
  };
}
function Vi(e) {
  return e.dataSaverUrl || e.thumbUrl || e.originalUrl;
}
function Pu(e) {
  return e.originalAvailable && e.originalUrl ? e.originalUrl : e.dataSaverUrl || e.originalUrl || e.thumbUrl;
}
function Nu(e) {
  return e.originalUrl || e.dataSaverUrl || e.thumbUrl;
}
function Ly(e, t) {
  const s = e.featured_output_index;
  if (typeof s == "number" && t[s]) return s;
  const n = e.featured_output;
  if (n && typeof n == "object") {
    const r = n.index;
    if (typeof r == "number" && t[r]) return r;
  }
  return 0;
}
function Mr(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((c, u) => jy(c, u)), r = Ly(t, n), o = Array.isArray(t.cells) ? t.cells : [], i = Array.isArray(t.cover) ? t.cover : [], a = Array.isArray(t.attempts) ? t.attempts : [], l = Array.isArray(t.errors) ? t.errors : [];
  return {
    id: rt(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: rt(t, "status", "outcome") || "unknown",
    workflow: rt(t, "workflow", "workflow_name"),
    workflowVersion: rt(t, "workflow_version", "workflowVersion", "version_id"),
    preset: rt(t, "preset", "preset_name"),
    prompt: rt(t, "prompt", "positive_prompt"),
    startedAt: rt(t, "started_at", "created_at") || null,
    completedAt: rt(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: rt(t, "note"),
    outputs: n,
    featuredOutput: n[r] ?? n[0] ?? null,
    featuredOutputIndex: r,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    replayReason: rt(t, "replay_reason", "replayReason"),
    attempts: a.map((c, u) => Dy(c, u)),
    errors: l.filter((c) => !!c && typeof c == "object").map((c) => ({ code: rt(c, "code") || "error", message: rt(c, "message") || "Unknown error" })),
    params: t.params && typeof t.params == "object" ? t.params : {},
    timing: t.timing && typeof t.timing == "object" ? t.timing : {},
    cells: o.map((c) => Mr(c)),
    cover: i.map((c) => c ? Mr(c) : null),
    axisLabels: {
      x: rt(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "x"),
      y: rt(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "y")
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
async function Vy(e = {}) {
  const t = new URLSearchParams(), s = { limit: 24, ...e };
  s.sort !== void 0 && (s.order = s.sort, delete s.sort), s.favorite_only !== void 0 && (s.favorite = s.favorite_only, delete s.favorite_only);
  for (const [n, r] of Object.entries(s))
    r !== void 0 && String(r) !== "" && t.set(n, String(r));
  return se(`/history-v2/feed?${t}`);
}
async function Uy(e) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}`).then(Tu);
}
async function Fy(e) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}`).then(Tu);
}
async function Wy(e, t) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function By(e, t) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function Gy(e, t) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function Hy(e, t) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function qy(e, t) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/featured`, { method: "PATCH", body: { output_index: t } });
}
async function Zy(e, t = {}) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/original`, { method: "POST", body: t });
}
async function Ky(e) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/original/retry`, { method: "POST" });
}
async function Jy(e) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function Qy(e) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function Yy(e) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/cancel`, { method: "POST" });
}
async function Xy(e, t) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/cells/${encodeURIComponent(t)}/retry`, { method: "POST" });
}
async function eb(e, t) {
  return se("/history-v2/bulk-delete", { method: "POST", body: { generation_ids: e, experiment_ids: t } });
}
async function tb(e) {
  return se(`/history-v2/assets/${encodeURIComponent(e)}/export`, { method: "POST" });
}
async function sb(e) {
  return se(`/history-v2/assets/${encodeURIComponent(e)}/open`, { method: "POST" });
}
async function nb(e) {
  return se(`/history-v2/assets/${encodeURIComponent(e)}/reveal`, { method: "POST" });
}
function rb(e) {
  const t = e.split(";")[0].trim().toLowerCase();
  return t === "image/png" ? "png" : t === "image/jpeg" ? "jpg" : t === "image/webp" ? "webp" : t === "image/gif" ? "gif" : t === "image/bmp" ? "bmp" : "png";
}
function ob(e, t, s) {
  return `${[e.workflow || "generation", e.id, `output-${t.index}`].map((r) => r.replace(/[^a-zA-Z0-9-_]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48)).filter(Boolean).join("-") || "history-output"}.${s}`;
}
async function ib(e, t, s = "original") {
  const n = s === "original" ? t.originalUrl : s === "dataSaver" ? t.dataSaverUrl : t.thumbUrl, r = await fetch(n);
  if (!r.ok) throw new Error(`Download failed with status ${r.status}`);
  const o = await r.blob(), i = ob(e, t, rb(o.type)), a = URL.createObjectURL(o);
  try {
    const l = document.createElement("a");
    l.href = a, l.download = i, document.body.appendChild(l), l.click(), l.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(a), 1e3);
  }
}
async function ab(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return se(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const Zs = Ys("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1, kind: "mixed", status: "" }), Xn = /* @__PURE__ */ mn("studio-history", () => {
  const e = /* @__PURE__ */ R([]), t = /* @__PURE__ */ R(null), s = /* @__PURE__ */ R(null), n = /* @__PURE__ */ R(Zs.read().query), r = /* @__PURE__ */ R(Zs.read().sort), o = /* @__PURE__ */ R(Zs.read().favoriteOnly), i = /* @__PURE__ */ R(Zs.read().kind), a = /* @__PURE__ */ R(Zs.read().status), l = /* @__PURE__ */ R(null), c = /* @__PURE__ */ R(!1), u = /* @__PURE__ */ R(!1), d = /* @__PURE__ */ R(null), h = /* @__PURE__ */ R(null), m = /* @__PURE__ */ R(null), _ = /* @__PURE__ */ R(null), S = /* @__PURE__ */ R(/* @__PURE__ */ new Set()), b = /* @__PURE__ */ R(!1), A = /* @__PURE__ */ R(null), M = qn(), Y = qn();
  let J = !1, ce = null;
  const Ae = Ue(() => e.value.find((w) => w.id === t.value) ?? null), re = Ue(() => e.value.find((w) => w.id === s.value) ?? Ae.value), U = Ue(() => ({
    a: e.value.find((w) => w.id === m.value) ?? null,
    b: e.value.find((w) => w.id === _.value) ?? null
  })), q = Ue(() => [...S.value]);
  function x() {
    Zs.write({ query: n.value, sort: r.value, favoriteOnly: o.value, kind: i.value, status: a.value });
  }
  function Q(w) {
    s.value = w, w && (t.value = w);
  }
  function xe(w) {
    n.value = w, x();
  }
  function C(w) {
    r.value = w, x();
  }
  function te(w) {
    o.value = w, x();
  }
  function Ne(w) {
    i.value = w, x();
  }
  function ke(w) {
    a.value = w, x();
  }
  function pe(w) {
    const N = e.value.findIndex((D) => D.id === w.id && D.kind === w.kind);
    N >= 0 ? e.value[N] = w : e.value.unshift(w);
  }
  function Ce(w, N) {
    e.value = e.value.filter((D) => !(D.id === N && D.kind === w)), t.value === N && (t.value = null), s.value === N && (s.value = null), m.value === N && (m.value = null), _.value === N && (_.value = null), S.value.delete(`${w}:${N}`);
  }
  async function ze(w = !1) {
    u.value = !0, d.value = null;
    try {
      const N = await M.run(async (he) => {
        const ne = await Vy({
          search: n.value,
          order: r.value,
          favorite: o.value ? !0 : void 0,
          kind: i.value === "mixed" ? void 0 : i.value,
          status: a.value || void 0,
          cursor: w ? l.value ?? void 0 : void 0
        });
        return he.aborted ? null : ne;
      });
      if (N.stale || !N.value) return;
      const D = N.value, F = (D.items ?? D.records ?? []).map(Mr);
      e.value = w ? e.value.concat(F) : F, l.value = D.next_cursor ?? null, c.value = D.has_more === !0 || !!l.value;
    } catch (N) {
      throw d.value = N instanceof Error ? N.message : "Could not load History V2", N;
    } finally {
      u.value = !1, J && (J = !1, ze());
    }
  }
  async function oe(w, N = "generation") {
    h.value = null;
    try {
      const D = await Y.run(async (F) => {
        const he = N === "experiment" ? await Fy(w) : await Uy(w);
        return F.aborted ? null : he;
      });
      if (D.stale || !D.value) return;
      pe(Mr(D.value)), t.value = w;
    } catch (D) {
      throw h.value = D instanceof Error ? D.message : "Could not load History detail", D;
    }
  }
  async function tt(w) {
    if (Q(w), !w) return;
    const N = e.value.find((D) => D.id === w);
    await oe(w, N?.kind ?? "generation");
  }
  async function Je(w, N) {
    const D = w.favorite;
    w.favorite = N;
    try {
      w.kind === "experiment" ? await By(w.id, N) : await Wy(w.id, N), Qe("history");
    } catch (F) {
      throw w.favorite = D, F;
    }
  }
  async function ue(w, N) {
    const D = w.note;
    w.note = N;
    try {
      w.kind === "experiment" ? await Hy(w.id, N) : await Gy(w.id, N), Qe("history");
    } catch (F) {
      throw w.note = D, F;
    }
  }
  async function y(w, N) {
    await qy(w.id, N), await oe(w.id, w.kind), Qe("history");
  }
  async function T(w) {
    await ab(w), Ce(w.kind, w.id), Qe("history");
  }
  function ve(w) {
    const N = `${w.kind}:${w.id}`, D = new Set(S.value);
    D.has(N) ? D.delete(N) : D.add(N), S.value = D;
  }
  function z() {
    S.value = /* @__PURE__ */ new Set();
  }
  async function E() {
    const w = [], N = [];
    for (const D of S.value) {
      const F = D.indexOf(":"), he = D.slice(0, F), ne = D.slice(F + 1);
      he === "experiment" ? N.push(ne) : w.push(ne);
    }
    if (!(!w.length && !N.length)) {
      await eb(w, N);
      for (const D of w) Ce("generation", D);
      for (const D of N) Ce("experiment", D);
      z(), Qe("history");
    }
  }
  async function P(w, N) {
    let D;
    return N === "original" ? D = await Zy(w.id) : N === "retry" ? D = await Ky(w.id) : D = await Jy(w.id), A.value = `${N} accepted for ${w.id}`, Qe("history"), D;
  }
  async function ie(w, N, D) {
    let F;
    return N === "resume" ? F = await Qy(w.id) : D ? F = await Xy(w.id, D) : F = await Yy(w.id), await oe(w.id, "experiment"), Qe("history"), F;
  }
  async function p(w) {
    const N = await tb(w.assetId);
    return w.exportState = "exported", N;
  }
  function v(w, N) {
    w === "a" ? m.value = N : _.value = N;
  }
  function k() {
    const w = m.value;
    m.value = _.value, _.value = w;
  }
  function I() {
    m.value = null, _.value = null;
  }
  async function j() {
    ce || (ce = so((w) => {
      if (w === "history") {
        if (u.value) {
          J = !0;
          return;
        }
        ze();
      }
    })), e.value.length || await ze();
  }
  function B() {
    e.value = [], t.value = null, s.value = null, l.value = null, m.value = null, _.value = null, S.value = /* @__PURE__ */ new Set();
  }
  return {
    records: e,
    selected: Ae,
    selectedId: t,
    focused: re,
    focusId: s,
    query: n,
    sort: r,
    favoriteOnly: o,
    kindFilter: i,
    statusFilter: a,
    cursor: l,
    hasMore: c,
    loading: u,
    error: d,
    detailError: h,
    compareA: m,
    compareB: _,
    compareRecords: U,
    selection: q,
    viewerOpen: b,
    actionMessage: A,
    setFocus: Q,
    setQuery: xe,
    setSort: C,
    setFavoriteOnly: te,
    setKindFilter: Ne,
    setStatusFilter: ke,
    loadFeed: ze,
    loadDetail: oe,
    applyRouteFocus: tt,
    setFavorite: Je,
    setNote: ue,
    setFeatured: y,
    remove: T,
    toggleSelection: ve,
    clearSelection: z,
    removeSelected: E,
    runReplayAction: P,
    runExperimentAction: ie,
    exportAsset: p,
    openHistoryAsset: sb,
    revealHistoryAsset: nb,
    downloadHistoryAsset: ib,
    selectCompare: v,
    swapCompare: k,
    clearCompare: I,
    selectFeedAsset: Vi,
    selectDetailAsset: Pu,
    selectCompareAsset: Nu,
    initialize: j,
    clear: B
  };
}), lb = ["aria-label", "data-testid"], cb = ["src", "alt"], ub = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:p-3 cmst:text-sm" }, db = { class: "cmst:min-w-0" }, fb = { class: "cmst:block cmst:truncate" }, mb = { class: "cmst:block cmst:truncate cmst:text-xs cmst:opacity-70" }, pb = ["aria-pressed", "aria-label", "data-testid"], hb = /* @__PURE__ */ Ct({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t, n = Xn();
    async function r(o, i) {
      i.stopPropagation(), await n.setFavorite(o, !o.favorite).catch(() => {
      });
    }
    return (o, i) => ($(), Ze(Xe, { class: "cmst:overflow-hidden" }, {
      default: W(() => [
        f("button", {
          type: "button",
          class: "cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:p-0 cmst:text-left",
          "aria-label": `Open ${e.record.workflow || e.record.id}`,
          "data-testid": `vue-history-card-${e.record.id}`,
          onClick: i[0] || (i[0] = (a) => s("select", e.record)),
          onKeydown: i[1] || (i[1] = Ws((a) => s("select", e.record), ["enter"]))
        }, [
          e.record.featuredOutput ? ($(), H("img", {
            key: 0,
            src: g(Vi)(e.record.featuredOutput),
            alt: e.record.workflow || e.record.id,
            class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
            loading: "lazy"
          }, null, 8, cb)) : we("", !0)
        ], 40, lb),
        f("div", ub, [
          f("div", db, [
            f("strong", fb, G(e.record.workflow || e.record.id), 1),
            f("span", mb, G(e.record.status) + " · " + G(e.record.kind), 1)
          ]),
          f("button", {
            type: "button",
            class: "cmst:shrink-0 cmst:rounded cmst:px-2 cmst:py-1 cmst:text-base",
            "aria-pressed": e.record.favorite ? "true" : "false",
            "aria-label": e.record.favorite ? `Remove ${e.record.id} from favorites` : `Add ${e.record.id} to favorites`,
            "data-testid": `vue-history-favorite-${e.record.id}`,
            onClick: i[2] || (i[2] = (a) => r(e.record, a))
          }, G(e.record.favorite ? "★" : "☆"), 9, pb)
        ])
      ]),
      _: 1
    }));
  }
}), gb = {
  class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2 cmst:lg:grid-cols-3",
  "data-testid": "vue-history-grid"
}, vb = /* @__PURE__ */ Ct({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => ($(), H("div", gb, [
      ($(!0), H(Ee, null, et(e.records, (o) => ($(), Ze(hb, {
        key: `${o.kind}:${o.id}`,
        record: o,
        onSelect: r[0] || (r[0] = (i) => s("select", i))
      }, null, 8, ["record"]))), 128))
    ]));
  }
}), yb = ["aria-label", "onKeydown"], bb = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, wb = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, _b = { class: "cmst:text-lg cmst:font-semibold" }, xb = { class: "cmst:text-xs cmst:opacity-70" }, kb = {
  key: 0,
  class: "cmst:mt-2 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Sb = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70",
  role: "status"
}, Cb = ["src", "alt", "data-testid"], Ab = {
  key: 3,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, Rb = {
  key: 4,
  class: "cmst:mt-3 cmst:text-sm cmst:text-red-300"
}, Ib = {
  key: 5,
  class: "cmst:mt-3 cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-viewer-params"
}, Eb = { class: "cmst:mt-1" }, $b = { class: "cmst:opacity-70" }, Ob = {
  key: 6,
  class: "cmst:mt-3 cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-viewer-attempts"
}, Tb = { class: "cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Pb = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Nb = { class: "cmst:mt-2 cmst:flex cmst:items-center cmst:gap-2" }, Mb = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-xs" }, zb = ["data-testid"], jb = {
  key: 0,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, Db = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, Lb = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:opacity-70"
}, Vb = { class: "cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1" }, Ub = {
  key: 1,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, Fb = { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, Wb = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, Bb = ["data-testid"], Gb = ["data-testid", "aria-label", "onClick", "onKeydown"], Hb = ["data-testid"], qb = {
  key: 0,
  class: "cmst:opacity-70"
}, Zb = { class: "cmst:mt-4 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, Kb = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, Jb = { key: 0 }, Qb = {
  key: 1,
  class: "cmst:flex cmst:items-center cmst:gap-2"
}, Yb = { class: "cmst:text-xs" }, Xb = /* @__PURE__ */ Ct({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = e, n = t, r = Xn(), o = /* @__PURE__ */ R(s.record?.note ?? ""), i = /* @__PURE__ */ R(!1), a = /* @__PURE__ */ R(null), l = /* @__PURE__ */ R(null), c = /* @__PURE__ */ R(null), u = /* @__PURE__ */ R(null), d = (S) => S ? Object.entries(S.params).map(([b, A]) => [b, String(A ?? "")]) : [], h = (S) => S && S.charAt(0).toUpperCase() + S.slice(1);
    hs(() => {
      c.value = document.activeElement, o.value = s.record?.note ?? "", l.value?.focus();
    }), Ri(() => {
      c.value?.focus?.();
    });
    async function m(S, b) {
      a.value = S;
      try {
        await b();
      } catch {
      } finally {
        a.value = null;
      }
    }
    function _() {
      n("close");
    }
    return (S, b) => e.record ? ($(), H("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-state": "open",
      "data-testid": "vue-history-viewer",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": `${e.record.kind} detail`,
      tabindex: "-1",
      onKeydown: Ws(Rr(_, ["stop"]), ["esc"])
    }, [
      f("div", bb, [
        f("div", wb, [
          f("div", null, [
            f("h2", _b, G(e.record.workflow || e.record.id), 1),
            f("p", xb, G(h(e.record.status)) + " · " + G(e.record.kind) + " · " + G(e.record.id), 1)
          ]),
          V(X, {
            ref_key: "closeBtn",
            ref: l,
            variant: "outline",
            size: "sm",
            "data-testid": "vue-viewer-close",
            onClick: _
          }, {
            default: W(() => [...b[13] || (b[13] = [
              O("Close", -1)
            ])]),
            _: 1
          }, 512)
        ]),
        g(r).detailError ? ($(), H("div", kb, G(g(r).detailError), 1)) : we("", !0),
        g(r).actionMessage ? ($(), H("p", Sb, G(g(r).actionMessage), 1)) : we("", !0),
        e.record.featuredOutput ? ($(), H("img", {
          key: 2,
          src: g(Pu)(e.record.featuredOutput),
          alt: e.record.workflow || e.record.id,
          class: "cmst:mx-auto cmst:mt-4 cmst:max-h-[50vh] cmst:max-w-full cmst:object-contain",
          "data-testid": `vue-viewer-image-${e.record.id}`
        }, null, 8, Cb)) : ($(), H("p", Ab, "No projected image asset.")),
        e.record.errors.length ? ($(), H("div", Rb, [
          ($(!0), H(Ee, null, et(e.record.errors, (A, M) => ($(), H("p", { key: M }, G(A.code) + ": " + G(A.message), 1))), 128))
        ])) : we("", !0),
        d(e.record).length ? ($(), H("div", Ib, [
          b[14] || (b[14] = f("h3", { class: "cmst:font-semibold" }, "Parameters", -1)),
          f("dl", Eb, [
            ($(!0), H(Ee, null, et(d(e.record), ([A, M]) => ($(), H("div", {
              key: A,
              class: "cmst:flex cmst:gap-2"
            }, [
              f("dt", $b, G(A), 1),
              f("dd", null, G(M), 1)
            ]))), 128))
          ])
        ])) : we("", !0),
        e.record.attempts.length ? ($(), H("div", Ob, [
          b[15] || (b[15] = f("h3", { class: "cmst:font-semibold" }, "Attempts", -1)),
          ($(!0), H(Ee, null, et(e.record.attempts, (A) => ($(), H("p", {
            key: A.index
          }, "Attempt " + G(A.index) + ": " + G(A.status), 1))), 128))
        ])) : we("", !0),
        f("div", Tb, [
          f("div", Pb, [
            b[18] || (b[18] = f("h3", { class: "cmst:font-semibold" }, "Annotations", -1)),
            f("div", Nb, [
              V(X, {
                size: "sm",
                variant: "outline",
                "aria-pressed": e.record.favorite ? "true" : "false",
                "data-testid": `vue-viewer-favorite-${e.record.id}`,
                onClick: b[0] || (b[0] = (A) => m("favorite", () => g(r).setFavorite(e.record, !e.record.favorite)))
              }, {
                default: W(() => [
                  O(G(e.record.favorite ? "★ Favorited" : "☆ Favorite"), 1)
                ]),
                _: 1
              }, 8, ["aria-pressed", "data-testid"])
            ]),
            f("label", Mb, [
              b[16] || (b[16] = O(" Note ", -1)),
              Ve(f("textarea", {
                "onUpdate:modelValue": b[1] || (b[1] = (A) => o.value = A),
                rows: "2",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-sm",
                "data-testid": `vue-viewer-note-${e.record.id}`
              }, null, 8, zb), [
                [at, o.value]
              ])
            ]),
            V(X, {
              class: "cmst:mt-2",
              size: "sm",
              variant: "secondary",
              "data-testid": `vue-viewer-note-save-${e.record.id}`,
              onClick: b[2] || (b[2] = (A) => m("note", () => g(r).setNote(e.record, o.value)))
            }, {
              default: W(() => [...b[17] || (b[17] = [
                O("Save note", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          e.record.kind === "generation" ? ($(), H("div", jb, [
            b[27] || (b[27] = f("h3", { class: "cmst:font-semibold" }, "Replay", -1)),
            f("div", Db, [
              V(X, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || a.value !== null,
                "data-testid": `vue-viewer-original-${e.record.id}`,
                onClick: b[3] || (b[3] = (A) => m("original", () => g(r).runReplayAction(e.record, "original")))
              }, {
                default: W(() => [...b[19] || (b[19] = [
                  O("Generate Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              V(X, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || a.value !== null,
                "data-testid": `vue-viewer-retry-${e.record.id}`,
                onClick: b[4] || (b[4] = (A) => m("retry", () => g(r).runReplayAction(e.record, "retry")))
              }, {
                default: W(() => [...b[20] || (b[20] = [
                  O("Retry Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              V(X, {
                size: "sm",
                variant: "outline",
                disabled: a.value !== null,
                "data-testid": `vue-viewer-resume-${e.record.id}`,
                onClick: b[5] || (b[5] = (A) => m("resume", () => g(r).runReplayAction(e.record, "resume")))
              }, {
                default: W(() => [...b[21] || (b[21] = [
                  O("Resume", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"])
            ]),
            e.record.replayCapable ? we("", !0) : ($(), H("p", Lb, G(e.record.replayReason || "Not replay-capable."), 1)),
            b[28] || (b[28] = f("h3", { class: "cmst:mt-3 cmst:font-semibold" }, "Outputs", -1)),
            ($(!0), H(Ee, null, et(e.record.outputs, (A) => ($(), H("div", {
              key: A.index,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs"
            }, [
              f("p", null, G(A.filename || `output ${A.index}`) + " · " + G(A.exportState), 1),
              f("div", Vb, [
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-download-${A.assetId}`,
                  onClick: (M) => m(`download-${A.index}`, () => g(r).downloadHistoryAsset(e.record, A, "original"))
                }, {
                  default: W(() => [...b[22] || (b[22] = [
                    O("Download", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-export-${A.assetId}`,
                  onClick: (M) => m(`export-${A.index}`, () => g(r).exportAsset(A))
                }, {
                  default: W(() => [...b[23] || (b[23] = [
                    O("Export", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (M) => m(`open-${A.index}`, () => g(r).openHistoryAsset(A.assetId))
                }, {
                  default: W(() => [...b[24] || (b[24] = [
                    O("Open", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (M) => m(`reveal-${A.index}`, () => g(r).revealHistoryAsset(A.assetId))
                }, {
                  default: W(() => [...b[25] || (b[25] = [
                    O("Reveal", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                V(X, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-featured-${A.index}`,
                  onClick: (M) => m("featured", () => g(r).setFeatured(e.record, A.index))
                }, {
                  default: W(() => [...b[26] || (b[26] = [
                    O("Feature", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"])
              ])
            ]))), 128))
          ])) : ($(), H("div", Ub, [
            b[32] || (b[32] = f("h3", { class: "cmst:font-semibold" }, "Experiment", -1)),
            f("p", Fb, "Cells: " + G(e.record.counts.cells) + " · Results: " + G(e.record.counts.results) + " · Failed: " + G(e.record.counts.failed), 1),
            f("div", Wb, [
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-resume-${e.record.id}`,
                onClick: b[6] || (b[6] = (A) => m("exp-resume", () => g(r).runExperimentAction(e.record, "resume")))
              }, {
                default: W(() => [...b[29] || (b[29] = [
                  O("Resume", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"]),
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-cancel-${e.record.id}`,
                onClick: b[7] || (b[7] = (A) => m("exp-cancel", () => g(r).runExperimentAction(e.record, "cancel")))
              }, {
                default: W(() => [...b[30] || (b[30] = [
                  O("Cancel", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"])
            ]),
            ($(!0), H(Ee, null, et(e.record.cells, (A) => ($(), H("div", {
              key: A.id,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs",
              "data-testid": `vue-cell-${A.id}`
            }, [
              f("button", {
                type: "button",
                class: "cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:text-left",
                "data-testid": `vue-cell-open-${A.id}`,
                "aria-label": `Open cell ${A.id}`,
                onClick: (M) => u.value = u.value === A.id ? null : A.id,
                onKeydown: Ws(Rr((M) => u.value = u.value === A.id ? null : A.id, ["prevent"]), ["enter"])
              }, [
                f("p", null, G(A.id) + " · " + G(A.status), 1)
              ], 40, Gb),
              u.value === A.id ? ($(), H("div", {
                key: 0,
                "data-testid": `vue-cell-detail-${A.id}`,
                tabindex: "0"
              }, [
                f("p", null, G(A.featuredOutput ? "Preview available" : "No preview projected") + " · " + G(A.status), 1),
                A.prompt ? ($(), H("p", qb, G(A.prompt), 1)) : we("", !0)
              ], 8, Hb)) : we("", !0),
              A.status === "failed" ? ($(), Ze(X, {
                key: 1,
                class: "cmst:mt-1",
                size: "sm",
                variant: "ghost",
                "data-testid": `vue-cell-retry-${A.id}`,
                onClick: (M) => m(`cell-${A.id}`, () => g(r).runExperimentAction(e.record, "cancel", A.id))
              }, {
                default: W(() => [...b[31] || (b[31] = [
                  O("Retry cell", -1)
                ])]),
                _: 1
              }, 8, ["data-testid", "onClick"])) : we("", !0)
            ], 8, Bb))), 128))
          ]))
        ]),
        f("div", Zb, [
          f("div", Kb, [
            V(X, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-a-${e.record.id}`,
              onClick: b[8] || (b[8] = (A) => g(r).selectCompare("a", e.record.id))
            }, {
              default: W(() => [...b[33] || (b[33] = [
                O("Compare A", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            V(X, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-b-${e.record.id}`,
              onClick: b[9] || (b[9] = (A) => g(r).selectCompare("b", e.record.id))
            }, {
              default: W(() => [...b[34] || (b[34] = [
                O("Compare B", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          i.value ? ($(), H("div", Qb, [
            f("span", Yb, "Delete this " + G(e.record.kind) + "?", 1),
            V(X, {
              size: "sm",
              "data-testid": `vue-delete-confirm-${e.record.id}`,
              onClick: b[11] || (b[11] = (A) => m("delete", () => g(r).remove(e.record).then(_)))
            }, {
              default: W(() => [...b[36] || (b[36] = [
                O("Confirm delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            V(X, {
              size: "sm",
              variant: "ghost",
              onClick: b[12] || (b[12] = (A) => i.value = !1)
            }, {
              default: W(() => [...b[37] || (b[37] = [
                O("Cancel", -1)
              ])]),
              _: 1
            })
          ])) : ($(), H("div", Jb, [
            V(X, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-delete-${e.record.id}`,
              onClick: b[10] || (b[10] = (A) => i.value = !0)
            }, {
              default: W(() => [...b[35] || (b[35] = [
                O("Delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]))
        ])
      ])
    ], 40, yb)) : we("", !0);
  }
});
function ew() {
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
const tw = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, sw = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70",
  "data-testid": "vue-picker-empty"
}, nw = {
  key: 1,
  class: "cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:sm:grid-cols-3"
}, rw = ["data-testid", "aria-label", "onClick"], ow = ["src", "alt"], iw = { class: "cmst:mt-1 cmst:block cmst:truncate cmst:text-xs" }, aw = { class: "cmst:mt-3 cmst:flex cmst:justify-center" }, lw = /* @__PURE__ */ Ct({
  __name: "HistoryPicker",
  emits: ["select", "cancel"],
  setup(e, { emit: t }) {
    const s = Xn(), n = /* @__PURE__ */ R(""), r = /* @__PURE__ */ R(null);
    hs(async () => {
      r.value = ew(), await s.initialize();
    });
    const o = t;
    let i;
    function a(c) {
      window.clearTimeout(i), i = window.setTimeout(() => {
        s.setQuery(c), s.loadFeed();
      }, 250);
    }
    function l(c) {
      o("select", c);
    }
    return (c, u) => ($(), Ze(Md, {
      to: r.value ?? void 0
    }, [
      f("div", {
        class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
        "data-state": "open",
        "data-testid": "vue-history-picker",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": "Pick a History generation",
        tabindex: "-1",
        onKeydown: u[4] || (u[4] = Ws(Rr((d) => o("cancel"), ["stop"]), ["esc"]))
      }, [
        V(Xe, { class: "cmst:w-[min(48rem,94vw)] cmst:max-h-[86vh] cmst:overflow-auto cmst:p-4" }, {
          default: W(() => [
            f("div", tw, [
              u[6] || (u[6] = f("h2", { class: "cmst:text-base cmst:font-semibold" }, "Pick from History", -1)),
              V(X, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-picker-cancel",
                onClick: u[0] || (u[0] = (d) => o("cancel"))
              }, {
                default: W(() => [...u[5] || (u[5] = [
                  O("Cancel", -1)
                ])]),
                _: 1
              })
            ]),
            Ve(f("input", {
              "onUpdate:modelValue": u[1] || (u[1] = (d) => n.value = d),
              class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              placeholder: "Search generations",
              "aria-label": "Search generations",
              onInput: u[2] || (u[2] = (d) => a(d.target.value))
            }, null, 544), [
              [at, n.value]
            ]),
            g(s).records.length ? ($(), H("div", nw, [
              ($(!0), H(Ee, null, et(g(s).records, (d) => ($(), H("button", {
                key: `${d.kind}:${d.id}`,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-picker-option-${d.id}`,
                "aria-label": `Select ${d.workflow || d.id}`,
                onClick: (h) => l(d)
              }, [
                d.featuredOutput ? ($(), H("img", {
                  key: 0,
                  src: g(Vi)(d.featuredOutput),
                  alt: d.workflow || d.id,
                  class: "cmst:aspect-square cmst:w-full cmst:object-cover cmst:rounded",
                  loading: "lazy"
                }, null, 8, ow)) : we("", !0),
                f("span", iw, G(d.workflow || d.id), 1)
              ], 8, rw))), 128))
            ])) : ($(), H("div", sw, "No generations match.")),
            f("div", aw, [
              g(s).hasMore ? ($(), Ze(X, {
                key: 0,
                variant: "outline",
                size: "sm",
                onClick: u[3] || (u[3] = (d) => g(s).loadFeed(!0))
              }, {
                default: W(() => [...u[7] || (u[7] = [
                  O("Load more", -1)
                ])]),
                _: 1
              })) : we("", !0)
            ])
          ]),
          _: 1
        })
      ], 32)
    ], 8, ["to"]));
  }
}), cw = { class: "cmst:flex cmst:items-center cmst:justify-between" }, uw = { class: "cmst:flex cmst:gap-2" }, dw = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-3" }, fw = ["src", "alt", "data-testid"], mw = {
  key: 1,
  class: "cmst:text-xs cmst:opacity-60"
}, pw = /* @__PURE__ */ Ct({
  __name: "CompareViewer",
  setup(e) {
    const t = Xn(), s = Ue(() => t.compareRecords);
    function n(r, o) {
      const a = t.records.find((l) => l.id === r)?.featuredOutput;
      return a ? o === "original" ? Nu(a) : a.dataSaverUrl || a.thumbUrl : null;
    }
    return (r, o) => s.value.a || s.value.b ? ($(), Ze(Xe, {
      key: 0,
      class: "cmst:p-4",
      "data-testid": "vue-compare"
    }, {
      default: W(() => [
        f("div", cw, [
          o[4] || (o[4] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Compare (transient — never persisted)", -1)),
          f("div", uw, [
            V(X, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-swap",
              onClick: o[0] || (o[0] = (i) => g(t).swapCompare())
            }, {
              default: W(() => [...o[2] || (o[2] = [
                O("Switch A/B", -1)
              ])]),
              _: 1
            }),
            V(X, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-clear",
              onClick: o[1] || (o[1] = (i) => g(t).clearCompare())
            }, {
              default: W(() => [...o[3] || (o[3] = [
                O("Clear", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        f("div", dw, [
          ($(), H(Ee, null, et(["a", "b"], (i) => f("figure", { key: i }, [
            n(i === "a" ? g(t).compareA : g(t).compareB, "original") ? ($(), H("img", {
              key: 0,
              src: n(i === "a" ? g(t).compareA : g(t).compareB, "original"),
              alt: `Compare ${i.toUpperCase()}`,
              class: "cmst:w-full cmst:rounded cmst:object-contain",
              "data-testid": `vue-compare-${i}`
            }, null, 8, fw)) : ($(), H("figcaption", mw, "Slot " + G(i.toUpperCase()) + " empty or deleted.", 1))
          ])), 64))
        ])
      ]),
      _: 1
    })) : we("", !0);
  }
}), hw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, gw = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, vw = { class: "cmst:flex cmst:gap-2" }, yw = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, bw = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, ww = ["value"], _w = ["value"], xw = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, kw = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Sw = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Cw = { class: "cmst:text-xs cmst:opacity-70" }, Aw = { class: "cmst:flex cmst:gap-2" }, Rw = { class: "cmst:flex cmst:justify-center" }, Iw = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, Ew = /* @__PURE__ */ Ct({
  __name: "HistoryView",
  setup(e) {
    const t = Xn(), s = Yc(), n = kp(), r = /* @__PURE__ */ R(t.query), o = /* @__PURE__ */ R(!1);
    function i() {
      const h = s.query.focus;
      return typeof h == "string" && h !== "" ? h : null;
    }
    hs(async () => {
      await t.initialize(), await t.applyRouteFocus(i());
    }), As(
      () => s.query.focus,
      (h) => {
        t.applyRouteFocus(typeof h == "string" ? h : null);
      }
    );
    let a;
    As(r, (h) => {
      window.clearTimeout(a), a = window.setTimeout(() => {
        t.setQuery(h), t.loadFeed();
      }, 250);
    });
    async function l(h) {
      t.setFocus(h.id), await n.replace({ name: "history", query: { focus: h.id } }), await t.loadDetail(h.id, h.kind), t.viewerOpen = !0;
    }
    async function c() {
      t.viewerOpen = !1, await n.replace({ name: "history" });
    }
    function u(h, m) {
      m.stopPropagation(), t.toggleSelection(h);
    }
    function d(h) {
      o.value = !1, l(h);
    }
    return (h, m) => ($(), H("section", {
      class: kt(g(Yn)()),
      "data-testid": "vue-page-history"
    }, [
      V(Xe, { class: "cmst:p-4" }, {
        default: W(() => [
          f("div", hw, [
            f("div", null, [
              f("h2", gw, [
                V(g(eu), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                m[15] || (m[15] = O("History V2", -1))
              ]),
              m[16] || (m[16] = f("p", { class: "cmst:text-sm cmst:opacity-80" }, "Server cursor stays authoritative; stale reads never commit.", -1))
            ]),
            f("div", vw, [
              V(X, {
                variant: "outline",
                size: "sm",
                "data-testid": "vue-history-picker-open",
                onClick: m[0] || (m[0] = (_) => o.value = !0)
              }, {
                default: W(() => [...m[17] || (m[17] = [
                  O("Pick generation", -1)
                ])]),
                _: 1
              }),
              V(X, {
                variant: "outline",
                size: "icon",
                "aria-label": "Refresh history",
                disabled: g(t).loading,
                onClick: m[1] || (m[1] = (_) => g(t).loadFeed())
              }, {
                default: W(() => [
                  V(g(to), {
                    class: kt(["cmst:size-4", g(t).loading ? "cmst:animate-spin" : ""])
                  }, null, 8, ["class"])
                ]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          f("div", yw, [
            f("label", bw, [
              V(g(Up), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              }),
              Ve(f("input", {
                "onUpdate:modelValue": m[2] || (m[2] = (_) => r.value = _),
                class: "cmst:h-9 cmst:w-56 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search history",
                "aria-label": "Search history",
                "data-testid": "vue-history-search"
              }, null, 512), [
                [at, r.value]
              ])
            ]),
            f("select", {
              value: g(t).kindFilter,
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              "aria-label": "Record kind",
              onChange: m[3] || (m[3] = (_) => {
                g(t).setKindFilter(_.target.value), g(t).loadFeed();
              })
            }, [...m[18] || (m[18] = [
              f("option", { value: "mixed" }, "All kinds", -1),
              f("option", { value: "generation" }, "Generations", -1),
              f("option", { value: "experiment" }, "Experiments", -1)
            ])], 40, ww),
            f("select", {
              value: g(t).statusFilter,
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              "aria-label": "Status filter",
              onChange: m[4] || (m[4] = (_) => {
                g(t).setStatusFilter(_.target.value), g(t).loadFeed();
              })
            }, [...m[19] || (m[19] = [
              f("option", { value: "" }, "All statuses", -1),
              f("option", { value: "completed" }, "Completed", -1),
              f("option", { value: "failed" }, "Failed", -1),
              f("option", { value: "running" }, "Running", -1),
              f("option", { value: "canceled" }, "Canceled", -1)
            ])], 40, _w),
            Ve(f("select", {
              "onUpdate:modelValue": m[5] || (m[5] = (_) => g(t).sort = _),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              "aria-label": "Sort order",
              onChange: m[6] || (m[6] = (_) => {
                g(t).setSort(g(t).sort), g(t).loadFeed();
              })
            }, [...m[20] || (m[20] = [
              f("option", { value: "newest" }, "Newest", -1),
              f("option", { value: "oldest" }, "Oldest", -1),
              f("option", { value: "fastest" }, "Fastest", -1),
              f("option", { value: "slowest" }, "Slowest", -1)
            ])], 544), [
              [ls, g(t).sort]
            ]),
            f("label", xw, [
              Ve(f("input", {
                "onUpdate:modelValue": m[7] || (m[7] = (_) => g(t).favoriteOnly = _),
                type: "checkbox",
                onChange: m[8] || (m[8] = (_) => {
                  g(t).setFavoriteOnly(g(t).favoriteOnly), g(t).loadFeed();
                })
              }, null, 544), [
                [tn, g(t).favoriteOnly]
              ]),
              m[21] || (m[21] = O(" Favorites", -1))
            ])
          ])
        ]),
        _: 1
      }),
      g(t).error ? ($(), H("div", kw, [
        O(G(g(t).error) + " ", 1),
        V(X, {
          class: "cmst:ml-2",
          size: "sm",
          variant: "outline",
          onClick: m[9] || (m[9] = (_) => g(t).loadFeed())
        }, {
          default: W(() => [...m[22] || (m[22] = [
            O("Retry", -1)
          ])]),
          _: 1
        })
      ])) : we("", !0),
      g(t).loading && !g(t).records.length ? ($(), Ze(Xe, {
        key: 1,
        class: "cmst:p-6 cmst:text-sm"
      }, {
        default: W(() => [...m[23] || (m[23] = [
          O("Loading History V2…", -1)
        ])]),
        _: 1
      })) : g(t).records.length ? ($(), H(Ee, { key: 3 }, [
        f("div", Sw, [
          f("p", Cw, G(g(t).records.length) + " records · " + G(g(t).selection.length) + " selected", 1),
          f("div", Aw, [
            g(t).selection.length ? ($(), Ze(X, {
              key: 0,
              size: "sm",
              variant: "outline",
              "data-testid": "vue-history-bulk-delete",
              onClick: m[11] || (m[11] = (_) => g(t).removeSelected())
            }, {
              default: W(() => [
                O("Delete selected (" + G(g(t).selection.length) + ")", 1)
              ]),
              _: 1
            })) : we("", !0),
            g(t).selection.length ? ($(), Ze(X, {
              key: 1,
              size: "sm",
              variant: "ghost",
              onClick: m[12] || (m[12] = (_) => g(t).clearSelection())
            }, {
              default: W(() => [...m[26] || (m[26] = [
                O("Clear selection", -1)
              ])]),
              _: 1
            })) : we("", !0)
          ])
        ]),
        V(vb, {
          records: g(t).records,
          onSelect: l
        }, null, 8, ["records"]),
        f("div", Rw, [
          g(t).hasMore ? ($(), Ze(X, {
            key: 0,
            variant: "outline",
            onClick: m[13] || (m[13] = (_) => g(t).loadFeed(!0))
          }, {
            default: W(() => [...m[27] || (m[27] = [
              O("Load more", -1)
            ])]),
            _: 1
          })) : we("", !0)
        ]),
        f("div", Iw, [
          ($(!0), H(Ee, null, et(g(t).records.slice(0, 6), (_) => ($(), Ze(X, {
            key: `bulk-${_.kind}-${_.id}`,
            size: "sm",
            variant: g(t).selection.includes(`${_.kind}:${_.id}`) ? "default" : "ghost",
            "data-testid": `vue-history-select-${_.id}`,
            onClick: (S) => u(_, S)
          }, {
            default: W(() => [
              O(G(g(t).selection.includes(`${_.kind}:${_.id}`) ? "✓" : "+") + " " + G(_.id.slice(0, 12)), 1)
            ]),
            _: 2
          }, 1032, ["variant", "data-testid", "onClick"]))), 128))
        ])
      ], 64)) : ($(), Ze(Xe, {
        key: 2,
        class: "cmst:p-6 cmst:text-sm cmst:opacity-75",
        "data-testid": "vue-history-empty"
      }, {
        default: W(() => [
          m[25] || (m[25] = O(" No History V2 records match this query. ", -1)),
          V(X, {
            class: "cmst:ml-2",
            size: "sm",
            variant: "outline",
            onClick: m[10] || (m[10] = (_) => {
              g(t).setQuery(""), r.value = "", g(t).setStatusFilter(""), g(t).setKindFilter("mixed"), g(t).loadFeed();
            })
          }, {
            default: W(() => [...m[24] || (m[24] = [
              O("Clear filters", -1)
            ])]),
            _: 1
          })
        ]),
        _: 1
      })),
      V(pw),
      g(t).viewerOpen ? ($(), Ze(Xb, {
        key: 4,
        record: g(t).selected,
        onClose: c
      }, null, 8, ["record"])) : we("", !0),
      o.value ? ($(), Ze(lw, {
        key: 5,
        onSelect: d,
        onCancel: m[14] || (m[14] = (_) => o.value = !1)
      })) : we("", !0)
    ], 2));
  }
}), $w = /* @__PURE__ */ mn("studio-playground", () => {
  const e = /* @__PURE__ */ R("txt2img"), t = /* @__PURE__ */ R(!1);
  function s(r) {
    e.value = r;
  }
  function n(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: s, setExperimentMode: n };
}), Ow = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Tw = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, Pw = ["checked"], Nw = { class: "cmst:text-sm cmst:opacity-80" }, Mw = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, zw = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, jw = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Dw = { key: 0 }, Lw = /* @__PURE__ */ Ct({
  __name: "PlaygroundView",
  setup(e) {
    const t = $w(), s = Ot(), n = /* @__PURE__ */ R(null), r = Ue(() => n.value ? s.get(n.value)?.progress ?? null : null);
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
    return (i, a) => ($(), H("section", {
      class: kt(g(Yn)()),
      "data-testid": "vue-page-playground"
    }, [
      V(Xe, { class: "cmst:p-4" }, {
        default: W(() => [
          f("h2", Ow, [
            V(g(Xc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = O(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = f("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          f("label", Tw, [
            f("input", {
              type: "checkbox",
              checked: g(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => g(t).setExperimentMode(l.target.checked))
            }, null, 40, Pw),
            a[2] || (a[2] = O(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      V(Xe, { class: "cmst:p-4" }, {
        default: W(() => [
          a[5] || (a[5] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          f("p", Nw, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + G(g(s).active.length) + ". ", 1),
          f("div", Mw, [
            V(X, {
              variant: "default",
              size: "sm",
              disabled: n.value !== null,
              onClick: o
            }, {
              default: W(() => [
                V(g(jp), { "aria-hidden": "true" }),
                a[4] || (a[4] = O(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? ($(), H("span", zw, G(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : we("", !0)
          ]),
          f("ul", jw, [
            ($(!0), H(Ee, null, et(g(s).all.slice(-5), (l) => ($(), H("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              f("strong", null, G(l.label), 1),
              O(" — " + G(l.status), 1),
              l.message ? ($(), H("span", Dw, " — " + G(l.message), 1)) : we("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), Vw = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Uw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Fw = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Ww = {
  "aria-label": "Settings sections",
  class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-1"
}, Bw = ["aria-current", "data-testid", "onClick"], Gw = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Hw = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, qw = ["value"], Zw = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, Kw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Jw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Qw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Yw = ["value"], Xw = ["value"], e_ = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70"
}, t_ = { class: "cmst:flex cmst:items-center cmst:justify-between" }, s_ = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, n_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, r_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, o_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, i_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, a_ = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-4 cmst:text-sm" }, l_ = { class: "cmst:flex cmst:items-center cmst:gap-2" }, c_ = { class: "cmst:flex cmst:items-center cmst:gap-2" }, u_ = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, d_ = ["aria-pressed", "data-testid", "onClick"], f_ = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70"
}, m_ = { class: "cmst:flex cmst:items-center cmst:justify-between" }, p_ = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, h_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, g_ = ["value"], v_ = ["value"], y_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, b_ = ["value"], w_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, __ = ["value"], x_ = { class: "cmst:flex cmst:items-center cmst:justify-between" }, k_ = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, S_ = { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, C_ = {
  key: 0,
  "data-testid": "vue-settings-restart-banner"
}, A_ = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, R_ = { class: "cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" }, I_ = /* @__PURE__ */ Ct({
  __name: "SettingsView",
  setup(e) {
    const t = mu(), s = /* @__PURE__ */ R(75), n = /* @__PURE__ */ R(""), r = /* @__PURE__ */ R("original"), o = /* @__PURE__ */ R("balanced"), i = /* @__PURE__ */ R(!1), a = /* @__PURE__ */ R(!0), l = /* @__PURE__ */ R("off"), c = /* @__PURE__ */ R(70), u = /* @__PURE__ */ R("off"), d = /* @__PURE__ */ R(""), h = /* @__PURE__ */ R(!1), m = /* @__PURE__ */ R(!1), _ = Ue(() => t.config), S = Ue(() => _.value?.available_gpus ?? []);
    function b() {
      const q = _.value;
      q && (s.value = q.quality, n.value = q.save_folder, r.value = q.output_format, o.value = q.webp_lossless_compression, i.value = q.auto_save_local, a.value = q.save_metadata_sidecar, l.value = q.data_saver_default, c.value = q.data_saver_quality, u.value = t.profileLevel, d.value = q.gpu, h.value = q.skip_plan_validation);
    }
    hs(async () => {
      await t.initialize().catch(() => {
      }), await t.loadGolden().catch(() => {
      }), b();
    });
    async function A() {
      await t.save({
        output_format: r.value,
        quality: Number(s.value),
        webp_lossless_compression: o.value,
        auto_save_local: i.value,
        save_folder: n.value,
        save_metadata_sidecar: a.value,
        data_saver_default: l.value,
        data_saver_quality: Number(c.value)
      }).catch(() => {
      }), b();
    }
    async function M() {
      await t.save({ gpu: d.value }).catch(() => {
      }), b();
    }
    async function Y() {
      await t.save({
        data_saver_default: l.value,
        data_saver_quality: Number(c.value)
      }).catch(() => {
      }), b();
    }
    async function J() {
      await t.setSkipPlanValidation(h.value).catch(() => {
      }), b();
    }
    async function ce() {
      await t.setProfile(u.value).catch(() => {
      }), b();
    }
    async function Ae(q) {
      await t.resetSection(q), b();
    }
    async function re() {
      if (!m.value) {
        m.value = !0;
        return;
      }
      m.value = !1, await t.resetAll(), b();
    }
    function U(q) {
      return "cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:border cmst:border-solid " + (t.activeSection === q ? "cmst:bg-cmst-secondary cmst:text-cmst-fg cmst:border-cmst-border" : "cmst:bg-transparent cmst:text-cmst-muted cmst:border-transparent cmst:hover:bg-cmst-secondary");
    }
    return (q, x) => ($(), H("section", {
      class: kt(g(Yn)()),
      "data-testid": "vue-page-settings"
    }, [
      g(t).error ? ($(), H("div", Vw, G(g(t).error), 1)) : we("", !0),
      V(Xe, { class: "cmst:p-4" }, {
        default: W(() => [
          f("div", Uw, [
            f("div", null, [
              f("h2", Fw, [
                V(g(su), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                x[20] || (x[20] = O(" Settings ", -1))
              ]),
              x[21] || (x[21] = f("p", { class: "cmst:text-sm cmst:opacity-80" }, "Server-backed authority. Failed saves revert to server truth.", -1))
            ]),
            V(X, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload settings",
              disabled: g(t).loading,
              onClick: x[0] || (x[0] = (Q) => g(t).load().then(b).catch(() => {
              }))
            }, {
              default: W(() => [
                V(g(to), {
                  class: kt(["cmst:size-4", g(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          f("nav", Ww, [
            ($(!0), H(Ee, null, et(g(fu), (Q) => ($(), H("button", {
              key: Q,
              type: "button",
              class: kt(U(Q)),
              "aria-current": g(t).activeSection === Q ? "true" : void 0,
              "data-testid": `vue-settings-tab-${Q}`,
              onClick: (xe) => g(t).setSection(Q)
            }, G(Q), 11, Bw))), 128))
          ])
        ]),
        _: 1
      }),
      g(t).activeSection === "generation" ? ($(), Ze(Xe, {
        key: 1,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          f("div", Gw, [
            x[23] || (x[23] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Generation", -1)),
            V(X, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-settings-reset-generation",
              onClick: x[1] || (x[1] = (Q) => Ae("generation"))
            }, {
              default: W(() => [...x[22] || (x[22] = [
                O("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          f("label", Hw, [
            x[24] || (x[24] = O(" GPU ", -1)),
            Ve(f("select", {
              "onUpdate:modelValue": x[2] || (x[2] = (Q) => d.value = Q),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              "data-testid": "vue-settings-gpu",
              onChange: M
            }, [
              ($(!0), H(Ee, null, et(S.value, (Q) => ($(), H("option", {
                key: Q.value,
                value: Q.value
              }, G(Q.label), 9, qw))), 128))
            ], 544), [
              [ls, d.value]
            ])
          ]),
          f("div", Zw, [
            f("label", Kw, [
              x[26] || (x[26] = O(" Data Saver default ", -1)),
              Ve(f("select", {
                "onUpdate:modelValue": x[3] || (x[3] = (Q) => l.value = Q),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: Y
              }, [...x[25] || (x[25] = [
                f("option", { value: "off" }, "Off", -1),
                f("option", { value: "on" }, "On", -1)
              ])], 544), [
                [ls, l.value]
              ])
            ]),
            f("label", Jw, [
              x[27] || (x[27] = O(" Data Saver quality ", -1)),
              Ve(f("input", {
                "onUpdate:modelValue": x[4] || (x[4] = (Q) => c.value = Q),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: Y
              }, null, 544), [
                [
                  at,
                  c.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            f("div", Qw, [
              x[29] || (x[29] = O(" Golden profile ", -1)),
              f("select", {
                value: g(t).selectedGoldenProfile,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-settings-golden-profile",
                onChange: x[5] || (x[5] = (Q) => g(t).selectGoldenProfile(Q.target.value))
              }, [
                x[28] || (x[28] = f("option", { value: "" }, "None", -1)),
                ($(!0), H(Ee, null, et(g(t).goldenProfiles, (Q) => ($(), H("option", {
                  key: Q.name,
                  value: Q.name
                }, G(Q.name), 9, Xw))), 128))
              ], 40, Yw)
            ])
          ]),
          _.value?.engine_migration_notice ? ($(), H("p", e_, G(_.value.engine_migration_notice), 1)) : we("", !0)
        ]),
        _: 1
      })) : we("", !0),
      g(t).activeSection === "outputs" ? ($(), Ze(Xe, {
        key: 2,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          f("div", t_, [
            x[31] || (x[31] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Outputs", -1)),
            V(X, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-settings-reset-outputs",
              onClick: x[6] || (x[6] = (Q) => Ae("outputs"))
            }, {
              default: W(() => [...x[30] || (x[30] = [
                O("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          f("div", s_, [
            f("label", n_, [
              x[33] || (x[33] = O(" Output format ", -1)),
              Ve(f("select", {
                "onUpdate:modelValue": x[7] || (x[7] = (Q) => r.value = Q),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, [...x[32] || (x[32] = [
                f("option", { value: "original" }, "Original", -1),
                f("option", { value: "png" }, "PNG", -1),
                f("option", { value: "jpeg" }, "JPEG", -1),
                f("option", { value: "webp" }, "WebP", -1)
              ])], 512), [
                [ls, r.value]
              ])
            ]),
            f("label", r_, [
              x[34] || (x[34] = O(" Quality ", -1)),
              Ve(f("input", {
                "onUpdate:modelValue": x[8] || (x[8] = (Q) => s.value = Q),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [
                  at,
                  s.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            f("label", o_, [
              x[36] || (x[36] = O(" WebP lossless compression ", -1)),
              Ve(f("select", {
                "onUpdate:modelValue": x[9] || (x[9] = (Q) => o.value = Q),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, [...x[35] || (x[35] = [
                f("option", { value: "balanced" }, "Balanced", -1),
                f("option", { value: "fast" }, "Fast", -1),
                f("option", { value: "best" }, "Best", -1)
              ])], 512), [
                [ls, o.value]
              ])
            ]),
            f("label", i_, [
              x[37] || (x[37] = O(" Save folder ", -1)),
              Ve(f("input", {
                "onUpdate:modelValue": x[10] || (x[10] = (Q) => n.value = Q),
                type: "text",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [at, n.value]
              ])
            ])
          ]),
          f("div", a_, [
            f("label", l_, [
              Ve(f("input", {
                "onUpdate:modelValue": x[11] || (x[11] = (Q) => i.value = Q),
                type: "checkbox"
              }, null, 512), [
                [tn, i.value]
              ]),
              x[38] || (x[38] = O(" Auto-save local ", -1))
            ]),
            f("label", c_, [
              Ve(f("input", {
                "onUpdate:modelValue": x[12] || (x[12] = (Q) => a.value = Q),
                type: "checkbox"
              }, null, 512), [
                [tn, a.value]
              ]),
              x[39] || (x[39] = O(" Save metadata sidecar ", -1))
            ]),
            V(X, {
              size: "sm",
              disabled: g(t).saving,
              "data-testid": "vue-settings-save-output",
              onClick: A
            }, {
              default: W(() => [
                O(G(g(t).saving ? "Saving…" : "Save outputs"), 1)
              ]),
              _: 1
            }, 8, ["disabled"])
          ])
        ]),
        _: 1
      })) : we("", !0),
      g(t).activeSection === "accounts" ? ($(), Ze(Xe, {
        key: 3,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          x[40] || (x[40] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Accounts & Tokens", -1)),
          x[41] || (x[41] = f("p", { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, "Credential status lives in Manage Modal. Golden favorites are a browser-only preference here.", -1)),
          f("div", u_, [
            ($(!0), H(Ee, null, et(g(t).goldenProfiles, (Q) => ($(), H("button", {
              key: Q.name,
              type: "button",
              class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:px-3 cmst:py-1 cmst:text-sm",
              "aria-pressed": g(t).favoriteGoldenProfiles.includes(Q.name) ? "true" : "false",
              "data-testid": `vue-golden-favorite-${Q.name}`,
              onClick: (xe) => g(t).toggleGoldenFavorite(Q.name)
            }, G(g(t).favoriteGoldenProfiles.includes(Q.name) ? "★" : "☆") + " " + G(Q.name), 9, d_))), 128))
          ]),
          g(t).goldenProfiles.length ? we("", !0) : ($(), H("p", f_, "Golden catalog not loaded yet."))
        ]),
        _: 1
      })) : we("", !0),
      g(t).activeSection === "interface" ? ($(), Ze(Xe, {
        key: 4,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          f("div", m_, [
            x[43] || (x[43] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Interface", -1)),
            V(X, {
              variant: "ghost",
              size: "sm",
              onClick: x[13] || (x[13] = (Q) => Ae("interface"))
            }, {
              default: W(() => [...x[42] || (x[42] = [
                O("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          f("div", p_, [
            f("label", h_, [
              x[44] || (x[44] = O(" History grid columns ", -1)),
              f("select", {
                value: g(t).columnsPreference,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: x[14] || (x[14] = (Q) => g(t).setHistoryColumns(Q.target.value))
              }, [
                ($(), H(Ee, null, et([2, 3, 4, 5, 6, 7, 8], (Q) => f("option", {
                  key: Q,
                  value: String(Q)
                }, G(Q), 9, v_)), 64))
              ], 40, g_)
            ]),
            f("label", y_, [
              x[46] || (x[46] = O(" Remote inventory refresh ", -1)),
              f("select", {
                value: g(t).refreshIntervalPreference,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: x[15] || (x[15] = (Q) => g(t).setInventoryInterval(Q.target.value))
              }, [...x[45] || (x[45] = [
                f("option", { value: "0" }, "Off", -1),
                f("option", { value: "60" }, "1 minute", -1),
                f("option", { value: "300" }, "5 minutes", -1),
                f("option", { value: "900" }, "15 minutes", -1),
                f("option", { value: "1800" }, "30 minutes", -1)
              ])], 40, b_)
            ]),
            f("label", w_, [
              x[48] || (x[48] = O(" Shell density ", -1)),
              f("select", {
                value: g(t).density,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-density-toggle",
                onChange: x[16] || (x[16] = (Q) => g(t).setDensity(Q.target.value))
              }, [...x[47] || (x[47] = [
                f("option", { value: "comfortable" }, "Comfortable", -1),
                f("option", { value: "compact" }, "Compact", -1)
              ])], 40, __)
            ])
          ])
        ]),
        _: 1
      })) : we("", !0),
      g(t).activeSection === "advanced" ? ($(), Ze(Xe, {
        key: 5,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          f("div", x_, [
            x[50] || (x[50] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Advanced", -1)),
            V(X, {
              variant: "ghost",
              size: "sm",
              onClick: x[17] || (x[17] = (Q) => Ae("advanced"))
            }, {
              default: W(() => [...x[49] || (x[49] = [
                O("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          f("label", k_, [
            x[52] || (x[52] = O(" Heavy tracing ", -1)),
            Ve(f("select", {
              "onUpdate:modelValue": x[18] || (x[18] = (Q) => u.value = Q),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              onChange: ce
            }, [...x[51] || (x[51] = [
              f("option", { value: "off" }, "Off", -1),
              f("option", { value: "summary" }, "Summary", -1),
              f("option", { value: "detailed" }, "Detailed", -1),
              f("option", { value: "trace" }, "Trace", -1),
              f("option", { value: "trace_verbose" }, "Verbose trace", -1)
            ])], 544), [
              [ls, u.value]
            ])
          ]),
          f("p", S_, [
            x[53] || (x[53] = O(" Requires ComfyUI restart. ", -1)),
            g(t).profileLevel !== g(t).effectiveProfileLevel ? ($(), H("span", C_, " Restart pending: selected " + G(g(t).profileLevel) + ", effective " + G(g(t).effectiveProfileLevel) + ". ", 1)) : we("", !0)
          ]),
          f("label", A_, [
            Ve(f("input", {
              "onUpdate:modelValue": x[19] || (x[19] = (Q) => h.value = Q),
              type: "checkbox",
              "data-testid": "vue-settings-skip-validation",
              onChange: J
            }, null, 544), [
              [tn, h.value]
            ]),
            x[54] || (x[54] = O(" Skip plan validation (temporary triage only) ", -1))
          ]),
          f("div", R_, [
            V(X, {
              variant: "outline",
              size: "sm",
              "data-testid": "vue-settings-reset-all",
              onClick: re
            }, {
              default: W(() => [
                O(G(m.value ? "Confirm reset all settings" : "Reset all settings"), 1)
              ]),
              _: 1
            }),
            x[55] || (x[55] = f("p", { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, "Resets only Settings-owned keys. Credentials and user data are not affected.", -1))
          ])
        ]),
        _: 1
      })) : we("", !0)
    ], 2));
  }
});
function Ui(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return Object.prototype.hasOwnProperty.call(t, "workflow") ? t.workflow : Object.prototype.hasOwnProperty.call(t, "version") ? t.version : Object.prototype.hasOwnProperty.call(t, "mapping") ? t.mapping : e;
}
async function E_(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.tag && t.set("tag", e.tag), e.folder && t.set("folder", e.folder), e.favorite && t.set("favorite", "1");
  const s = t.toString() ? `?${t}` : "";
  return se(`/studio/workflows${s}`);
}
async function $_(e) {
  return se(`/studio/workflows/${encodeURIComponent(e)}`).then((t) => ({ ...t, workflow: Ui(t) }));
}
async function O_(e) {
  return se(`/studio/workflows/${encodeURIComponent(e)}/versions`);
}
async function T_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}`).then((t) => Ui(t));
}
async function P_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`).then((t) => Ui(t));
}
async function N_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/candidates`);
}
async function M_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/dependencies`);
}
async function z_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`);
}
async function wl(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/portability`);
}
async function j_() {
  return se("/studio/workflows/folders");
}
async function D_() {
  return se("/studio/workflows/tags");
}
async function _l(e, t) {
  return se(`/studio/workflows/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function L_(e) {
  return se("/studio/workflows", { method: "POST", body: e });
}
async function V_(e) {
  return se("/studio/workflows/import", { method: "POST", body: e });
}
async function U_(e) {
  return se(`/studio/workflows/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function F_(e) {
  return se("/studio/workflows/folders", { method: "POST", body: { path: e } });
}
async function W_(e, t) {
  return se(`/studio/workflows/${encodeURIComponent(e)}/versions`, { method: "POST", body: t });
}
async function B_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/state`);
}
async function G_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`, { method: "POST", body: t });
}
async function H_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/revision`, { method: "POST", body: t });
}
async function q_(e, t) {
  return se(`/studio/workflows/${encodeURIComponent(e)}/dependencies/nonessential`, { method: "POST", body: { keys: t } });
}
async function Z_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`, { method: "PATCH", body: t });
}
async function K_(e, t) {
  return se(`/studio/method-compat?workflow_id=${encodeURIComponent(e)}&version_id=${encodeURIComponent(t)}`);
}
async function J_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`);
}
async function Q_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`, { method: "POST", body: t });
}
async function Y_(e, t) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function X_(e) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function ex(e, t = {}) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}/duplicate`, { method: "POST", body: t });
}
async function tx(e, t) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}/copy-to-version`, { method: "POST", body: { workflow_version_id: t } });
}
async function sx(e, t) {
  return se(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`);
}
async function nx(e) {
  return se("/studio/guidance-mappings", { method: "POST", body: { mapping: e } });
}
async function rx(e, t) {
  return se(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`, { method: "DELETE" });
}
async function ox(e) {
  const t = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(e)}/export`);
  if (!t.ok) return { ok: !1, message: `Export failed with status ${t.status}` };
  const s = await t.blob(), n = t.headers.get("Content-Disposition") || "", r = /filename="?([^";]+)"?/.exec(n);
  return { ok: !0, blob: s, filename: r ? r[1].trim() : "manifest.json" };
}
async function xl(e, t = !0) {
  return se(`/studio/workflows/import-manifest?dry_run=${t ? "1" : "0"}`, { method: "POST", body: e });
}
function ix(e) {
  const t = String(e || "t2i").toLowerCase();
  return t === "txt2img" ? "t2i" : t;
}
const ws = ["feature-type", "required-bindings", "exposed-controls", "details"];
function Rn(e) {
  return {
    v: 1,
    workflowId: e.workflowId || "",
    versionId: e.versionId || "",
    step: e.step && ws.includes(e.step) ? e.step : "feature-type",
    featureType: e.featureType || "t2i",
    bindings: e.bindings || {},
    outputBinding: e.outputBinding || null,
    controls: Array.isArray(e.controls) ? e.controls.slice(0, 64) : [],
    details: e.details || {}
  };
}
function ax(e, t, s) {
  if (!e || e.length > 12e3) return null;
  try {
    const n = JSON.parse(e);
    return n.v !== 1 || n.workflowId !== t || n.versionId !== s ? null : Rn(n);
  } catch {
    return null;
  }
}
async function er(e, t) {
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
async function lx(e) {
  return er("/customnode/install/git_url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: e })
  });
}
async function cx(e) {
  return er("/manager/queue/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(e || {})
  });
}
async function ux() {
  return er("/manager/queue/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
}
async function dx() {
  return er("/customnode/getlist?mode=default&skip_update=true");
}
async function fx() {
  return er("/customnode/getmappings?mode=default");
}
function ui(e) {
  return String(e || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}
function Mu(e) {
  return String(e || "").split("/").filter(Boolean).pop() || "";
}
function mx(e) {
  try {
    return new RegExp(e);
  } catch {
    return null;
  }
}
function px(e, t) {
  const s = {}, n = {}, r = {}, o = [], i = (l, c, u) => {
    const d = String(c ?? "").toLowerCase();
    d && !l[d] && (l[d] = u);
  }, a = (l, c) => {
    const u = {
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
    s[String(l).toLowerCase()] = u;
    const d = String(c.repository || "");
    return d && (i(s, ui(d), u), i(s, Mu(d).toLowerCase(), u)), u;
  };
  for (const [l, c] of Object.entries(e || {}))
    c && typeof c == "object" && a(l, c);
  if (t && typeof t == "object")
    for (const [l, c] of Object.entries(t)) {
      const u = Array.isArray(c) ? c[0] : c.classes, d = Array.isArray(c) ? c[1] : {}, h = s[String(l).toLowerCase()] || s[ui(l)];
      if (h) {
        if (Array.isArray(d.preemptions))
          for (const m of d.preemptions) i(r, m, h);
        if (typeof d.nodename_pattern == "string") {
          const m = mx(d.nodename_pattern);
          m && o.push({ re: m, record: h });
        }
      }
      for (const m of Array.isArray(u) ? u : [])
        h && i(n, m, h);
    }
  return { packs: s, byClass: n, preemptions: r, patterns: o };
}
function hx(e, t) {
  if (!t || !e) return null;
  for (const r of [e.cnr_id, e.aux_id]) {
    if (!r) continue;
    const o = String(r), i = t.packs[o.toLowerCase()] || t.packs[ui(o)] || t.packs[Mu(o).toLowerCase()];
    if (i) return i;
  }
  const s = Array.isArray(e.classes) ? e.classes : e.classes ? [e.classes] : [], n = s.map((r) => String(r ?? "").toLowerCase()).filter(Boolean);
  for (const r of n)
    if (t.preemptions[r]) return t.preemptions[r];
  for (const r of n)
    if (t.byClass[r]) return t.byClass[r];
  for (const r of s) {
    const o = String(r ?? "");
    if (o) {
      for (const i of t.patterns || [])
        if (i.re.test(o)) return i.record;
    }
  }
  return null;
}
function gx(e, t) {
  const s = hx(e, t);
  if (s)
    return { kind: "cnr", pack: s, url: "", name: s.name || String(e.name || "") };
  const n = String(e.repository_url || "");
  return n ? { kind: "git", pack: null, url: n, name: String(e.name || "") } : { kind: "none", pack: null, url: "", name: String(e.name || "") };
}
function vx(e) {
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
async function yx(e) {
  if (!e || e.kind === "none")
    return { ok: !1, message: "No Manager install target identified for this pack." };
  try {
    if (e.kind === "cnr") {
      const r = await cx(vx(e.pack));
      if (!r) return { ok: !1, message: "Could not reach ComfyUI-Manager." };
      if (r.status === 403)
        return { ok: !1, message: "Manager refused the CNR install (403). Raise Manager's security level, then retry." };
      if (!r.ok) {
        const i = r.data, a = i && (i.message || i.error) || `HTTP ${r.status}`;
        return { ok: !1, message: `Install failed: ${String(a)}` };
      }
      const o = await ux();
      return !o || !o.ok ? { ok: !1, message: "Install queued, but Manager did not start it. Open ComfyUI-Manager and press Start." } : { ok: !0, message: "Install queued through ComfyUI-Manager — restart ComfyUI to load it." };
    }
    const t = await lx(e.url);
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
const _n = "comfymodal.studio.wizard.draft.v1", bx = /* @__PURE__ */ mn("studio-workflows", () => {
  const e = /* @__PURE__ */ R([]), t = /* @__PURE__ */ R(null), s = /* @__PURE__ */ R(null), n = /* @__PURE__ */ R([]), r = /* @__PURE__ */ R(null), o = /* @__PURE__ */ R(null), i = /* @__PURE__ */ R(null), a = /* @__PURE__ */ R(null), l = /* @__PURE__ */ R(null), c = /* @__PURE__ */ R(null), u = /* @__PURE__ */ R([]), d = /* @__PURE__ */ R(null), h = /* @__PURE__ */ R(null), m = /* @__PURE__ */ R(""), _ = /* @__PURE__ */ R(""), S = /* @__PURE__ */ R(!1), b = /* @__PURE__ */ R(""), A = /* @__PURE__ */ R(!1), M = /* @__PURE__ */ R(null), Y = /* @__PURE__ */ R(!1), J = /* @__PURE__ */ R(null), ce = /* @__PURE__ */ R(!1), Ae = /* @__PURE__ */ R(null), re = /* @__PURE__ */ R(null), U = /* @__PURE__ */ R(null), q = /* @__PURE__ */ R(null), x = qn(), Q = /* @__PURE__ */ R(null), xe = /* @__PURE__ */ R({});
  let C = null;
  function te(L) {
    t.value = L;
  }
  function Ne() {
    t.value = null, s.value = null, n.value = [], r.value = null;
  }
  async function ke() {
    A.value = !0, M.value = null;
    try {
      const [L, K, ye] = await Promise.all([
        E_({ search: b.value, tag: m.value || void 0, folder: _.value || void 0, favorite: S.value || void 0 }),
        j_().catch(() => null),
        D_().catch(() => null)
      ]);
      e.value = L.workflows ?? [], d.value = K, h.value = ye;
    } catch (L) {
      throw M.value = L instanceof Error ? L.message : "Could not load workflows", L;
    } finally {
      A.value = !1;
    }
  }
  async function pe() {
    C || (C = so((L) => {
      L === "workflows" && !A.value && ke();
    })), e.value.length || await ke();
  }
  async function Ce(L) {
    t.value = L;
    const K = await x.run(async (Rt) => {
      const [Mt, ro] = await Promise.all([$_(L), O_(L)]);
      return Rt.aborted ? null : { workflowResponse: Mt, versionsResponse: ro };
    });
    if (K.stale || !K.value) return;
    s.value = K.value.workflowResponse.workflow ?? null, n.value = K.value.versionsResponse.versions ?? [];
    const ye = s.value?.latest_version_id, We = n.value.find((Rt) => Rt.workflow_version_id === ye) ?? n.value.at(-1) ?? null;
    We && await ze(We.workflow_version_id);
  }
  async function ze(L) {
    const K = await x.run(async (We) => {
      const [Rt, Mt, ro, zu, ju, Du, Lu] = await Promise.all([
        T_(L),
        P_(L),
        M_(L),
        z_(L),
        wl(L),
        J_(L),
        B_(L)
      ]);
      return We.aborted ? null : { versionResponse: Rt, mappingResponse: Mt, dependencyResponse: ro, compatibilityResponse: zu, portabilityResponse: ju, presetsResponse: Du, stateResponse: Lu };
    });
    if (K.stale || !K.value) return;
    r.value = K.value.versionResponse, o.value = K.value.mappingResponse, i.value = null, a.value = K.value.dependencyResponse, l.value = K.value.compatibilityResponse, c.value = K.value.portabilityResponse, re.value = K.value.stateResponse;
    const ye = K.value.presetsResponse;
    u.value = ye.presets ?? [], s.value && L && (U.value = await K_(s.value.workflow_id, L).catch(() => null));
  }
  async function oe() {
    r.value && (i.value = await N_(r.value.workflow_version_id));
  }
  function tt() {
    const L = s.value?.workflow_id ?? "", K = r.value?.workflow_version_id ?? "";
    try {
      J.value = ax(sessionStorage.getItem(_n), L, K) ?? Rn({ workflowId: L, versionId: K, featureType: ix(s.value?.workflow_type) });
    } catch {
      J.value = Rn({ workflowId: L, versionId: K });
    }
    Y.value = !0;
  }
  function Je() {
    try {
      const L = typeof performance < "u" && typeof performance.getEntriesByType == "function" ? performance.getEntriesByType("navigation") : [], K = L && L[0] && L[0].type;
      if (K) return K === "reload" || K === "back_forward";
      const ye = performance.navigation;
      return !!ye && ye.type !== 0;
    } catch {
      return !1;
    }
  }
  async function ue() {
    if (Y.value || !Je()) return !1;
    let L = null;
    try {
      L = sessionStorage.getItem(_n);
    } catch {
      return !1;
    }
    if (!L) return !1;
    let K = null;
    try {
      const ye = JSON.parse(L);
      if (ye.v !== 1 || !ye.workflowId || !ye.versionId) return !1;
      K = Rn(ye);
    } catch {
      return !1;
    }
    try {
      await Ce(K.workflowId);
    } catch {
      return !1;
    }
    return r.value?.workflow_version_id !== K.versionId ? !1 : (J.value = K, Y.value = !0, !0);
  }
  function y(L) {
    if (J.value) {
      J.value = Rn({ ...J.value, ...L });
      try {
        sessionStorage.setItem(_n, JSON.stringify(J.value));
      } catch {
      }
    }
  }
  function T(L) {
    y({ step: L });
  }
  function ve() {
    Y.value = !1, J.value = null;
    try {
      sessionStorage.removeItem(_n);
    } catch {
    }
  }
  async function z(L) {
    t.value && (await _l(t.value, L), await ke(), await Ce(t.value), Qe("workflows"));
  }
  async function E(L, K) {
    await _l(L, { favorite: K }), await ke(), Qe("workflows");
  }
  async function P(L) {
    await L_(L), await ke(), Qe("workflows");
  }
  async function ie(L) {
    const K = Ot(), ye = K.start({ kind: "workflow-import", label: "Import workflow" });
    try {
      await V_(L), K.finish(ye, "Workflow imported"), await ke(), Qe("workflows");
    } catch (We) {
      throw K.fail(ye, We instanceof Error ? We.message : "Import failed"), We;
    }
  }
  async function p() {
    t.value && (await U_(t.value), Ne(), await ke(), Qe("workflows"));
  }
  async function v(L) {
    await F_(L), await ke();
  }
  async function k(L) {
    t.value && (await W_(t.value, L), await Ce(t.value), Qe("workflows"));
  }
  async function I(L) {
    const K = r.value?.workflow_version_id;
    if (!K) throw new Error("No version selected");
    const ye = o.value;
    !!ye && typeof ye.mapping_id == "string" ? await H_(K, L) : await G_(K, L), await ze(K), Qe("workflows");
  }
  async function j(L) {
    t.value && (await q_(t.value, L), r.value && await ze(r.value.workflow_version_id));
  }
  async function B() {
    if (Q.value) return Q.value;
    try {
      const [L, K] = await Promise.all([
        dx(),
        fx()
      ]), ye = (L?.data ?? {}).node_packs, We = K?.data ?? {};
      Q.value = px(
        ye ?? {},
        We
      );
    } catch {
      Q.value = null;
    }
    return Q.value;
  }
  async function w(L) {
    const K = String(L.name || L.cnr_id || "node"), ye = await B(), We = gx(L, ye);
    xe.value = { ...xe.value, [K]: "Installing…" };
    const Rt = await yx(We);
    xe.value = { ...xe.value, [K]: Rt.message }, Rt.ok && await no().loadInventory().catch(() => {
    });
  }
  async function N(L) {
    r.value && (await Z_(r.value.workflow_version_id, L), await ze(r.value.workflow_version_id));
  }
  async function D() {
    r.value && (c.value = await wl(r.value.workflow_version_id));
  }
  async function F() {
    if (!r.value) return;
    const L = await ox(r.value.workflow_version_id);
    if (!L.ok || !L.blob) throw new Error(L.message || "Export failed");
    const K = URL.createObjectURL(L.blob);
    try {
      const ye = document.createElement("a");
      ye.href = K, ye.download = L.filename || "manifest.json", document.body.appendChild(ye), ye.click(), ye.remove();
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(K), 1e3);
    }
  }
  async function he(L) {
    const K = await xl(L, !0);
    return q.value = K, K;
  }
  async function ne(L) {
    await xl(L, !1), q.value = null, await ke(), Qe("workflows");
  }
  function _e(L) {
    const K = {};
    for (const [ye, We] of Object.entries(L))
      We instanceof Blob || typeof We == "string" && (We.startsWith("blob:") || We.startsWith("data:image/")) || ye === "sourceImage" || ye === "referenceImages" || ye === "mask" || ye === "sketch" || ye === "generatedImages" || ye === "compareImages" || (K[ye] = We);
    return K;
  }
  async function Re(L) {
    r.value && (await Q_(r.value.workflow_version_id, {
      ...L,
      studio_state: _e(L.studio_state)
    }), await ze(r.value.workflow_version_id));
  }
  async function Le(L, K) {
    const ye = K.studio_state && typeof K.studio_state == "object" ? { ...K, studio_state: _e(K.studio_state) } : K;
    await Y_(L, ye), r.value && await ze(r.value.workflow_version_id);
  }
  async function He(L) {
    await X_(L), r.value && await ze(r.value.workflow_version_id);
  }
  async function Z(L, K) {
    await ex(L, K ? { name: K } : {}), r.value && await ze(r.value.workflow_version_id);
  }
  async function le(L, K) {
    await tx(L, K), Qe("workflows");
  }
  async function ae(L, K) {
    return sx(L, K);
  }
  async function Oe(L) {
    await nx(L);
  }
  async function De(L, K) {
    await rx(L, K);
  }
  async function Ie() {
    const L = J.value;
    if (!L) throw new Error("No wizard draft");
    const K = L.bindings || {};
    if (!Object.values(K).filter(
      (We) => We && typeof We == "object" && We.confirmed === !0
    ).length) throw new Error("Confirm at least one graph binding first");
    if (!L.outputBinding) throw new Error("Capture the output binding first");
    ce.value = !0, Ae.value = null;
    try {
      await I({
        feature_type: L.featureType,
        bindings: L.bindings,
        output_binding: L.outputBinding,
        controls: L.controls,
        details: L.details
      });
      try {
        sessionStorage.removeItem(_n);
      } catch {
      }
      J.value = null, Y.value = !1;
    } catch (We) {
      throw Ae.value = We instanceof Error ? We.message : "Mapping save failed", We;
    } finally {
      ce.value = !1;
    }
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
    folders: d,
    tags: h,
    tagFilter: m,
    folderFilter: _,
    favoritesOnly: S,
    versionState: re,
    methodCompat: U,
    manifestPreview: q,
    query: b,
    loading: A,
    error: M,
    wizardOpen: Y,
    wizardDraft: J,
    wizardSaving: ce,
    wizardError: Ae,
    select: te,
    clear: Ne,
    loadList: ke,
    initialize: pe,
    selectWorkflow: Ce,
    selectVersion: ze,
    loadMappingCandidates: oe,
    openWizard: tt,
    updateWizard: y,
    setWizardStep: T,
    closeWizard: ve,
    updateMetadata: z,
    maybeResumeWizard: ue,
    toggleFavorite: E,
    createNewWorkflow: P,
    importNewWorkflow: ie,
    deleteSelectedWorkflow: p,
    createFolder: v,
    captureVersion: k,
    saveMapping: I,
    markNonessential: j,
    saveCompatibility: N,
    recheckPortability: D,
    loadManagerIndex: B,
    installDependencyNode: w,
    dependencyInstallMessage: xe,
    exportManifest: F,
    previewManifestImport: he,
    commitManifestImport: ne,
    sanitizePresetState: _e,
    createPreset: Re,
    savePreset: Le,
    removePreset: He,
    duplicateCurrentPreset: Z,
    copyPresetForward: le,
    loadGuidance: ae,
    saveGuidance: Oe,
    removeGuidance: De,
    saveWizardMapping: Ie
  };
}), wx = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, _x = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, xx = { class: "cmst:flex cmst:gap-2" }, kx = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, Sx = { class: "cmst:flex cmst:items-center cmst:gap-1 cmst:text-sm" }, Cx = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, Ax = ["data-testid", "onClick"], Rx = { class: "cmst:block cmst:text-xs cmst:opacity-70" }, Ix = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70"
}, Ex = { class: "cmst:mt-3" }, $x = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:text-red-300",
  role: "alert"
}, Ox = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Tx = { class: "cmst:text-base cmst:font-semibold" }, Px = { class: "cmst:text-xs cmst:opacity-70" }, Nx = { class: "cmst:flex cmst:gap-2" }, Mx = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, zx = ["value"], jx = ["value"], Dx = {
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70",
  "data-testid": "vue-version-runnable"
}, Lx = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, Vx = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Ux = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Fx = { class: "cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, Wx = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, Bx = { class: "cmst:mt-2" }, Gx = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:text-xs"
}, Hx = {
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm",
  "data-testid": "vue-dependencies"
}, qx = { class: "cmst:mt-2 cmst:flex cmst:max-h-56 cmst:flex-col cmst:gap-1 cmst:overflow-auto" }, Zx = {
  class: "cmst:ml-2",
  "data-testid": "dependency-model-state"
}, Kx = { class: "cmst:ml-2" }, Jx = ["checked", "onChange"], Qx = {
  key: 1,
  class: "cmst:ml-2",
  "data-testid": "dependency-model-install-note"
}, Yx = {
  key: 1,
  class: "cmst:ml-2",
  "data-testid": "dependency-node-install-note"
}, Xx = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, e1 = { class: "cmst:mt-2 cmst:flex cmst:gap-1" }, t1 = { class: "cmst:mt-4" }, s1 = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, n1 = { class: "cmst:mt-2 cmst:text-sm" }, r1 = { class: "cmst:mt-4" }, o1 = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, i1 = { class: "cmst:mt-3 cmst:text-sm" }, a1 = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, l1 = ["onKeydown"], c1 = { class: "cmst:flex cmst:items-center cmst:justify-between" }, u1 = { class: "cmst:text-xs cmst:opacity-70" }, d1 = { class: "cmst:mt-5 cmst:rounded-md cmst:bg-cmst-bg cmst:p-4" }, f1 = ["value"], m1 = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, p1 = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs"
}, h1 = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, g1 = { class: "cmst:mt-2 cmst:text-sm" }, v1 = { class: "cmst:mt-3" }, y1 = { class: "cmst:mt-2 cmst:max-h-40 cmst:overflow-auto cmst:text-xs" }, b1 = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-red-300",
  role: "alert"
}, w1 = { class: "cmst:mt-4 cmst:flex cmst:justify-between" }, _1 = /* @__PURE__ */ Ct({
  __name: "WorkflowsView",
  setup(e) {
    const t = bx(), s = no(), n = /* @__PURE__ */ R(""), r = /* @__PURE__ */ R("workflows"), o = /* @__PURE__ */ R(""), i = /* @__PURE__ */ R(""), a = /* @__PURE__ */ R(""), l = /* @__PURE__ */ R(""), c = /* @__PURE__ */ R(""), u = /* @__PURE__ */ R(""), d = /* @__PURE__ */ R(""), h = /* @__PURE__ */ R(""), m = /* @__PURE__ */ R(""), _ = /* @__PURE__ */ R("txt2img"), S = /* @__PURE__ */ R(""), b = Ue(() => Math.max(0, ws.indexOf(t.wizardDraft?.step ?? "feature-type"))), A = Ue(() => ws[b.value]);
    hs(async () => {
      await Promise.all([t.initialize(), s.initialize()]), await t.maybeResumeWizard().catch(() => !1);
    });
    async function M() {
      t.query = n.value, await t.loadList();
    }
    async function Y(ue) {
      await t.selectWorkflow(ue);
      const y = t.selectedWorkflow;
      l.value = String(y?.name ?? ""), c.value = String(y?.folder ?? "");
    }
    function J() {
      t.openWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!0);
    }
    function ce() {
      window.__comfymodalCancelStudioGraphBinding?.(), t.closeWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
    }
    async function Ae() {
      if (!o.value.trim()) return;
      const ue = o.value.trim();
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = "Click a node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "prompt",
          label: "prompt",
          allowOutput: !1,
          onCapture: (y) => {
            t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { ...y, confirmed: !0 } } }), a.value = `Confirmed ${String(y.nodeTitle ?? y.nodeId ?? "graph target")}`;
          },
          onCancel: (y) => {
            a.value = y;
          }
        });
        return;
      }
      t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { target: ue, confirmed: !0 } } }), a.value = `Confirmed graph target ${ue}`;
    }
    async function re() {
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = "Click the output node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "output",
          label: "output",
          allowOutput: !0,
          onCapture: (ue) => {
            t.updateWizard({ outputBinding: { ...ue, confirmed: !0 } }), a.value = `Output bound to ${String(ue.nodeTitle ?? ue.nodeId ?? "graph target")}`;
          },
          onCancel: (ue) => {
            a.value = ue;
          }
        });
        return;
      }
      t.updateWizard({ outputBinding: { target: "SaveImage.images", confirmed: !0 } }), a.value = "Output binding recorded";
    }
    async function U() {
      a.value = "";
      try {
        await t.saveWizardMapping(), a.value = "Mapping saved";
      } catch (ue) {
        a.value = ue instanceof Error ? ue.message : "Save failed";
      }
    }
    function q() {
      const ue = ws[Math.min(ws.length - 1, b.value + 1)];
      t.setWizardStep(ue);
    }
    function x() {
      const ue = ws[Math.max(0, b.value - 1)];
      t.setWizardStep(ue);
    }
    function Q() {
      if (!i.value.trim()) return;
      const ue = [...t.wizardDraft?.controls ?? [], { label: i.value.trim(), enabled: !0 }];
      t.updateWizard({ controls: ue }), i.value = "";
    }
    async function xe() {
      d.value = "";
      try {
        const ue = JSON.parse(u.value);
        await t.importNewWorkflow(ue), u.value = "";
      } catch (ue) {
        d.value = ue instanceof Error ? ue.message : "Import failed";
      }
    }
    async function C() {
      await t.updateMetadata({ name: l.value, folder: c.value }).catch(() => {
      });
    }
    async function te() {
      try {
        await t.saveMapping(JSON.parse(S.value || "{}"));
      } catch {
      }
    }
    const Ne = Ue(() => t.dependencies ?? {}), ke = Ue(() => {
      const ue = Ne.value.models;
      if (!Array.isArray(ue)) return [];
      const y = new Set(
        Array.isArray(Ne.value.nonessential_keys ?? Ne.value.nonessential) ? (Ne.value.nonessential_keys ?? Ne.value.nonessential).map(String) : []
      );
      return ue.filter((T) => !!T && typeof T == "object").map((T, ve) => {
        const z = String(T.key || T.filename || `model-${ve}`), E = Array.isArray(T.source_urls) ? T.source_urls : [];
        return {
          key: z,
          filename: String(T.filename || z),
          folder: String(T.folder || ""),
          state: String(T.state || "unknown"),
          nonessential: y.has(z),
          hasSource: E.length > 0 || typeof T.remote_model == "object",
          message: t.dependencyInstallMessage[z] ?? "",
          raw: T
        };
      });
    }), pe = Ue(() => {
      const ue = Ne.value.custom_nodes;
      return Array.isArray(ue) ? ue.filter((y) => !!y && typeof y == "object").map((y, T) => {
        const ve = String(y.name || y.cnr_id || `node-${T}`);
        return {
          key: ve,
          name: String(y.name || ve),
          state: String(y.state || "unknown"),
          message: t.dependencyInstallMessage[ve] ?? "",
          raw: y
        };
      }) : [];
    }), Ce = Ue(() => {
      const ue = Ne.value.summary;
      if (ue && typeof ue == "object") {
        const y = ue, T = Number(y.installed ?? 0), ve = Number(y.missing ?? 0);
        return `${T} installed · ${ve} missing · ${ve === 0 ? "ready" : "attention"}`;
      }
      return t.dependencies ? `${ke.value.length + pe.value.length} requirements` : "not loaded";
    }), ze = Ue(() => {
      const ue = t.versionState;
      if (ue && typeof ue.runnable == "boolean")
        return ue.runnable ? "Runnable" : "Not runnable — resolve dependencies";
      const y = t.selectedVersion;
      return y && typeof y.runnable == "boolean" ? y.runnable ? "Runnable" : "Not runnable — resolve dependencies" : "";
    });
    async function oe(ue, y) {
      const T = new Set(
        ke.value.filter((ve) => ve.nonessential).map((ve) => ve.key)
      );
      y ? T.add(ue) : T.delete(ue), await t.markNonessential([...T]).catch(() => {
      });
    }
    async function tt(ue) {
      const y = ue.raw.remote_model && typeof ue.raw.remote_model == "object" ? ue.raw.remote_model : ue.raw, T = String(y.url || y.download_url || ""), ve = T ? { url: T, filename: ue.filename, save_path: ue.folder } : { filename: ue.filename, folder: ue.folder };
      try {
        await s.installModel(ve);
      } catch {
      }
    }
    async function Je(ue) {
      await t.installDependencyNode(ue.raw);
    }
    return (ue, y) => ($(), H("section", {
      class: kt(g(Yn)()),
      "data-testid": "vue-page-workflows"
    }, [
      V(Xe, { class: "cmst:p-4" }, {
        default: W(() => [
          f("div", wx, [
            f("div", null, [
              f("h2", _x, [
                V(g(ti), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                y[29] || (y[29] = O("Workflows & Models", -1))
              ]),
              y[30] || (y[30] = f("p", { class: "cmst:text-sm cmst:opacity-80" }, "Workflow/version state and shared infrastructure inventory remain separate authorities.", -1))
            ]),
            f("div", xx, [
              V(X, {
                variant: r.value === "workflows" ? "default" : "outline",
                size: "sm",
                onClick: y[0] || (y[0] = (T) => r.value = "workflows")
              }, {
                default: W(() => [
                  V(g(ti), { class: "cmst:size-4" }),
                  y[31] || (y[31] = O("Workflows", -1))
                ]),
                _: 1
              }, 8, ["variant"]),
              V(X, {
                variant: r.value === "models" ? "default" : "outline",
                size: "sm",
                onClick: y[1] || (y[1] = (T) => r.value = "models")
              }, {
                default: W(() => [
                  V(g(Op), { class: "cmst:size-4" }),
                  y[32] || (y[32] = O("Models / Nodes", -1))
                ]),
                _: 1
              }, 8, ["variant"])
            ])
          ])
        ]),
        _: 1
      }),
      r.value === "workflows" ? ($(), H(Ee, { key: 0 }, [
        V(Xe, { class: "cmst:p-4" }, {
          default: W(() => [
            f("div", kx, [
              Ve(f("input", {
                "onUpdate:modelValue": y[2] || (y[2] = (T) => n.value = T),
                class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search workflows",
                "aria-label": "Search workflows",
                onKeyup: Ws(M, ["enter"])
              }, null, 544), [
                [at, n.value]
              ]),
              Ve(f("select", {
                "onUpdate:modelValue": y[3] || (y[3] = (T) => g(t).tagFilter = T),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                "aria-label": "Filter by tag",
                onChange: y[4] || (y[4] = (T) => g(t).loadList())
              }, [...y[33] || (y[33] = [
                f("option", { value: "" }, "All tags", -1)
              ])], 544), [
                [ls, g(t).tagFilter]
              ]),
              f("label", Sx, [
                Ve(f("input", {
                  "onUpdate:modelValue": y[5] || (y[5] = (T) => g(t).favoritesOnly = T),
                  type: "checkbox",
                  onChange: y[6] || (y[6] = (T) => g(t).loadList())
                }, null, 544), [
                  [tn, g(t).favoritesOnly]
                ]),
                y[34] || (y[34] = O(" Favorites", -1))
              ]),
              V(X, {
                size: "sm",
                variant: "secondary",
                onClick: M
              }, {
                default: W(() => [...y[35] || (y[35] = [
                  O("Search", -1)
                ])]),
                _: 1
              }),
              V(X, {
                size: "sm",
                variant: "outline",
                onClick: y[7] || (y[7] = (T) => g(t).loadList())
              }, {
                default: W(() => [
                  V(g(to), { class: "cmst:size-4" })
                ]),
                _: 1
              })
            ]),
            f("div", Cx, [
              ($(!0), H(Ee, null, et(g(t).workflows, (T) => ($(), H("button", {
                key: T.workflow_id,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-workflow-${T.workflow_id}`,
                onClick: (ve) => Y(T.workflow_id)
              }, [
                f("strong", null, G(T.name || T.workflow_id), 1),
                f("span", Rx, G(T.folder || "No folder") + " · " + G(T.latest_version_id || "No version"), 1)
              ], 8, Ax))), 128))
            ]),
            g(t).workflows.length ? we("", !0) : ($(), H("p", Ix, "No workflows returned by the server.")),
            f("div", Ex, [
              y[37] || (y[37] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Import workflow", -1)),
              Ve(f("textarea", {
                "onUpdate:modelValue": y[8] || (y[8] = (T) => u.value = T),
                rows: "3",
                class: "cmst:mt-1 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-xs",
                placeholder: '{"name": "...", "static_graph": {...}}',
                "data-testid": "vue-workflow-import-input"
              }, null, 512), [
                [at, u.value]
              ]),
              d.value ? ($(), H("p", $x, G(d.value), 1)) : we("", !0),
              V(X, {
                class: "cmst:mt-2",
                size: "sm",
                "data-testid": "vue-workflow-import",
                onClick: xe
              }, {
                default: W(() => [...y[36] || (y[36] = [
                  O("Import", -1)
                ])]),
                _: 1
              })
            ])
          ]),
          _: 1
        }),
        g(t).selectedWorkflow ? ($(), Ze(Xe, {
          key: 0,
          class: "cmst:p-4"
        }, {
          default: W(() => [
            f("div", Ox, [
              f("div", null, [
                f("h3", Tx, G(g(t).selectedWorkflow.name), 1),
                f("p", Px, "Version " + G(g(t).selectedVersion?.version ?? g(t).selectedVersion?.workflow_version_id), 1)
              ]),
              f("div", Nx, [
                V(X, {
                  size: "sm",
                  variant: "outline",
                  "data-testid": `vue-workflow-favorite-${g(t).selectedWorkflow.workflow_id}`,
                  onClick: y[9] || (y[9] = (T) => g(t).toggleFavorite(g(t).selectedWorkflow.workflow_id, !g(t).selectedWorkflow.favorite))
                }, {
                  default: W(() => [...y[38] || (y[38] = [
                    O("★", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid"]),
                V(X, {
                  size: "sm",
                  onClick: J
                }, {
                  default: W(() => [
                    V(g(Gp), { class: "cmst:size-4" }),
                    y[39] || (y[39] = O("Setup wizard", -1))
                  ]),
                  _: 1
                })
              ])
            ]),
            f("div", Mx, [
              f("select", {
                value: g(t).selectedVersion?.workflow_version_id ?? "",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                "aria-label": "Select version",
                "data-testid": "vue-version-select",
                onChange: y[10] || (y[10] = (T) => g(t).selectVersion(T.target.value))
              }, [
                ($(!0), H(Ee, null, et(g(t).versions, (T) => ($(), H("option", {
                  key: T.workflow_version_id,
                  value: T.workflow_version_id
                }, "v" + G(T.version ?? T.workflow_version_id), 9, jx))), 128))
              ], 40, zx),
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-version-capture",
                onClick: y[11] || (y[11] = (T) => g(t).captureVersion({}))
              }, {
                default: W(() => [...y[40] || (y[40] = [
                  O("Capture version", -1)
                ])]),
                _: 1
              }),
              V(X, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-workflow-delete",
                onClick: y[12] || (y[12] = (T) => g(t).deleteSelectedWorkflow())
              }, {
                default: W(() => [...y[41] || (y[41] = [
                  O("Delete workflow", -1)
                ])]),
                _: 1
              })
            ]),
            f("p", Dx, G(ze.value), 1),
            f("div", Lx, [
              f("label", Vx, [
                y[42] || (y[42] = O("Name", -1)),
                Ve(f("input", {
                  "onUpdate:modelValue": y[13] || (y[13] = (T) => l.value = T),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
                }, null, 512), [
                  [at, l.value]
                ])
              ]),
              f("label", Ux, [
                y[43] || (y[43] = O("Folder", -1)),
                Ve(f("input", {
                  "onUpdate:modelValue": y[14] || (y[14] = (T) => c.value = T),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
                }, null, 512), [
                  [at, c.value]
                ])
              ])
            ]),
            V(X, {
              class: "cmst:mt-2",
              size: "sm",
              variant: "secondary",
              "data-testid": "vue-workflow-save-meta",
              onClick: C
            }, {
              default: W(() => [...y[44] || (y[44] = [
                O("Save metadata", -1)
              ])]),
              _: 1
            }),
            f("div", Fx, [
              f("div", Wx, [
                y[47] || (y[47] = O("Mapping", -1)),
                y[48] || (y[48] = f("br", null, null, -1)),
                f("strong", null, G(g(t).mapping ? "configured" : "not configured"), 1),
                f("div", Bx, [
                  V(X, {
                    size: "sm",
                    variant: "ghost",
                    onClick: y[15] || (y[15] = (T) => g(t).loadMappingCandidates())
                  }, {
                    default: W(() => [...y[45] || (y[45] = [
                      O("Load candidates", -1)
                    ])]),
                    _: 1
                  })
                ]),
                g(t).mappingCandidates ? ($(), H("pre", Gx, G(JSON.stringify(g(t).mappingCandidates, null, 1).slice(0, 800)), 1)) : we("", !0),
                Ve(f("textarea", {
                  "onUpdate:modelValue": y[16] || (y[16] = (T) => S.value = T),
                  rows: "3",
                  class: "cmst:mt-2 cmst:w-full cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-xs",
                  placeholder: '{"bindings": {...}}'
                }, null, 512), [
                  [at, S.value]
                ]),
                V(X, {
                  class: "cmst:mt-1",
                  size: "sm",
                  "data-testid": "vue-mapping-save",
                  onClick: te
                }, {
                  default: W(() => [...y[46] || (y[46] = [
                    O("Save mapping", -1)
                  ])]),
                  _: 1
                })
              ]),
              f("div", Hx, [
                f("p", null, [
                  y[49] || (y[49] = O("Dependencies", -1)),
                  y[50] || (y[50] = f("br", null, null, -1)),
                  f("strong", null, G(Ce.value), 1)
                ]),
                f("ul", qx, [
                  ($(!0), H(Ee, null, et(ke.value, (T) => ($(), H("li", {
                    key: `model-${T.key}`,
                    class: "cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs",
                    "data-testid": "dependency-model-row"
                  }, [
                    f("span", null, G(T.filename) + " (" + G(T.folder) + ") · " + G(T.state), 1),
                    f("span", Zx, G(T.state), 1),
                    f("label", Kx, [
                      f("input", {
                        type: "checkbox",
                        checked: T.nonessential,
                        onChange: (ve) => oe(T.key, ve.target.checked)
                      }, null, 40, Jx),
                      y[51] || (y[51] = O(" nonessential", -1))
                    ]),
                    T.state === "missing" && T.hasSource ? ($(), Ze(X, {
                      key: 0,
                      class: "cmst:ml-2",
                      size: "sm",
                      variant: "ghost",
                      "data-testid": "dependency-model-install-now",
                      onClick: (ve) => tt(T)
                    }, {
                      default: W(() => [...y[52] || (y[52] = [
                        O("Install now", -1)
                      ])]),
                      _: 1
                    }, 8, ["onClick"])) : we("", !0),
                    T.message ? ($(), H("span", Qx, G(T.message), 1)) : we("", !0)
                  ]))), 128)),
                  ($(!0), H(Ee, null, et(pe.value, (T) => ($(), H("li", {
                    key: `node-${T.key}`,
                    class: "cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs",
                    "data-testid": "dependency-node-row"
                  }, [
                    f("span", null, G(T.name) + " · " + G(T.state), 1),
                    T.state === "missing" ? ($(), Ze(X, {
                      key: 0,
                      class: "cmst:ml-2",
                      size: "sm",
                      variant: "ghost",
                      "data-testid": "dependency-node-install-now",
                      onClick: (ve) => Je(T)
                    }, {
                      default: W(() => [...y[53] || (y[53] = [
                        O("Install now", -1)
                      ])]),
                      _: 1
                    }, 8, ["onClick"])) : we("", !0),
                    T.message ? ($(), H("span", Yx, G(T.message), 1)) : we("", !0)
                  ]))), 128))
                ])
              ]),
              f("div", Xx, [
                y[56] || (y[56] = O("Portability", -1)),
                y[57] || (y[57] = f("br", null, null, -1)),
                f("strong", null, G(g(t).portability ? "analyzed" : "not analyzed"), 1),
                f("div", e1, [
                  V(X, {
                    size: "sm",
                    variant: "ghost",
                    onClick: y[17] || (y[17] = (T) => g(t).recheckPortability())
                  }, {
                    default: W(() => [...y[54] || (y[54] = [
                      O("Recheck", -1)
                    ])]),
                    _: 1
                  }),
                  V(X, {
                    size: "sm",
                    variant: "ghost",
                    "data-testid": "vue-manifest-export",
                    onClick: y[18] || (y[18] = (T) => g(t).exportManifest())
                  }, {
                    default: W(() => [...y[55] || (y[55] = [
                      O("Export manifest", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ]),
            f("div", t1, [
              y[60] || (y[60] = f("h4", { class: "cmst:text-sm cmst:font-semibold" }, "Presets (image-free configuration only)", -1)),
              f("div", s1, [
                Ve(f("input", {
                  "onUpdate:modelValue": y[19] || (y[19] = (T) => h.value = T),
                  class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                  placeholder: "Preset name"
                }, null, 512), [
                  [at, h.value]
                ]),
                V(X, {
                  size: "sm",
                  "data-testid": "vue-preset-create",
                  onClick: y[20] || (y[20] = (T) => {
                    g(t).createPreset({ name: h.value || "Untitled", studio_state: {} }), h.value = "";
                  })
                }, {
                  default: W(() => [...y[58] || (y[58] = [
                    O("Create preset", -1)
                  ])]),
                  _: 1
                })
              ]),
              f("ul", n1, [
                ($(!0), H(Ee, null, et(g(t).presets, (T, ve) => ($(), H("li", {
                  key: ve,
                  class: "cmst:flex cmst:items-center cmst:gap-2"
                }, [
                  f("span", null, G(String(T.name || `preset ${ve}`)), 1),
                  V(X, {
                    size: "sm",
                    variant: "ghost",
                    onClick: (z) => g(t).removePreset(String(T.preset_id || T.id || ""))
                  }, {
                    default: W(() => [...y[59] || (y[59] = [
                      O("Delete", -1)
                    ])]),
                    _: 1
                  }, 8, ["onClick"])
                ]))), 128))
              ])
            ]),
            f("div", r1, [
              y[63] || (y[63] = f("h4", { class: "cmst:text-sm cmst:font-semibold" }, "Guidance mapping", -1)),
              f("div", o1, [
                Ve(f("input", {
                  "onUpdate:modelValue": y[21] || (y[21] = (T) => m.value = T),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                  placeholder: "model sha256"
                }, null, 512), [
                  [at, m.value]
                ]),
                Ve(f("select", {
                  "onUpdate:modelValue": y[22] || (y[22] = (T) => _.value = T),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
                }, [...y[61] || (y[61] = [
                  f("option", { value: "txt2img" }, "txt2img", -1),
                  f("option", { value: "i2i" }, "i2i", -1)
                ])], 512), [
                  [ls, _.value]
                ]),
                V(X, {
                  size: "sm",
                  variant: "outline",
                  onClick: y[23] || (y[23] = (T) => g(t).loadGuidance(m.value, _.value))
                }, {
                  default: W(() => [...y[62] || (y[62] = [
                    O("Load", -1)
                  ])]),
                  _: 1
                })
              ])
            ])
          ]),
          _: 1
        })) : we("", !0)
      ], 64)) : ($(), Ze(Xe, {
        key: 1,
        class: "cmst:p-4"
      }, {
        default: W(() => [
          y[66] || (y[66] = f("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared model inventory", -1)),
          y[67] || (y[67] = f("p", { class: "cmst:mt-1 cmst:text-sm cmst:opacity-70" }, "Owned by infrastructureStore; workflow dependencies reference this state.", -1)),
          f("div", i1, "Models: " + G(g(s).models.length) + " · Custom nodes: " + G(g(s).customNodes.length), 1),
          f("div", a1, [
            V(X, {
              size: "sm",
              variant: "outline",
              onClick: y[24] || (y[24] = (T) => g(s).rescanModelsNow(!0))
            }, {
              default: W(() => [...y[64] || (y[64] = [
                O("Rescan models", -1)
              ])]),
              _: 1
            }),
            V(X, {
              size: "sm",
              variant: "outline",
              onClick: y[25] || (y[25] = (T) => g(s).refreshCustomNodesNow())
            }, {
              default: W(() => [...y[65] || (y[65] = [
                O("Refresh nodes", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        _: 1
      })),
      g(t).wizardOpen ? ($(), H("div", {
        key: 2,
        class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
        "data-state": "open",
        "data-testid": "vue-workflow-wizard",
        tabindex: "-1",
        onKeydown: Ws(Rr(ce, ["stop"]), ["esc"])
      }, [
        V(Xe, { class: "cmst:w-[min(42rem,94vw)] cmst:max-h-[90vh] cmst:overflow-auto cmst:p-5" }, {
          default: W(() => [
            f("div", c1, [
              f("div", null, [
                y[68] || (y[68] = f("h2", { class: "cmst:text-lg cmst:font-semibold" }, "Setup workflow", -1)),
                f("p", u1, "Step " + G(b.value + 1) + " of " + G(g(ws).length) + " · " + G(A.value), 1)
              ]),
              V(X, {
                variant: "ghost",
                size: "sm",
                onClick: ce
              }, {
                default: W(() => [...y[69] || (y[69] = [
                  O("Close", -1)
                ])]),
                _: 1
              })
            ]),
            f("div", d1, [
              A.value === "feature-type" ? ($(), H(Ee, { key: 0 }, [
                y[71] || (y[71] = f("h3", { class: "cmst:font-semibold" }, "Feature Type", -1)),
                y[72] || (y[72] = f("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Feature type is explicit and provider-neutral.", -1)),
                f("select", {
                  class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  value: g(t).wizardDraft?.featureType,
                  onChange: y[26] || (y[26] = (T) => g(t).updateWizard({ featureType: T.target.value }))
                }, [...y[70] || (y[70] = [
                  f("option", { value: "t2i" }, "Text to Image", -1),
                  f("option", { value: "i2i" }, "Image to Image", -1),
                  f("option", { value: "inpaint" }, "Inpaint", -1),
                  f("option", { value: "sketch" }, "Sketch", -1),
                  f("option", { value: "outpaint" }, "Outpaint", -1)
                ])], 40, f1)
              ], 64)) : A.value === "required-bindings" ? ($(), H(Ee, { key: 1 }, [
                y[74] || (y[74] = f("h3", { class: "cmst:font-semibold" }, "Required Bindings", -1)),
                y[75] || (y[75] = f("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Graph binding is explicit: underlying ComfyUI graph interaction is enabled while this step is active.", -1)),
                f("div", m1, [
                  Ve(f("input", {
                    "onUpdate:modelValue": y[27] || (y[27] = (T) => o.value = T),
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                    placeholder: "Node/widget target"
                  }, null, 512), [
                    [at, o.value]
                  ]),
                  V(X, {
                    size: "sm",
                    onClick: Ae
                  }, {
                    default: W(() => [...y[73] || (y[73] = [
                      O("Confirm binding", -1)
                    ])]),
                    _: 1
                  })
                ]),
                a.value ? ($(), H("p", p1, G(a.value), 1)) : we("", !0)
              ], 64)) : A.value === "exposed-controls" ? ($(), H(Ee, { key: 2 }, [
                y[78] || (y[78] = f("h3", { class: "cmst:font-semibold" }, "Exposed Controls", -1)),
                y[79] || (y[79] = f("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Workflow configuration controls live here — not a generic form builder.", -1)),
                f("div", h1, [
                  Ve(f("input", {
                    "onUpdate:modelValue": y[28] || (y[28] = (T) => i.value = T),
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                    placeholder: "Control label"
                  }, null, 512), [
                    [at, i.value]
                  ]),
                  V(X, {
                    size: "sm",
                    onClick: Q
                  }, {
                    default: W(() => [...y[76] || (y[76] = [
                      O("Add control", -1)
                    ])]),
                    _: 1
                  })
                ]),
                f("ul", g1, [
                  ($(!0), H(Ee, null, et(g(t).wizardDraft?.controls ?? [], (T, ve) => ($(), H("li", { key: ve }, "· " + G(String(T.label ?? T)), 1))), 128))
                ]),
                f("div", v1, [
                  V(X, {
                    size: "sm",
                    variant: "outline",
                    onClick: re
                  }, {
                    default: W(() => [...y[77] || (y[77] = [
                      O("Capture output binding", -1)
                    ])]),
                    _: 1
                  })
                ])
              ], 64)) : ($(), H(Ee, { key: 3 }, [
                y[80] || (y[80] = f("h3", { class: "cmst:font-semibold" }, "Details", -1)),
                y[81] || (y[81] = f("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Review the explicit bindings before saving the version mapping.", -1)),
                f("pre", y1, G(JSON.stringify({ bindings: g(t).wizardDraft?.bindings, output: g(t).wizardDraft?.outputBinding, controls: g(t).wizardDraft?.controls }, null, 1)), 1),
                g(t).wizardError ? ($(), H("p", b1, G(g(t).wizardError), 1)) : we("", !0),
                V(X, {
                  class: "cmst:mt-3",
                  size: "sm",
                  disabled: g(t).wizardSaving,
                  "data-testid": "vue-wizard-save",
                  onClick: U
                }, {
                  default: W(() => [
                    O(G(g(t).wizardSaving ? "Saving…" : "Save mapping"), 1)
                  ]),
                  _: 1
                }, 8, ["disabled"])
              ], 64))
            ]),
            f("div", w1, [
              V(X, {
                variant: "outline",
                size: "sm",
                disabled: b.value === 0,
                onClick: x
              }, {
                default: W(() => [...y[82] || (y[82] = [
                  O("Back", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              V(X, {
                size: "sm",
                disabled: b.value === g(ws).length - 1,
                onClick: q
              }, {
                default: W(() => [...y[83] || (y[83] = [
                  O("Next", -1)
                ])]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          _: 1
        })
      ], 40, l1)) : we("", !0)
    ], 2));
  }
}), x1 = {
  playground: Lw,
  history: Ew,
  workflows: _1,
  backend: zy,
  settings: I_
};
function k1(e = {}) {
  let t;
  return e.memory || !e.win ? t = sp() : t = Pv(e.win, e.initial), xp({
    history: t,
    routes: Ni.map((n) => ({
      path: `/${n}`,
      name: n,
      component: x1[n]
    }))
  });
}
function S1(e, t = {}) {
  const s = hm(), n = k1({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = fm(Ov);
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
  S1 as mountStudioPreview
};

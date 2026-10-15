/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function Yo(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const n of e.split(",")) t[n] = 1;
  return (n) => n in t;
}
const Ee = {}, Rn = [], jt = () => {
}, il = () => !1, kr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), Sr = (e) => e.startsWith("onUpdate:"), Ge = Object.assign, Qo = (e, t) => {
  const n = e.indexOf(t);
  n > -1 && e.splice(n, 1);
}, Eu = Object.prototype.hasOwnProperty, be = (e, t) => Eu.call(e, t), Q = Array.isArray, hn = (e) => Ds(e) === "[object Map]", rr = (e) => Ds(e) === "[object Set]", Ii = (e) => Ds(e) === "[object Date]", te = (e) => typeof e == "function", Re = (e) => typeof e == "string", dt = (e) => typeof e == "symbol", _e = (e) => e !== null && typeof e == "object", al = (e) => (_e(e) || te(e)) && te(e.then) && te(e.catch), ll = Object.prototype.toString, Ds = (e) => ll.call(e), Cu = (e) => Ds(e).slice(8, -1), cl = (e) => Ds(e) === "[object Object]", Er = (e) => Re(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, ms = /* @__PURE__ */ Yo(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), Cr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((n) => t[n] || (t[n] = e(n)));
}, Au = /-\w/g, Ye = Cr(
  (e) => e.replace(Au, (t) => t.slice(1).toUpperCase())
), Ou = /\B([A-Z])/g, Ln = Cr(
  (e) => e.replace(Ou, "-$1").toLowerCase()
), Ar = Cr((e) => e.charAt(0).toUpperCase() + e.slice(1)), tr = Cr(
  (e) => e ? `on${Ar(e)}` : ""
), Dt = (e, t) => !Object.is(e, t), nr = (e, ...t) => {
  for (let n = 0; n < e.length; n++)
    e[n](...t);
}, ul = (e, t, n, s = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: s,
    value: n
  });
}, Xo = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let Pi;
const Or = () => Pi || (Pi = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Ls(e) {
  if (Q(e)) {
    const t = {};
    for (let n = 0; n < e.length; n++) {
      const s = e[n], r = Re(s) ? Pu(s) : Ls(s);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (Re(e) || _e(e))
    return e;
}
const Ru = /;(?![^(]*\))/g, Tu = /:([^]+)/, Iu = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function Pu(e) {
  const t = {};
  return e.replace(Iu, (n) => n.startsWith("/*") ? "" : n).split(Ru).forEach((n) => {
    if (n) {
      const s = n.split(Tu);
      s.length > 1 && (t[s[0].trim()] = s[1].trim());
    }
  }), t;
}
function yt(e) {
  let t = "";
  if (Re(e))
    t = e;
  else if (Q(e))
    for (let n = 0; n < e.length; n++) {
      const s = yt(e[n]);
      s && (t += s + " ");
    }
  else if (_e(e))
    for (const n in e)
      e[n] && (t += n + " ");
  return t.trim();
}
function Nu(e) {
  if (!e) return null;
  let { class: t, style: n } = e;
  return t && !Re(t) && (e.class = yt(t)), n && (e.style = Ls(n)), e;
}
const Mu = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", Du = /* @__PURE__ */ Yo(Mu);
function fl(e) {
  return !!e || e === "";
}
function Lu(e, t, n) {
  if (e.length !== t.length) return !1;
  let s = !0;
  for (let r = 0; s && r < e.length; r++)
    s = Rr(e[r], t[r], n);
  return s;
}
function Ni(e, t, n) {
  if (e.size !== t.size) return !1;
  const s = Array.from(t), r = new Uint8Array(s.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < s.length; a++)
      if (!r[a] && Rr(o, s[a], n)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function ju(e, t, n) {
  let s = hn(e), r = hn(t);
  if (s || r || (s = rr(e), r = rr(t), s || r))
    return s && r ? Ni(e, t, n) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !Rr(e[a], t[a], n))
      return !1;
  }
  return String(e) === String(t);
}
function Mi(e, t, n, s) {
  n || (n = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = n;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = s(e, t, n);
  return r.delete(e), o.delete(t), i;
}
function Rr(e, t, n) {
  if (e === t) return !0;
  let s = Ii(e), r = Ii(t);
  return s || r ? s && r ? e.getTime() === t.getTime() : !1 : (s = dt(e), r = dt(t), s || r ? e === t : (s = Q(e), r = Q(t), s || r ? s && r ? Mi(e, t, n, Lu) : !1 : (s = _e(e), r = _e(t), s || r ? !s || !r ? !1 : Mi(e, t, n, ju) : String(e) === String(t))));
}
const dl = (e) => !!(e && e.__v_isRef === !0), Ne = (e) => Re(e) ? e : e == null ? "" : Q(e) || _e(e) && (e.toString === ll || !te(e.toString)) ? dl(e) ? Ne(e.value) : JSON.stringify(e, pl, 2) : String(e), pl = (e, t) => dl(t) ? pl(e, t.value) : hn(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (n, [s, r], o) => (n[Wr(s, o) + " =>"] = r, n),
    {}
  )
} : rr(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((n) => Wr(n))
} : dt(t) ? Wr(t) : _e(t) && !Q(t) && !cl(t) ? String(t) : t, Wr = (e, t = "") => {
  var n;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    dt(e) ? `Symbol(${(n = e.description) != null ? n : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Be;
class hl {
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
      let t, n;
      if (this.scopes) {
        const s = this.scopes.slice();
        for (t = 0, n = s.length; t < n; t++)
          s[t].pause();
      }
      for (t = 0, n = this.effects.length; t < n; t++)
        this.effects[t].pause();
    }
  }
  /**
   * Resumes the effect scope, including all child scopes and effects.
   */
  resume() {
    if (this._active && this._isPaused) {
      this._isPaused = !1;
      let t, n;
      if (this.scopes) {
        const r = this.scopes.slice();
        for (t = 0, n = r.length; t < n; t++)
          r[t].resume();
      }
      const s = this.effects.slice();
      for (t = 0, n = s.length; t < n; t++)
        s[t].resume();
    }
  }
  run(t) {
    if (this._active) {
      const n = Be;
      try {
        return Be = this, t();
      } finally {
        Be = n;
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
      let n, s;
      for (n = 0, s = this.effects.length; n < s; n++)
        this.effects[n].stop();
      for (this.effects.length = 0, n = 0, s = this.cleanups.length; n < s; n++)
        this.cleanups[n]();
      if (this.cleanups.length = 0, this.scopes) {
        const r = this.scopes.slice();
        for (n = 0, s = r.length; n < s; n++)
          r[n].stop(!0);
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
function Tr(e) {
  return new hl(e);
}
function Ir() {
  return Be;
}
function ei(e, t = !1) {
  Be && Be.cleanups.push(e);
}
let Ce;
const Hr = /* @__PURE__ */ new WeakSet();
class ml {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, Be && (Be.active ? Be.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, Hr.has(this) && (Hr.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || yl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, Di(this), vl(this);
    const t = Ce, n = wt;
    Ce = this, wt = !0;
    try {
      return this.fn();
    } finally {
      bl(this), Ce = t, wt = n, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        si(t);
      this.deps = this.depsTail = void 0, Di(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? Hr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    ko(this) && this.run();
  }
  get dirty() {
    return ko(this);
  }
}
let gl = 0, gs, ys;
function yl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = ys, ys = e;
    return;
  }
  e.next = gs, gs = e;
}
function ti() {
  gl++;
}
function ni() {
  if (--gl > 0)
    return;
  if (ys) {
    let t = ys;
    for (ys = void 0; t; ) {
      const n = t.next;
      t.next = void 0, t.flags &= -9, t = n;
    }
  }
  let e;
  for (; gs; ) {
    let t = gs;
    for (gs = void 0; t; ) {
      const n = t.next;
      if (t.next = void 0, t.flags &= -9, t.flags & 1)
        try {
          t.trigger();
        } catch (s) {
          e || (e = s);
        }
      t = n;
    }
  }
  if (e) throw e;
}
function vl(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function bl(e) {
  let t, n = e.depsTail, s = n;
  for (; s; ) {
    const r = s.prevDep;
    s.version === -1 ? (s === n && (n = r), si(s), $u(s)) : t = s, s.dep.activeLink = s.prevActiveLink, s.prevActiveLink = void 0, s = r;
  }
  e.deps = t, e.depsTail = n;
}
function ko(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (_l(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function _l(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === ks) || (e.globalVersion = ks, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !ko(e))))
    return;
  e.flags |= 2;
  const t = e.dep, n = Ce, s = wt;
  Ce = e, wt = !0;
  try {
    vl(e);
    const r = e.fn(e._value);
    (t.version === 0 || Dt(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Ce = n, wt = s, bl(e), e.flags &= -3;
  }
}
function si(e, t = !1) {
  const { dep: n, prevSub: s, nextSub: r } = e;
  if (s && (s.nextSub = r, e.prevSub = void 0), r && (r.prevSub = s, e.nextSub = void 0), n.subs === e && (n.subs = s, !s && n.computed)) {
    n.computed.flags &= -5;
    for (let o = n.computed.deps; o; o = o.nextDep)
      si(o, !0);
  }
  !t && !--n.sc && n.map && n.map.delete(n.key);
}
function $u(e) {
  const { prevDep: t, nextDep: n } = e;
  t && (t.nextDep = n, e.prevDep = void 0), n && (n.prevDep = t, e.nextDep = void 0);
}
let wt = !0;
const xl = [];
function Vt() {
  xl.push(wt), wt = !1;
}
function Bt() {
  const e = xl.pop();
  wt = e === void 0 ? !0 : e;
}
function Di(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const n = Ce;
    Ce = void 0;
    try {
      t();
    } finally {
      Ce = n;
    }
  }
}
let ks = 0;
class Fu {
  constructor(t, n) {
    this.sub = t, this.dep = n, this.version = n.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class ri {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!Ce || !wt || Ce === this.computed)
      return;
    let n = this.activeLink;
    if (n === void 0 || n.sub !== Ce)
      n = this.activeLink = new Fu(Ce, this), Ce.deps ? (n.prevDep = Ce.depsTail, Ce.depsTail.nextDep = n, Ce.depsTail = n) : Ce.deps = Ce.depsTail = n, wl(n);
    else if (n.version === -1 && (n.version = this.version, n.nextDep)) {
      const s = n.nextDep;
      s.prevDep = n.prevDep, n.prevDep && (n.prevDep.nextDep = s), n.prevDep = Ce.depsTail, n.nextDep = void 0, Ce.depsTail.nextDep = n, Ce.depsTail = n, Ce.deps === n && (Ce.deps = s);
    }
    return n;
  }
  trigger(t) {
    this.version++, ks++, this.notify(t);
  }
  notify(t) {
    ti();
    try {
      for (let n = this.subs; n; n = n.prevSub)
        n.sub.notify() && n.sub.dep.notify();
    } finally {
      ni();
    }
  }
}
function wl(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let s = t.deps; s; s = s.nextDep)
        wl(s);
    }
    const n = e.dep.subs;
    n !== e && (e.prevSub = n, n && (n.nextSub = e)), e.dep.subs = e;
  }
}
const or = /* @__PURE__ */ new WeakMap(), Pn = /* @__PURE__ */ Symbol(
  ""
), So = /* @__PURE__ */ Symbol(
  ""
), Ss = /* @__PURE__ */ Symbol(
  ""
);
function Ke(e, t, n) {
  if (wt && Ce) {
    let s = or.get(e);
    s || or.set(e, s = /* @__PURE__ */ new Map());
    let r = s.get(n);
    r || (s.set(n, r = new ri()), r.map = s, r.key = n), r.track();
  }
}
function Yt(e, t, n, s, r, o) {
  const i = or.get(e);
  if (!i) {
    ks++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (ti(), t === "clear")
    i.forEach(a);
  else {
    const l = Q(e), c = l && Er(n);
    if (l && n === "length") {
      const u = Number(s);
      i.forEach((f, d) => {
        (d === "length" || d === Ss || !dt(d) && d >= u) && a(f);
      });
    } else
      switch ((n !== void 0 || i.has(void 0)) && a(i.get(n)), c && a(i.get(Ss)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(Pn)), hn(e) && a(i.get(So)));
          break;
        case "delete":
          l || (a(i.get(Pn)), hn(e) && a(i.get(So)));
          break;
        case "set":
          hn(e) && a(i.get(Pn));
          break;
      }
  }
  ni();
}
function Vu(e, t) {
  const n = or.get(e);
  return n && n.get(t);
}
function Vn(e) {
  const t = /* @__PURE__ */ ge(e);
  return t === e || (Ke(t, "iterate", Ss), /* @__PURE__ */ ft(e)) ? t : /* @__PURE__ */ zt(e) ? /* @__PURE__ */ $t(e) ? t.map((n) => yn(mt(n))) : t.map(yn) : t.map(mt);
}
function Pr(e) {
  return Ke(e = /* @__PURE__ */ ge(e), "iterate", Ss), e;
}
function Pt(e, t) {
  return /* @__PURE__ */ zt(e) ? yn(/* @__PURE__ */ $t(e) ? mt(t) : t) : mt(t);
}
const Bu = {
  __proto__: null,
  [Symbol.iterator]() {
    return qr(this, Symbol.iterator, (e) => Pt(this, e));
  },
  concat(...e) {
    return Vn(this).concat(
      ...e.map((t) => Q(t) ? Vn(t) : t)
    );
  },
  entries() {
    return qr(this, "entries", (e) => (e[1] = Pt(this, e[1]), e));
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
      (n) => n.map((s) => Pt(this, s)),
      arguments
    );
  },
  find(e, t) {
    return Ht(
      this,
      "find",
      e,
      t,
      (n) => Pt(this, n),
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
      (n) => Pt(this, n),
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
    return Zr(this, "includes", e);
  },
  indexOf(...e) {
    return Zr(this, "indexOf", e);
  },
  join(e) {
    return Vn(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return Zr(this, "lastIndexOf", e);
  },
  map(e, t) {
    return Ht(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return is(this, "pop");
  },
  push(...e) {
    return is(this, "push", e);
  },
  reduce(e, ...t) {
    return ji(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return ji(this, "reduceRight", e, t);
  },
  shift() {
    return is(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return Ht(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return is(this, "splice", e);
  },
  toReversed() {
    return Vn(this).toReversed();
  },
  toSorted(e) {
    return Vn(this).toSorted(e);
  },
  toSpliced(...e) {
    return Vn(this).toSpliced(...e);
  },
  unshift(...e) {
    return is(this, "unshift", e);
  },
  values() {
    return qr(this, "values", (e) => Pt(this, e));
  }
};
function qr(e, t, n) {
  const s = Pr(e), r = s[t], o = r.call(s);
  if (s !== e && !/* @__PURE__ */ ft(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => Li(o.next(), n), r !== kl[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => Li(o._next(), n);
  }
  return o;
}
function Li(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const kl = Array.prototype;
function Ht(e, t, n, s, r, o) {
  const i = Pr(e), a = i !== e && !/* @__PURE__ */ ft(e), l = i[t];
  if (l !== kl[t]) {
    const f = l.apply(e, o);
    return a ? mt(f) : f;
  }
  let c = n;
  i !== e && (a ? c = function(f, d) {
    return n.call(this, Pt(e, f), d, e);
  } : n.length > 2 && (c = function(f, d) {
    return n.call(this, f, d, e);
  }));
  const u = l.call(i, c, s);
  return a && r ? r(u) : u;
}
function ji(e, t, n, s) {
  const r = Pr(e), o = r !== e && !/* @__PURE__ */ ft(e);
  let i = n, a = !1;
  r !== e && (o ? (a = s.length === 0, i = function(c, u, f) {
    return a && (a = !1, c = Pt(e, c)), n.call(this, c, Pt(e, u), f, e);
  }) : n.length > 3 && (i = function(c, u, f) {
    return n.call(this, c, u, f, e);
  }));
  const l = r[t](i, ...s);
  return a ? Pt(e, l) : l;
}
function Zr(e, t, n) {
  const s = /* @__PURE__ */ ge(e);
  Ke(s, "iterate", Ss);
  const r = s[t](...n);
  return (r === -1 || r === !1) && /* @__PURE__ */ Nr(n[0]) ? (n[0] = /* @__PURE__ */ ge(n[0]), s[t](...n)) : r;
}
function is(e, t, n = []) {
  Vt(), ti();
  const s = (/* @__PURE__ */ ge(e))[t].apply(e, n);
  return ni(), Bt(), s;
}
const zu = /* @__PURE__ */ Yo("__proto__,__v_isRef,__isVue"), Sl = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(dt)
);
function Uu(e) {
  dt(e) || (e = String(e));
  const t = /* @__PURE__ */ ge(this);
  return Ke(t, "has", e), t.hasOwnProperty(e);
}
class El {
  constructor(t = !1, n = !1) {
    this._isReadonly = t, this._isShallow = n;
  }
  get(t, n, s) {
    if (n === "__v_skip") return t.__v_skip;
    const r = this._isReadonly, o = this._isShallow;
    if (n === "__v_isReactive")
      return !r;
    if (n === "__v_isReadonly")
      return r;
    if (n === "__v_isShallow")
      return o;
    if (n === "__v_raw")
      return s === (r ? o ? Xu : Rl : o ? Ol : Al).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(s) ? t : void 0;
    const i = Q(t);
    if (!r) {
      let l;
      if (i && (l = Bu[n]))
        return l;
      if (n === "hasOwnProperty")
        return Uu;
    }
    const a = Reflect.get(
      t,
      n,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ Me(t) ? t : s
    );
    if ((dt(n) ? Sl.has(n) : zu(n)) || (r || Ke(t, "get", n), o))
      return a;
    if (/* @__PURE__ */ Me(a)) {
      const l = i && Er(n) ? a : a.value;
      return r && _e(l) ? /* @__PURE__ */ Co(l) : l;
    }
    return _e(a) ? r ? /* @__PURE__ */ Co(a) : /* @__PURE__ */ jn(a) : a;
  }
}
class Cl extends El {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, n, s, r) {
    let o = t[n];
    const i = Q(t) && Er(n);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ zt(o);
      if (!/* @__PURE__ */ ft(s) && !/* @__PURE__ */ zt(s) && (o = /* @__PURE__ */ ge(o), s = /* @__PURE__ */ ge(s)), !i && /* @__PURE__ */ Me(o) && !/* @__PURE__ */ Me(s))
        return c || (o.value = s), !0;
    }
    const a = i ? Number(n) < t.length : be(t, n), l = Reflect.set(
      t,
      n,
      s,
      /* @__PURE__ */ Me(t) ? t : r
    );
    return t === /* @__PURE__ */ ge(r) && l && (a ? Dt(s, o) && Yt(t, "set", n, s) : Yt(t, "add", n, s)), l;
  }
  deleteProperty(t, n) {
    const s = be(t, n);
    t[n];
    const r = Reflect.deleteProperty(t, n);
    return r && s && Yt(t, "delete", n, void 0), r;
  }
  has(t, n) {
    const s = Reflect.has(t, n);
    return (!dt(n) || !Sl.has(n)) && Ke(t, "has", n), s;
  }
  ownKeys(t) {
    return Ke(
      t,
      "iterate",
      Q(t) ? "length" : Pn
    ), Reflect.ownKeys(t);
  }
}
class Wu extends El {
  constructor(t = !1) {
    super(!0, t);
  }
  set(t, n) {
    return !0;
  }
  deleteProperty(t, n) {
    return !0;
  }
}
const Hu = /* @__PURE__ */ new Cl(), qu = /* @__PURE__ */ new Wu(), Zu = /* @__PURE__ */ new Cl(!0);
const Eo = (e) => e, Vs = (e) => Reflect.getPrototypeOf(e);
function Gu(e, t, n) {
  return function(...s) {
    const r = this.__v_raw, o = /* @__PURE__ */ ge(r), i = hn(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...s), u = n ? Eo : t ? yn : mt;
    return !t && Ke(
      o,
      "iterate",
      l ? So : Pn
    ), Ge(
      // inheriting all iterator properties
      Object.create(c),
      {
        // iterator protocol
        next() {
          const { value: f, done: d } = c.next();
          return d ? { value: f, done: d } : {
            value: a ? [u(f[0]), u(f[1])] : u(f),
            done: d
          };
        }
      }
    );
  };
}
function Bs(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function Ku(e, t) {
  const n = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ ge(o), a = /* @__PURE__ */ ge(r);
      e || (Dt(r, a) && Ke(i, "get", r), Ke(i, "get", a));
      const { has: l } = Vs(i), c = t ? Eo : e ? yn : mt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && Ke(/* @__PURE__ */ ge(r), "iterate", Pn), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ ge(o), a = /* @__PURE__ */ ge(r);
      return e || (Dt(r, a) && Ke(i, "has", r), Ke(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ ge(a), c = t ? Eo : e ? yn : mt;
      return !e && Ke(l, "iterate", Pn), a.forEach((u, f) => r.call(o, c(u), c(f), i));
    }
  };
  return Ge(
    n,
    e ? {
      add: Bs("add"),
      set: Bs("set"),
      delete: Bs("delete"),
      clear: Bs("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ ge(this), i = Vs(o), a = /* @__PURE__ */ ge(r), l = !t && !/* @__PURE__ */ ft(r) && !/* @__PURE__ */ zt(r) ? a : r;
        return i.has.call(o, l) || Dt(r, l) && i.has.call(o, r) || Dt(a, l) && i.has.call(o, a) || (o.add(l), Yt(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ ft(o) && !/* @__PURE__ */ zt(o) && (o = /* @__PURE__ */ ge(o));
        const i = /* @__PURE__ */ ge(this), { has: a, get: l } = Vs(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ ge(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? Dt(o, u) && Yt(i, "set", r, o) : Yt(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ ge(this), { has: i, get: a } = Vs(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ ge(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && Yt(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ ge(this), o = r.size !== 0, i = r.clear();
        return o && Yt(
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
    n[r] = Gu(r, e, t);
  }), n;
}
function oi(e, t) {
  const n = Ku(e, t);
  return (s, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? s : Reflect.get(
    be(n, r) && r in s ? n : s,
    r,
    o
  );
}
const Ju = {
  get: /* @__PURE__ */ oi(!1, !1)
}, Yu = {
  get: /* @__PURE__ */ oi(!1, !0)
}, Qu = {
  get: /* @__PURE__ */ oi(!0, !1)
};
const Al = /* @__PURE__ */ new WeakMap(), Ol = /* @__PURE__ */ new WeakMap(), Rl = /* @__PURE__ */ new WeakMap(), Xu = /* @__PURE__ */ new WeakMap();
function ef(e) {
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
function jn(e) {
  return /* @__PURE__ */ zt(e) ? e : ii(
    e,
    !1,
    Hu,
    Ju,
    Al
  );
}
// @__NO_SIDE_EFFECTS__
function Tl(e) {
  return ii(
    e,
    !1,
    Zu,
    Yu,
    Ol
  );
}
// @__NO_SIDE_EFFECTS__
function Co(e) {
  return ii(
    e,
    !0,
    qu,
    Qu,
    Rl
  );
}
function ii(e, t, n, s, r) {
  if (!_e(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = ef(Cu(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? s : n
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function $t(e) {
  return /* @__PURE__ */ zt(e) ? /* @__PURE__ */ $t(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function zt(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function ft(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function Nr(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function ge(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ ge(t) : e;
}
function ai(e) {
  return !be(e, "__v_skip") && Object.isExtensible(e) && ul(e, "__v_skip", !0), e;
}
const mt = (e) => _e(e) ? /* @__PURE__ */ jn(e) : e, yn = (e) => _e(e) ? /* @__PURE__ */ Co(e) : e;
// @__NO_SIDE_EFFECTS__
function Me(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function oe(e) {
  return Il(e, !1);
}
// @__NO_SIDE_EFFECTS__
function Zn(e) {
  return Il(e, !0);
}
function Il(e, t) {
  return /* @__PURE__ */ Me(e) ? e : new tf(e, t);
}
class tf {
  constructor(t, n) {
    this.dep = new ri(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = n ? t : /* @__PURE__ */ ge(t), this._value = n ? t : mt(t), this.__v_isShallow = n;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const n = this._rawValue, s = this.__v_isShallow || /* @__PURE__ */ ft(t) || /* @__PURE__ */ zt(t);
    t = s ? t : /* @__PURE__ */ ge(t), Dt(t, n) && (this._rawValue = t, this._value = s ? t : mt(t), this.dep.trigger());
  }
}
function nf(e) {
  e.dep && e.dep.trigger();
}
function C(e) {
  return /* @__PURE__ */ Me(e) ? e.value : e;
}
function Qe(e) {
  return te(e) ? e() : C(e);
}
const sf = {
  get: (e, t, n) => t === "__v_raw" ? e : C(Reflect.get(e, t, n)),
  set: (e, t, n, s) => {
    const r = e[t];
    return /* @__PURE__ */ Me(r) && !/* @__PURE__ */ Me(n) ? (r.value = n, !0) : Reflect.set(e, t, n, s);
  }
};
function Pl(e) {
  return /* @__PURE__ */ $t(e) ? e : new Proxy(e, sf);
}
// @__NO_SIDE_EFFECTS__
function li(e) {
  const t = Q(e) ? new Array(e.length) : {};
  for (const n in e)
    t[n] = of(e, n);
  return t;
}
class rf {
  constructor(t, n, s) {
    this._object = t, this._defaultValue = s, this.__v_isRef = !0, this._value = void 0, this._key = dt(n) ? n : String(n), this._raw = /* @__PURE__ */ ge(t);
    let r = !0, o = t;
    if (!Q(t) || dt(this._key) || !Er(this._key))
      do
        r = !/* @__PURE__ */ Nr(o) || /* @__PURE__ */ ft(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = C(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ Me(this._raw[this._key])) {
      const n = this._object[this._key];
      if (/* @__PURE__ */ Me(n)) {
        n.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return Vu(this._raw, this._key);
  }
}
function of(e, t, n) {
  return new rf(e, t, n);
}
class af {
  constructor(t, n, s) {
    this.fn = t, this.setter = n, this._value = void 0, this.dep = new ri(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = ks - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !n, this.isSSR = s;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Ce !== this)
      return yl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return _l(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function lf(e, t, n = !1) {
  let s, r;
  return te(e) ? s = e : (s = e.get, r = e.set), new af(s, r, n);
}
const zs = {}, ir = /* @__PURE__ */ new WeakMap();
let An;
function cf(e, t = !1, n = An) {
  if (n) {
    let s = ir.get(n);
    s || ir.set(n, s = []), s.push(e);
  }
}
function uf(e, t, n = Ee) {
  const { immediate: s, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = n, c = (O) => r ? O : /* @__PURE__ */ ft(O) || r === !1 || r === 0 ? Qt(O, 1) : Qt(O);
  let u, f, d, h, y = !1, v = !1;
  if (/* @__PURE__ */ Me(e) ? (f = () => e.value, y = /* @__PURE__ */ ft(e)) : /* @__PURE__ */ $t(e) ? (f = () => c(e), y = !0) : Q(e) ? (v = !0, y = e.some((O) => /* @__PURE__ */ $t(O) || /* @__PURE__ */ ft(O)), f = () => e.map((O) => {
    if (/* @__PURE__ */ Me(O))
      return O.value;
    if (/* @__PURE__ */ $t(O))
      return c(O);
    if (te(O))
      return l ? l(O, 2) : O();
  })) : te(e) ? t ? f = l ? () => l(e, 2) : e : f = () => {
    if (d) {
      Vt();
      try {
        d();
      } finally {
        Bt();
      }
    }
    const O = An;
    An = u;
    try {
      return l ? l(e, 3, [h]) : e(h);
    } finally {
      An = O;
    }
  } : f = jt, t && r) {
    const O = f, U = r === !0 ? 1 / 0 : r;
    f = () => Qt(O(), U);
  }
  const w = Ir(), R = () => {
    u.stop(), w && w.active && Qo(w.effects, u);
  };
  if (o && t) {
    const O = t;
    t = (...U) => {
      try {
        return O(...U);
      } finally {
        R();
      }
    };
  }
  let x = v ? new Array(e.length).fill(zs) : zs;
  const N = (O) => {
    if (!(!(u.flags & 1) || !u.dirty && !O))
      if (t) {
        const U = u.run();
        if (O || r || y || (v ? U.some((ve, F) => Dt(ve, x[F])) : Dt(U, x))) {
          const ve = An;
          Vt();
          try {
            d && d(), An = u;
            const F = [
              U,
              // pass undefined as the old value when it's changed for the first time
              x === zs ? void 0 : v && x[0] === zs ? [] : x,
              h
            ];
            x = U, l ? l(t, 3, F) : (
              // @ts-expect-error
              t(...F)
            );
          } finally {
            An = ve, Bt();
          }
        }
      } else
        u.run();
  };
  return a && a(N), u = new ml(f), u.scheduler = i ? () => i(N, !1) : N, h = (O) => cf(O, !1, u), d = u.onStop = () => {
    const O = ir.get(u);
    if (O) {
      if (l)
        l(O, 4);
      else
        for (const U of O) U();
      ir.delete(u);
    }
  }, t ? s ? N(!0) : x = u.run() : i ? i(N.bind(null, !0), !0) : u.run(), R.pause = u.pause.bind(u), R.resume = u.resume.bind(u), R.stop = R, R;
}
function Qt(e, t = 1 / 0, n) {
  if (t <= 0 || !_e(e) || e.__v_skip || (n = n || /* @__PURE__ */ new Map(), (n.get(e) || 0) >= t))
    return e;
  if (n.set(e, t), t--, /* @__PURE__ */ Me(e))
    Qt(e.value, t, n);
  else if (Q(e))
    for (let s = 0; s < e.length; s++)
      Qt(e[s], t, n);
  else if (rr(e) || hn(e))
    e.forEach((s) => {
      Qt(s, t, n);
    });
  else if (cl(e)) {
    for (const s in e)
      Qt(e[s], t, n);
    for (const s of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, s) && Qt(e[s], t, n);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function js(e, t, n, s) {
  try {
    return s ? e(...s) : e();
  } catch (r) {
    Mr(r, t, n);
  }
}
function kt(e, t, n, s) {
  if (te(e)) {
    const r = js(e, t, n, s);
    return r && al(r) && r.catch((o) => {
      Mr(o, t, n);
    }), r;
  }
  if (Q(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(kt(e[o], t, n, s));
    return r;
  }
}
function Mr(e, t, n, s = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || Ee;
  if (t) {
    let a = t.parent;
    const l = t.proxy, c = `https://vuejs.org/error-reference/#runtime-${n}`;
    for (; a; ) {
      const u = a.ec;
      if (u) {
        for (let f = 0; f < u.length; f++)
          if (u[f](e, l, c) === !1)
            return;
      }
      a = a.parent;
    }
    if (o) {
      Vt(), js(o, null, 10, [
        e,
        l,
        c
      ]), Bt();
      return;
    }
  }
  ff(e, n, r, s, i);
}
function ff(e, t, n, s = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const rt = [];
let xt = -1;
const Nt = [];
let fn = null, Un = 0;
const Nl = /* @__PURE__ */ Promise.resolve();
let ar = null;
function St(e) {
  const t = ar || Nl;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function df(e) {
  let t = xt + 1, n = rt.length;
  for (; t < n; ) {
    const s = t + n >>> 1, r = rt[s], o = Es(r);
    o < e || o === e && r.flags & 2 ? t = s + 1 : n = s;
  }
  return t;
}
function ci(e) {
  if (!(e.flags & 1)) {
    const t = Es(e), n = rt[rt.length - 1];
    !n || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= Es(n) ? rt.push(e) : rt.splice(df(t), 0, e), e.flags |= 1, Ml();
  }
}
function Ml() {
  ar || (ar = Nl.then(jl));
}
function pf(e) {
  if (!Q(e))
    fn && e.id === -1 ? fn.splice(Un + 1, 0, e) : e.flags & 1 || (Nt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Nt.push(e[t]);
  Ml();
}
function Dl(e, t, n, s = xt + 1) {
  for (; s < rt.length; s++) {
    const r = rt[s];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      rt.splice(s, 1), s = e ? s - 1 : xt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function Ll(e, t, n = 0) {
  if (Nt.length) {
    let s = Nt, r = 0;
    if (t) {
      s = [];
      for (let i = 0; i < Nt.length; i++) {
        const a = Nt[i];
        (a.i !== void 0 ? !a.i || a.i.uid < n : t.has(a)) ? Nt[r++] = a : s.push(a);
      }
    }
    const o = [...new Set(s)].sort((i, a) => Es(i) - Es(a));
    if (Nt.length = r, fn) {
      for (let i = 0; i < o.length; i++)
        fn.push(o[i]);
      return;
    }
    for (fn = o, Un = 0; Un < fn.length; Un++) {
      const i = fn[Un];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    fn = null, Un = 0;
  }
}
let Gr = !1;
function hf(e, t) {
  if (Gr) {
    e();
    return;
  }
  const n = t === void 0 ? void 0 : new Set(Nt);
  e(), Gr = !0;
  try {
    Dl(void 0, t), Ll(void 0, n, t);
  } finally {
    Gr = !1;
  }
}
const Es = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function jl(e) {
  try {
    for (xt = 0; xt < rt.length; xt++) {
      const t = rt[xt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), js(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; xt < rt.length; xt++) {
      const t = rt[xt];
      t && (t.flags &= -2);
    }
    xt = -1, rt.length = 0, Ll(), ar = null, (rt.length || Nt.length) && jl();
  }
}
let Ze = null, $l = null;
function lr(e) {
  const t = Ze;
  return Ze = e, $l = e && e.type.__scopeId || null, t;
}
function re(e, t = Ze, n) {
  if (!t || e._n)
    return e;
  const s = (...r) => {
    s._d && dr(-1);
    const o = lr(t), i = Xt.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = Xt.length; l > i; l--) gi();
      lr(o), s._d && dr(1);
    }
    return a;
  };
  return s._n = !0, s._c = !0, s._d = !0, s;
}
function Cs(e, t) {
  if (Ze === null)
    return e;
  const n = Vr(Ze), s = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = Ee] = t[r];
    o && (te(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && Qt(i), s.push({
      dir: o,
      instance: n,
      value: i,
      oldValue: void 0,
      arg: a,
      modifiers: l
    }));
  }
  return e;
}
function kn(e, t, n, s) {
  const r = e.dirs, o = t && t.dirs;
  for (let i = 0; i < r.length; i++) {
    const a = r[i];
    o && (a.oldValue = o[i].value);
    let l = a.dir[s];
    l && (Vt(), kt(l, n, 8, [
      e.el,
      a,
      e,
      t
    ]), Bt());
  }
}
function vs(e, t) {
  if (Je) {
    let n = Je.provides;
    const s = Je.parent && Je.parent.provides;
    s === n && (n = Je.provides = Object.create(s)), n[e] = t;
  }
}
function ot(e, t, n = !1) {
  const s = Ct();
  if (s || Nn) {
    let r = Nn ? Nn._context.provides : s ? s.parent == null || s.ce ? s.vnode.appContext && s.vnode.appContext.provides : s.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return n && te(t) ? t.call(s && s.proxy) : t;
  }
}
function ui() {
  return !!(Ct() || Nn);
}
const mf = /* @__PURE__ */ Symbol.for("v-scx"), gf = () => ot(mf);
function Kn(e, t) {
  return fi(e, null, t);
}
function je(e, t, n) {
  return fi(e, t, n);
}
function fi(e, t, n = Ee) {
  const { immediate: s, deep: r, flush: o, once: i } = n, a = Ge({}, n), l = t && s || !t && o !== "post";
  let c;
  if (Ts) {
    if (o === "sync") {
      const h = gf();
      c = h.__watcherHandles || (h.__watcherHandles = []);
    } else if (!l) {
      const h = () => {
      };
      return h.stop = jt, h.resume = jt, h.pause = jt, h;
    }
  }
  const u = Je;
  a.call = (h, y, v) => kt(h, u, y, v);
  let f = !1;
  o === "post" ? a.scheduler = (h) => {
    h.i = u, nt(h, u && u.suspense);
  } : o !== "sync" && (f = !0, a.scheduler = (h, y) => {
    y ? h() : ci(h);
  }), a.augmentJob = (h) => {
    t && (h.flags |= 4), f && (h.flags |= 2, u && (h.id = u.uid, h.i = u));
  };
  const d = uf(e, t, a);
  return Ts && (c ? c.push(d) : l && d()), d;
}
function yf(e, t, n) {
  const s = this.proxy, r = Re(e) ? e.includes(".") ? Fl(s, e) : () => s[e] : e.bind(s, s);
  let o;
  te(t) ? o = t : (o = t.handler, n = t);
  const i = $s(this), a = fi(r, o.bind(s), n);
  return i(), a;
}
function Fl(e, t) {
  const n = t.split(".");
  return () => {
    let s = e;
    for (let r = 0; r < n.length && s; r++)
      s = s[n[r]];
    return s;
  };
}
const cn = /* @__PURE__ */ new WeakMap(), Vl = /* @__PURE__ */ Symbol("_vte"), Dr = (e) => e.__isTeleport, On = (e) => e && (e.disabled || e.disabled === ""), vf = (e) => e && (e.defer || e.defer === ""), $i = (e) => typeof SVGElement < "u" && e instanceof SVGElement, Fi = (e) => typeof MathMLElement == "function" && e instanceof MathMLElement, Ao = (e, t) => {
  const n = e && e.to;
  return Re(n) ? t ? t(n) : null : n;
}, bf = {
  name: "Teleport",
  __isTeleport: !0,
  process(e, t, n, s, r, o, i, a, l, c) {
    const {
      mc: u,
      pc: f,
      pbc: d,
      o: { insert: h, querySelector: y, createText: v, createComment: w, parentNode: R }
    } = c, x = On(t.props);
    let { dynamicChildren: N } = t;
    const O = (F, S, j) => {
      F.shapeFlag & 16 && u(
        F.children,
        S,
        j,
        r,
        o,
        i,
        a,
        l
      );
    }, U = (F = t) => {
      const S = On(F.props), j = F.target = Ao(F.props, y), pe = Oo(j, F, v, h);
      j && (i !== "svg" && $i(j) ? i = "svg" : i !== "mathml" && Fi(j) && (i = "mathml"), r && r.isCE && (r.ce._teleportTargets || (r.ce._teleportTargets = /* @__PURE__ */ new Set())).add(j), S || (O(F, j, pe), fs(F, !1)));
    }, ve = (F) => {
      const S = () => {
        if (cn.get(F) === S) {
          if (cn.delete(F), On(F.props)) {
            const j = R(F.el) || n;
            O(F, j, F.anchor), fs(F, !0);
          }
          U(F);
        }
      };
      cn.set(F, S), nt(S, o);
    };
    if (e == null) {
      const F = t.el = v(""), S = t.anchor = v("");
      if (h(F, n, s), h(S, n, s), vf(t.props) || o && o.pendingBranch) {
        ve(t);
        return;
      }
      x && (O(t, n, S), fs(t, !0)), U();
    } else {
      t.el = e.el;
      const F = t.anchor = e.anchor, S = cn.get(e);
      if (S) {
        S.flags |= 8, cn.delete(e), ve(t);
        return;
      }
      t.targetStart = e.targetStart;
      const j = t.target = e.target, pe = t.targetAnchor = e.targetAnchor, Ae = On(e.props), Te = Ae ? n : j, $e = Ae ? F : pe;
      if (i === "svg" || $i(j) ? i = "svg" : (i === "mathml" || Fi(j)) && (i = "mathml"), N ? (d(
        e.dynamicChildren,
        N,
        Te,
        r,
        o,
        i,
        a
      ), mi(e, t, !0)) : l || f(
        e,
        t,
        Te,
        $e,
        r,
        o,
        i,
        a,
        !1
      ), x)
        Ae ? t.props && e.props && t.props.to !== e.props.to && (t.props.to = e.props.to) : Us(
          t,
          n,
          F,
          c,
          1
        );
      else if ((t.props && t.props.to) !== (e.props && e.props.to)) {
        const Xe = Ao(t.props, y);
        Xe && (t.target = Xe, Us(
          t,
          Xe,
          null,
          c,
          0
        ));
      } else Ae && Us(
        t,
        j,
        pe,
        c,
        1
      );
      fs(t, x);
    }
  },
  remove(e, t, n, { um: s, o: { remove: r } }, o) {
    const {
      shapeFlag: i,
      children: a,
      anchor: l,
      targetStart: c,
      targetAnchor: u,
      target: f,
      props: d
    } = e, h = On(d), y = o || !h, v = cn.get(e);
    if (v && (v.flags |= 8, cn.delete(e)), f && (r(c), r(u)), o && r(l), !v && (h || f) && i & 16)
      for (let w = 0; w < a.length; w++) {
        const R = a[w];
        s(
          R,
          t,
          n,
          y,
          !!R.dynamicChildren
        );
      }
  },
  move: Us,
  hydrate: _f
};
function Us(e, t, n, { o: { insert: s }, m: r }, o = 2) {
  o === 0 && (e.targetStart && s(e.targetStart, t, n), s(e.targetAnchor, t, n), n = e.targetAnchor);
  const { el: i, anchor: a, shapeFlag: l, children: c, props: u } = e, f = o === 2;
  if (f && s(i, t, n), !cn.has(e) && (!f || On(u)) && l & 16)
    for (let d = 0; d < c.length; d++)
      r(
        c[d],
        t,
        n,
        2
      );
  f && s(a, t, n);
}
function _f(e, t, n, s, r, o, {
  o: { nextSibling: i, parentNode: a, querySelector: l, insert: c, createText: u }
}, f) {
  function d(w, R) {
    let x = R;
    for (; x; ) {
      if (x && x.nodeType === 8) {
        if (x.data === "teleport start anchor")
          t.targetStart = x;
        else if (x.data === "teleport anchor") {
          t.targetAnchor = x, w._lpa = t.targetAnchor && i(t.targetAnchor);
          break;
        }
      }
      x = i(x);
    }
  }
  function h(w, R) {
    R.anchor = f(
      i(w),
      R,
      a(w),
      n,
      s,
      r,
      o
    );
  }
  const y = t.target = Ao(
    t.props,
    l
  ), v = On(t.props);
  if (y) {
    const w = y._lpa || y.firstChild;
    t.shapeFlag & 16 && (v ? (h(e, t), d(y, w), t.targetAnchor || Oo(
      y,
      t,
      u,
      c,
      // if target is the same as the main view, insert anchors before current node
      // to avoid hydrating mismatch
      a(e) === y ? e : null
    )) : (t.anchor = i(e), d(y, w), t.targetAnchor || Oo(y, t, u, c), f(
      w && i(w),
      t,
      y,
      n,
      s,
      r,
      o
    ))), fs(t, v);
  } else v && t.shapeFlag & 16 && (h(e, t), t.targetStart = e, t.targetAnchor = i(e));
  return t.anchor && i(t.anchor);
}
const xf = bf;
function fs(e, t) {
  const n = e.ctx;
  if (n && n.ut) {
    let s, r;
    for (t ? (s = e.el, r = e.anchor) : (s = e.targetStart, r = e.targetAnchor); s && s !== r; )
      s.nodeType === 1 && s.setAttribute("data-v-owner", n.uid), s = s.nextSibling;
    n.ut();
  }
}
function Oo(e, t, n, s, r = null) {
  const o = t.targetStart = n(""), i = t.targetAnchor = n("");
  return o[Vl] = i, e && (s(o, e, r), s(i, e, r)), i;
}
const Kr = /* @__PURE__ */ Symbol("_leaveCb");
function wf(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const n of e)
      if (n.type !== pt) {
        t = n;
        break;
      }
  }
  return t;
}
function Bl(e) {
  if (!di(e))
    return Dr(e.type) && e.children ? wf(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: n } = e;
  if (n) {
    if (t & 16)
      return n[0];
    if (t & 32 && te(n.default))
      return n.default();
  }
}
function cr(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const n = e.component.subTree;
    cr(
      Dr(n.type) && Bl(n) || n,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === qe && Q(e.children)) {
    const n = Xl(e.children, !1);
    n && cr(n, t);
  }
}
function Ro(e) {
  if (e.component)
    return Ro(e.component.subTree);
  if (e.type === qe) {
    const t = Q(e.children) && Xl(e.children, !1);
    return t ? Ro(t) : void 0;
  }
  if (e.type !== pt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function ke(e, t) {
  return te(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    Ge({ name: e.name }, t, { setup: e })
  ) : e;
}
function kf() {
  const e = Ct();
  return e ? (e.appContext.config.idPrefix || "v") + "-" + e.ids[0] + e.ids[1]++ : "";
}
function zl(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function Vi(e, t) {
  let n;
  return !!((n = Object.getOwnPropertyDescriptor(e, t)) && !n.configurable);
}
const ur = /* @__PURE__ */ new WeakMap();
function bs(e, t, n, s, r = !1) {
  if (Q(e)) {
    e.forEach(
      (v, w) => bs(
        v,
        t && (Q(t) ? t[w] : t),
        n,
        s,
        r
      )
    );
    return;
  }
  if (Gn(s) && !r) {
    s.shapeFlag & 512 && s.type.__asyncResolved && s.component.subTree.component && bs(e, t, n, s.component.subTree);
    return;
  }
  const o = s.shapeFlag & 4 ? Vr(s.component) : s.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === Ee ? a.refs = {} : a.refs, f = a.setupState, d = /* @__PURE__ */ ge(f), h = f === Ee ? il : (v) => Vi(u, v) ? !1 : be(d, v), y = (v, w) => !(w && Vi(u, w));
  if (c != null && c !== l) {
    if (Bi(t), Re(c))
      u[c] = null, h(c) && (f[c] = null);
    else if (/* @__PURE__ */ Me(c)) {
      const v = t;
      y(c, v.k) && (c.value = null), v.k && (u[v.k] = null);
    }
  }
  if (te(l))
    js(l, a, 12, [i, u]);
  else {
    const v = Re(l), w = /* @__PURE__ */ Me(l);
    if (v || w) {
      const R = () => {
        if (e.f) {
          const x = v ? h(l) ? f[l] : u[l] : y() || !e.k ? l.value : u[e.k];
          if (r)
            Q(x) && Qo(x, o);
          else if (Q(x))
            x.includes(o) || x.push(o);
          else if (v)
            u[l] = [o], h(l) && (f[l] = u[l]);
          else {
            const N = [o];
            y(l, e.k) && (l.value = N), e.k && (u[e.k] = N);
          }
        } else v ? (u[l] = i, h(l) && (f[l] = i)) : w && (y(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const x = () => {
          R(), ur.delete(e);
        };
        x.id = -1, ur.set(e, x), nt(x, n);
      } else
        Bi(e), R();
    }
  }
}
function Bi(e) {
  const t = ur.get(e);
  t && (t.flags |= 8, ur.delete(e));
}
Or().requestIdleCallback;
Or().cancelIdleCallback;
const Gn = (e) => !!e.type.__asyncLoader, di = (e) => e.type.__isKeepAlive;
function Sf(e, t) {
  Ul(e, "a", t);
}
function Ef(e, t) {
  Ul(e, "da", t);
}
function Ul(e, t, n = Je) {
  const s = e.__wdc || (e.__wdc = () => {
    let r = n;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (Lr(t, s, n), n) {
    let r = n.parent;
    for (; r && r.parent; )
      di(r.parent.vnode) && Cf(s, t, n, r), r = r.parent;
  }
}
function Cf(e, t, n, s) {
  const r = Lr(
    t,
    e,
    s,
    !0
    /* prepend */
  );
  jr(() => {
    Qo(s[t], r);
  }, n);
}
function Lr(e, t, n = Je, s = !1) {
  if (n) {
    const r = n[e] || (n[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Vt();
      const a = $s(n), l = kt(t, n, e, i);
      return a(), Bt(), l;
    });
    return s ? r.unshift(o) : r.push(o), o;
  }
}
const rn = (e) => (t, n = Je) => {
  (!Ts || e === "sp") && Lr(e, (...s) => t(...s), n);
}, Af = rn("bm"), ss = rn("m"), Of = rn(
  "bu"
), Wl = rn("u"), Hl = rn(
  "bum"
), jr = rn("um"), Rf = rn(
  "sp"
), Tf = rn("rtg"), If = rn("rtc");
function Pf(e, t = Je) {
  Lr("ec", e, t);
}
const Nf = "components", ql = /* @__PURE__ */ Symbol.for("v-ndc");
function Mf(e) {
  return Re(e) ? Df(Nf, e, !1) || e : e || ql;
}
function Df(e, t, n = !0, s = !1) {
  const r = Ze || Je;
  if (r) {
    const o = r.type;
    {
      const a = gd(
        o,
        !1
      );
      if (a && (a === t || a === Ye(t) || a === Ar(Ye(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      zi(r[e] || o[e], t) || // global registration
      zi(r.appContext[e], t)
    );
    return !i && s ? o : i;
  }
}
function zi(e, t) {
  return e && (e[t] || e[Ye(t)] || e[Ar(Ye(t))]);
}
function Zl(e, t, n, s) {
  let r;
  const o = n, i = Q(e);
  if (i || Re(e)) {
    const a = i && /* @__PURE__ */ $t(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ ft(e), c = /* @__PURE__ */ zt(e), e = Pr(e)), r = new Array(e.length);
    for (let u = 0, f = e.length; u < f; u++)
      r[u] = t(
        l ? c ? yn(mt(e[u])) : mt(e[u]) : e[u],
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
  else if (_e(e))
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
function We(e, t, n, s, r, o) {
  if (n == null && (n = {}), Ze.ce || Ze.parent && Gn(Ze.parent) && Ze.parent.ce) {
    const c = n, u = Object.keys(c).length > 0;
    return fe(), De(
      qe,
      null,
      [Y("slot", c, s)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = Xt.length;
  fe();
  let l;
  try {
    const c = i && Gl(i(n)), u = n.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = De(
      qe,
      {
        key: (u && !dt(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && s ? "_fb" : "")
      },
      c || (s ? s() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = Xt.length; u > a; u--) gi();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function Gl(e) {
  return e.some((t) => Jn(t) ? !(t.type === pt || t.type === qe && !Gl(t.children)) : !0) ? e : null;
}
const To = (e) => e ? mc(e) ? Vr(e) : To(e.parent) : null, _s = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ Ge(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => To(e.parent),
    $root: (e) => To(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => Jl(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      ci(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = St.bind(e.proxy)),
    $watch: (e) => yf.bind(e)
  })
), Jr = (e, t) => e !== Ee && !e.__isScriptSetup && be(e, t), Lf = {
  get({ _: e }, t) {
    if (t === "__v_skip")
      return !0;
    const { ctx: n, setupState: s, data: r, props: o, accessCache: i, type: a, appContext: l } = e;
    if (t[0] !== "$") {
      const d = i[t];
      if (d !== void 0)
        switch (d) {
          case 1:
            return s[t];
          case 2:
            return r[t];
          case 4:
            return n[t];
          case 3:
            return o[t];
        }
      else {
        if (Jr(s, t))
          return i[t] = 1, s[t];
        if (r !== Ee && be(r, t))
          return i[t] = 2, r[t];
        if (be(o, t))
          return i[t] = 3, o[t];
        if (n !== Ee && be(n, t))
          return i[t] = 4, n[t];
        Io && (i[t] = 0);
      }
    }
    const c = _s[t];
    let u, f;
    if (c)
      return t === "$attrs" && Ke(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (u = a.__cssModules) && (u = u[t])
    )
      return u;
    if (n !== Ee && be(n, t))
      return i[t] = 4, n[t];
    if (
      // global properties
      f = l.config.globalProperties, be(f, t)
    )
      return f[t];
  },
  set({ _: e }, t, n) {
    const { data: s, setupState: r, ctx: o } = e;
    return Jr(r, t) ? (r[t] = n, !0) : s !== Ee && be(s, t) ? (s[t] = n, !0) : be(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = n, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: n, ctx: s, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(n[a] || e !== Ee && a[0] !== "$" && be(e, a) || Jr(t, a) || be(o, a) || be(s, a) || be(_s, a) || be(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, n) {
    return n.get != null ? e._.accessCache[t] = 0 : be(n, "value") && this.set(e, t, n.value, null), Reflect.defineProperty(e, t, n);
  }
};
function Ui(e) {
  return Q(e) ? e.reduce(
    (t, n) => (t[n] = null, t),
    {}
  ) : e;
}
let Io = !0;
function jf(e) {
  const t = Jl(e), n = e.proxy, s = e.ctx;
  Io = !1, t.beforeCreate && Wi(t.beforeCreate, e, "bc");
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
    beforeMount: f,
    mounted: d,
    beforeUpdate: h,
    updated: y,
    activated: v,
    deactivated: w,
    beforeDestroy: R,
    beforeUnmount: x,
    destroyed: N,
    unmounted: O,
    render: U,
    renderTracked: ve,
    renderTriggered: F,
    errorCaptured: S,
    serverPrefetch: j,
    // public API
    expose: pe,
    inheritAttrs: Ae,
    // assets
    components: Te,
    directives: $e,
    filters: Xe
  } = t;
  if (c && $f(c, s, null), i)
    for (const X in i) {
      const de = i[X];
      te(de) && (s[X] = de.bind(n));
    }
  if (r) {
    const X = r.call(n, n);
    _e(X) && (e.data = /* @__PURE__ */ jn(X));
  }
  if (Io = !0, o)
    for (const X in o) {
      const de = o[X], at = te(de) ? de.bind(n, n) : te(de.get) ? de.get.bind(n, n) : jt, q = !te(de) && te(de.set) ? de.set.bind(n) : jt, lt = ue({
        get: at,
        set: q
      });
      Object.defineProperty(s, X, {
        enumerable: !0,
        configurable: !0,
        get: () => lt.value,
        set: (Ue) => lt.value = Ue
      });
    }
  if (a)
    for (const X in a)
      Kl(a[X], s, n, X);
  if (l) {
    const X = te(l) ? l.call(n) : l;
    Reflect.ownKeys(X).forEach((de) => {
      vs(de, X[de]);
    });
  }
  u && Wi(u, e, "c");
  function ce(X, de) {
    Q(de) ? de.forEach((at) => X(at.bind(n))) : de && X(de.bind(n));
  }
  if (ce(Af, f), ce(ss, d), ce(Of, h), ce(Wl, y), ce(Sf, v), ce(Ef, w), ce(Pf, S), ce(If, ve), ce(Tf, F), ce(Hl, x), ce(jr, O), ce(Rf, j), Q(pe))
    if (pe.length) {
      const X = e.exposed || (e.exposed = {});
      pe.forEach((de) => {
        Object.defineProperty(X, de, {
          get: () => n[de],
          set: (at) => n[de] = at,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  U && e.render === jt && (e.render = U), Ae != null && (e.inheritAttrs = Ae), Te && (e.components = Te), $e && (e.directives = $e), j && zl(e);
}
function $f(e, t, n = jt) {
  Q(e) && (e = Po(e));
  for (const s in e) {
    const r = e[s];
    let o;
    _e(r) ? "default" in r ? o = ot(
      r.from || s,
      r.default,
      !0
    ) : o = ot(r.from || s) : o = ot(r), /* @__PURE__ */ Me(o) ? Object.defineProperty(t, s, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[s] = o;
  }
}
function Wi(e, t, n) {
  kt(
    Q(e) ? e.map((s) => s.bind(t.proxy)) : e.bind(t.proxy),
    t,
    n
  );
}
function Kl(e, t, n, s) {
  let r = s.includes(".") ? Fl(n, s) : () => n[s];
  if (Re(e)) {
    const o = t[e];
    te(o) && je(r, o);
  } else if (te(e))
    je(r, e.bind(n));
  else if (_e(e))
    if (Q(e))
      e.forEach((o) => Kl(o, t, n, s));
    else {
      const o = te(e.handler) ? e.handler.bind(n) : t[e.handler];
      te(o) && je(r, o, e);
    }
}
function Jl(e) {
  const t = e.type, { mixins: n, extends: s } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !n && !s ? l = t : (l = {}, r.length && r.forEach(
    (c) => fr(l, c, i, !0)
  ), fr(l, t, i)), _e(t) && o.set(t, l), l;
}
function fr(e, t, n, s = !1) {
  const { mixins: r, extends: o } = t;
  o && fr(e, o, n, !0), r && r.forEach(
    (i) => fr(e, i, n, !0)
  );
  for (const i in t)
    if (!(s && i === "expose")) {
      const a = Ff[i] || n && n[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const Ff = {
  data: Hi,
  props: qi,
  emits: qi,
  // objects
  methods: ds,
  computed: ds,
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
  components: ds,
  directives: ds,
  // watch
  watch: Bf,
  // provide / inject
  provide: Hi,
  inject: Vf
};
function Hi(e, t) {
  return t ? e ? function() {
    return Ge(
      te(e) ? e.call(this, this) : e,
      te(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function Vf(e, t) {
  return ds(Po(e), Po(t));
}
function Po(e) {
  if (Q(e)) {
    const t = {};
    for (let n = 0; n < e.length; n++)
      t[e[n]] = e[n];
    return t;
  }
  return e;
}
function tt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function ds(e, t) {
  return e ? Ge(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function qi(e, t) {
  return e ? Q(e) && Q(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : Ge(
    /* @__PURE__ */ Object.create(null),
    Ui(e),
    Ui(t ?? {})
  ) : t;
}
function Bf(e, t) {
  if (!e) return t;
  if (!t) return e;
  const n = Ge(/* @__PURE__ */ Object.create(null), e);
  for (const s in t)
    n[s] = tt(e[s], t[s]);
  return n;
}
function Yl() {
  return {
    app: null,
    config: {
      isNativeTag: il,
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
function Uf(e, t) {
  return function(s, r = null) {
    te(s) || (s = Ge({}, s)), r != null && !_e(r) && (r = null);
    const o = Yl(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: zf++,
      _component: s,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: vd,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...f) {
        return i.has(u) || (u && te(u.install) ? (i.add(u), u.install(c, ...f)) : te(u) && (i.add(u), u(c, ...f))), c;
      },
      mixin(u) {
        return o.mixins.includes(u) || o.mixins.push(u), c;
      },
      component(u, f) {
        return f ? (o.components[u] = f, c) : o.components[u];
      },
      directive(u, f) {
        return f ? (o.directives[u] = f, c) : o.directives[u];
      },
      mount(u, f, d) {
        if (!l) {
          const h = c._ceVNode || Y(s, r);
          return h.appContext = o, d === !0 ? d = "svg" : d === !1 && (d = void 0), e(h, u, d), l = !0, c._container = u, u.__vue_app__ = c, Vr(h.component);
        }
      },
      onUnmount(u) {
        a.push(u);
      },
      unmount() {
        l && (kt(
          a,
          c._instance,
          16
        ), e(null, c._container), delete c._container.__vue_app__);
      },
      provide(u, f) {
        return o.provides[u] = f, c;
      },
      runWithContext(u) {
        const f = Nn;
        Nn = c;
        try {
          return u();
        } finally {
          Nn = f;
        }
      }
    };
    return c;
  };
}
let Nn = null;
const Wf = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${Ye(t)}Modifiers`] || e[`${Ln(t)}Modifiers`];
function Hf(e, t, ...n) {
  if (e.isUnmounted) return;
  const s = e.vnode.props || Ee;
  let r = n;
  const o = t.startsWith("update:"), i = o && Wf(s, t.slice(7));
  i && (i.trim && (r = n.map((u) => Re(u) ? u.trim() : u)), i.number && (r = r.map(Xo)));
  let a, l = s[a = tr(t)] || // also try camelCase event handler (#2249)
  s[a = tr(Ye(t))];
  !l && o && (l = s[a = tr(Ln(t))]), l && kt(
    l,
    e,
    6,
    r
  );
  const c = s[a + "Once"];
  if (c) {
    if (!e.emitted)
      e.emitted = {};
    else if (e.emitted[a])
      return;
    e.emitted[a] = !0, kt(
      c,
      e,
      6,
      r
    );
  }
}
const qf = /* @__PURE__ */ new WeakMap();
function Ql(e, t, n = !1) {
  const s = n ? qf : t.emitsCache, r = s.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!te(e)) {
    const l = (c) => {
      const u = Ql(c, t, !0);
      u && (a = !0, Ge(i, u));
    };
    !n && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (_e(e) && s.set(e, null), null) : (Q(o) ? o.forEach((l) => i[l] = null) : Ge(i, o), _e(e) && s.set(e, i), i);
}
function $r(e, t) {
  return !e || !kr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), be(e, t[0].toLowerCase() + t.slice(1)) || be(e, Ln(t)) || be(e, t));
}
function Zi(e) {
  const {
    type: t,
    vnode: n,
    proxy: s,
    withProxy: r,
    propsOptions: [o],
    slots: i,
    attrs: a,
    emit: l,
    render: c,
    renderCache: u,
    props: f,
    data: d,
    setupState: h,
    ctx: y,
    inheritAttrs: v
  } = e, w = lr(e);
  let R, x;
  try {
    if (n.shapeFlag & 4) {
      const O = r || s, U = O;
      R = Mt(
        c.call(
          U,
          O,
          u,
          f,
          h,
          d,
          y
        )
      ), x = a;
    } else {
      const O = t;
      R = Mt(
        O.length > 1 ? O(
          f,
          { attrs: a, slots: i, emit: l }
        ) : O(
          f,
          null
        )
      ), x = t.props ? a : Zf(a);
    }
  } catch (O) {
    Xt.length = 0, Mr(O, e, 1), R = Y(pt);
  }
  let N = R;
  if (x && v !== !1) {
    const O = Object.keys(x), { shapeFlag: U } = N;
    O.length && U & 7 && (o && O.some(Sr) && (x = Gf(
      x,
      o
    )), N = Mn(N, x, !1, !0));
  }
  if (n.dirs && (N = Mn(N, null, !1, !0), N.dirs = N.dirs ? N.dirs.concat(n.dirs) : n.dirs), n.transition) {
    const O = Dr(N.type) && Bl(N) || N;
    cr(O, n.transition);
  }
  return R = N, lr(w), R;
}
function Xl(e, t = !0) {
  let n;
  for (let s = 0; s < e.length; s++) {
    const r = e[s];
    if (Jn(r)) {
      if (r.type !== pt || r.children === "v-if") {
        if (n)
          return;
        n = r;
      }
    } else
      return;
  }
  return n;
}
const Zf = (e) => {
  let t;
  for (const n in e)
    (n === "class" || n === "style" || kr(n)) && ((t || (t = {}))[n] = e[n]);
  return t;
}, Gf = (e, t) => {
  const n = {};
  for (const s in e)
    (!Sr(s) || !(s.slice(9) in t)) && (n[s] = e[s]);
  return n;
};
function Kf(e, t, n) {
  const { props: s, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (n && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return s ? Gi(s, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let f = 0; f < u.length; f++) {
        const d = u[f];
        if (ec(i, s, d) && !$r(c, d))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : s === i ? !1 : s ? i ? Gi(s, i, c) : !0 : !!i;
  return !1;
}
function Gi(e, t, n) {
  const s = Object.keys(t);
  if (s.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < s.length; r++) {
    const o = s[r];
    if (!be(e, o) || ec(t, e, o) && !$r(n, o))
      return !0;
  }
  return !1;
}
function ec(e, t, n) {
  const s = e[n], r = t[n];
  return n === "style" && _e(s) && _e(r) ? !Rr(s, r) : s !== r;
}
function Jf({ vnode: e, parent: t, suspense: n }, s) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = s, e = r), r === e)
      (e = t.vnode).el = s, t = t.parent;
    else
      break;
  }
  n && n.activeBranch === e && (n.vnode.el = s);
}
const tc = {}, nc = () => Object.create(tc), sc = (e) => Object.getPrototypeOf(e) === tc;
function Yf(e, t, n, s = !1) {
  const r = {}, o = nc();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), rc(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  n ? e.props = s ? r : /* @__PURE__ */ Tl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function Qf(e, t, n, s) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ ge(r), [l] = e.propsOptions;
  let c = !1;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (s || i > 0) && !(i & 16)
  ) {
    if (i & 8) {
      const u = e.vnode.dynamicProps;
      for (let f = 0; f < u.length; f++) {
        let d = u[f];
        if ($r(e.emitsOptions, d))
          continue;
        const h = t[d];
        if (l)
          if (be(o, d))
            h !== o[d] && (o[d] = h, c = !0);
          else {
            const y = Ye(d);
            r[y] = No(
              l,
              a,
              y,
              h,
              e,
              !1
            );
          }
        else
          h !== o[d] && (o[d] = h, c = !0);
      }
    }
  } else {
    rc(e, t, r, o) && (c = !0);
    let u;
    for (const f in a)
      (!t || // for camelCase
      !be(t, f) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = Ln(f)) === f || !be(t, u))) && (l ? n && // for camelCase
      (n[f] !== void 0 || // for kebab-case
      n[u] !== void 0) && (r[f] = No(
        l,
        a,
        f,
        void 0,
        e,
        !0
      )) : delete r[f]);
    if (o !== a)
      for (const f in o)
        (!t || !be(t, f)) && (delete o[f], c = !0);
  }
  c && Yt(e.attrs, "set", "");
}
function rc(e, t, n, s) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (ms(l))
        continue;
      const c = t[l];
      let u;
      r && be(r, u = Ye(l)) ? !o || !o.includes(u) ? n[u] = c : (a || (a = {}))[u] = c : $r(e.emitsOptions, l) || (!(l in s) || c !== s[l]) && (s[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ ge(n), c = a || Ee;
    for (let u = 0; u < o.length; u++) {
      const f = o[u];
      n[f] = No(
        r,
        l,
        f,
        c[f],
        e,
        !be(c, f)
      );
    }
  }
  return i;
}
function No(e, t, n, s, r, o) {
  const i = e[n];
  if (i != null) {
    const a = be(i, "default");
    if (a && s === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && te(l)) {
        const { propsDefaults: c } = r;
        if (n in c)
          s = c[n];
        else {
          const u = $s(r);
          s = c[n] = l.call(
            null,
            t
          ), u();
        }
      } else
        s = l;
      r.ce && r.ce._setProp(n, s);
    }
    i[
      0
      /* shouldCast */
    ] && (o && !a ? s = !1 : i[
      1
      /* shouldCastTrue */
    ] && (s === "" || s === Ln(n)) && (s = !0));
  }
  return s;
}
const Xf = /* @__PURE__ */ new WeakMap();
function oc(e, t, n = !1) {
  const s = n ? Xf : t.propsCache, r = s.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!te(e)) {
    const u = (f) => {
      l = !0;
      const [d, h] = oc(f, t, !0);
      Ge(i, d), h && a.push(...h);
    };
    !n && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return _e(e) && s.set(e, Rn), Rn;
  if (Q(o))
    for (let u = 0; u < o.length; u++) {
      const f = Ye(o[u]);
      Ki(f) && (i[f] = Ee);
    }
  else if (o)
    for (const u in o) {
      const f = Ye(u);
      if (Ki(f)) {
        const d = o[u], h = i[f] = Q(d) || te(d) ? { type: d } : Ge({}, d), y = h.type;
        let v = !1, w = !0;
        if (Q(y))
          for (let R = 0; R < y.length; ++R) {
            const x = y[R], N = te(x) && x.name;
            if (N === "Boolean") {
              v = !0;
              break;
            } else N === "String" && (w = !1);
          }
        else
          v = te(y) && y.name === "Boolean";
        h[
          0
          /* shouldCast */
        ] = v, h[
          1
          /* shouldCastTrue */
        ] = w, (v || be(h, "default")) && a.push(f);
      }
    }
  const c = [i, a];
  return _e(e) && s.set(e, c), c;
}
function Ki(e) {
  return e[0] !== "$" && !ms(e);
}
const pi = (e) => e === "_" || e === "_ctx" || e === "$stable", hi = (e) => Q(e) ? e.map(Mt) : [Mt(e)], ed = (e, t, n) => {
  if (t._n)
    return t;
  const s = re((...r) => hi(t(...r)), n);
  return s._c = !1, s;
}, ic = (e, t, n) => {
  const s = e._ctx;
  for (const r in e) {
    if (pi(r)) continue;
    const o = e[r];
    if (te(o))
      t[r] = ed(r, o, s);
    else if (o != null) {
      const i = hi(o);
      t[r] = () => i;
    }
  }
}, ac = (e, t) => {
  const n = hi(t);
  e.slots.default = () => n;
}, lc = (e, t, n) => {
  for (const s in t)
    (n || !pi(s)) && (e[s] = t[s]);
}, td = (e, t, n) => {
  const s = e.slots = nc();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (lc(s, t, n), n && ul(s, "_", r, !0)) : ic(t, s);
  } else t && ac(e, t);
}, nd = (e, t, n) => {
  const { vnode: s, slots: r } = e;
  let o = !0, i = Ee;
  if (s.shapeFlag & 32) {
    const a = t._;
    a ? n && a === 1 ? o = !1 : lc(r, t, n) : (o = !t.$stable, ic(t, r)), i = t;
  } else t && (ac(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !pi(a) && i[a] == null && delete r[a];
}, nt = ad;
function sd(e) {
  return rd(e);
}
function rd(e, t) {
  const n = Or();
  n.__VUE__ = !0;
  const {
    insert: s,
    remove: r,
    patchProp: o,
    createElement: i,
    createText: a,
    createComment: l,
    setText: c,
    setElementText: u,
    parentNode: f,
    nextSibling: d,
    setScopeId: h = jt,
    insertStaticContent: y
  } = e, v = (p, m, g, b = null, _ = null, E = null, T = void 0, D = null, M = !!m.dynamicChildren) => {
    if (p === m)
      return;
    p && !as(p, m) && (b = k(p), Ue(p, _, E, !0), p = null), m.patchFlag === -2 && (M = !1, m.dynamicChildren = null), m.dynamicChildren && p && p.dynamicChildren && p.dynamicChildren.hasOnce && (m.dynamicChildren === Rn && (m.dynamicChildren = []), m.dynamicChildren.hasOnce = !0);
    const { type: A, ref: G, shapeFlag: L } = m;
    switch (A) {
      case Fr:
        w(p, m, g, b);
        break;
      case pt:
        R(p, m, g, b);
        break;
      case Qr:
        p == null && x(m, g, b, T);
        break;
      case qe:
        Te(
          p,
          m,
          g,
          b,
          _,
          E,
          T,
          D,
          M
        );
        break;
      default:
        L & 1 ? U(
          p,
          m,
          g,
          b,
          _,
          E,
          T,
          D,
          M
        ) : L & 6 ? $e(
          p,
          m,
          g,
          b,
          _,
          E,
          T,
          D,
          M
        ) : (L & 64 || L & 128) && A.process(
          p,
          m,
          g,
          b,
          _,
          E,
          T,
          D,
          M,
          I
        );
    }
    G != null && _ ? bs(G, p && p.ref, E, m || p, !m) : G == null && p && p.ref != null && bs(p.ref, null, E, p, !0);
  }, w = (p, m, g, b) => {
    if (p == null)
      s(
        m.el = a(m.children),
        g,
        b
      );
    else {
      const _ = m.el = p.el;
      m.children !== p.children && c(_, m.children);
    }
  }, R = (p, m, g, b) => {
    p == null ? s(
      m.el = l(m.children || ""),
      g,
      b
    ) : m.el = p.el;
  }, x = (p, m, g, b) => {
    [p.el, p.anchor] = y(
      p.children,
      m,
      g,
      b,
      p.el,
      p.anchor
    );
  }, N = ({ el: p, anchor: m }, g, b) => {
    let _;
    for (; p && p !== m; )
      _ = d(p), s(p, g, b), p = _;
    s(m, g, b);
  }, O = ({ el: p, anchor: m }) => {
    let g;
    for (; p && p !== m; )
      g = d(p), r(p), p = g;
    r(m);
  }, U = (p, m, g, b, _, E, T, D, M) => {
    if (m.type === "svg" ? T = "svg" : m.type === "math" && (T = "mathml"), p == null)
      ve(
        m,
        g,
        b,
        _,
        E,
        T,
        D,
        M
      );
    else {
      const A = p.el && p.el._isVueCE ? p.el : null;
      try {
        A && A._beginPatch(), j(
          p,
          m,
          _,
          E,
          T,
          D,
          M
        );
      } finally {
        A && A._endPatch();
      }
    }
  }, ve = (p, m, g, b, _, E, T, D) => {
    let M, A;
    const { props: G, shapeFlag: L, transition: K, dirs: ee } = p;
    if (M = p.el = i(
      p.type,
      E,
      G && G.is,
      G
    ), L & 8 ? u(M, p.children) : L & 16 && S(
      p.children,
      M,
      null,
      b,
      _,
      Yr(p, E),
      T,
      D
    ), ee && kn(p, null, b, "created"), F(M, p, p.scopeId, T, b), G) {
      for (const Se in G)
        Se !== "value" && !ms(Se) && o(M, Se, null, G[Se], E, b);
      "value" in G && o(M, "value", null, G.value, E), (A = G.onVnodeBeforeMount) && Tt(A, b, p);
    }
    ee && kn(p, null, b, "beforeMount");
    const he = od(_, K);
    he && K.beforeEnter(M), s(M, m, g), ((A = G && G.onVnodeMounted) || he || ee) && nt(() => {
      try {
        A && Tt(A, b, p), he && K.enter(M), ee && kn(p, null, b, "mounted");
      } finally {
      }
    }, _);
  }, F = (p, m, g, b, _) => {
    if (g && h(p, g), b)
      for (let E = 0; E < b.length; E++)
        h(p, b[E]);
    if (_) {
      let E = _.subTree;
      if (m === E || uc(E.type) && (E.ssContent === m || E.ssFallback === m)) {
        const T = _.vnode;
        F(
          p,
          T,
          T.scopeId,
          T.slotScopeIds,
          _.parent
        );
      }
    }
  }, S = (p, m, g, b, _, E, T, D, M = 0) => {
    for (let A = M; A < p.length; A++) {
      const G = p[A] = D ? Jt(p[A]) : Mt(p[A]);
      v(
        null,
        G,
        m,
        g,
        b,
        _,
        E,
        T,
        D
      );
    }
  }, j = (p, m, g, b, _, E, T) => {
    const D = m.el = p.el;
    let { patchFlag: M, dynamicChildren: A, dirs: G } = m;
    M |= p.patchFlag & 16;
    const L = p.props || Ee, K = m.props || Ee;
    let ee;
    if (g && Sn(g, !1), (ee = K.onVnodeBeforeUpdate) && Tt(ee, g, m, p), G && kn(m, p, g, "beforeUpdate"), g && Sn(g, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    A && (!p.dynamicChildren || p.dynamicChildren.length !== A.length) && (M = 0, T = !1, A = null), (L.innerHTML && K.innerHTML == null || L.textContent && K.textContent == null) && u(D, ""), A ? pe(
      p.dynamicChildren,
      A,
      D,
      g,
      b,
      Yr(m, _),
      E
    ) : T || de(
      p,
      m,
      D,
      null,
      g,
      b,
      Yr(m, _),
      E,
      !1
    ), M > 0) {
      if (M & 16)
        Ae(D, L, K, g, _);
      else if (M & 2 && L.class !== K.class && o(D, "class", null, K.class, _), M & 4 && o(D, "style", L.style, K.style, _), M & 8) {
        const he = m.dynamicProps;
        for (let Se = 0; Se < he.length; Se++) {
          const we = he[Se], Le = L[we], He = K[we];
          (He !== Le || we === "value") && o(D, we, Le, He, _, g);
        }
      }
      M & 1 && p.children !== m.children && u(D, m.children);
    } else !T && A == null && Ae(D, L, K, g, _);
    ((ee = K.onVnodeUpdated) || G) && nt(() => {
      ee && Tt(ee, g, m, p), G && kn(m, p, g, "updated");
    }, b);
  }, pe = (p, m, g, b, _, E, T) => {
    for (let D = 0; D < m.length; D++) {
      const M = p[D], A = m[D], G = M.el || Mo(M), L = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        G && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (M.type === qe || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !as(M, A) || // - In the case of a component, it could contain anything.
        M.shapeFlag & 198) ? f(G) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          g
        )
      );
      v(
        M,
        A,
        L,
        null,
        b,
        _,
        E,
        T,
        !0
      );
    }
  }, Ae = (p, m, g, b, _) => {
    if (m !== g) {
      if (m !== Ee)
        for (const E in m)
          !ms(E) && !(E in g) && o(
            p,
            E,
            m[E],
            null,
            _,
            b
          );
      for (const E in g) {
        if (ms(E)) continue;
        const T = g[E], D = m[E];
        T !== D && E !== "value" && o(p, E, D, T, _, b);
      }
      "value" in g && o(p, "value", m.value, g.value, _);
    }
  }, Te = (p, m, g, b, _, E, T, D, M) => {
    const A = m.el = p ? p.el : a(""), G = m.anchor = p ? p.anchor : a("");
    let { patchFlag: L, dynamicChildren: K, slotScopeIds: ee } = m;
    ee && (D = D ? D.concat(ee) : ee), p == null ? (s(A, g, b), s(G, g, b), S(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      m.children || [],
      g,
      G,
      _,
      E,
      T,
      D,
      M
    )) : L > 0 && L & 64 && K && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    p.dynamicChildren && p.dynamicChildren.length === K.length ? (pe(
      p.dynamicChildren,
      K,
      g,
      _,
      E,
      T,
      D
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (m.key != null || _ && m === _.subTree) && mi(
      p,
      m,
      !0
      /* shallow */
    )) : de(
      p,
      m,
      g,
      G,
      _,
      E,
      T,
      D,
      M
    );
  }, $e = (p, m, g, b, _, E, T, D, M) => {
    m.slotScopeIds = D, p == null ? m.shapeFlag & 512 ? _.ctx.activate(
      m,
      g,
      b,
      T,
      M
    ) : Xe(
      m,
      g,
      b,
      _,
      E,
      T,
      M
    ) : et(p, m, M);
  }, Xe = (p, m, g, b, _, E, T) => {
    const D = p.component = fd(
      p,
      b,
      _
    );
    if (di(p) && (D.ctx.renderer = I), dd(D, !1, T), D.asyncDep) {
      if (_ && _.registerDep(
        D,
        ce,
        T,
        E
      ), !p.el) {
        const M = D.subTree = Y(pt);
        R(null, M, m, g), p.placeholder = M.el;
      }
    } else
      ce(
        D,
        p,
        m,
        g,
        _,
        E,
        T
      );
  }, et = (p, m, g) => {
    const b = m.component = p.component;
    if (Kf(p, m, g))
      if (b.asyncDep && !b.asyncResolved) {
        m.el = p.el, m.placeholder = p.placeholder, X(b, m, g);
        return;
      } else
        b.next = m, b.update();
    else
      m.el = p.el, m.placeholder = p.placeholder, b.vnode = m;
  }, ce = (p, m, g, b, _, E, T) => {
    const D = () => {
      if (p.isMounted) {
        let { next: L, bu: K, u: ee, parent: he, vnode: Se } = p;
        {
          const Ot = cc(p);
          if (Ot) {
            L && (L.el = Se.el, X(p, L, T)), Ot.asyncDep.then(() => {
              nt(() => {
                p.isUnmounted || A();
              }, _);
            });
            return;
          }
        }
        let we = L, Le;
        Sn(p, !1), L ? (L.el = Se.el, X(p, L, T)) : L = Se, K && nr(K), (Le = L.props && L.props.onVnodeBeforeUpdate) && Tt(Le, he, L, Se), Sn(p, !0);
        const He = Zi(p), At = p.subTree;
        p.subTree = He, v(
          At,
          He,
          // parent may have changed if it's in a teleport
          f(At.el),
          // anchor may have changed if it's in a fragment
          k(At),
          p,
          _,
          E
        ), L.el = He.el, we === null && Jf(p, He.el), ee && nt(ee, _), (Le = L.props && L.props.onVnodeUpdated) && nt(
          () => Tt(Le, he, L, Se),
          _
        );
      } else {
        let L;
        const { el: K, props: ee } = m, { bm: he, m: Se, parent: we, root: Le, type: He } = p, At = Gn(m);
        Sn(p, !1), he && nr(he), !At && (L = ee && ee.onVnodeBeforeMount) && Tt(L, we, m), Sn(p, !0);
        {
          Le.ce && Le.ce._hasShadowRoot() && Le.ce._injectChildStyle(
            He,
            p.parent ? p.parent.type : void 0
          );
          const Ot = p.subTree = Zi(p);
          v(
            null,
            Ot,
            g,
            b,
            p,
            _,
            E
          ), m.el = Ot.el;
        }
        if (Se && nt(Se, _), !At && (L = ee && ee.onVnodeMounted)) {
          const Ot = m;
          nt(
            () => Tt(L, we, Ot),
            _
          );
        }
        (m.shapeFlag & 256 || we && Gn(we.vnode) && we.vnode.shapeFlag & 256) && p.a && nt(p.a, _), p.isMounted = !0, m = g = b = null;
      }
    };
    p.scope.on();
    const M = p.effect = new ml(D);
    p.scope.off();
    const A = p.update = M.run.bind(M), G = p.job = M.runIfDirty.bind(M);
    G.i = p, G.id = p.uid, M.scheduler = () => ci(G), Sn(p, !0), A();
  }, X = (p, m, g) => {
    m.component = p;
    const b = p.vnode.props;
    p.vnode = m, p.next = null, Qf(p, m.props, b, g), nd(p, m.children, g), Vt(), Dl(p), Bt();
  }, de = (p, m, g, b, _, E, T, D, M = !1) => {
    const A = p && p.children, G = p ? p.shapeFlag : 0, L = m.children, { patchFlag: K, shapeFlag: ee } = m;
    if (K > 0) {
      if (K & 128) {
        q(
          A,
          L,
          g,
          b,
          _,
          E,
          T,
          D,
          M
        );
        return;
      } else if (K & 256) {
        at(
          A,
          L,
          g,
          b,
          _,
          E,
          T,
          D,
          M
        );
        return;
      }
    }
    ee & 8 ? (G & 16 && xe(A, _, E), L !== A && u(g, L)) : G & 16 ? ee & 16 ? q(
      A,
      L,
      g,
      b,
      _,
      E,
      T,
      D,
      M
    ) : xe(A, _, E, !0) : (G & 8 && u(g, ""), ee & 16 && S(
      L,
      g,
      b,
      _,
      E,
      T,
      D,
      M
    ));
  }, at = (p, m, g, b, _, E, T, D, M) => {
    p = p || Rn, m = m || Rn;
    const A = p.length, G = m.length, L = Math.min(A, G);
    let K;
    for (K = 0; K < L; K++) {
      const ee = m[K] = M ? Jt(m[K]) : Mt(m[K]);
      v(
        p[K],
        ee,
        g,
        null,
        _,
        E,
        T,
        D,
        M
      );
    }
    A > G ? xe(
      p,
      _,
      E,
      !0,
      !1,
      L
    ) : S(
      m,
      g,
      b,
      _,
      E,
      T,
      D,
      M,
      L
    );
  }, q = (p, m, g, b, _, E, T, D, M) => {
    let A = 0;
    const G = m.length;
    let L = p.length - 1, K = G - 1;
    for (; A <= L && A <= K; ) {
      const ee = p[A], he = m[A] = M ? Jt(m[A]) : Mt(m[A]);
      if (as(ee, he))
        v(
          ee,
          he,
          g,
          null,
          _,
          E,
          T,
          D,
          M
        );
      else
        break;
      A++;
    }
    for (; A <= L && A <= K; ) {
      const ee = p[L], he = m[K] = M ? Jt(m[K]) : Mt(m[K]);
      if (as(ee, he))
        v(
          ee,
          he,
          g,
          null,
          _,
          E,
          T,
          D,
          M
        );
      else
        break;
      L--, K--;
    }
    if (A > L) {
      if (A <= K) {
        const ee = K + 1, he = ee < G ? m[ee].el : b;
        for (; A <= K; )
          v(
            null,
            m[A] = M ? Jt(m[A]) : Mt(m[A]),
            g,
            he,
            _,
            E,
            T,
            D,
            M
          ), A++;
      }
    } else if (A > K)
      for (; A <= L; )
        Ue(p[A], _, E, !0), A++;
    else {
      const ee = A, he = A, Se = /* @__PURE__ */ new Map();
      for (A = he; A <= K; A++) {
        const ct = m[A] = M ? Jt(m[A]) : Mt(m[A]);
        ct.key != null && Se.set(ct.key, A);
      }
      let we, Le = 0;
      const He = K - he + 1;
      let At = !1, Ot = 0;
      const os = new Array(He);
      for (A = 0; A < He; A++) os[A] = 0;
      for (A = ee; A <= L; A++) {
        const ct = p[A];
        if (Le >= He) {
          Ue(ct, _, E, !0);
          continue;
        }
        let Rt;
        if (ct.key != null)
          Rt = Se.get(ct.key);
        else
          for (we = he; we <= K; we++)
            if (os[we - he] === 0 && as(ct, m[we])) {
              Rt = we;
              break;
            }
        Rt === void 0 ? Ue(ct, _, E, !0) : (os[Rt - he] = A + 1, Rt >= Ot ? Ot = Rt : At = !0, v(
          ct,
          m[Rt],
          g,
          null,
          _,
          E,
          T,
          D,
          M
        ), Le++);
      }
      const Oi = At ? id(os) : Rn;
      for (we = Oi.length - 1, A = He - 1; A >= 0; A--) {
        const ct = he + A, Rt = m[ct], Ri = m[ct + 1], Ti = ct + 1 < G ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          Ri.el || Mo(Ri)
        ) : b;
        os[A] === 0 ? v(
          null,
          Rt,
          g,
          Ti,
          _,
          E,
          T,
          D,
          M
        ) : At && (we < 0 || A !== Oi[we] ? lt(Rt, g, Ti, 2) : we--);
      }
    }
  }, lt = (p, m, g, b, _ = null) => {
    const { el: E, type: T, transition: D, children: M, shapeFlag: A } = p;
    if (A & 6) {
      lt(p.component.subTree, m, g, b);
      return;
    }
    if (A & 128) {
      p.suspense.move(m, g, b);
      return;
    }
    if (A & 64) {
      T.move(p, m, g, I);
      return;
    }
    if (T === qe) {
      s(E, m, g);
      for (let L = 0; L < M.length; L++)
        lt(M[L], m, g, b);
      s(p.anchor, m, g);
      return;
    }
    if (T === Qr) {
      N(p, m, g);
      return;
    }
    if (b !== 2 && A & 1 && D)
      if (b === 0)
        D.persisted && !E[Kr] ? s(E, m, g) : (D.beforeEnter(E), s(E, m, g), nt(() => D.enter(E), _));
      else {
        const { leave: L, delayLeave: K, afterLeave: ee } = D, he = () => {
          p.ctx.isUnmounted ? r(E) : s(E, m, g);
        }, Se = () => {
          const we = E._isLeaving || !!E[Kr];
          E._isLeaving && E[Kr](
            !0
            /* cancelled */
          ), D.persisted && !we ? he() : L(E, () => {
            he(), ee && ee();
          });
        };
        K ? K(E, he, Se) : Se();
      }
    else
      s(E, m, g);
  }, Ue = (p, m, g, b = !1, _ = !1) => {
    const {
      type: E,
      props: T,
      ref: D,
      children: M,
      dynamicChildren: A,
      shapeFlag: G,
      patchFlag: L,
      dirs: K,
      cacheIndex: ee,
      memo: he
    } = p;
    if ((L === -2 || A && A.hasOnce) && (_ = !1), D != null && (Vt(), bs(D, null, g, p, !0), Bt()), ee != null && (!p.ctx || p.ctx === m) && (m.renderCache[ee] = void 0), G & 256) {
      m.ctx.deactivate(p);
      return;
    }
    const Se = G & 1 && K, we = !Gn(p);
    let Le;
    if (we && (Le = T && T.onVnodeBeforeUnmount) && Tt(Le, m, p), G & 6)
      Ie(p.component, g, b);
    else {
      if (G & 128) {
        p.suspense.unmount(g, b);
        return;
      }
      Se && kn(p, null, m, "beforeUnmount"), G & 64 ? p.type.remove(
        p,
        m,
        g,
        I,
        b
      ) : A && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !A.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (E !== qe || L > 0 && L & 64) ? xe(
        A,
        m,
        g,
        !1,
        !0
      ) : (E === qe && L & 384 || !_ && G & 16) && xe(M, m, g), b && Wt(p);
    }
    const He = he != null && ee == null;
    (we && (Le = T && T.onVnodeUnmounted) || Se || He) && nt(() => {
      Le && Tt(Le, m, p), Se && kn(p, null, m, "unmounted"), He && (p.el = null);
    }, g);
  }, Wt = (p) => {
    const { type: m, el: g, anchor: b, transition: _ } = p, E = m === qe;
    if (E && !_) {
      _t(g, b);
      return;
    }
    if (m === Qr) {
      O(p), _ && !_.persisted && _.afterLeave && _.afterLeave();
      return;
    }
    const T = E ? Ro(p) : p, D = () => {
      E ? f(g) && _t(g, b) : r(g), _ && !_.persisted && _.afterLeave && _.afterLeave();
    };
    if (T && T.shapeFlag & 1 && _ && !_.persisted) {
      const { leave: M, delayLeave: A } = _, G = T.el, L = () => M(G, D);
      A ? A(G, D, L) : L();
    } else
      D();
  }, _t = (p, m) => {
    let g;
    for (; p !== m; )
      g = d(p), r(p), p = g;
    r(m);
  }, Ie = (p, m, g) => {
    const { bum: b, scope: _, job: E, subTree: T, um: D, m: M, a: A } = p;
    Ji(M), Ji(A), b && nr(b), _.stop(), E ? (E.flags |= 8, Ue(T, p, m, g)) : p.vnode.el && T && (T.transition = p.vnode.transition, Ue(T, p, m, g)), D && nt(D, m), nt(() => {
      p.isUnmounted = !0;
    }, m);
  }, xe = (p, m, g, b = !1, _ = !1, E = 0) => {
    for (let T = E; T < p.length; T++)
      Ue(p[T], m, g, b, _);
  }, k = (p) => {
    if (p.shapeFlag & 6)
      return k(p.component.subTree);
    if (p.shapeFlag & 128)
      return p.suspense.next();
    const m = d(p.anchor || p.el), g = m && m[Vl];
    return g ? d(g) : m;
  }, B = (p, m, g) => {
    const b = p && m._vnode ? void 0 : p && p.component ? p.component.uid : ud();
    hf(() => {
      p == null ? m._vnode && Ue(m._vnode, null, null, !0) : v(
        m._vnode || null,
        p,
        m,
        null,
        null,
        null,
        g
      ), m._vnode = p;
    }, b);
  }, I = {
    p: v,
    um: Ue,
    m: lt,
    r: Wt,
    mt: Xe,
    mc: S,
    pc: de,
    pbc: pe,
    n: k,
    o: e
  };
  return {
    render: B,
    hydrate: void 0,
    createApp: Uf(B)
  };
}
function Yr({ type: e, props: t }, n) {
  return n === "svg" && e === "foreignObject" || n === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : n;
}
function Sn({ effect: e, job: t }, n) {
  n ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function od(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function mi(e, t, n = !1) {
  const s = e.children, r = t.children;
  if (Q(s) && Q(r))
    for (let o = 0; o < s.length; o++) {
      const i = s[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = Jt(r[o]), a.el = i.el), !n && a.patchFlag !== -2 && mi(i, a)), a.type === Fr && (a.patchFlag === -1 && (a = r[o] = Jt(a)), a.el = i.el), a.type === pt && !a.el && (a.el = i.el);
    }
}
function id(e) {
  const t = e.slice(), n = [0];
  let s, r, o, i, a;
  const l = e.length;
  for (s = 0; s < l; s++) {
    const c = e[s];
    if (c !== 0) {
      if (r = n[n.length - 1], e[r] < c) {
        t[s] = r, n.push(s);
        continue;
      }
      for (o = 0, i = n.length - 1; o < i; )
        a = o + i >> 1, e[n[a]] < c ? o = a + 1 : i = a;
      c < e[n[o]] && (o > 0 && (t[s] = n[o - 1]), n[o] = s);
    }
  }
  for (o = n.length, i = n[o - 1]; o-- > 0; )
    n[o] = i, i = t[i];
  return n;
}
function cc(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : cc(t);
}
function Ji(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function Mo(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? Mo(t.subTree) : null;
}
const uc = (e) => e.__isSuspense;
function ad(e, t) {
  t && t.pendingBranch ? Q(e) ? t.effects.push(...e) : t.effects.push(e) : pf(e);
}
const qe = /* @__PURE__ */ Symbol.for("v-fgt"), Fr = /* @__PURE__ */ Symbol.for("v-txt"), pt = /* @__PURE__ */ Symbol.for("v-cmt"), Qr = /* @__PURE__ */ Symbol.for("v-stc"), Xt = [];
let ut = null;
function fe(e = !1) {
  Xt.push(ut = e ? null : []);
}
function gi() {
  Xt.pop(), ut = Xt[Xt.length - 1] || null;
}
let As = 1;
function dr(e, t = !1) {
  As += e, e < 0 && ut && t && (ut.hasOnce = !0);
}
function fc(e) {
  return e.dynamicChildren = As > 0 ? ut || Rn : null, gi(), As > 0 && ut && ut.push(e), e;
}
function it(e, t, n, s, r, o) {
  return fc(
    H(
      e,
      t,
      n,
      s,
      r,
      o,
      !0
    )
  );
}
function De(e, t, n, s, r) {
  return fc(
    Y(
      e,
      t,
      n,
      s,
      r,
      !0
    )
  );
}
function Jn(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function as(e, t) {
  return e.type === t.type && e.key === t.key;
}
const dc = ({ key: e }) => e ?? null, sr = ({
  ref: e,
  ref_key: t,
  ref_for: n
}) => (typeof e == "number" && (e = "" + e), e != null ? Re(e) || /* @__PURE__ */ Me(e) || te(e) ? { i: Ze, r: e, k: t, f: !!n } : e : null);
function H(e, t = null, n = null, s = 0, r = null, o = e === qe ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && dc(t),
    ref: t && sr(t),
    scopeId: $l,
    slotScopeIds: null,
    children: n,
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
    patchFlag: s,
    dynamicProps: r,
    dynamicChildren: null,
    appContext: null,
    ctx: Ze
  };
  return a ? (pr(l, n), o & 128 && e.normalize(l)) : n && (l.shapeFlag |= Re(n) ? 8 : 16), As > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  ut && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && ut.push(l), l;
}
const Y = ld;
function ld(e, t = null, n = null, s = 0, r = null, o = !1) {
  if ((!e || e === ql) && (e = pt), Jn(e)) {
    const a = Mn(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return n && pr(a, n), As > 0 && !o && ut && (a.shapeFlag & 6 ? ut[ut.indexOf(e)] = a : ut.push(a)), a.patchFlag = -2, a;
  }
  if (yd(e) && (e = e.__vccOpts), t) {
    t = pc(t);
    let { class: a, style: l } = t;
    a && !Re(a) && (t.class = yt(a)), _e(l) && (/* @__PURE__ */ Nr(l) && !Q(l) && (l = Ge({}, l)), t.style = Ls(l));
  }
  const i = Re(e) ? 1 : uc(e) ? 128 : Dr(e) ? 64 : _e(e) ? 4 : te(e) ? 2 : 0;
  return H(
    e,
    t,
    n,
    s,
    r,
    i,
    o,
    !0
  );
}
function pc(e) {
  return e ? /* @__PURE__ */ Nr(e) || sc(e) ? Ge({}, e) : e : null;
}
function Mn(e, t, n = !1, s = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? gt(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && dc(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      n && o ? Q(o) ? o.concat(sr(t)) : [o, sr(t)] : sr(t)
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
    patchFlag: t && e.type !== qe ? i === -1 ? 16 : i | 16 : i,
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
    ssContent: e.ssContent && Mn(e.ssContent),
    ssFallback: e.ssFallback && Mn(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && s && cr(
    u,
    l.clone(u)
  ), u;
}
function le(e = " ", t = 0) {
  return Y(Fr, null, e, t);
}
function Os(e = "", t = !1) {
  return t ? (fe(), De(pt, null, e)) : Y(pt, null, e);
}
function Mt(e) {
  return e == null || typeof e == "boolean" ? Y(pt) : Q(e) ? Y(
    qe,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : Jn(e) ? Jt(e) : Y(Fr, null, String(e));
}
function Jt(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : Mn(e);
}
function pr(e, t) {
  let n = 0;
  const { shapeFlag: s } = e;
  if (t == null)
    t = null;
  else if (Q(t))
    n = 16;
  else if (typeof t == "object")
    if (s & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), pr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      n = 32;
      const r = t._;
      !r && !sc(t) ? t._ctx = Ze : r === 3 && Ze && (Ze.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (te(t)) {
    if (s & 65) {
      pr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: Ze }, n = 32;
  } else
    t = String(t), s & 64 ? (n = 16, t = [le(t)]) : n = 8;
  e.children = t, e.shapeFlag |= n;
}
function gt(...e) {
  const t = {};
  for (let n = 0; n < e.length; n++) {
    const s = e[n];
    for (const r in s)
      if (r === "class")
        t.class !== s.class && (t.class = yt([t.class, s.class]));
      else if (r === "style")
        t.style = Ls([t.style, s.style]);
      else if (kr(r)) {
        const o = t[r], i = s[r];
        i && o !== i && !(Q(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !Sr(r) && (t[r] = i);
      } else r !== "" && (t[r] = s[r]);
  }
  return t;
}
function Tt(e, t, n, s = null) {
  kt(e, t, 7, [
    n,
    s
  ]);
}
const cd = Yl();
let hc = 0;
function ud() {
  return hc;
}
function fd(e, t, n) {
  const s = e.type, r = (t ? t.appContext : e.appContext) || cd, o = {
    uid: hc++,
    vnode: e,
    type: s,
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
    scope: new hl(
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
    propsOptions: oc(s, r),
    emitsOptions: Ql(s, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: Ee,
    // inheritAttrs
    inheritAttrs: s.inheritAttrs,
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
    suspense: n,
    suspenseId: n ? n.pendingId : 0,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = Hf.bind(null, o), e.ce && e.ce(o), o;
}
let Je = null;
const Ct = () => Je || Ze;
let hr, Rs;
{
  const e = Or(), t = (n, s) => {
    let r;
    return (r = e[n]) || (r = e[n] = []), r.push(s), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  hr = t(
    "__VUE_INSTANCE_SETTERS__",
    (n) => Je = n
  ), Rs = t(
    "__VUE_SSR_SETTERS__",
    (n) => Ts = n
  );
}
const $s = (e) => {
  const t = Je;
  return hr(e), e.scope.on(), () => {
    e.scope.off(), hr(t);
  };
}, Yi = () => {
  Je && Je.scope.off(), hr(null);
};
function mc(e) {
  return e.vnode.shapeFlag & 4;
}
let Ts = !1;
function dd(e, t = !1, n = !1) {
  t && Rs(t);
  const { props: s, children: r } = e.vnode, o = mc(e);
  Yf(e, s, o, t), td(e, r, n || t);
  const i = o ? pd(e, t) : void 0;
  return t && Rs(!1), i;
}
function pd(e, t) {
  const n = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Lf);
  const { setup: s } = n;
  if (s) {
    Vt();
    const r = e.setupContext = s.length > 1 ? md(e) : null, o = $s(e), i = js(
      s,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = al(i);
    if (Bt(), o(), (a || e.sp) && !Gn(e) && zl(e), a) {
      if (i.then(Yi, Yi), t)
        return i.then((l) => {
          Rs(!0);
          try {
            Qi(e, l, t);
          } finally {
            Rs(!1);
          }
        }).catch((l) => {
          Mr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      Qi(e, i);
  } else
    gc(e);
}
function Qi(e, t, n) {
  te(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : _e(t) && (e.setupState = Pl(t)), gc(e);
}
function gc(e, t, n) {
  const s = e.type;
  e.render || (e.render = s.render || jt);
  {
    const r = $s(e);
    Vt();
    try {
      jf(e);
    } finally {
      Bt(), r();
    }
  }
}
const hd = {
  get(e, t) {
    return Ke(e, "get", ""), e[t];
  }
};
function md(e) {
  const t = (n) => {
    e.exposed = n || {};
  };
  return {
    attrs: new Proxy(e.attrs, hd),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Vr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(Pl(ai(e.exposed)), {
    get(t, n) {
      if (n in t)
        return t[n];
      if (n in _s)
        return _s[n](e);
    },
    has(t, n) {
      return n in t || n in _s;
    }
  })) : e.proxy;
}
function gd(e, t = !0) {
  return te(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function yd(e) {
  return te(e) && "__vccOpts" in e;
}
const ue = (e, t) => /* @__PURE__ */ lf(e, t, Ts);
function en(e, t, n) {
  try {
    dr(-1);
    const s = arguments.length;
    return s === 2 ? _e(t) && !Q(t) ? Jn(t) ? Y(e, null, [t]) : Y(e, t) : Y(e, null, t) : (s > 3 ? n = Array.prototype.slice.call(arguments, 2) : s === 3 && Jn(n) && (n = [n]), Y(e, t, n));
  } finally {
    dr(1);
  }
}
const vd = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Do;
const Xi = typeof window < "u" && window.trustedTypes;
if (Xi)
  try {
    Do = /* @__PURE__ */ Xi.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const yc = Do ? (e) => Do.createHTML(e) : (e) => e, bd = "http://www.w3.org/2000/svg", _d = "http://www.w3.org/1998/Math/MathML", Kt = typeof document < "u" ? document : null, ea = Kt && /* @__PURE__ */ Kt.createElement("template"), xd = {
  insert: (e, t, n) => {
    t.insertBefore(e, n || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, n, s) => {
    const r = t === "svg" ? Kt.createElementNS(bd, e) : t === "mathml" ? Kt.createElementNS(_d, e) : n ? Kt.createElement(e, { is: n }) : Kt.createElement(e);
    return e === "select" && s && s.multiple != null && r.setAttribute("multiple", s.multiple), r;
  },
  createText: (e) => Kt.createTextNode(e),
  createComment: (e) => Kt.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => Kt.querySelector(e),
  setScopeId(e, t) {
    e.setAttribute(t, "");
  },
  // __UNSAFE__
  // Reason: innerHTML.
  // Static content here can only come from compiled templates.
  // As long as the user only uses trusted templates, this is safe.
  insertStaticContent(e, t, n, s, r, o) {
    const i = n ? n.previousSibling : t.lastChild;
    if (r && (r === o || r.nextSibling))
      for (; t.insertBefore(r.cloneNode(!0), n), !(r === o || !(r = r.nextSibling)); )
        ;
    else {
      ea.innerHTML = yc(
        s === "svg" ? `<svg>${e}</svg>` : s === "mathml" ? `<math>${e}</math>` : e
      );
      const a = ea.content;
      if (s === "svg" || s === "mathml") {
        const l = a.firstChild;
        for (; l.firstChild; )
          a.appendChild(l.firstChild);
        a.removeChild(l);
      }
      t.insertBefore(a, n);
    }
    return [
      // first
      i ? i.nextSibling : t.firstChild,
      // last
      n ? n.previousSibling : t.lastChild
    ];
  }
}, wd = /* @__PURE__ */ Symbol("_vtc");
function kd(e, t, n) {
  const s = e[wd];
  s && (t = (t ? [t, ...s] : [...s]).join(" ")), t == null ? e.removeAttribute("class") : n ? e.setAttribute("class", t) : e.className = t;
}
const mr = /* @__PURE__ */ Symbol("_vod"), vc = /* @__PURE__ */ Symbol("_vsh"), Lo = {
  // used for prop mismatch check during hydration
  name: "show",
  beforeMount(e, { value: t }, { transition: n }) {
    e[mr] = e.style.display === "none" ? "" : e.style.display, n && t ? n.beforeEnter(e) : ls(e, t);
  },
  mounted(e, { value: t }, { transition: n }) {
    n && t && n.enter(e);
  },
  updated(e, { value: t, oldValue: n }, { transition: s }) {
    !t != !n && (s ? t ? (s.beforeEnter(e), ls(e, !0), s.enter(e)) : s.leave(e, () => {
      ls(e, !1);
    }) : ls(e, t));
  },
  beforeUnmount(e, { value: t }) {
    ls(e, t);
  }
};
function ls(e, t) {
  e.style.display = t ? e[mr] : "none", e[vc] = !t;
}
const Sd = /* @__PURE__ */ Symbol(""), Ed = /(?:^|;)\s*display\s*:/;
function Cd(e, t, n) {
  const s = e.style, r = Re(n);
  let o = !1;
  if (n && !r) {
    if (t)
      if (Re(t))
        for (const i of t.split(";")) {
          const a = i.slice(0, i.indexOf(":")).trim();
          n[a] == null && ps(s, a, "");
        }
      else
        for (const i in t)
          n[i] == null && ps(s, i, "");
    for (const i in n) {
      i === "display" && (o = !0);
      const a = n[i];
      a != null ? Od(
        e,
        i,
        !Re(t) && t ? t[i] : void 0,
        a
      ) || ps(s, i, a) : ps(s, i, "");
    }
  } else if (r) {
    if (t !== n) {
      const i = s[Sd];
      i && (n += ";" + i), s.cssText = n, o = Ed.test(n);
    }
  } else t && e.removeAttribute("style");
  mr in e && ((!r || t !== n) && (e[mr] = o ? s.display : ""), e[vc] && (s.display = "none"));
}
const Ws = /\s*!important$/;
function ps(e, t, n) {
  if (Q(n))
    n.forEach((s) => ps(e, t, s));
  else if (n == null && (n = ""), t.startsWith("--"))
    Ws.test(n) ? e.setProperty(t, n.replace(Ws, ""), "important") : e.setProperty(t, n);
  else {
    const s = Ad(e, t);
    Ws.test(n) ? e.setProperty(
      Ln(s),
      n.replace(Ws, ""),
      "important"
    ) : e[s] = n;
  }
}
const ta = ["Webkit", "Moz", "ms"], Xr = {};
function Ad(e, t) {
  const n = Xr[t];
  if (n)
    return n;
  let s = Ye(t);
  if (s !== "filter" && s in e)
    return Xr[t] = s;
  s = Ar(s);
  for (let r = 0; r < ta.length; r++) {
    const o = ta[r] + s;
    if (o in e)
      return Xr[t] = o;
  }
  return t;
}
function Od(e, t, n, s) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && Re(s) && n === s;
}
const na = "http://www.w3.org/1999/xlink";
function sa(e, t, n, s, r, o = Du(t)) {
  s && t.startsWith("xlink:") ? n == null ? e.removeAttributeNS(na, t.slice(6, t.length)) : e.setAttributeNS(na, t, n) : n == null || o && !fl(n) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : dt(n) ? String(n) : n
  );
}
function ra(e, t, n, s, r) {
  if (t === "innerHTML" || t === "textContent") {
    n != null && (e[t] = t === "innerHTML" ? yc(n) : n);
    return;
  }
  const o = e.tagName;
  if (t === "value" && o !== "PROGRESS" && // custom elements may use _value internally
  !o.includes("-")) {
    const a = o === "OPTION" ? e.getAttribute("value") || "" : e.value, l = n == null ? (
      // #11647: value should be set as empty string for null and undefined,
      // but <input type="checkbox"> should be set as 'on'.
      e.type === "checkbox" ? "on" : ""
    ) : String(n);
    (a !== l || !("_value" in e)) && (e.value = l), n == null && e.removeAttribute(t), e._value = n;
    return;
  }
  let i = !1;
  if (n === "" || n == null) {
    const a = typeof e[t];
    a === "boolean" ? n = fl(n) : n == null && a === "string" ? (n = "", i = !0) : a === "number" && (n = 0, i = !0);
  }
  try {
    e[t] = n;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function Wn(e, t, n, s) {
  e.addEventListener(t, n, s);
}
function Rd(e, t, n, s) {
  e.removeEventListener(t, n, s);
}
const oa = /* @__PURE__ */ Symbol("_vei");
function Td(e, t, n, s, r = null) {
  const o = e[oa] || (e[oa] = {}), i = o[t];
  if (s && i)
    i.value = s;
  else {
    const [a, l] = Nd(t);
    if (s) {
      const c = o[t] = Ld(
        s,
        r
      );
      Wn(e, a, c, l);
    } else i && (Rd(e, a, i, l), o[t] = void 0);
  }
}
const Id = /(Once|Passive|Capture)$/, Pd = /^on:?(?:Once|Passive|Capture)$/;
function Nd(e) {
  let t, n;
  for (; (n = e.match(Id)) && !Pd.test(e); )
    t || (t = {}), e = e.slice(0, e.length - n[1].length), t[n[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Ln(e.slice(2)), t];
}
let eo = 0;
const Md = /* @__PURE__ */ Promise.resolve(), Dd = () => eo || (Md.then(() => eo = 0), eo = Date.now());
function Ld(e, t) {
  const n = (s) => {
    if (!s._vts)
      s._vts = Date.now();
    else if (s._vts <= n.attached)
      return;
    const r = n.value;
    if (Q(r)) {
      const o = s.stopImmediatePropagation;
      s.stopImmediatePropagation = () => {
        o.call(s), s._stopped = !0;
      };
      const i = r.slice(), a = [s];
      for (let l = 0; l < i.length && !s._stopped; l++) {
        const c = i[l];
        c && kt(
          c,
          t,
          5,
          a
        );
      }
    } else
      kt(
        r,
        t,
        5,
        [s]
      );
  };
  return n.value = e, n.attached = Dd(), n;
}
const ia = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, jd = (e, t, n, s, r, o) => {
  const i = r === "svg";
  t === "class" ? kd(e, s, i) : t === "style" ? Cd(e, n, s) : kr(t) ? Sr(t) || Td(e, t, n, s, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : $d(e, t, s, i)) ? (ra(e, t, s), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && sa(e, t, s, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (Fd(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !Re(s))) ? ra(e, Ye(t), s, o, t) : (t === "true-value" ? e._trueValue = s : t === "false-value" && (e._falseValue = s), sa(e, t, s, i));
};
function $d(e, t, n, s) {
  if (s)
    return !!(t === "innerHTML" || t === "textContent" || t in e && ia(t) && te(n));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return ia(t) && Re(n) ? !1 : t in e;
}
function Fd(e, t) {
  const n = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!n)
    return !1;
  const s = Ye(t);
  return Array.isArray(n) ? n.some((r) => Ye(r) === s) : Object.keys(n).some((r) => Ye(r) === s);
}
const aa = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return Q(t) ? (n) => nr(t, n) : t;
};
function Vd(e) {
  e.target.composing = !0;
}
function la(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const Hs = /* @__PURE__ */ Symbol("_assign"), qs = /* @__PURE__ */ Symbol("_initialValue");
function to(e, t, n) {
  return t && (e = e.trim()), n && (e = Xo(e)), e;
}
const bc = {
  created(e, { modifiers: { lazy: t, trim: n, number: s } }, r) {
    e.parentNode && (e.type === "text" ? e[qs] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[qs] = e.defaultValue.replace(/\r\n?/g, `
`))), e[Hs] = aa(r);
    const o = s || r.props && r.props.type === "number";
    Wn(e, t ? "change" : "input", (i) => {
      i.target.composing || e[Hs](to(e.value, n, o));
    }), (n || o) && Wn(e, "change", () => {
      e.value = to(e.value, n, o);
    }), t || (Wn(e, "compositionstart", Vd), Wn(e, "compositionend", la), Wn(e, "change", la));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: n, number: s } }) {
    const r = t ?? "", o = e[qs];
    delete e[qs], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[Hs](to(e.value, n, s)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: n, modifiers: { lazy: s, trim: r, number: o } }, i) {
    if (e[Hs] = aa(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? Xo(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (s && t === n || r && e.value.trim() === l) || (e.value = l);
  }
}, Bd = ["ctrl", "shift", "alt", "meta"], zd = {
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
  exact: (e, t) => Bd.some((n) => e[`${n}Key`] && !t.includes(n))
}, Ud = (e, t) => {
  if (!e) return e;
  const n = e._withMods || (e._withMods = {}), s = t.join(".");
  return n[s] || (n[s] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = zd[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, Wd = /* @__PURE__ */ Ge({ patchProp: jd }, xd);
let ca;
function Hd() {
  return ca || (ca = sd(Wd));
}
const qd = ((...e) => {
  const t = Hd().createApp(...e), { mount: n } = t;
  return t.mount = (s) => {
    const r = Gd(s);
    if (!r) return;
    const o = t._component;
    !te(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = n(r, !1, Zd(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function Zd(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function Gd(e) {
  return Re(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let _c;
const Br = (e) => _c = e, xc = (
  /* istanbul ignore next */
  Symbol()
);
function jo(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var xs;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})(xs || (xs = {}));
function Kd() {
  const e = Tr(!0), t = e.run(() => /* @__PURE__ */ oe({}));
  let n = [], s = [];
  const r = ai({
    install(o) {
      Br(r), r._a = o, o.provide(xc, r), o.config.globalProperties.$pinia = r, s.forEach((i) => n.push(i)), s = [];
    },
    use(o) {
      return this._a ? n.push(o) : s.push(o), this;
    },
    _p: n,
    // it's actually undefined here
    // @ts-expect-error
    _a: null,
    _e: e,
    _s: /* @__PURE__ */ new Map(),
    state: t
  });
  return r;
}
const wc = () => {
};
function ua(e, t, n, s = wc) {
  e.add(t);
  const r = () => {
    e.delete(t) && s();
  };
  return !n && Ir() && ei(r), r;
}
function Bn(e, ...t) {
  e.forEach((n) => {
    n(...t);
  });
}
const Jd = (e) => e(), fa = Symbol(), no = Symbol();
function $o(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((n, s) => e.set(s, n)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const n in t) {
    if (!t.hasOwnProperty(n))
      continue;
    const s = t[n], r = e[n];
    jo(r) && jo(s) && e.hasOwnProperty(n) && !/* @__PURE__ */ Me(s) && !/* @__PURE__ */ $t(s) ? e[n] = $o(r, s) : e[n] = s;
  }
  return e;
}
const Yd = (
  /* istanbul ignore next */
  Symbol()
);
function Qd(e) {
  return !jo(e) || !Object.prototype.hasOwnProperty.call(e, Yd);
}
const { assign: un } = Object;
function Xd(e) {
  return !!(/* @__PURE__ */ Me(e) && e.effect);
}
function ep(e, t, n, s) {
  const { state: r, actions: o, getters: i } = t, a = n.state.value[e];
  let l;
  function c() {
    a || (n.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ li(n.state.value[e]);
    return un(u, o, Object.keys(i || {}).reduce((f, d) => (f[d] = ai(ue(() => {
      Br(n);
      const h = n._s.get(e);
      return i[d].call(h, h);
    })), f), {}));
  }
  return l = kc(e, c, t, n, s, !0), l;
}
function kc(e, t, n = {}, s, r, o) {
  let i;
  const a = un({ actions: {} }, n), l = { deep: !0 };
  let c, u, f = /* @__PURE__ */ new Set(), d = /* @__PURE__ */ new Set(), h;
  const y = s.state.value[e];
  !o && !y && (s.state.value[e] = {});
  let v;
  function w(S) {
    let j;
    c = u = !1, typeof S == "function" ? (S(s.state.value[e]), j = {
      type: xs.patchFunction,
      storeId: e,
      events: h
    }) : ($o(s.state.value[e], S), j = {
      type: xs.patchObject,
      payload: S,
      storeId: e,
      events: h
    });
    const pe = v = Symbol();
    St().then(() => {
      v === pe && (c = !0);
    }), u = !0, Bn(f, j, s.state.value[e]);
  }
  const R = o ? function() {
    const { state: j } = n, pe = j ? j() : {};
    this.$patch((Ae) => {
      un(Ae, pe);
    });
  } : (
    /* istanbul ignore next */
    wc
  );
  function x() {
    i.stop(), f.clear(), d.clear(), s._s.delete(e);
  }
  const N = (S, j = "") => {
    if (fa in S)
      return S[no] = j, S;
    const pe = function() {
      Br(s);
      const Ae = Array.from(arguments), Te = /* @__PURE__ */ new Set(), $e = /* @__PURE__ */ new Set();
      function Xe(X) {
        Te.add(X);
      }
      function et(X) {
        $e.add(X);
      }
      Bn(d, {
        args: Ae,
        name: pe[no],
        store: U,
        after: Xe,
        onError: et
      });
      let ce;
      try {
        ce = S.apply(this && this.$id === e ? this : U, Ae);
      } catch (X) {
        throw Bn($e, X), X;
      }
      return ce instanceof Promise ? ce.then((X) => (Bn(Te, X), X)).catch((X) => (Bn($e, X), Promise.reject(X))) : (Bn(Te, ce), ce);
    };
    return pe[fa] = !0, pe[no] = j, pe;
  }, O = {
    _p: s,
    // _s: scope,
    $id: e,
    $onAction: ua.bind(null, d),
    $patch: w,
    $reset: R,
    $subscribe(S, j = {}) {
      const pe = ua(f, S, j.detached, () => Ae()), Ae = i.run(() => je(() => s.state.value[e], (Te) => {
        (j.flush === "sync" ? u : c) && S({
          storeId: e,
          type: xs.direct,
          events: h
        }, Te);
      }, un({}, l, j)));
      return pe;
    },
    $dispose: x
  }, U = /* @__PURE__ */ jn(O);
  s._s.set(e, U);
  const F = (s._a && s._a.runWithContext || Jd)(() => s._e.run(() => (i = Tr()).run(() => t({ action: N }))));
  for (const S in F) {
    const j = F[S];
    if (/* @__PURE__ */ Me(j) && !Xd(j) || /* @__PURE__ */ $t(j))
      o || (y && Qd(j) && (/* @__PURE__ */ Me(j) ? j.value = y[S] : $o(j, y[S])), s.state.value[e][S] = j);
    else if (typeof j == "function") {
      const pe = N(j, S);
      F[S] = pe, a.actions[S] = j;
    }
  }
  return un(U, F), un(/* @__PURE__ */ ge(U), F), Object.defineProperty(U, "$state", {
    get: () => s.state.value[e],
    set: (S) => {
      w((j) => {
        un(j, S);
      });
    }
  }), s._p.forEach((S) => {
    un(U, i.run(() => S({
      store: U,
      app: s._a,
      pinia: s,
      options: a
    })));
  }), y && o && n.hydrate && n.hydrate(U.$state, y), c = !0, u = !0, U;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function rs(e, t, n) {
  let s;
  const r = typeof t == "function";
  s = r ? n : t;
  function o(i, a) {
    const l = ui();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? ot(xc, null) : null), i && Br(i), i = _c, i._s.has(e) || (r ? kc(e, t, s, i) : ep(e, s, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const Hn = typeof document < "u";
function Sc(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function tp(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && Sc(e.default);
}
const Oe = Object.assign;
function so(e, t) {
  const n = {};
  for (const s in t) {
    const r = t[s];
    n[s] = Et(r) ? r.map(e) : e(r);
  }
  return n;
}
const ws = () => {
}, Et = Array.isArray;
function da(e, t) {
  const n = {};
  for (const s in e) n[s] = s in t ? t[s] : e[s];
  return n;
}
const Ec = /#/g, np = /&/g, sp = /\//g, rp = /=/g, op = /\?/g, Cc = /\+/g, ip = /%5B/g, ap = /%5D/g, Ac = /%5E/g, lp = /%60/g, Oc = /%7B/g, cp = /%7C/g, Rc = /%7D/g, up = /%20/g;
function yi(e) {
  return e == null ? "" : encodeURI("" + e).replace(cp, "|").replace(ip, "[").replace(ap, "]");
}
function fp(e) {
  return yi(e).replace(Oc, "{").replace(Rc, "}").replace(Ac, "^");
}
function Fo(e) {
  return yi(e).replace(Cc, "%2B").replace(up, "+").replace(Ec, "%23").replace(np, "%26").replace(lp, "`").replace(Oc, "{").replace(Rc, "}").replace(Ac, "^");
}
function dp(e) {
  return Fo(e).replace(rp, "%3D");
}
function pp(e) {
  return yi(e).replace(Ec, "%23").replace(op, "%3F");
}
function hp(e) {
  return pp(e).replace(sp, "%2F");
}
function Is(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const mp = /\/$/, gp = (e) => e.replace(mp, "");
function ro(e, t, n = "/") {
  let s, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (s = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (s = s || t.slice(0, a), i = t.slice(a, t.length)), s = _p(s ?? t, n), {
    fullPath: s + o + i,
    path: s,
    query: r,
    hash: Is(i)
  };
}
function yp(e, t) {
  const n = t.query ? e(t.query) : "";
  return t.path + (n && "?") + n + (t.hash || "");
}
function vp(e, t, n) {
  const s = t.matched.length - 1, r = n.matched.length - 1;
  return s > -1 && s === r && Yn(t.matched[s], n.matched[r]) && Tc(t.params, n.params) && e(t.query) === e(n.query) && t.hash === n.hash;
}
function Yn(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function Tc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var n in e) if (!bp(e[n], t[n])) return !1;
  return !0;
}
function bp(e, t) {
  return Et(e) ? pa(e, t) : Et(t) ? pa(t, e) : e?.valueOf() === t?.valueOf();
}
function pa(e, t) {
  return Et(t) ? e.length === t.length && e.every((n, s) => n === t[s]) : e.length === 1 && e[0] === t;
}
function _p(e, t) {
  if (e.startsWith("/")) return e;
  if (!e) return t;
  const n = t.split("/"), s = e.split("/"), r = s[s.length - 1];
  (r === ".." || r === ".") && s.push("");
  let o = n.length - 1, i, a;
  for (i = 0; i < s.length; i++)
    if (a = s[i], a !== ".")
      if (a === "..")
        o > 1 && o--;
      else break;
  return n.slice(0, o).join("/") + "/" + s.slice(i).join("/");
}
const on = {
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
let Vo = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), ha = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const oo = "";
function xp(e) {
  if (!e) if (Hn) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), gp(e);
}
const wp = /^[^#]+#/;
function kp(e, t) {
  return e.replace(wp, "#") + t;
}
function Sp(e, t) {
  const n = document.documentElement.getBoundingClientRect(), s = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: s.left - n.left - (t.left || 0),
    top: s.top - n.top - (t.top || 0)
  };
}
const Ep = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function Cp(e) {
  let t;
  if ("el" in e) {
    const n = e.el, s = typeof n == "string" && n.startsWith("#"), r = typeof n == "string" ? s ? document.getElementById(n.slice(1)) : document.querySelector(n) : n;
    if (!r)
      return;
    t = Sp(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function ma(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Bo = /* @__PURE__ */ new Map();
function Ap(e, t) {
  Bo.set(e, t);
}
function Op(e) {
  const t = Bo.get(e);
  return Bo.delete(e), t;
}
function Rp(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function Ic(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let Pe = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const Pc = Symbol("");
Pe.MATCHER_NOT_FOUND + "", Pe.NAVIGATION_GUARD_REDIRECT + "", Pe.NAVIGATION_ABORTED + "", Pe.NAVIGATION_CANCELLED + "", Pe.NAVIGATION_DUPLICATED + "";
function Qn(e, t) {
  return Oe(/* @__PURE__ */ new Error(), {
    type: e,
    [Pc]: !0
  }, t);
}
function qt(e, t) {
  return e instanceof Error && Pc in e && (t == null || !!(e.type & t));
}
const Tp = [
  "params",
  "query",
  "hash"
];
function Ip(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const n of Tp) n in e && (t[n] = e[n]);
  return JSON.stringify(t, null, 2);
}
function Pp(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const n = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let s = 0; s < n.length; ++s) {
    const r = n[s].replace(Cc, " "), o = r.indexOf("="), i = Is(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : Is(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      Et(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function ga(e) {
  let t = "";
  for (let n in e) {
    const s = e[n];
    if (n = dp(n), s == null) {
      s !== void 0 && (t += (t.length ? "&" : "") + n);
      continue;
    }
    (Et(s) ? s.map((r) => r && Fo(r)) : [s && Fo(s)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + n, r != null && (t += "=" + r));
    });
  }
  return t;
}
function Np(e) {
  const t = {};
  for (const n in e) {
    const s = e[n];
    s !== void 0 && (t[n] = Et(s) ? s.map((r) => r == null ? null : "" + r) : s == null ? s : "" + s);
  }
  return t;
}
const Mp = Symbol(""), ya = Symbol(""), zr = Symbol(""), vi = Symbol(""), zo = Symbol("");
function cs() {
  let e = [];
  function t(s) {
    return e.push(s), () => {
      const r = e.indexOf(s);
      r > -1 && e.splice(r, 1);
    };
  }
  function n() {
    e = [];
  }
  return {
    add: t,
    list: () => e.slice(),
    reset: n
  };
}
function dn(e, t, n, s, r, o = (i) => i()) {
  const i = s && (s.enterCallbacks[r] = s.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (d) => {
      d === !1 ? l(Qn(Pe.NAVIGATION_ABORTED, {
        from: n,
        to: t
      })) : d instanceof Error ? l(d) : Rp(d) ? l(Qn(Pe.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: d
      })) : (i && s.enterCallbacks[r] === i && typeof d == "function" && i.push(d), a());
    }, u = o(() => e.call(s && s.instances[r], t, n, c));
    let f = Promise.resolve(u);
    e.length < 3 && (f = f.then(c)), f.catch((d) => l(d));
  });
}
function io(e, t, n, s, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (Sc(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(dn(c, n, s, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const f = tp(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = f;
            const d = (f.__vccOpts || f)[t];
            return d && dn(d, n, s, i, a, r)();
          }));
        }
    }
  return o;
}
function Dp(e, t) {
  const n = [], s = [], r = [], o = Math.max(t.matched.length, e.matched.length);
  for (let i = 0; i < o; i++) {
    const a = t.matched[i];
    a && (e.matched.find((c) => Yn(c, a)) ? s.push(a) : n.push(a));
    const l = e.matched[i];
    l && (t.matched.find((c) => Yn(c, l)) || r.push(l));
  }
  return [
    n,
    s,
    r
  ];
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
function Lp(e = "") {
  let t = [], n = [[oo, {}]], s = 0;
  e = xp(e);
  function r(a, l = {}) {
    s++, s !== n.length && n.splice(s), n.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const f = {
      direction: c,
      delta: u,
      type: Vo.pop
    };
    for (const d of t) d(a, l, f);
  }
  const i = {
    location: oo,
    state: {},
    base: e,
    createHref: kp.bind(null, e),
    replace(a, l) {
      n.splice(s--, 1), r(a, l);
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
      t = [], n = [[oo, {}]], s = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? ha.back : ha.forward;
      s = Math.max(0, Math.min(s + a, n.length - 1)), l && o(this.location, c, {
        direction: u,
        delta: a
      });
    }
  };
  return Object.defineProperty(i, "location", {
    enumerable: !0,
    get: () => n[s][0]
  }), Object.defineProperty(i, "state", {
    enumerable: !0,
    get: () => n[s][1]
  }), i;
}
let Tn = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var Ve = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(Ve || {});
const jp = {
  type: Tn.Static,
  value: ""
}, $p = /[a-zA-Z0-9_]/;
function Fp(e) {
  if (!e) return [[]];
  if (e === "/") return [[jp]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(h) {
    throw new Error(`ERR (${n})/"${c}": ${h}`);
  }
  let n = Ve.Static, s = n;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function f() {
    c && (n === Ve.Static ? o.push({
      type: Tn.Static,
      value: c
    }) : n === Ve.Param || n === Ve.ParamRegExp || n === Ve.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: Tn.Param,
      value: c,
      regexp: u,
      repeatable: l === "*" || l === "+",
      optional: l === "*" || l === "?"
    })) : t("Invalid state to consume buffer"), c = "");
  }
  function d() {
    c += l;
  }
  for (; a < e.length; ) {
    if (l = e[a++], l === "\\" && n !== Ve.ParamRegExp) {
      s = n, n = Ve.EscapeNext;
      continue;
    }
    switch (n) {
      case Ve.Static:
        l === "/" ? (c && f(), i()) : l === ":" ? (f(), n = Ve.Param) : d();
        break;
      case Ve.EscapeNext:
        d(), n = s;
        break;
      case Ve.Param:
        l === "(" ? n = Ve.ParamRegExp : $p.test(l) ? d() : (f(), n = Ve.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case Ve.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : n = Ve.ParamRegExpEnd : u += l;
        break;
      case Ve.ParamRegExpEnd:
        f(), n = Ve.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return n === Ve.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), f(), i(), r;
}
const va = "[^/]+?", Vp = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var st = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(st || {});
const Bp = /[.+*?^${}()[\]/\\]/g;
function zp(e, t) {
  const n = Oe({}, Vp, t), s = [];
  let r = n.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [st.Root];
    n.strict && !c.length && (r += "/");
    for (let f = 0; f < c.length; f++) {
      const d = c[f];
      let h = st.Segment + (n.sensitive ? st.BonusCaseSensitive : 0);
      if (d.type === Tn.Static)
        f || (r += "/"), r += d.value.replace(Bp, "\\$&"), h += st.Static;
      else if (d.type === Tn.Param) {
        const { value: y, repeatable: v, optional: w, regexp: R } = d;
        o.push({
          name: y,
          repeatable: v,
          optional: w
        });
        const x = R || va;
        if (x !== va) {
          h += st.BonusCustomRegExp;
          try {
            `${x}`;
          } catch (O) {
            throw new Error(`Invalid custom RegExp for param "${y}" (${x}): ` + O.message);
          }
        }
        let N = v ? `((?:${x})(?:/(?:${x}))*)` : `(${x})`;
        f || (N = w && c.length < 2 ? `(?:/${N})` : "/" + N), w && (N += "?"), r += N, h += st.Dynamic, w && (h += st.BonusOptional), v && (h += st.BonusRepeatable), x === ".*" && (h += st.BonusWildcard);
      }
      u.push(h);
    }
    s.push(u);
  }
  if (n.strict && n.end) {
    const c = s.length - 1;
    s[c][s[c].length - 1] += st.BonusStrict;
  }
  n.strict || (r += "/?"), n.end ? r += "$" : n.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const i = new RegExp(r, n.sensitive ? "" : "i");
  function a(c) {
    const u = c.match(i), f = {};
    if (!u) return null;
    for (let d = 1; d < u.length; d++) {
      const h = u[d] || "", y = o[d - 1];
      f[y.name] = h && y.repeatable ? h.split("/") : h;
    }
    return f;
  }
  function l(c) {
    let u = "", f = !1;
    for (const d of e) {
      (!f || !u.endsWith("/")) && (u += "/"), f = !1;
      for (const h of d) if (h.type === Tn.Static) u += h.value;
      else if (h.type === Tn.Param) {
        const { value: y, repeatable: v, optional: w } = h, R = y in c ? c[y] : "";
        if (Et(R) && !v) throw new Error(`Provided param "${y}" is an array but it is not repeatable (* or + modifiers)`);
        const x = Et(R) ? R.join("/") : R;
        if (!x) if (w)
          d.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : f = !0);
        else throw new Error(`Missing required param "${y}"`);
        u += x;
      }
    }
    return u || "/";
  }
  return {
    re: i,
    score: s,
    keys: o,
    parse: a,
    stringify: l
  };
}
function Up(e, t) {
  let n = 0;
  for (; n < e.length && n < t.length; ) {
    const s = t[n] - e[n];
    if (s) return s;
    n++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === st.Static + st.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === st.Static + st.Segment ? 1 : -1 : 0;
}
function Nc(e, t) {
  let n = 0;
  const s = e.score, r = t.score;
  for (; n < s.length && n < r.length; ) {
    const o = Up(s[n], r[n]);
    if (o) return o;
    n++;
  }
  if (Math.abs(r.length - s.length) === 1) {
    if (ba(s)) return 1;
    if (ba(r)) return -1;
  }
  return r.length - s.length;
}
function ba(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const Wp = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function Hp(e, t, n) {
  const s = zp(Fp(e.path), n), r = Oe(s, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function qp(e, t) {
  const n = [], s = /* @__PURE__ */ new Map();
  t = da(Wp, t);
  function r(f) {
    return s.get(f);
  }
  function o(f, d, h) {
    const y = !h, v = xa(f);
    v.aliasOf = h && h.record;
    const w = da(t, f), R = [v];
    if ("alias" in f) {
      const O = typeof f.alias == "string" ? [f.alias] : f.alias;
      for (const U of O) R.push(xa(Oe({}, v, {
        components: h ? h.record.components : v.components,
        path: U,
        aliasOf: h ? h.record : v
      })));
    }
    let x, N;
    for (const O of R) {
      const { path: U } = O;
      if (d && U[0] !== "/") {
        const ve = d.record.path, F = ve[ve.length - 1] === "/" ? "" : "/";
        O.path = d.record.path + (U && F + U);
      }
      if (x = Hp(O, d, w), h ? h.alias.push(x) : (N = N || x, N !== x && N.alias.push(x), y && f.name && !wa(x) && i(f.name)), Mc(x) && l(x), v.children) {
        const ve = v.children;
        for (let F = 0; F < ve.length; F++) o(ve[F], x, h && h.children[F]);
      }
      h = h || x;
    }
    return N ? () => {
      i(N);
    } : ws;
  }
  function i(f) {
    if (Ic(f)) {
      const d = s.get(f);
      d && (s.delete(f), n.splice(n.indexOf(d), 1), d.children.forEach(i), d.alias.forEach(i));
    } else {
      const d = n.indexOf(f);
      d > -1 && (n.splice(d, 1), f.record.name && s.delete(f.record.name), f.children.forEach(i), f.alias.forEach(i));
    }
  }
  function a() {
    return n;
  }
  function l(f) {
    const d = Kp(f, n);
    n.splice(d, 0, f), f.record.name && !wa(f) && s.set(f.record.name, f);
  }
  function c(f, d) {
    let h, y = {}, v, w;
    if ("name" in f && f.name) {
      if (h = s.get(f.name), !h) throw Qn(Pe.MATCHER_NOT_FOUND, { location: f });
      w = h.record.name, y = Oe(_a(d.params, h.keys.filter((N) => !N.optional).concat(h.parent ? h.parent.keys.filter((N) => N.optional) : []).map((N) => N.name)), f.params && _a(f.params, h.keys.map((N) => N.name))), v = h.stringify(y);
    } else if (f.path != null)
      v = f.path, h = n.find((N) => N.re.test(v)), h && (y = h.parse(v), w = h.record.name);
    else {
      if (h = d.name ? s.get(d.name) : n.find((N) => N.re.test(d.path)), !h) throw Qn(Pe.MATCHER_NOT_FOUND, {
        location: f,
        currentLocation: d
      });
      w = h.record.name, y = Oe({}, d.params, f.params), v = h.stringify(y);
    }
    const R = [];
    let x = h;
    for (; x; )
      R.unshift(x.record), x = x.parent;
    return {
      name: w,
      path: v,
      params: y,
      matched: R,
      meta: Gp(R)
    };
  }
  e.forEach((f) => o(f));
  function u() {
    n.length = 0, s.clear();
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
function _a(e, t) {
  const n = {};
  for (const s of t) s in e && (n[s] = e[s]);
  return n;
}
function xa(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: Zp(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function Zp(e) {
  const t = {}, n = e.props || !1;
  if ("component" in e) t.default = n;
  else for (const s in e.components) t[s] = typeof n == "object" ? n[s] : n;
  return t;
}
function wa(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function Gp(e) {
  return e.reduce((t, n) => Oe(t, n.meta), {});
}
function Kp(e, t) {
  let n = 0, s = t.length;
  for (; n !== s; ) {
    const o = n + s >> 1;
    Nc(e, t[o]) < 0 ? s = o : n = o + 1;
  }
  const r = Jp(e);
  return r && (s = t.lastIndexOf(r, s - 1)), s;
}
function Jp(e) {
  let t = e;
  for (; t = t.parent; ) if (Mc(t) && Nc(e, t) === 0) return t;
}
function Mc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function ka(e) {
  const t = ot(zr), n = ot(vi), s = ue(() => {
    const l = C(e.to);
    return t.resolve(l);
  }), r = ue(() => {
    const { matched: l } = s.value, { length: c } = l, u = l[c - 1], f = n.matched;
    if (!u || !f.length) return -1;
    const d = f.findIndex(Yn.bind(null, u));
    if (d > -1) return d;
    const h = Sa(l[c - 2]);
    return c > 1 && Sa(u) === h && f[f.length - 1].path !== h ? f.findIndex(Yn.bind(null, l[c - 2])) : d;
  }), o = ue(() => r.value > -1 && eh(n.params, s.value.params)), i = ue(() => r.value > -1 && r.value === n.matched.length - 1 && Tc(n.params, s.value.params));
  function a(l = {}) {
    if (Xp(l)) {
      const c = t[C(e.replace) ? "replace" : "push"](C(e.to)).catch(ws);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: s,
    href: ue(() => s.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function Yp(e) {
  return e.length === 1 ? e[0] : e;
}
const Qp = /* @__PURE__ */ ke({
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
  useLink: ka,
  setup(e, { slots: t }) {
    const n = /* @__PURE__ */ jn(ka(e)), { options: s } = ot(zr), r = ue(() => ({
      [Ea(e.activeClass, s.linkActiveClass, "router-link-active")]: n.isActive,
      [Ea(e.exactActiveClass, s.linkExactActiveClass, "router-link-exact-active")]: n.isExactActive
    }));
    return () => {
      const o = t.default && Yp(t.default(n));
      return e.custom ? o : en("a", {
        "aria-current": n.isExactActive ? e.ariaCurrentValue : null,
        href: n.href,
        onClick: n.navigate,
        class: r.value
      }, o);
    };
  }
}), Dc = Qp;
function Xp(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function eh(e, t) {
  for (const n in t) {
    const s = t[n], r = e[n];
    if (typeof s == "string") {
      if (s !== r) return !1;
    } else if (!Et(r) || r.length !== s.length || s.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function Sa(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const Ea = (e, t, n) => e ?? t ?? n, th = /* @__PURE__ */ ke({
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
  setup(e, { attrs: t, slots: n }) {
    const s = ot(zo), r = ue(() => e.route || s.value), o = ot(ya, 0), i = ue(() => {
      let c = C(o);
      const { matched: u } = r.value;
      let f;
      for (; (f = u[c]) && !f.components; ) c++;
      return c;
    }), a = ue(() => r.value.matched[i.value]);
    vs(ya, ue(() => i.value + 1)), vs(Mp, a), vs(zo, r);
    const l = /* @__PURE__ */ oe();
    return je(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, f], [d, h, y]) => {
      u && (u.instances[f] = c, h && h !== u && c && c === d && (u.leaveGuards.size || (u.leaveGuards = h.leaveGuards), u.updateGuards.size || (u.updateGuards = h.updateGuards))), c && u && (!h || !Yn(u, h) || !d) && (u.enterCallbacks[f] || []).forEach((v) => v(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, f = a.value, d = f && f.components[u];
      if (!d) return Ca(n.default, {
        Component: d,
        route: c
      });
      const h = f.props[u], y = h ? h === !0 ? c.params : typeof h == "function" ? h(c) : h : null, w = en(d, Oe({}, y, t, {
        onVnodeUnmounted: (R) => {
          R.component.isUnmounted && (f.instances[u] = null);
        },
        ref: l
      }));
      return Ca(n.default, {
        Component: w,
        route: c
      }) || w;
    };
  }
});
function Ca(e, t) {
  if (!e) return null;
  const n = e(t);
  return n.length === 1 ? n[0] : n;
}
const Lc = th;
function nh(e) {
  const t = qp(e.routes, e), n = e.parseQuery || Pp, s = e.stringifyQuery || ga, r = e.history, o = cs(), i = cs(), a = cs(), l = /* @__PURE__ */ Zn(on);
  let c = on;
  Hn && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = so.bind(null, (k) => "" + k), f = so.bind(null, hp), d = so.bind(null, Is);
  function h(k, B) {
    let I, J;
    return Ic(k) ? (I = t.getRecordMatcher(k), J = B) : J = k, t.addRoute(J, I);
  }
  function y(k) {
    const B = t.getRecordMatcher(k);
    B && t.removeRoute(B);
  }
  function v() {
    return t.getRoutes().map((k) => k.record);
  }
  function w(k) {
    return !!t.getRecordMatcher(k);
  }
  function R(k, B) {
    if (B = Oe({}, B || l.value), typeof k == "string") {
      const b = ro(n, k, B.path), _ = t.resolve({ path: b.path }, B), E = r.createHref(b.fullPath);
      return Oe(b, _, {
        params: d(_.params),
        hash: Is(b.hash),
        redirectedFrom: void 0,
        href: E
      });
    }
    let I;
    if (k.path != null)
      I = Oe({}, k, { path: ro(n, k.path, B.path).path });
    else {
      const b = Oe({}, k.params);
      for (const _ in b) b[_] == null && delete b[_];
      I = Oe({}, k, { params: f(b) }), B.params = f(B.params);
    }
    const J = t.resolve(I, B), p = k.hash || "";
    J.params = u(d(J.params));
    const m = yp(s, Oe({}, k, {
      hash: fp(p),
      path: J.path
    })), g = r.createHref(m);
    return Oe({
      fullPath: m,
      hash: p,
      query: s === ga ? Np(k.query) : k.query || {}
    }, J, {
      redirectedFrom: void 0,
      href: g
    });
  }
  function x(k) {
    return typeof k == "string" ? ro(n, k, l.value.path) : Oe({}, k);
  }
  function N(k, B) {
    if (c !== k) return Qn(Pe.NAVIGATION_CANCELLED, {
      from: B,
      to: k
    });
  }
  function O(k) {
    return F(k);
  }
  function U(k) {
    return O(Oe(x(k), { replace: !0 }));
  }
  function ve(k, B) {
    const I = k.matched[k.matched.length - 1];
    if (I && I.redirect) {
      const { redirect: J } = I;
      let p = typeof J == "function" ? J(k, B) : J;
      return typeof p == "string" && (p = p.includes("?") || p.includes("#") ? p = x(p) : { path: p }, p.params = {}), Oe({
        query: k.query,
        hash: k.hash,
        params: p.path != null ? {} : k.params
      }, p);
    }
  }
  function F(k, B) {
    const I = c = R(k), J = l.value, p = k.state, m = k.force, g = k.replace === !0, b = ve(I, J);
    if (b) return F(Oe(x(b), {
      state: typeof b == "object" ? Oe({}, p, b.state) : p,
      force: m,
      replace: g
    }), B || I);
    const _ = I;
    _.redirectedFrom = B;
    let E;
    return !m && vp(s, J, I) && (E = Qn(Pe.NAVIGATION_DUPLICATED, {
      to: _,
      from: J
    }), lt(J, J, !0, !1)), (E ? Promise.resolve(E) : pe(_, J)).catch((T) => qt(T) ? qt(T, Pe.NAVIGATION_GUARD_REDIRECT) ? T : q(T) : de(T, _, J)).then((T) => {
      if (T) {
        if (qt(T, Pe.NAVIGATION_GUARD_REDIRECT))
          return F(Oe({ replace: g }, x(T.to), {
            state: typeof T.to == "object" ? Oe({}, p, T.to.state) : p,
            force: m
          }), B || _);
      } else T = Te(_, J, !0, g, p);
      return Ae(_, J, T), T;
    });
  }
  function S(k, B) {
    const I = N(k, B);
    return I ? Promise.reject(I) : Promise.resolve();
  }
  function j(k) {
    const B = _t.values().next().value;
    return B && typeof B.runWithContext == "function" ? B.runWithContext(k) : k();
  }
  function pe(k, B) {
    let I;
    const [J, p, m] = Dp(k, B);
    I = io(J.reverse(), "beforeRouteLeave", k, B);
    for (const b of J) b.leaveGuards.forEach((_) => {
      I.push(dn(_, k, B));
    });
    const g = S.bind(null, k, B);
    return I.push(g), xe(I).then(() => {
      I = [];
      for (const b of o.list()) I.push(dn(b, k, B));
      return I.push(g), xe(I);
    }).then(() => {
      I = io(p, "beforeRouteUpdate", k, B);
      for (const b of p) b.updateGuards.forEach((_) => {
        I.push(dn(_, k, B));
      });
      return I.push(g), xe(I);
    }).then(() => {
      I = [];
      for (const b of m) if (b.beforeEnter) if (Et(b.beforeEnter)) for (const _ of b.beforeEnter) I.push(dn(_, k, B));
      else I.push(dn(b.beforeEnter, k, B));
      return I.push(g), xe(I);
    }).then(() => (k.matched.forEach((b) => b.enterCallbacks = {}), I = io(m, "beforeRouteEnter", k, B, j), I.push(g), xe(I))).then(() => {
      I = [];
      for (const b of i.list()) I.push(dn(b, k, B));
      return I.push(g), xe(I);
    }).catch((b) => qt(b, Pe.NAVIGATION_CANCELLED) ? b : Promise.reject(b));
  }
  function Ae(k, B, I) {
    a.list().forEach((J) => j(() => J(k, B, I)));
  }
  function Te(k, B, I, J, p) {
    const m = N(k, B);
    if (m) return m;
    const g = B === on, b = Hn ? history.state : {};
    I && (J || g ? r.replace(k.fullPath, Oe({ scroll: g && b && b.scroll }, p)) : r.push(k.fullPath, p)), l.value = k, lt(k, B, I, g), q();
  }
  let $e;
  function Xe() {
    $e || ($e = r.listen((k, B, I) => {
      if (!Ie.listening) return;
      const J = R(k), p = ve(J, Ie.currentRoute.value);
      if (p) {
        F(Oe(p, {
          replace: !0,
          force: !0
        }), J).catch(ws);
        return;
      }
      c = J;
      const m = l.value;
      Hn && Ap(ma(m.fullPath, I.delta), Ep()), pe(J, m).catch((g) => qt(g, Pe.NAVIGATION_ABORTED | Pe.NAVIGATION_CANCELLED) ? g : qt(g, Pe.NAVIGATION_GUARD_REDIRECT) ? (F(Oe(x(g.to), { force: !0 }), J).then((b) => {
        qt(b, Pe.NAVIGATION_ABORTED | Pe.NAVIGATION_DUPLICATED) && !I.delta && I.type === Vo.pop && r.go(-1, !1);
      }).catch(ws), Promise.reject()) : (I.delta && r.go(-I.delta, !1), de(g, J, m))).then((g) => {
        g = g || Te(J, m, !1), g && (I.delta && !qt(g, Pe.NAVIGATION_CANCELLED) ? r.go(-I.delta, !1) : I.type === Vo.pop && qt(g, Pe.NAVIGATION_ABORTED | Pe.NAVIGATION_DUPLICATED) && r.go(-1, !1)), Ae(J, m, g);
      }).catch(ws);
    }));
  }
  let et = cs(), ce = cs(), X;
  function de(k, B, I) {
    q(k);
    const J = ce.list();
    return J.length ? J.forEach((p) => p(k, B, I)) : console.error(k), Promise.reject(k);
  }
  function at() {
    return X && l.value !== on ? Promise.resolve() : new Promise((k, B) => {
      et.add([k, B]);
    });
  }
  function q(k) {
    return X || (X = !k, Xe(), et.list().forEach(([B, I]) => k ? I(k) : B()), et.reset()), k;
  }
  function lt(k, B, I, J) {
    const { scrollBehavior: p } = e;
    if (!Hn || !p) return Promise.resolve();
    const m = !I && Op(ma(k.fullPath, 0)) || (J || !I) && history.state && history.state.scroll || null;
    return St().then(() => p(k, B, m)).then((g) => g && Cp(g)).catch((g) => de(g, k, B));
  }
  const Ue = (k) => r.go(k);
  let Wt;
  const _t = /* @__PURE__ */ new Set(), Ie = {
    currentRoute: l,
    listening: !0,
    addRoute: h,
    removeRoute: y,
    clearRoutes: t.clearRoutes,
    hasRoute: w,
    getRoutes: v,
    resolve: R,
    options: e,
    push: O,
    replace: U,
    go: Ue,
    back: () => Ue(-1),
    forward: () => Ue(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: ce.add,
    isReady: at,
    install(k) {
      k.component("RouterLink", Dc), k.component("RouterView", Lc), k.config.globalProperties.$router = Ie, Object.defineProperty(k.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => C(l)
      }), Hn && !Wt && l.value === on && (Wt = !0, O(r.location).catch((J) => {
      }));
      const B = {};
      for (const J in on) Object.defineProperty(B, J, {
        get: () => l.value[J],
        enumerable: !0
      });
      k.provide(zr, Ie), k.provide(vi, /* @__PURE__ */ Tl(B)), k.provide(zo, l);
      const I = k.unmount;
      _t.add(k), k.unmount = function() {
        _t.delete(k), _t.size < 1 && (c = on, $e && $e(), $e = null, l.value = on, Wt = !1, X = !1), I();
      };
    }
  };
  function xe(k) {
    return k.reduce((B, I) => B.then(() => j(I)), Promise.resolve());
  }
  return Ie;
}
function sh() {
  return ot(zr);
}
function rh(e) {
  return ot(vi);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const En = {
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
const Aa = (...e) => e.filter((t, n, s) => !!t && t.trim() !== "" && s.indexOf(t) === n).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function ao(e) {
  return e != null;
}
function oh(e, t = {}) {
  const n = t.attributeNames ?? {}, s = (d) => n[d] ?? d, r = e.size ?? e.width ?? En.width, o = e.size ?? e.height ?? En.height, i = e.aliases?.filter((d) => typeof d == "string" && d.trim() !== "").map((d) => `lucide-${d}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? Aa(...l) : Aa("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? En["stroke-width"]) * Number(e.size ?? e.width ?? En.width) / Number(t.size ?? t.width ?? En.width) : t.strokeWidth ?? En["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(En).reduce((d, [h, y]) => (d[s(h)] = y, d), {}),
      ..."color" in t && t.color && {
        [s("stroke")]: t.color
      },
      ..."size" in t && ao(t.size) && {
        [s("width")]: t.size,
        [s("height")]: t.size
      },
      ..."width" in t && ao(t.width) && {
        [s("width")]: t.width
      },
      ..."height" in t && ao(t.height) && {
        [s("height")]: t.height
      },
      [s("stroke-width")]: u,
      ...c && {
        [s("class")]: c
      },
      [s("viewBox")]: `0 0 ${r} ${o}`,
      ...t.hasA11yProp === !1 ? {
        [s("aria-hidden")]: "true"
      } : {},
      ..."attributes" in t && t.attributes
    },
    e.node.map((d) => {
      const [h, y, v] = d, w = t.nonScalingStroke ? { [s("vector-effect")]: "non-scaling-stroke", ...y } : y;
      return v ? [h, w, v] : [h, w];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ih = (e) => {
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
const Zs = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ah = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const lh = /* @__PURE__ */ Symbol("lucide-icons");
function ch() {
  return ot(lh, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const uh = ({
  name: e,
  iconNode: t,
  "icon-node": n,
  icon: s = {
    name: e && ah(e),
    node: t ?? n ?? [],
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
  width: f = u,
  height: d = u,
  color: h,
  ...y
}, { slots: v }) => {
  const {
    size: w,
    color: R,
    strokeWidth: x = 2,
    absoluteStrokeWidth: N = !1,
    nonScalingStroke: O = !1,
    class: U = ""
  } = ch(), ve = Zs(r) || Zs(o) || r === !0 || o === !0 || N === !0, F = Zs(i) || Zs(a) || i === !0 || a === !0 || O === !0;
  delete y.class;
  const S = v.default?.(), [, j, pe = []] = oh(s, {
    color: h ?? R,
    width: f ?? u ?? w,
    height: d ?? u ?? w,
    strokeWidth: l ?? c ?? x,
    absoluteStrokeWidth: ve,
    nonScalingStroke: F,
    className: U,
    hasA11yProp: S != null && S.length > 0 || ih(y),
    attributes: y
  });
  return en("svg", j, [
    ...pe.map(([Ae, Te]) => en(Ae, Te)),
    ...S ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function xn(e, t = []) {
  const n = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (s, { slots: r }) => en(
    uh,
    {
      ...s,
      icon: n
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
const fh = {
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
}, jc = xn(fh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const dh = {
  name: "info",
  size: 24,
  node: [
    ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
    ["path", { d: "M12 16v-4", key: "1dtifu" }],
    ["path", { d: "M12 8h.01", key: "e9boi3" }]
  ]
}, ph = xn(dh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const hh = {
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
}, $c = xn(hh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const mh = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, gh = xn(mh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const yh = {
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
}, vh = xn(yh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const bh = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, Fc = xn(bh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const _h = {
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
}, Vc = xn(_h);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const xh = {
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
}, Bc = xn(xh);
function wh(e) {
  return Ir() ? (ei(e), !0) : !1;
}
const lo = /* @__PURE__ */ new WeakMap(), kh = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const n = e[0], s = (t = Ct()) == null ? void 0 : t.proxy;
  if (s == null && !ui())
    throw new Error("injectLocal must be called in setup");
  return s && lo.has(s) && n in lo.get(s) ? lo.get(s)[n] : ot(...e);
}, Sh = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const Eh = Object.prototype.toString, Ch = (e) => Eh.call(e) === "[object Object]";
function Oa(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function co(e) {
  return Array.isArray(e) ? e : [e];
}
function Ah(e, t, n) {
  return je(
    e,
    t,
    {
      ...n,
      immediate: !0
    }
  );
}
const zc = Sh ? window : void 0;
function Oh(e) {
  var t;
  const n = Qe(e);
  return (t = n?.$el) != null ? t : n;
}
function Rh(...e) {
  const t = [], n = () => {
    t.forEach((a) => a()), t.length = 0;
  }, s = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = ue(() => {
    const a = co(Qe(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = Ah(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => Oh(c))) != null ? l : [zc].filter((c) => c != null),
        co(Qe(r.value ? e[1] : e[0])),
        co(C(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Qe(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (n(), !a?.length || !l?.length || !c?.length)
        return;
      const f = Ch(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (d) => l.flatMap(
            (h) => c.map((y) => s(d, h, y, f))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), n();
  };
  return wh(n), i;
}
// @__NO_SIDE_EFFECTS__
function Th() {
  const e = /* @__PURE__ */ Zn(!1), t = Ct();
  return t && ss(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function Ih(e) {
  const t = /* @__PURE__ */ Th();
  return ue(() => (t.value, !!e()));
}
const Ph = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function Nh() {
  const e = ui() ? /* @__PURE__ */ kh(Ph, null) : null;
  return typeof e == "number" ? e : void 0;
}
function Mh(e, t = {}) {
  const { window: n = zc, ssrWidth: s = /* @__PURE__ */ Nh() } = t, r = /* @__PURE__ */ Ih(() => n && "matchMedia" in n && typeof n.matchMedia == "function"), o = /* @__PURE__ */ Zn(typeof s == "number"), i = /* @__PURE__ */ Zn(), a = /* @__PURE__ */ Zn(!1), l = (c) => {
    a.value = c.matches;
  };
  return Kn(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Qe(e).split(",");
      a.value = c.some((u) => {
        const f = u.includes("not all"), d = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), h = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let y = !!(d || h);
        return d && y && (y = s >= Oa(d[1])), h && y && (y = s <= Oa(h[1])), f ? !y : y;
      });
      return;
    }
    r.value && (i.value = n.matchMedia(Qe(e)), a.value = i.value.matches);
  }), Rh(i, "change", l, { passive: !0 }), ue(() => a.value);
}
const Uc = "comfymodal", bi = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], Dh = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function vn(e) {
  return typeof e == "string" && bi.indexOf(e) !== -1;
}
function Gs(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function Wc(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const n = e.charAt(0) === "#" ? e.slice(1) : e;
  if (n === "") return t;
  const s = n.split("&"), r = s[0], o = r.indexOf("=");
  if (o === -1 || Gs(r.slice(0, o)) !== Uc) return t;
  const i = Gs(r.slice(o + 1));
  if (!vn(i)) return t;
  let a = null;
  for (let l = 1; l < s.length; l++) {
    const c = s[l], u = c.indexOf("=");
    if (u === -1 || Gs(c.slice(0, u)) !== "focus") continue;
    const f = Gs(c.slice(u + 1));
    a = f === null || f === "" ? null : f;
    break;
  }
  return { matched: !0, page: i, focus: a };
}
function Hc(e) {
  if (!vn(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + Uc + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function Ra(e, t) {
  if (!t || !vn(t.page)) return "none";
  if (!e || !vn(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const n = e.focus || null, s = t.focus || null;
  return n === s ? "none" : "replace";
}
function Lh(e, t) {
  if (e && vn(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const n = Wc(t);
  return n.matched && vn(n.page) ? { page: n.page, focus: n.focus } : { page: "playground", focus: null };
}
const jh = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function uo(e) {
  return jh.has(e);
}
let Ta = 0;
function $h() {
  return Ta += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${Ta}`;
}
const qc = /* @__PURE__ */ rs("studio-operations", () => {
  const e = /* @__PURE__ */ oe(/* @__PURE__ */ new Map()), t = ue(() => [...e.value.values()]), n = ue(
    () => t.value.filter((d) => d.status === "pending" || d.status === "running")
  );
  function s(d) {
    return e.value.get(d);
  }
  function r(d) {
    const h = Date.now(), y = $h();
    return e.value.set(y, {
      id: y,
      kind: d.kind,
      label: d.label,
      status: d.status ?? "running",
      progress: d.progress,
      message: d.message,
      startedAt: h,
      finishedAt: void 0,
      workspaceId: d.workspaceId
    }), y;
  }
  function o(d, h) {
    const y = e.value.get(d);
    if (!y) return;
    const { status: v, ...w } = h, R = { ...y, ...w };
    !uo(y.status) && v !== void 0 && !uo(v) && (R.status = v), e.value.set(d, R);
  }
  function i(d, h, y) {
    const v = e.value.get(d);
    !v || uo(v.status) || e.value.set(d, {
      ...v,
      status: h,
      message: y === void 0 ? v.message : y,
      finishedAt: Date.now()
    });
  }
  function a(d, h) {
    i(d, "completed", h);
  }
  function l(d, h) {
    i(d, "failed", h);
  }
  function c(d, h) {
    i(d, "canceled", h);
  }
  function u(d) {
    e.value.delete(d);
  }
  function f() {
    e.value.clear();
  }
  return {
    byId: e,
    all: t,
    active: n,
    get: s,
    start: r,
    patch: o,
    finish: a,
    fail: l,
    cancel: c,
    remove: u,
    clear: f
  };
});
var ye;
(function(e) {
  e.assertEqual = (r) => {
  };
  function t(r) {
  }
  e.assertIs = t;
  function n(r) {
    throw new Error();
  }
  e.assertNever = n, e.arrayToEnum = (r) => {
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
  function s(r, o = " | ") {
    return r.map((i) => typeof i == "string" ? `'${i}'` : i).join(o);
  }
  e.joinValues = s, e.jsonStringifyReplacer = (r, o) => typeof o == "bigint" ? o.toString() : o;
})(ye || (ye = {}));
var Ia;
(function(e) {
  e.mergeShapes = (t, n) => ({
    ...t,
    ...n
    // second overwrites first
  });
})(Ia || (Ia = {}));
const W = ye.arrayToEnum([
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
]), pn = (e) => {
  switch (typeof e) {
    case "undefined":
      return W.undefined;
    case "string":
      return W.string;
    case "number":
      return Number.isNaN(e) ? W.nan : W.number;
    case "boolean":
      return W.boolean;
    case "function":
      return W.function;
    case "bigint":
      return W.bigint;
    case "symbol":
      return W.symbol;
    case "object":
      return Array.isArray(e) ? W.array : e === null ? W.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? W.promise : typeof Map < "u" && e instanceof Map ? W.map : typeof Set < "u" && e instanceof Set ? W.set : typeof Date < "u" && e instanceof Date ? W.date : W.object;
    default:
      return W.unknown;
  }
}, P = ye.arrayToEnum([
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
class tn extends Error {
  get errors() {
    return this.issues;
  }
  constructor(t) {
    super(), this.issues = [], this.addIssue = (s) => {
      this.issues = [...this.issues, s];
    }, this.addIssues = (s = []) => {
      this.issues = [...this.issues, ...s];
    };
    const n = new.target.prototype;
    Object.setPrototypeOf ? Object.setPrototypeOf(this, n) : this.__proto__ = n, this.name = "ZodError", this.issues = t;
  }
  format(t) {
    const n = t || function(o) {
      return o.message;
    }, s = { _errors: [] }, r = (o) => {
      for (const i of o.issues)
        if (i.code === "invalid_union")
          i.unionErrors.map(r);
        else if (i.code === "invalid_return_type")
          r(i.returnTypeError);
        else if (i.code === "invalid_arguments")
          r(i.argumentsError);
        else if (i.path.length === 0)
          s._errors.push(n(i));
        else {
          let a = s, l = 0;
          for (; l < i.path.length; ) {
            const c = i.path[l];
            l === i.path.length - 1 ? (a[c] = a[c] || { _errors: [] }, a[c]._errors.push(n(i))) : a[c] = a[c] || { _errors: [] }, a = a[c], l++;
          }
        }
    };
    return r(this), s;
  }
  static assert(t) {
    if (!(t instanceof tn))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, ye.jsonStringifyReplacer, 2);
  }
  get isEmpty() {
    return this.issues.length === 0;
  }
  flatten(t = (n) => n.message) {
    const n = {}, s = [];
    for (const r of this.issues)
      if (r.path.length > 0) {
        const o = r.path[0];
        n[o] = n[o] || [], n[o].push(t(r));
      } else
        s.push(t(r));
    return { formErrors: s, fieldErrors: n };
  }
  get formErrors() {
    return this.flatten();
  }
}
tn.create = (e) => new tn(e);
const Uo = (e, t) => {
  let n;
  switch (e.code) {
    case P.invalid_type:
      e.received === W.undefined ? n = "Required" : n = `Expected ${e.expected}, received ${e.received}`;
      break;
    case P.invalid_literal:
      n = `Invalid literal value, expected ${JSON.stringify(e.expected, ye.jsonStringifyReplacer)}`;
      break;
    case P.unrecognized_keys:
      n = `Unrecognized key(s) in object: ${ye.joinValues(e.keys, ", ")}`;
      break;
    case P.invalid_union:
      n = "Invalid input";
      break;
    case P.invalid_union_discriminator:
      n = `Invalid discriminator value. Expected ${ye.joinValues(e.options)}`;
      break;
    case P.invalid_enum_value:
      n = `Invalid enum value. Expected ${ye.joinValues(e.options)}, received '${e.received}'`;
      break;
    case P.invalid_arguments:
      n = "Invalid function arguments";
      break;
    case P.invalid_return_type:
      n = "Invalid function return type";
      break;
    case P.invalid_date:
      n = "Invalid date";
      break;
    case P.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (n = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (n = `${n} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? n = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? n = `Invalid input: must end with "${e.validation.endsWith}"` : ye.assertNever(e.validation) : e.validation !== "regex" ? n = `Invalid ${e.validation}` : n = "Invalid";
      break;
    case P.too_small:
      e.type === "array" ? n = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? n = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? n = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? n = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? n = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : n = "Invalid input";
      break;
    case P.too_big:
      e.type === "array" ? n = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? n = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? n = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? n = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? n = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : n = "Invalid input";
      break;
    case P.custom:
      n = "Invalid input";
      break;
    case P.invalid_intersection_types:
      n = "Intersection results could not be merged";
      break;
    case P.not_multiple_of:
      n = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case P.not_finite:
      n = "Number must be finite";
      break;
    default:
      n = t.defaultError, ye.assertNever(e);
  }
  return { message: n };
};
let Fh = Uo;
function Vh() {
  return Fh;
}
const Bh = (e) => {
  const { data: t, path: n, errorMaps: s, issueData: r } = e, o = [...n, ...r.path || []], i = {
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
  const l = s.filter((c) => !!c).slice().reverse();
  for (const c of l)
    a = c(i, { data: t, defaultError: a }).message;
  return {
    ...r,
    path: o,
    message: a
  };
};
function $(e, t) {
  const n = Vh(), s = Bh({
    issueData: t,
    data: e.data,
    path: e.path,
    errorMaps: [
      e.common.contextualErrorMap,
      // contextual error map is first priority
      e.schemaErrorMap,
      // then schema-bound map if available
      n,
      // then global override map
      n === Uo ? void 0 : Uo
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(s);
}
class ht {
  constructor() {
    this.value = "valid";
  }
  dirty() {
    this.value === "valid" && (this.value = "dirty");
  }
  abort() {
    this.value !== "aborted" && (this.value = "aborted");
  }
  static mergeArray(t, n) {
    const s = [];
    for (const r of n) {
      if (r.status === "aborted")
        return ne;
      r.status === "dirty" && t.dirty(), s.push(r.value);
    }
    return { status: t.value, value: s };
  }
  static async mergeObjectAsync(t, n) {
    const s = [];
    for (const r of n) {
      const o = await r.key, i = await r.value;
      s.push({
        key: o,
        value: i
      });
    }
    return ht.mergeObjectSync(t, s);
  }
  static mergeObjectSync(t, n) {
    const s = {};
    for (const r of n) {
      const { key: o, value: i } = r;
      if (o.status === "aborted" || i.status === "aborted")
        return ne;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (s[o.value] = i.value);
    }
    return { status: t.value, value: s };
  }
}
const ne = Object.freeze({
  status: "aborted"
}), hs = (e) => ({ status: "dirty", value: e }), vt = (e) => ({ status: "valid", value: e }), Pa = (e) => e.status === "aborted", Na = (e) => e.status === "dirty", Xn = (e) => e.status === "valid", gr = (e) => typeof Promise < "u" && e instanceof Promise;
var Z;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(Z || (Z = {}));
class bn {
  constructor(t, n, s, r) {
    this._cachedPath = [], this.parent = t, this.data = n, this._path = s, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const Ma = (e, t) => {
  if (Xn(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const n = new tn(e.common.issues);
      return this._error = n, this._error;
    }
  };
};
function ae(e) {
  if (!e)
    return {};
  const { errorMap: t, invalid_type_error: n, required_error: s, description: r } = e;
  if (t && (n || s))
    throw new Error(`Can't use "invalid_type_error" or "required_error" in conjunction with custom error map.`);
  return t ? { errorMap: t, description: r } : { errorMap: (i, a) => {
    const { message: l } = e;
    return i.code === "invalid_enum_value" ? { message: l ?? a.defaultError } : typeof a.data > "u" ? { message: l ?? s ?? a.defaultError } : i.code !== "invalid_type" ? { message: a.defaultError } : { message: l ?? n ?? a.defaultError };
  }, description: r };
}
class me {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return pn(t.data);
  }
  _getOrReturnCtx(t, n) {
    return n || {
      common: t.parent.common,
      data: t.data,
      parsedType: pn(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new ht(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: pn(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const n = this._parse(t);
    if (gr(n))
      throw new Error("Synchronous parse encountered promise.");
    return n;
  }
  _parseAsync(t) {
    const n = this._parse(t);
    return Promise.resolve(n);
  }
  parse(t, n) {
    const s = this.safeParse(t, n);
    if (s.success)
      return s.data;
    throw s.error;
  }
  safeParse(t, n) {
    const s = {
      common: {
        issues: [],
        async: n?.async ?? !1,
        contextualErrorMap: n?.errorMap
      },
      path: n?.path || [],
      schemaErrorMap: this._def.errorMap,
      parent: null,
      data: t,
      parsedType: pn(t)
    }, r = this._parseSync({ data: t, path: s.path, parent: s });
    return Ma(s, r);
  }
  "~validate"(t) {
    const n = {
      common: {
        issues: [],
        async: !!this["~standard"].async
      },
      path: [],
      schemaErrorMap: this._def.errorMap,
      parent: null,
      data: t,
      parsedType: pn(t)
    };
    if (!this["~standard"].async)
      try {
        const s = this._parseSync({ data: t, path: [], parent: n });
        return Xn(s) ? {
          value: s.value
        } : {
          issues: n.common.issues
        };
      } catch (s) {
        s?.message?.toLowerCase()?.includes("encountered") && (this["~standard"].async = !0), n.common = {
          issues: [],
          async: !0
        };
      }
    return this._parseAsync({ data: t, path: [], parent: n }).then((s) => Xn(s) ? {
      value: s.value
    } : {
      issues: n.common.issues
    });
  }
  async parseAsync(t, n) {
    const s = await this.safeParseAsync(t, n);
    if (s.success)
      return s.data;
    throw s.error;
  }
  async safeParseAsync(t, n) {
    const s = {
      common: {
        issues: [],
        contextualErrorMap: n?.errorMap,
        async: !0
      },
      path: n?.path || [],
      schemaErrorMap: this._def.errorMap,
      parent: null,
      data: t,
      parsedType: pn(t)
    }, r = this._parse({ data: t, path: s.path, parent: s }), o = await (gr(r) ? r : Promise.resolve(r));
    return Ma(s, o);
  }
  refine(t, n) {
    const s = (r) => typeof n == "string" || typeof n > "u" ? { message: n } : typeof n == "function" ? n(r) : n;
    return this._refinement((r, o) => {
      const i = t(r), a = () => o.addIssue({
        code: P.custom,
        ...s(r)
      });
      return typeof Promise < "u" && i instanceof Promise ? i.then((l) => l ? !0 : (a(), !1)) : i ? !0 : (a(), !1);
    });
  }
  refinement(t, n) {
    return this._refinement((s, r) => t(s) ? !0 : (r.addIssue(typeof n == "function" ? n(s, r) : n), !1));
  }
  _refinement(t) {
    return new ts({
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
      validate: (n) => this["~validate"](n)
    };
  }
  optional() {
    return mn.create(this, this._def);
  }
  nullable() {
    return ns.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return Ft.create(this);
  }
  promise() {
    return _r.create(this, this._def);
  }
  or(t) {
    return vr.create([this, t], this._def);
  }
  and(t) {
    return br.create(this, t, this._def);
  }
  transform(t) {
    return new ts({
      ...ae(this._def),
      schema: this,
      typeName: se.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const n = typeof t == "function" ? t : () => t;
    return new Ho({
      ...ae(this._def),
      innerType: this,
      defaultValue: n,
      typeName: se.ZodDefault
    });
  }
  brand() {
    return new um({
      typeName: se.ZodBranded,
      type: this,
      ...ae(this._def)
    });
  }
  catch(t) {
    const n = typeof t == "function" ? t : () => t;
    return new qo({
      ...ae(this._def),
      innerType: this,
      catchValue: n,
      typeName: se.ZodCatch
    });
  }
  describe(t) {
    const n = this.constructor;
    return new n({
      ...this._def,
      description: t
    });
  }
  pipe(t) {
    return _i.create(this, t);
  }
  readonly() {
    return Zo.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const zh = /^c[^\s-]{8,}$/i, Uh = /^[0-9a-z]+$/, Wh = /^[0-9A-HJKMNP-TV-Z]{26}$/i, Hh = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, qh = /^[a-z0-9_-]{21}$/i, Zh = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, Gh = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Kh = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, Jh = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let fo;
const Yh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, Qh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, Xh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, em = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, tm = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, nm = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, Zc = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", sm = new RegExp(`^${Zc}$`);
function Gc(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const n = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${n}`;
}
function rm(e) {
  return new RegExp(`^${Gc(e)}$`);
}
function om(e) {
  let t = `${Zc}T${Gc(e)}`;
  const n = [];
  return n.push(e.local ? "Z?" : "Z"), e.offset && n.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${n.join("|")})`, new RegExp(`^${t}$`);
}
function im(e, t) {
  return !!((t === "v4" || !t) && Yh.test(e) || (t === "v6" || !t) && Xh.test(e));
}
function am(e, t) {
  if (!Zh.test(e))
    return !1;
  try {
    const [n] = e.split(".");
    if (!n)
      return !1;
    const s = n.replace(/-/g, "+").replace(/_/g, "/").padEnd(n.length + (4 - n.length % 4) % 4, "="), r = JSON.parse(atob(s));
    return !(typeof r != "object" || r === null || "typ" in r && r?.typ !== "JWT" || !r.alg || t && r.alg !== t);
  } catch {
    return !1;
  }
}
function lm(e, t) {
  return !!((t === "v4" || !t) && Qh.test(e) || (t === "v6" || !t) && em.test(e));
}
class In extends me {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== W.string) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_type,
        expected: W.string,
        received: o.parsedType
      }), ne;
    }
    const s = new ht();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), $(r, {
          code: P.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), s.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), $(r, {
          code: P.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), s.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? $(r, {
          code: P.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && $(r, {
          code: P.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), s.dirty());
      } else if (o.kind === "email")
        Kh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "email",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "emoji")
        fo || (fo = new RegExp(Jh, "u")), fo.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "emoji",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "uuid")
        Hh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "uuid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "nanoid")
        qh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "nanoid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "cuid")
        zh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "cuid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "cuid2")
        Uh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "cuid2",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "ulid")
        Wh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "ulid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), $(r, {
            validation: "url",
            code: P.invalid_string,
            message: o.message
          }), s.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "regex",
        code: P.invalid_string,
        message: o.message
      }), s.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), s.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), s.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), s.dirty()) : o.kind === "datetime" ? om(o).test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: "datetime",
        message: o.message
      }), s.dirty()) : o.kind === "date" ? sm.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: "date",
        message: o.message
      }), s.dirty()) : o.kind === "time" ? rm(o).test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: "time",
        message: o.message
      }), s.dirty()) : o.kind === "duration" ? Gh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "duration",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "ip" ? im(t.data, o.version) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "ip",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "jwt" ? am(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "jwt",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "cidr" ? lm(t.data, o.version) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "cidr",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "base64" ? tm.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "base64",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "base64url" ? nm.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "base64url",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : ye.assertNever(o);
    return { status: s.value, value: t.data };
  }
  _regex(t, n, s) {
    return this.refinement((r) => t.test(r), {
      validation: n,
      code: P.invalid_string,
      ...Z.errToObj(s)
    });
  }
  _addCheck(t) {
    return new In({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...Z.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...Z.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...Z.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...Z.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...Z.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...Z.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...Z.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...Z.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...Z.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...Z.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...Z.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...Z.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...Z.errToObj(t) });
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
      ...Z.errToObj(t?.message)
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
      ...Z.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...Z.errToObj(t) });
  }
  regex(t, n) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...Z.errToObj(n)
    });
  }
  includes(t, n) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: n?.position,
      ...Z.errToObj(n?.message)
    });
  }
  startsWith(t, n) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...Z.errToObj(n)
    });
  }
  endsWith(t, n) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...Z.errToObj(n)
    });
  }
  min(t, n) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...Z.errToObj(n)
    });
  }
  max(t, n) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...Z.errToObj(n)
    });
  }
  length(t, n) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...Z.errToObj(n)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, Z.errToObj(t));
  }
  trim() {
    return new In({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new In({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new In({
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
    for (const n of this._def.checks)
      n.kind === "min" && (t === null || n.value > t) && (t = n.value);
    return t;
  }
  get maxLength() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "max" && (t === null || n.value < t) && (t = n.value);
    return t;
  }
}
In.create = (e) => new In({
  checks: [],
  typeName: se.ZodString,
  coerce: e?.coerce ?? !1,
  ...ae(e)
});
function cm(e, t) {
  const n = (e.toString().split(".")[1] || "").length, s = (t.toString().split(".")[1] || "").length, r = n > s ? n : s, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class Ps extends me {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== W.number) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_type,
        expected: W.number,
        received: o.parsedType
      }), ne;
    }
    let s;
    const r = new ht();
    for (const o of this._def.checks)
      o.kind === "int" ? ye.isInteger(t.data) || (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? cm(t.data, o.value) !== 0 && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.not_finite,
        message: o.message
      }), r.dirty()) : ye.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, n) {
    return this.setLimit("min", t, !0, Z.toString(n));
  }
  gt(t, n) {
    return this.setLimit("min", t, !1, Z.toString(n));
  }
  lte(t, n) {
    return this.setLimit("max", t, !0, Z.toString(n));
  }
  lt(t, n) {
    return this.setLimit("max", t, !1, Z.toString(n));
  }
  setLimit(t, n, s, r) {
    return new Ps({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: n,
          inclusive: s,
          message: Z.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Ps({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  int(t) {
    return this._addCheck({
      kind: "int",
      message: Z.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: Z.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: Z.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: Z.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: Z.toString(t)
    });
  }
  multipleOf(t, n) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: Z.toString(n)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: Z.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: Z.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: Z.toString(t)
    });
  }
  get minValue() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "min" && (t === null || n.value > t) && (t = n.value);
    return t;
  }
  get maxValue() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "max" && (t === null || n.value < t) && (t = n.value);
    return t;
  }
  get isInt() {
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && ye.isInteger(t.value));
  }
  get isFinite() {
    let t = null, n = null;
    for (const s of this._def.checks) {
      if (s.kind === "finite" || s.kind === "int" || s.kind === "multipleOf")
        return !0;
      s.kind === "min" ? (n === null || s.value > n) && (n = s.value) : s.kind === "max" && (t === null || s.value < t) && (t = s.value);
    }
    return Number.isFinite(n) && Number.isFinite(t);
  }
}
Ps.create = (e) => new Ps({
  checks: [],
  typeName: se.ZodNumber,
  coerce: e?.coerce || !1,
  ...ae(e)
});
class Ns extends me {
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
    if (this._getType(t) !== W.bigint)
      return this._getInvalidInput(t);
    let s;
    const r = new ht();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : ye.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const n = this._getOrReturnCtx(t);
    return $(n, {
      code: P.invalid_type,
      expected: W.bigint,
      received: n.parsedType
    }), ne;
  }
  gte(t, n) {
    return this.setLimit("min", t, !0, Z.toString(n));
  }
  gt(t, n) {
    return this.setLimit("min", t, !1, Z.toString(n));
  }
  lte(t, n) {
    return this.setLimit("max", t, !0, Z.toString(n));
  }
  lt(t, n) {
    return this.setLimit("max", t, !1, Z.toString(n));
  }
  setLimit(t, n, s, r) {
    return new Ns({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: n,
          inclusive: s,
          message: Z.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Ns({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: Z.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: Z.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: Z.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: Z.toString(t)
    });
  }
  multipleOf(t, n) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: Z.toString(n)
    });
  }
  get minValue() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "min" && (t === null || n.value > t) && (t = n.value);
    return t;
  }
  get maxValue() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "max" && (t === null || n.value < t) && (t = n.value);
    return t;
  }
}
Ns.create = (e) => new Ns({
  checks: [],
  typeName: se.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...ae(e)
});
class Da extends me {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== W.boolean) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: W.boolean,
        received: s.parsedType
      }), ne;
    }
    return vt(t.data);
  }
}
Da.create = (e) => new Da({
  typeName: se.ZodBoolean,
  coerce: e?.coerce || !1,
  ...ae(e)
});
class yr extends me {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== W.date) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_type,
        expected: W.date,
        received: o.parsedType
      }), ne;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_date
      }), ne;
    }
    const s = new ht();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), s.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), s.dirty()) : ye.assertNever(o);
    return {
      status: s.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new yr({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, n) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: Z.toString(n)
    });
  }
  max(t, n) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: Z.toString(n)
    });
  }
  get minDate() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "min" && (t === null || n.value > t) && (t = n.value);
    return t != null ? new Date(t) : null;
  }
  get maxDate() {
    let t = null;
    for (const n of this._def.checks)
      n.kind === "max" && (t === null || n.value < t) && (t = n.value);
    return t != null ? new Date(t) : null;
  }
}
yr.create = (e) => new yr({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: se.ZodDate,
  ...ae(e)
});
class La extends me {
  _parse(t) {
    if (this._getType(t) !== W.symbol) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: W.symbol,
        received: s.parsedType
      }), ne;
    }
    return vt(t.data);
  }
}
La.create = (e) => new La({
  typeName: se.ZodSymbol,
  ...ae(e)
});
class ja extends me {
  _parse(t) {
    if (this._getType(t) !== W.undefined) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: W.undefined,
        received: s.parsedType
      }), ne;
    }
    return vt(t.data);
  }
}
ja.create = (e) => new ja({
  typeName: se.ZodUndefined,
  ...ae(e)
});
class $a extends me {
  _parse(t) {
    if (this._getType(t) !== W.null) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: W.null,
        received: s.parsedType
      }), ne;
    }
    return vt(t.data);
  }
}
$a.create = (e) => new $a({
  typeName: se.ZodNull,
  ...ae(e)
});
class Fa extends me {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return vt(t.data);
  }
}
Fa.create = (e) => new Fa({
  typeName: se.ZodAny,
  ...ae(e)
});
class Va extends me {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return vt(t.data);
  }
}
Va.create = (e) => new Va({
  typeName: se.ZodUnknown,
  ...ae(e)
});
class _n extends me {
  _parse(t) {
    const n = this._getOrReturnCtx(t);
    return $(n, {
      code: P.invalid_type,
      expected: W.never,
      received: n.parsedType
    }), ne;
  }
}
_n.create = (e) => new _n({
  typeName: se.ZodNever,
  ...ae(e)
});
class Ba extends me {
  _parse(t) {
    if (this._getType(t) !== W.undefined) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: W.void,
        received: s.parsedType
      }), ne;
    }
    return vt(t.data);
  }
}
Ba.create = (e) => new Ba({
  typeName: se.ZodVoid,
  ...ae(e)
});
class Ft extends me {
  _parse(t) {
    const { ctx: n, status: s } = this._processInputParams(t), r = this._def;
    if (n.parsedType !== W.array)
      return $(n, {
        code: P.invalid_type,
        expected: W.array,
        received: n.parsedType
      }), ne;
    if (r.exactLength !== null) {
      const i = n.data.length > r.exactLength.value, a = n.data.length < r.exactLength.value;
      (i || a) && ($(n, {
        code: i ? P.too_big : P.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), s.dirty());
    }
    if (r.minLength !== null && n.data.length < r.minLength.value && ($(n, {
      code: P.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), s.dirty()), r.maxLength !== null && n.data.length > r.maxLength.value && ($(n, {
      code: P.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), s.dirty()), n.common.async)
      return Promise.all([...n.data].map((i, a) => r.type._parseAsync(new bn(n, i, n.path, a)))).then((i) => ht.mergeArray(s, i));
    const o = [...n.data].map((i, a) => r.type._parseSync(new bn(n, i, n.path, a)));
    return ht.mergeArray(s, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, n) {
    return new Ft({
      ...this._def,
      minLength: { value: t, message: Z.toString(n) }
    });
  }
  max(t, n) {
    return new Ft({
      ...this._def,
      maxLength: { value: t, message: Z.toString(n) }
    });
  }
  length(t, n) {
    return new Ft({
      ...this._def,
      exactLength: { value: t, message: Z.toString(n) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Ft.create = (e, t) => new Ft({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: se.ZodArray,
  ...ae(t)
});
function qn(e) {
  if (e instanceof ze) {
    const t = {};
    for (const n in e.shape) {
      const s = e.shape[n];
      t[n] = mn.create(qn(s));
    }
    return new ze({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof Ft ? new Ft({
    ...e._def,
    type: qn(e.element)
  }) : e instanceof mn ? mn.create(qn(e.unwrap())) : e instanceof ns ? ns.create(qn(e.unwrap())) : e instanceof Dn ? Dn.create(e.items.map((t) => qn(t))) : e;
}
class ze extends me {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), n = ye.objectKeys(t);
    return this._cached = { shape: t, keys: n }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== W.object) {
      const c = this._getOrReturnCtx(t);
      return $(c, {
        code: P.invalid_type,
        expected: W.object,
        received: c.parsedType
      }), ne;
    }
    const { status: s, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof _n && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], f = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new bn(r, f, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof _n) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && ($(r, {
          code: P.unrecognized_keys,
          keys: a
        }), s.dirty());
      else if (c !== "strip") throw new Error("Internal ZodObject error: invalid unknownKeys value.");
    } else {
      const c = this._def.catchall;
      for (const u of a) {
        const f = r.data[u];
        l.push({
          key: { status: "valid", value: u },
          value: c._parse(
            new bn(r, f, r.path, u)
            //, ctx.child(key), value, getParsedType(value)
          ),
          alwaysSet: u in r.data
        });
      }
    }
    return r.common.async ? Promise.resolve().then(async () => {
      const c = [];
      for (const u of l) {
        const f = await u.key, d = await u.value;
        c.push({
          key: f,
          value: d,
          alwaysSet: u.alwaysSet
        });
      }
      return c;
    }).then((c) => ht.mergeObjectSync(s, c)) : ht.mergeObjectSync(s, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return Z.errToObj, new ze({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (n, s) => {
          const r = this._def.errorMap?.(n, s).message ?? s.defaultError;
          return n.code === "unrecognized_keys" ? {
            message: Z.errToObj(t).message ?? r
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
  setKey(t, n) {
    return this.augment({ [t]: n });
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
    const n = {};
    for (const s of ye.objectKeys(t))
      t[s] && this.shape[s] && (n[s] = this.shape[s]);
    return new ze({
      ...this._def,
      shape: () => n
    });
  }
  omit(t) {
    const n = {};
    for (const s of ye.objectKeys(this.shape))
      t[s] || (n[s] = this.shape[s]);
    return new ze({
      ...this._def,
      shape: () => n
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return qn(this);
  }
  partial(t) {
    const n = {};
    for (const s of ye.objectKeys(this.shape)) {
      const r = this.shape[s];
      t && !t[s] ? n[s] = r : n[s] = r.optional();
    }
    return new ze({
      ...this._def,
      shape: () => n
    });
  }
  required(t) {
    const n = {};
    for (const s of ye.objectKeys(this.shape))
      if (t && !t[s])
        n[s] = this.shape[s];
      else {
        let o = this.shape[s];
        for (; o instanceof mn; )
          o = o._def.innerType;
        n[s] = o;
      }
    return new ze({
      ...this._def,
      shape: () => n
    });
  }
  keyof() {
    return Kc(ye.objectKeys(this.shape));
  }
}
ze.create = (e, t) => new ze({
  shape: () => e,
  unknownKeys: "strip",
  catchall: _n.create(),
  typeName: se.ZodObject,
  ...ae(t)
});
ze.strictCreate = (e, t) => new ze({
  shape: () => e,
  unknownKeys: "strict",
  catchall: _n.create(),
  typeName: se.ZodObject,
  ...ae(t)
});
ze.lazycreate = (e, t) => new ze({
  shape: e,
  unknownKeys: "strip",
  catchall: _n.create(),
  typeName: se.ZodObject,
  ...ae(t)
});
class vr extends me {
  _parse(t) {
    const { ctx: n } = this._processInputParams(t), s = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return n.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new tn(a.ctx.common.issues));
      return $(n, {
        code: P.invalid_union,
        unionErrors: i
      }), ne;
    }
    if (n.common.async)
      return Promise.all(s.map(async (o) => {
        const i = {
          ...n,
          common: {
            ...n.common,
            issues: []
          },
          parent: null
        };
        return {
          result: await o._parseAsync({
            data: n.data,
            path: n.path,
            parent: i
          }),
          ctx: i
        };
      })).then(r);
    {
      let o;
      const i = [];
      for (const l of s) {
        const c = {
          ...n,
          common: {
            ...n.common,
            issues: []
          },
          parent: null
        }, u = l._parseSync({
          data: n.data,
          path: n.path,
          parent: c
        });
        if (u.status === "valid")
          return u;
        u.status === "dirty" && !o && (o = { result: u, ctx: c }), c.common.issues.length && i.push(c.common.issues);
      }
      if (o)
        return n.common.issues.push(...o.ctx.common.issues), o.result;
      const a = i.map((l) => new tn(l));
      return $(n, {
        code: P.invalid_union,
        unionErrors: a
      }), ne;
    }
  }
  get options() {
    return this._def.options;
  }
}
vr.create = (e, t) => new vr({
  options: e,
  typeName: se.ZodUnion,
  ...ae(t)
});
function Wo(e, t) {
  const n = pn(e), s = pn(t);
  if (e === t)
    return { valid: !0, data: e };
  if (n === W.object && s === W.object) {
    const r = ye.objectKeys(t), o = ye.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = Wo(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (n === W.array && s === W.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = Wo(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return n === W.date && s === W.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class br extends me {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t), r = (o, i) => {
      if (Pa(o) || Pa(i))
        return ne;
      const a = Wo(o.value, i.value);
      return a.valid ? ((Na(o) || Na(i)) && n.dirty(), { status: n.value, value: a.data }) : ($(s, {
        code: P.invalid_intersection_types
      }), ne);
    };
    return s.common.async ? Promise.all([
      this._def.left._parseAsync({
        data: s.data,
        path: s.path,
        parent: s
      }),
      this._def.right._parseAsync({
        data: s.data,
        path: s.path,
        parent: s
      })
    ]).then(([o, i]) => r(o, i)) : r(this._def.left._parseSync({
      data: s.data,
      path: s.path,
      parent: s
    }), this._def.right._parseSync({
      data: s.data,
      path: s.path,
      parent: s
    }));
  }
}
br.create = (e, t, n) => new br({
  left: e,
  right: t,
  typeName: se.ZodIntersection,
  ...ae(n)
});
class Dn extends me {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.parsedType !== W.array)
      return $(s, {
        code: P.invalid_type,
        expected: W.array,
        received: s.parsedType
      }), ne;
    if (s.data.length < this._def.items.length)
      return $(s, {
        code: P.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), ne;
    !this._def.rest && s.data.length > this._def.items.length && ($(s, {
      code: P.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), n.dirty());
    const o = [...s.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new bn(s, i, s.path, a)) : null;
    }).filter((i) => !!i);
    return s.common.async ? Promise.all(o).then((i) => ht.mergeArray(n, i)) : ht.mergeArray(n, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Dn({
      ...this._def,
      rest: t
    });
  }
}
Dn.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Dn({
    items: e,
    typeName: se.ZodTuple,
    rest: null,
    ...ae(t)
  });
};
class za extends me {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.parsedType !== W.map)
      return $(s, {
        code: P.invalid_type,
        expected: W.map,
        received: s.parsedType
      }), ne;
    const r = this._def.keyType, o = this._def.valueType, i = [...s.data.entries()].map(([a, l], c) => ({
      key: r._parse(new bn(s, a, s.path, [c, "key"])),
      value: o._parse(new bn(s, l, s.path, [c, "value"]))
    }));
    if (s.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return ne;
          (c.status === "dirty" || u.status === "dirty") && n.dirty(), a.set(c.value, u.value);
        }
        return { status: n.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return ne;
        (c.status === "dirty" || u.status === "dirty") && n.dirty(), a.set(c.value, u.value);
      }
      return { status: n.value, value: a };
    }
  }
}
za.create = (e, t, n) => new za({
  valueType: t,
  keyType: e,
  typeName: se.ZodMap,
  ...ae(n)
});
class Ms extends me {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.parsedType !== W.set)
      return $(s, {
        code: P.invalid_type,
        expected: W.set,
        received: s.parsedType
      }), ne;
    const r = this._def;
    r.minSize !== null && s.data.size < r.minSize.value && ($(s, {
      code: P.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), n.dirty()), r.maxSize !== null && s.data.size > r.maxSize.value && ($(s, {
      code: P.too_big,
      maximum: r.maxSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.maxSize.message
    }), n.dirty());
    const o = this._def.valueType;
    function i(l) {
      const c = /* @__PURE__ */ new Set();
      for (const u of l) {
        if (u.status === "aborted")
          return ne;
        u.status === "dirty" && n.dirty(), c.add(u.value);
      }
      return { status: n.value, value: c };
    }
    const a = [...s.data.values()].map((l, c) => o._parse(new bn(s, l, s.path, c)));
    return s.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, n) {
    return new Ms({
      ...this._def,
      minSize: { value: t, message: Z.toString(n) }
    });
  }
  max(t, n) {
    return new Ms({
      ...this._def,
      maxSize: { value: t, message: Z.toString(n) }
    });
  }
  size(t, n) {
    return this.min(t, n).max(t, n);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Ms.create = (e, t) => new Ms({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: se.ZodSet,
  ...ae(t)
});
class Ua extends me {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: n } = this._processInputParams(t);
    return this._def.getter()._parse({ data: n.data, path: n.path, parent: n });
  }
}
Ua.create = (e, t) => new Ua({
  getter: e,
  typeName: se.ZodLazy,
  ...ae(t)
});
class Wa extends me {
  _parse(t) {
    if (t.data !== this._def.value) {
      const n = this._getOrReturnCtx(t);
      return $(n, {
        received: n.data,
        code: P.invalid_literal,
        expected: this._def.value
      }), ne;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Wa.create = (e, t) => new Wa({
  value: e,
  typeName: se.ZodLiteral,
  ...ae(t)
});
function Kc(e, t) {
  return new es({
    values: e,
    typeName: se.ZodEnum,
    ...ae(t)
  });
}
class es extends me {
  _parse(t) {
    if (typeof t.data != "string") {
      const n = this._getOrReturnCtx(t), s = this._def.values;
      return $(n, {
        expected: ye.joinValues(s),
        received: n.parsedType,
        code: P.invalid_type
      }), ne;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const n = this._getOrReturnCtx(t), s = this._def.values;
      return $(n, {
        received: n.data,
        code: P.invalid_enum_value,
        options: s
      }), ne;
    }
    return vt(t.data);
  }
  get options() {
    return this._def.values;
  }
  get enum() {
    const t = {};
    for (const n of this._def.values)
      t[n] = n;
    return t;
  }
  get Values() {
    const t = {};
    for (const n of this._def.values)
      t[n] = n;
    return t;
  }
  get Enum() {
    const t = {};
    for (const n of this._def.values)
      t[n] = n;
    return t;
  }
  extract(t, n = this._def) {
    return es.create(t, {
      ...this._def,
      ...n
    });
  }
  exclude(t, n = this._def) {
    return es.create(this.options.filter((s) => !t.includes(s)), {
      ...this._def,
      ...n
    });
  }
}
es.create = Kc;
class Ha extends me {
  _parse(t) {
    const n = ye.getValidEnumValues(this._def.values), s = this._getOrReturnCtx(t);
    if (s.parsedType !== W.string && s.parsedType !== W.number) {
      const r = ye.objectValues(n);
      return $(s, {
        expected: ye.joinValues(r),
        received: s.parsedType,
        code: P.invalid_type
      }), ne;
    }
    if (this._cache || (this._cache = new Set(ye.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = ye.objectValues(n);
      return $(s, {
        received: s.data,
        code: P.invalid_enum_value,
        options: r
      }), ne;
    }
    return vt(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
Ha.create = (e, t) => new Ha({
  values: e,
  typeName: se.ZodNativeEnum,
  ...ae(t)
});
class _r extends me {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: n } = this._processInputParams(t);
    if (n.parsedType !== W.promise && n.common.async === !1)
      return $(n, {
        code: P.invalid_type,
        expected: W.promise,
        received: n.parsedType
      }), ne;
    const s = n.parsedType === W.promise ? n.data : Promise.resolve(n.data);
    return vt(s.then((r) => this._def.type.parseAsync(r, {
      path: n.path,
      errorMap: n.common.contextualErrorMap
    })));
  }
}
_r.create = (e, t) => new _r({
  type: e,
  typeName: se.ZodPromise,
  ...ae(t)
});
class ts extends me {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === se.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (i) => {
        $(s, i), i.fatal ? n.abort() : n.dirty();
      },
      get path() {
        return s.path;
      }
    };
    if (o.addIssue = o.addIssue.bind(o), r.type === "preprocess") {
      const i = r.transform(s.data, o);
      if (s.common.async)
        return Promise.resolve(i).then(async (a) => {
          if (n.value === "aborted")
            return ne;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: s.path,
            parent: s
          });
          return l.status === "aborted" ? ne : l.status === "dirty" || n.value === "dirty" ? hs(l.value) : l;
        });
      {
        if (n.value === "aborted")
          return ne;
        const a = this._def.schema._parseSync({
          data: i,
          path: s.path,
          parent: s
        });
        return a.status === "aborted" ? ne : a.status === "dirty" || n.value === "dirty" ? hs(a.value) : a;
      }
    }
    if (r.type === "refinement") {
      const i = (a) => {
        const l = r.refinement(a, o);
        if (s.common.async)
          return Promise.resolve(l);
        if (l instanceof Promise)
          throw new Error("Async refinement encountered during synchronous parse operation. Use .parseAsync instead.");
        return a;
      };
      if (s.common.async === !1) {
        const a = this._def.schema._parseSync({
          data: s.data,
          path: s.path,
          parent: s
        });
        return a.status === "aborted" ? ne : (a.status === "dirty" && n.dirty(), i(a.value), { status: n.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: s.data, path: s.path, parent: s }).then((a) => a.status === "aborted" ? ne : (a.status === "dirty" && n.dirty(), i(a.value).then(() => ({ status: n.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (s.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: s.data,
          path: s.path,
          parent: s
        });
        if (!Xn(i))
          return ne;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: n.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: s.data, path: s.path, parent: s }).then((i) => Xn(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: n.value,
          value: a
        })) : ne);
    ye.assertNever(r);
  }
}
ts.create = (e, t, n) => new ts({
  schema: e,
  typeName: se.ZodEffects,
  effect: t,
  ...ae(n)
});
ts.createWithPreprocess = (e, t, n) => new ts({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: se.ZodEffects,
  ...ae(n)
});
class mn extends me {
  _parse(t) {
    return this._getType(t) === W.undefined ? vt(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
mn.create = (e, t) => new mn({
  innerType: e,
  typeName: se.ZodOptional,
  ...ae(t)
});
class ns extends me {
  _parse(t) {
    return this._getType(t) === W.null ? vt(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
ns.create = (e, t) => new ns({
  innerType: e,
  typeName: se.ZodNullable,
  ...ae(t)
});
class Ho extends me {
  _parse(t) {
    const { ctx: n } = this._processInputParams(t);
    let s = n.data;
    return n.parsedType === W.undefined && (s = this._def.defaultValue()), this._def.innerType._parse({
      data: s,
      path: n.path,
      parent: n
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
Ho.create = (e, t) => new Ho({
  innerType: e,
  typeName: se.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...ae(t)
});
class qo extends me {
  _parse(t) {
    const { ctx: n } = this._processInputParams(t), s = {
      ...n,
      common: {
        ...n.common,
        issues: []
      }
    }, r = this._def.innerType._parse({
      data: s.data,
      path: s.path,
      parent: {
        ...s
      }
    });
    return gr(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new tn(s.common.issues);
        },
        input: s.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new tn(s.common.issues);
        },
        input: s.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
qo.create = (e, t) => new qo({
  innerType: e,
  typeName: se.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...ae(t)
});
class qa extends me {
  _parse(t) {
    if (this._getType(t) !== W.nan) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: W.nan,
        received: s.parsedType
      }), ne;
    }
    return { status: "valid", value: t.data };
  }
}
qa.create = (e) => new qa({
  typeName: se.ZodNaN,
  ...ae(e)
});
class um extends me {
  _parse(t) {
    const { ctx: n } = this._processInputParams(t), s = n.data;
    return this._def.type._parse({
      data: s,
      path: n.path,
      parent: n
    });
  }
  unwrap() {
    return this._def.type;
  }
}
class _i extends me {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: s.data,
          path: s.path,
          parent: s
        });
        return o.status === "aborted" ? ne : o.status === "dirty" ? (n.dirty(), hs(o.value)) : this._def.out._parseAsync({
          data: o.value,
          path: s.path,
          parent: s
        });
      })();
    {
      const r = this._def.in._parseSync({
        data: s.data,
        path: s.path,
        parent: s
      });
      return r.status === "aborted" ? ne : r.status === "dirty" ? (n.dirty(), {
        status: "dirty",
        value: r.value
      }) : this._def.out._parseSync({
        data: r.value,
        path: s.path,
        parent: s
      });
    }
  }
  static create(t, n) {
    return new _i({
      in: t,
      out: n,
      typeName: se.ZodPipeline
    });
  }
}
class Zo extends me {
  _parse(t) {
    const n = this._def.innerType._parse(t), s = (r) => (Xn(r) && (r.value = Object.freeze(r.value)), r);
    return gr(n) ? n.then((r) => s(r)) : s(n);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Zo.create = (e, t) => new Zo({
  innerType: e,
  typeName: se.ZodReadonly,
  ...ae(t)
});
var se;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(se || (se = {}));
_n.create;
Ft.create;
vr.create;
br.create;
Dn.create;
const fm = es.create;
_r.create;
mn.create;
ns.create;
const dm = "comfymodal.studio.vue.";
function pm() {
  const e = /* @__PURE__ */ new Map();
  return {
    getItem: (t) => e.has(t) ? e.get(t) : null,
    setItem: (t, n) => {
      e.set(t, n);
    },
    removeItem: (t) => {
      e.delete(t);
    }
  };
}
function hm() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return pm();
}
function mm(e, t, n, s) {
  const r = dm + e, o = hm();
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
      if (!n) return a ?? t;
      const l = n.safeParse(a);
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
const gm = fm(["comfortable", "compact"]), po = mm(
  "shell.density",
  "comfortable",
  gm
), Jc = /* @__PURE__ */ rs("studio-settings", () => {
  const e = /* @__PURE__ */ oe("studio"), t = /* @__PURE__ */ oe(po.read());
  function n(o) {
    e.value = o;
  }
  function s(o) {
    t.value = o, po.write(o);
  }
  function r() {
    e.value = "studio", t.value = "comfortable", po.write("comfortable");
  }
  return { activeSection: e, density: t, setSection: n, setDensity: s, reset: r };
});
function Yc(e) {
  var t, n, s = "";
  if (typeof e == "string" || typeof e == "number") s += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (n = Yc(e[t])) && (s && (s += " "), s += n);
  } else for (n in e) e[n] && (s && (s += " "), s += n);
  return s;
}
function Qc() {
  for (var e, t, n = 0, s = "", r = arguments.length; n < r; n++) (e = arguments[n]) && (t = Yc(e)) && (s && (s += " "), s += t);
  return s;
}
const ym = (e, t) => {
  const n = new Array(e.length + t.length);
  for (let s = 0; s < e.length; s++)
    n[s] = e[s];
  for (let s = 0; s < t.length; s++)
    n[e.length + s] = t[s];
  return n;
}, vm = (e, t) => ({
  classGroupId: e,
  validator: t
}), Xc = (e = /* @__PURE__ */ new Map(), t = null, n) => ({
  nextPart: e,
  validators: t,
  classGroupId: n
}), xr = "-", Za = [], bm = "arbitrary..", _m = (e) => {
  const t = wm(e), {
    conflictingClassGroups: n,
    conflictingClassGroupModifiers: s
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return xm(i);
      const a = i.split(xr), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return eu(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = s[i], c = n[i];
        return l ? c ? ym(c, l) : l : c || Za;
      }
      return n[i] || Za;
    }
  };
}, eu = (e, t, n) => {
  if (e.length - t === 0)
    return n.classGroupId;
  const r = e[t], o = n.nextPart.get(r);
  if (o) {
    const c = eu(e, t + 1, o);
    if (c) return c;
  }
  const i = n.validators;
  if (i === null)
    return;
  const a = t === 0 ? e.join(xr) : e.slice(t).join(xr), l = i.length;
  for (let c = 0; c < l; c++) {
    const u = i[c];
    if (u.validator(a))
      return u.classGroupId;
  }
}, xm = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), n = t.indexOf(":"), s = t.slice(0, n);
  return s ? bm + s : void 0;
})(), wm = (e) => {
  const {
    theme: t,
    classGroups: n
  } = e;
  return km(n, t);
}, km = (e, t) => {
  const n = Xc();
  for (const s in e) {
    const r = e[s];
    xi(r, n, s, t);
  }
  return n;
}, xi = (e, t, n, s) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    Sm(i, t, n, s);
  }
}, Sm = (e, t, n, s) => {
  if (typeof e == "string") {
    Em(e, t, n);
    return;
  }
  if (typeof e == "function") {
    Cm(e, t, n, s);
    return;
  }
  Am(e, t, n, s);
}, Em = (e, t, n) => {
  const s = e === "" ? t : tu(t, e);
  s.classGroupId = n;
}, Cm = (e, t, n, s) => {
  if (Om(e)) {
    xi(e(s), t, n, s);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(vm(n, e));
}, Am = (e, t, n, s) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    xi(l, tu(t, a), n, s);
  }
}, tu = (e, t) => {
  let n = e;
  const s = t.split(xr), r = s.length;
  for (let o = 0; o < r; o++) {
    const i = s[o];
    let a = n.nextPart.get(i);
    a || (a = Xc(), n.nextPart.set(i, a)), n = a;
  }
  return n;
}, Om = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Rm = (e) => {
  if (e < 1)
    return {
      get: () => {
      },
      set: () => {
      }
    };
  let t = 0, n = /* @__PURE__ */ Object.create(null), s = /* @__PURE__ */ Object.create(null);
  const r = (o, i) => {
    n[o] = i, t++, t > e && (t = 0, s = n, n = /* @__PURE__ */ Object.create(null));
  };
  return {
    get(o) {
      let i = n[o];
      if (i !== void 0)
        return i;
      if ((i = s[o]) !== void 0)
        return r(o, i), i;
    },
    set(o, i) {
      o in n ? n[o] = i : r(o, i);
    }
  };
}, Go = "!", Ga = ":", Tm = [], Ka = (e, t, n, s, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: n,
  maybePostfixModifierPosition: s,
  isExternal: r
}), Im = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: n
  } = e;
  let s = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let v = 0; v < u; v++) {
      const w = r[v];
      if (i === 0 && a === 0) {
        if (w === Ga) {
          o.push(r.slice(l, v)), l = v + 1;
          continue;
        }
        if (w === "/") {
          c = v;
          continue;
        }
      }
      w === "[" ? i++ : w === "]" ? i-- : w === "(" ? a++ : w === ")" && a--;
    }
    const f = o.length === 0 ? r : r.slice(l);
    let d = f, h = !1;
    f.endsWith(Go) ? (d = f.slice(0, -1), h = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      f.startsWith(Go) && (d = f.slice(1), h = !0)
    );
    const y = c && c > l ? c - l : void 0;
    return Ka(o, h, d, y);
  };
  if (t) {
    const r = t + Ga, o = s;
    s = (i) => i.startsWith(r) ? o(i.slice(r.length)) : Ka(Tm, !1, i, void 0, !0);
  }
  if (n) {
    const r = s;
    s = (o) => n({
      className: o,
      parseClassName: r
    });
  }
  return s;
}, Pm = (e) => {
  const t = /* @__PURE__ */ new Map();
  return e.orderSensitiveModifiers.forEach((n, s) => {
    t.set(n, 1e6 + s);
  }), (n) => {
    const s = [];
    let r = [];
    for (let o = 0; o < n.length; o++) {
      const i = n[o], a = i[0] === "[", l = t.has(i);
      a || l ? (r.length > 0 && (r.sort(), s.push(...r), r = []), s.push(i)) : r.push(i);
    }
    return r.length > 0 && (r.sort(), s.push(...r)), s;
  };
}, Nm = (e) => ({
  cache: Rm(e.cacheSize),
  parseClassName: Im(e),
  sortModifiers: Pm(e),
  postfixLookupClassGroupIds: Mm(e),
  ..._m(e)
}), Mm = (e) => {
  const t = /* @__PURE__ */ Object.create(null), n = e.postfixLookupClassGroups;
  if (n)
    for (let s = 0; s < n.length; s++)
      t[n[s]] = !0;
  return t;
}, Dm = /\s+/, Lm = (e, t) => {
  const {
    parseClassName: n,
    getClassGroupId: s,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Dm);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const f = l[u], {
      isExternal: d,
      modifiers: h,
      hasImportantModifier: y,
      baseClassName: v,
      maybePostfixModifierPosition: w
    } = n(f);
    if (d) {
      c = f + (c.length > 0 ? " " + c : c);
      continue;
    }
    let R = !!w, x;
    if (R) {
      const F = v.substring(0, w);
      x = s(F);
      const S = x && i[x] ? s(v) : void 0;
      S && S !== x && (x = S, R = !1);
    } else
      x = s(v);
    if (!x) {
      if (!R) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (x = s(v), !x) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      R = !1;
    }
    const N = h.length === 0 ? "" : h.length === 1 ? h[0] : o(h).join(":"), O = y ? N + Go : N, U = O + x;
    if (a.indexOf(U) > -1)
      continue;
    a.push(U);
    const ve = r(x, R);
    for (let F = 0; F < ve.length; ++F) {
      const S = ve[F];
      a.push(O + S);
    }
    c = f + (c.length > 0 ? " " + c : c);
  }
  return c;
}, jm = (...e) => {
  let t = 0, n, s, r = "";
  for (; t < e.length; )
    (n = e[t++]) && (s = nu(n)) && (r && (r += " "), r += s);
  return r;
}, nu = (e) => {
  if (typeof e == "string")
    return e;
  let t, n = "";
  for (let s = 0; s < e.length; s++)
    e[s] && (t = nu(e[s])) && (n && (n += " "), n += t);
  return n;
}, $m = (e, ...t) => {
  let n, s, r, o;
  const i = (l) => {
    const c = t.reduce((u, f) => f(u), e());
    return n = Nm(c), s = n.cache.get, r = n.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = s(l);
    if (c)
      return c;
    const u = Lm(l, n);
    return r(l, u), u;
  };
  return o = i, (...l) => o(jm(...l));
}, Fm = [], Fe = (e) => {
  const t = (n) => n[e] || Fm;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, su = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, ru = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Vm = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, Bm = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, zm = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Um = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Wm = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, Hm = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, an = (e) => Vm.test(e), ie = (e) => !!e && !Number.isNaN(Number(e)), It = (e) => !!e && Number.isInteger(Number(e)), ho = (e) => e.endsWith("%") && ie(e.slice(0, -1)), Zt = (e) => Bm.test(e), ou = () => !0, qm = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  zm.test(e) && !Um.test(e)
), wi = () => !1, Zm = (e) => Wm.test(e), Gm = (e) => Hm.test(e), Km = (e) => !V(e) && !z(e), Jm = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), Ym = (e) => wn(e, lu, wi), V = (e) => su.test(e), Cn = (e) => wn(e, cu, qm), Ja = (e) => wn(e, og, ie), Qm = (e) => wn(e, fu, ou), Xm = (e) => wn(e, uu, wi), Ya = (e) => wn(e, iu, wi), eg = (e) => wn(e, au, Gm), Ks = (e) => wn(e, du, Zm), z = (e) => ru.test(e), us = (e) => $n(e, cu), tg = (e) => $n(e, uu), Qa = (e) => $n(e, iu), ng = (e) => $n(e, lu), sg = (e) => $n(e, au), Js = (e) => $n(e, du, !0), rg = (e) => $n(e, fu, !0), wn = (e, t, n) => {
  const s = su.exec(e);
  return s ? s[1] ? t(s[1]) : n(s[2]) : !1;
}, $n = (e, t, n = !1) => {
  const s = ru.exec(e);
  return s ? s[1] ? t(s[1]) : n : !1;
}, iu = (e) => e === "position" || e === "percentage", au = (e) => e === "image" || e === "url", lu = (e) => e === "length" || e === "size" || e === "bg-size", cu = (e) => e === "length", og = (e) => e === "number", uu = (e) => e === "family-name", fu = (e) => e === "number" || e === "weight", du = (e) => e === "shadow", ig = () => {
  const e = Fe("color"), t = Fe("font"), n = Fe("text"), s = Fe("font-weight"), r = Fe("tracking"), o = Fe("leading"), i = Fe("breakpoint"), a = Fe("container"), l = Fe("spacing"), c = Fe("radius"), u = Fe("shadow"), f = Fe("inset-shadow"), d = Fe("text-shadow"), h = Fe("drop-shadow"), y = Fe("blur"), v = Fe("perspective"), w = Fe("aspect"), R = Fe("ease"), x = Fe("animate"), N = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], O = () => [
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
  ], U = () => [...O(), z, V], ve = () => ["auto", "hidden", "clip", "visible", "scroll"], F = () => ["auto", "contain", "none"], S = () => [z, V, l], j = () => [an, "full", "auto", ...S()], pe = () => [It, "none", "subgrid", z, V], Ae = () => ["auto", {
    span: ["full", It, z, V]
  }, It, z, V], Te = () => [It, "auto", z, V], $e = () => ["auto", "min", "max", "fr", z, V], Xe = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], et = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], ce = () => ["auto", ...S()], X = () => [an, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...S()], de = () => [a, an, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...S()], at = () => [an, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...S()], q = () => [e, z, V], lt = () => [...O(), Qa, Ya, {
    position: [z, V]
  }], Ue = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], Wt = () => ["auto", "cover", "contain", ng, Ym, {
    size: [z, V]
  }], _t = () => [ho, us, Cn], Ie = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    z,
    V
  ], xe = () => ["", ie, us, Cn], k = () => ["solid", "dashed", "dotted", "double"], B = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], I = () => [ie, ho, Qa, Ya], J = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    y,
    z,
    V
  ], p = () => ["none", ie, z, V], m = () => ["none", ie, z, V], g = () => [ie, z, V], b = () => [an, "full", ...S()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [Zt],
      breakpoint: [Zt],
      color: [ou],
      container: [Zt],
      "drop-shadow": [Zt],
      ease: ["in", "out", "in-out"],
      font: [Km],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [Zt],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [Zt],
      shadow: [Zt],
      spacing: ["px", ie],
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
        aspect: ["auto", "square", an, V, z, w]
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
        "@container": ["", "normal", "size", z, V]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [Jm],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [ie, "auto", V, z, a]
      }],
      /**
       * Break After
       * @see https://tailwindcss.com/docs/break-after
       */
      "break-after": [{
        "break-after": N()
      }],
      /**
       * Break Before
       * @see https://tailwindcss.com/docs/break-before
       */
      "break-before": [{
        "break-before": N()
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
        object: U()
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
        overscroll: F()
      }],
      /**
       * Overscroll Behavior X
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-x": [{
        "overscroll-x": F()
      }],
      /**
       * Overscroll Behavior Y
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-y": [{
        "overscroll-y": F()
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
        inset: j()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": j()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": j()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": j(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: j()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": j(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: j()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": j()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": j()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: j()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: j()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: j()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: j()
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
        z: [It, "auto", z, V]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [an, "full", "auto", a, ...S()]
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
        flex: [ie, an, "auto", "initial", "none", V]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", ie, z, V]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", ie, z, V]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [It, "first", "last", "none", z, V]
      }],
      /**
       * Grid Template Columns
       * @see https://tailwindcss.com/docs/grid-template-columns
       */
      "grid-cols": [{
        "grid-cols": pe()
      }],
      /**
       * Grid Column Start / End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start-end": [{
        col: Ae()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": Te()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": Te()
      }],
      /**
       * Grid Template Rows
       * @see https://tailwindcss.com/docs/grid-template-rows
       */
      "grid-rows": [{
        "grid-rows": pe()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: Ae()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": Te()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": Te()
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
        "auto-cols": $e()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": $e()
      }],
      /**
       * Gap
       * @see https://tailwindcss.com/docs/gap
       */
      gap: [{
        gap: S()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": S()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": S()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...Xe(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...et(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...et()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...Xe()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...et(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...et(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": Xe()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...et(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...et()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: S()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: S()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: S()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: S()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: S()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: S()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: S()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: S()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: S()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: S()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: S()
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
        "space-x": S()
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
        "space-y": S()
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
        block: ["auto", ...at()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...at()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...at()]
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
        text: ["base", n, us, Cn]
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
        font: [s, rg, Qm]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", ho, V]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [tg, Xm, t]
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
        tracking: [r, z, V]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [ie, "none", z, Ja]
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
          ...S()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", z, V]
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
        list: ["disc", "decimal", "none", z, V]
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
        placeholder: q()
      }],
      /**
       * Text Color
       * @see https://tailwindcss.com/docs/text-color
       */
      "text-color": [{
        text: q()
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
        decoration: [ie, "from-font", "auto", z, Cn]
      }],
      /**
       * Text Decoration Color
       * @see https://tailwindcss.com/docs/text-decoration-color
       */
      "text-decoration-color": [{
        decoration: q()
      }],
      /**
       * Text Underline Offset
       * @see https://tailwindcss.com/docs/text-underline-offset
       */
      "underline-offset": [{
        "underline-offset": [ie, "auto", z, V]
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
        indent: S()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [It, z, V]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", z, V]
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
        content: ["none", z, V]
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
        bg: lt()
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
        bg: Wt()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, It, z, V],
          radial: ["", z, V],
          conic: ["", It, z, V]
        }, sg, eg]
      }],
      /**
       * Background Color
       * @see https://tailwindcss.com/docs/background-color
       */
      "bg-color": [{
        bg: q()
      }],
      /**
       * Gradient Color Stops From Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from-pos": [{
        from: _t()
      }],
      /**
       * Gradient Color Stops Via Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via-pos": [{
        via: _t()
      }],
      /**
       * Gradient Color Stops To Position
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to-pos": [{
        to: _t()
      }],
      /**
       * Gradient Color Stops From
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-from": [{
        from: q()
      }],
      /**
       * Gradient Color Stops Via
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-via": [{
        via: q()
      }],
      /**
       * Gradient Color Stops To
       * @see https://tailwindcss.com/docs/gradient-color-stops
       */
      "gradient-to": [{
        to: q()
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
        border: xe()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": xe()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": xe()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": xe()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": xe()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": xe()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": xe()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": xe()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": xe()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": xe()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": xe()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": xe()
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
        "divide-y": xe()
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
        border: q()
      }],
      /**
       * Border Color Inline
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-x": [{
        "border-x": q()
      }],
      /**
       * Border Color Block
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-y": [{
        "border-y": q()
      }],
      /**
       * Border Color Inline Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-s": [{
        "border-s": q()
      }],
      /**
       * Border Color Inline End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-e": [{
        "border-e": q()
      }],
      /**
       * Border Color Block Start
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-bs": [{
        "border-bs": q()
      }],
      /**
       * Border Color Block End
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-be": [{
        "border-be": q()
      }],
      /**
       * Border Color Top
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-t": [{
        "border-t": q()
      }],
      /**
       * Border Color Right
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-r": [{
        "border-r": q()
      }],
      /**
       * Border Color Bottom
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-b": [{
        "border-b": q()
      }],
      /**
       * Border Color Left
       * @see https://tailwindcss.com/docs/border-color
       */
      "border-color-l": [{
        "border-l": q()
      }],
      /**
       * Divide Color
       * @see https://tailwindcss.com/docs/divide-color
       */
      "divide-color": [{
        divide: q()
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
        "outline-offset": [ie, z, V]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", ie, us, Cn]
      }],
      /**
       * Outline Color
       * @see https://tailwindcss.com/docs/outline-color
       */
      "outline-color": [{
        outline: q()
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
          Js,
          Ks
        ]
      }],
      /**
       * Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
       */
      "shadow-color": [{
        shadow: q()
      }],
      /**
       * Inset Box Shadow
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
       */
      "inset-shadow": [{
        "inset-shadow": ["none", f, Js, Ks]
      }],
      /**
       * Inset Box Shadow Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
       */
      "inset-shadow-color": [{
        "inset-shadow": q()
      }],
      /**
       * Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
       */
      "ring-w": [{
        ring: xe()
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
        ring: q()
      }],
      /**
       * Ring Offset Width
       * @see https://v3.tailwindcss.com/docs/ring-offset-width
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-w": [{
        "ring-offset": [ie, Cn]
      }],
      /**
       * Ring Offset Color
       * @see https://v3.tailwindcss.com/docs/ring-offset-color
       * @deprecated since Tailwind CSS v4.0.0
       * @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
       */
      "ring-offset-color": [{
        "ring-offset": q()
      }],
      /**
       * Inset Ring Width
       * @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
       */
      "inset-ring-w": [{
        "inset-ring": xe()
      }],
      /**
       * Inset Ring Color
       * @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
       */
      "inset-ring-color": [{
        "inset-ring": q()
      }],
      /**
       * Text Shadow
       * @see https://tailwindcss.com/docs/text-shadow
       */
      "text-shadow": [{
        "text-shadow": ["none", d, Js, Ks]
      }],
      /**
       * Text Shadow Color
       * @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
       */
      "text-shadow-color": [{
        "text-shadow": q()
      }],
      /**
       * Opacity
       * @see https://tailwindcss.com/docs/opacity
       */
      opacity: [{
        opacity: [ie, z, V]
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
        "mask-linear": [ie]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": I()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": I()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": q()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": q()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": I()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": I()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": q()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": q()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": I()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": I()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": q()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": q()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": I()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": I()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": q()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": q()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": I()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": I()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": q()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": q()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": I()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": I()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": q()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": q()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": I()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": I()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": q()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": q()
      }],
      "mask-image-radial": [{
        "mask-radial": [z, V]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": I()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": I()
      }],
      "mask-image-radial-from-color": [{
        "mask-radial-from": q()
      }],
      "mask-image-radial-to-color": [{
        "mask-radial-to": q()
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
        "mask-radial-at": O()
      }],
      "mask-image-conic-pos": [{
        "mask-conic": [ie]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": I()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": I()
      }],
      "mask-image-conic-from-color": [{
        "mask-conic-from": q()
      }],
      "mask-image-conic-to-color": [{
        "mask-conic-to": q()
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
        mask: lt()
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
        mask: Wt()
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
        mask: ["none", z, V]
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
          z,
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
        brightness: [ie, z, V]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [ie, z, V]
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
          Js,
          Ks
        ]
      }],
      /**
       * Drop Shadow Color
       * @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
       */
      "drop-shadow-color": [{
        "drop-shadow": q()
      }],
      /**
       * Grayscale
       * @see https://tailwindcss.com/docs/grayscale
       */
      grayscale: [{
        grayscale: ["", ie, z, V]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [ie, z, V]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", ie, z, V]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [ie, z, V]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", ie, z, V]
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
          z,
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
        "backdrop-brightness": [ie, z, V]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [ie, z, V]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", ie, z, V]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [ie, z, V]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", ie, z, V]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [ie, z, V]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [ie, z, V]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", ie, z, V]
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
        "border-spacing": S()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": S()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": S()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", z, V]
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
        duration: [ie, "initial", z, V]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", R, z, V]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [ie, z, V]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", x, z, V]
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
        perspective: [v, z, V]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": U()
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
        transform: [z, V, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: U()
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
        zoom: [It, z, V]
      }],
      // ---------------------
      // --- Interactivity ---
      // ---------------------
      /**
       * Accent Color
       * @see https://tailwindcss.com/docs/accent-color
       */
      accent: [{
        accent: q()
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
        caret: q()
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", z, V]
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
        "scrollbar-thumb": q()
      }],
      /**
       * Scrollbar Track Color
       * @see https://tailwindcss.com/docs/scrollbar-color
       */
      "scrollbar-track-color": [{
        "scrollbar-track": q()
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
        "scroll-m": S()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": S()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": S()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": S()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": S()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": S()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": S()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": S()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": S()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": S()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": S()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": S()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": S()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": S()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": S()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": S()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": S()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": S()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": S()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": S()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": S()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": S()
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
        "will-change": ["auto", "scroll", "contents", "transform", z, V]
      }],
      // -----------
      // --- SVG ---
      // -----------
      /**
       * Fill
       * @see https://tailwindcss.com/docs/fill
       */
      fill: [{
        fill: ["none", ...q()]
      }],
      /**
       * Stroke Width
       * @see https://tailwindcss.com/docs/stroke-width
       */
      "stroke-w": [{
        stroke: [ie, us, Cn, Ja]
      }],
      /**
       * Stroke
       * @see https://tailwindcss.com/docs/stroke
       */
      stroke: [{
        stroke: ["none", ...q()]
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
}, ag = /* @__PURE__ */ $m(ig);
function ki(...e) {
  return ag(Qc(e));
}
const lg = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, cg = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, ug = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, fg = { class: "cmst:flex-1" }, dg = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, pg = { "data-testid": "vue-status-route" }, hg = { "data-testid": "vue-status-ops" }, mg = { "data-testid": "vue-status-density" }, gg = { class: "cmst:flex cmst:items-center cmst:gap-1" }, yg = /* @__PURE__ */ ke({
  __name: "StudioApp",
  setup(e) {
    const t = rh(), n = qc(), s = Jc(), r = Mh("(min-width: 768px)"), o = {
      playground: jc,
      history: Fc,
      workflows: $c,
      backend: Vc,
      settings: Bc
    }, i = ue(() => String(t.name ?? "playground"));
    function a(l) {
      const c = i.value === l;
      return ki(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        c ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (l, c) => (fe(), it("div", lg, [
      H("header", cg, [
        c[0] || (c[0] = H("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          le(" Modal Studio "),
          H("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        H("nav", ug, [
          (fe(!0), it(qe, null, Zl(C(bi), (u) => (fe(), De(C(Dc), {
            key: u,
            to: { name: u },
            class: yt(a(u)),
            "data-testid": `vue-nav-${u}`
          }, {
            default: re(() => [
              (fe(), De(Mf(o[u]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              le(" " + Ne(C(Dh)[u]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      H("main", fg, [
        Y(C(Lc))
      ]),
      H("footer", dg, [
        H("span", null, [
          c[1] || (c[1] = le("route: ", -1)),
          H("strong", pg, Ne(i.value), 1)
        ]),
        H("span", null, [
          c[2] || (c[2] = le(" operations: ", -1)),
          H("strong", hg, Ne(C(n).active.length) + " active", 1),
          le(" / " + Ne(C(n).all.length) + " total ", 1)
        ]),
        H("span", null, [
          c[3] || (c[3] = le(" density: ", -1)),
          H("strong", mg, Ne(C(s).density), 1)
        ]),
        H("span", gg, [
          Y(C(gh), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          c[4] || (c[4] = le(" viewport: ", -1)),
          H("strong", null, Ne(C(r) ? "wide" : "narrow"), 1),
          c[5] || (c[5] = le(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), vg = "/", pu = { page: "playground", focus: null };
function Ys(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function mo(e) {
  const [t, n] = e.split("?"), s = t.replace(/^\//, ""), r = vn(s) ? s : pu.page;
  let o = null;
  if (n)
    for (const i of n.split("&")) {
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
function go(e) {
  const t = Wc(e.location.hash);
  return !t.matched || !vn(t.page) ? null : { page: t.page, focus: t.focus };
}
function yo(e, t, n) {
  const s = Hc(t);
  if (!s) return;
  const r = e.location.pathname + e.location.search + s;
  n === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function bg(e, t) {
  let n = Lh(t, e.location.hash), s = Ys(n), r = {};
  const o = s, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = s;
    n = go(e) ?? { ...pu }, s = Ys(n), i.forEach((d) => d(s, u));
  }, c = (u, f) => u === null && f === o;
  return {
    get base() {
      return vg;
    },
    get location() {
      return s;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const f = Hc(mo(u));
      return f === "" ? "#" + u : f;
    },
    replace: (u, f) => {
      const d = go(e), h = mo(u), y = Ys(h);
      n = h, f !== void 0 && (r = f), s = y, !c(d, y) && Ra(d, h) !== "none" && yo(e, h, "replace");
    },
    push: (u, f) => {
      const d = go(e), h = mo(u), y = Ys(h);
      if (n = h, f !== void 0 && (r = f), s = y, c(d, y)) return;
      const v = Ra(d, h);
      v === "push" ? yo(e, h, "push") : v === "replace" && yo(e, h, "replace");
    },
    go: (u) => {
      e.history.go(u);
    },
    listen: (u) => {
      const f = (d, h) => {
        u(d, h, { type: "pop", direction: "unknown", delta: 0 });
      };
      return i.add(f), a || (e.addEventListener("popstate", l), a = !0), () => {
        i.delete(f), i.size === 0 && a && (e.removeEventListener("popstate", l), a = !1);
      };
    },
    destroy: () => {
      i.clear(), a && (e.removeEventListener("popstate", l), a = !1);
    }
  };
}
function hu(e, t) {
  const n = typeof e == "string" && !t ? `${e}Context` : t, s = Symbol(n);
  return [(i) => {
    const a = ot(s, i);
    if (a || a === null) return a;
    throw new Error(`Injection \`${s.toString()}\` not found. Component must be used within ${Array.isArray(e) ? `one of the following components: ${e.join(", ")}` : `\`${e}\``}`);
  }, (i) => (vs(s, i), i)];
}
function Lt() {
  let e = document.activeElement;
  if (e == null) return null;
  for (; e != null && e.shadowRoot != null && e.shadowRoot.activeElement != null; ) e = e.shadowRoot.activeElement;
  return e;
}
function mu(e, t, n) {
  const s = n.originalEvent.target, r = new CustomEvent(e, {
    bubbles: !1,
    cancelable: !0,
    detail: n
  });
  t && s.addEventListener(e, t, { once: !0 }), s.dispatchEvent(r);
}
function _g(e, t) {
  return Ir() ? (ei(e, t), !0) : !1;
}
// @__NO_SIDE_EFFECTS__
function xg(e) {
  let t = !1, n;
  const s = Tr(!0);
  return ((...r) => (t || (n = s.run(() => e(...r)), t = !0), n));
}
const nn = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const wg = (e) => typeof e < "u", kg = Object.prototype.toString, Sg = (e) => kg.call(e) === "[object Object]", Xa = /* @__PURE__ */ Eg();
function Eg() {
  var e, t, n;
  return nn && !!(!((e = window) === null || e === void 0 || (e = e.navigator) === null || e === void 0) && e.userAgent) && (/iP(?:ad|hone|od)/.test(window.navigator.userAgent) || ((t = window) === null || t === void 0 || (t = t.navigator) === null || t === void 0 ? void 0 : t.maxTouchPoints) > 2 && /iPad|Macintosh/.test((n = window) === null || n === void 0 ? void 0 : n.navigator.userAgent));
}
function vo(e) {
  return Array.isArray(e) ? e : [e];
}
function Cg(e) {
  return Ct();
}
// @__NO_SIDE_EFFECTS__
function Ag(e) {
  if (!nn) return e;
  let t = 0, n, s;
  const r = () => {
    t -= 1, s && t <= 0 && (s.stop(), n = void 0, s = void 0);
  };
  return ((...o) => (t += 1, s || (s = Tr(!0), n = s.run(() => e(...o))), _g(r), n));
}
function Og(e, t) {
  Cg() && Hl(e, t);
}
function Rg(e, t, n) {
  return je(e, t, {
    ...n,
    immediate: !0
  });
}
const Si = nn ? window : void 0;
function Ur(e) {
  var t;
  const n = Qe(e);
  return (t = n?.$el) !== null && t !== void 0 ? t : n;
}
function gu(...e) {
  const t = (s, r, o, i) => (s.addEventListener(r, o, i), () => s.removeEventListener(r, o, i)), n = ue(() => {
    const s = vo(Qe(e[0])).filter((r) => r != null);
    return s.every((r) => typeof r != "string") ? s : void 0;
  });
  return Rg(() => {
    var s, r;
    return [
      (s = (r = n.value) === null || r === void 0 ? void 0 : r.map((o) => Ur(o))) !== null && s !== void 0 ? s : [Si].filter((o) => o != null),
      vo(Qe(n.value ? e[1] : e[0])),
      vo(C(n.value ? e[2] : e[1])),
      Qe(n.value ? e[3] : e[2])
    ];
  }, ([s, r, o, i], a, l) => {
    if (!s?.length || !r?.length || !o?.length) return;
    const c = Sg(i) ? { ...i } : i, u = s.flatMap((f) => r.flatMap((d) => o.map((h) => t(f, d, h, c))));
    l(() => {
      u.forEach((f) => f());
    });
  }, { flush: "post" });
}
// @__NO_SIDE_EFFECTS__
function Tg() {
  const e = /* @__PURE__ */ Zn(!1), t = Ct();
  return t && ss(() => {
    e.value = !0;
  }, t), e;
}
function Ig(e) {
  return typeof e == "function" ? e : typeof e == "string" ? (t) => t.key === e : Array.isArray(e) ? (t) => e.includes(t.key) : () => !0;
}
function Pg(...e) {
  let t, n, s = {};
  e.length === 3 ? (t = e[0], n = e[1], s = e[2]) : e.length === 2 ? typeof e[1] == "object" ? (t = !0, n = e[0], s = e[1]) : (t = e[0], n = e[1]) : (t = !0, n = e[0]);
  const { target: r = Si, eventName: o = "keydown", passive: i = !1, dedupe: a = !1 } = s, l = Ig(t);
  return gu(r, o, (u) => {
    u.repeat && Qe(a) || l(u) && n(u);
  }, i);
}
function Ng(e) {
  return JSON.parse(JSON.stringify(e));
}
// @__NO_SIDE_EFFECTS__
function Mg(e, t, n, s = {}) {
  var r, o;
  const { clone: i = !1, passive: a = !1, eventName: l, deep: c = !1, defaultValue: u, shouldEmit: f } = s, d = Ct(), h = n || d?.emit || (d == null || (r = d.$emit) === null || r === void 0 ? void 0 : r.bind(d)) || (d == null || (o = d.proxy) === null || o === void 0 || (o = o.$emit) === null || o === void 0 ? void 0 : o.bind(d?.proxy));
  let y = l;
  y = y || `update:${t.toString()}`;
  const v = (x) => i ? typeof i == "function" ? i(x) : Ng(x) : x, w = () => wg(e[t]) ? v(e[t]) : u, R = (x) => {
    f ? f(x) && h(y, x) : h(y, x);
  };
  if (a) {
    const x = /* @__PURE__ */ oe(w());
    let N = !1;
    return je(() => e[t], (O) => {
      N || (N = !0, x.value = v(O), St(() => N = !1));
    }), je(x, (O) => {
      !N && (O !== e[t] || c) && R(O);
    }, { deep: c }), x;
  } else return ue({
    get() {
      return w();
    },
    set(x) {
      R(x);
    }
  });
}
function Ei(e) {
  return e ? e.flatMap((t) => t.type === qe ? Ei(t.children) : [t]) : [];
}
const [Ci] = /* @__PURE__ */ hu("ConfigProvider"), wr = /* @__PURE__ */ new WeakMap();
function yu(e, t) {
  let n = wr.get(e);
  n || (n = {
    owners: /* @__PURE__ */ new Set(),
    original: e.body.style.pointerEvents
  }, wr.set(e, n)), n.owners.add(t), e.body.style.pointerEvents = "none";
}
function vu(e, t) {
  const n = wr.get(e);
  n?.owners.delete(t) && n.owners.size === 0 && (wr.delete(e), e.body.style.pointerEvents = n.original);
}
function bo(e) {
  if (e === null || typeof e != "object")
    return !1;
  const t = Object.getPrototypeOf(e);
  return t !== null && t !== Object.prototype && Object.getPrototypeOf(t) !== null || Symbol.iterator in e ? !1 : Symbol.toStringTag in e ? Object.prototype.toString.call(e) === "[object Module]" : !0;
}
function Ko(e, t, n = ".", s) {
  if (!bo(t))
    return Ko(e, {}, n, s);
  const r = { ...t };
  for (const o of Object.keys(e)) {
    if (o === "__proto__" || o === "constructor")
      continue;
    const i = e[o];
    i != null && (s && s(r, o, i, n) || (Array.isArray(i) && Array.isArray(r[o]) ? r[o] = [...i, ...r[o]] : bo(i) && bo(r[o]) ? r[o] = Ko(
      i,
      r[o],
      (n ? `${n}.` : "") + o.toString(),
      s
    ) : r[o] = i));
  }
  return r;
}
function Dg(e) {
  return (...t) => (
    // eslint-disable-next-line unicorn/no-array-reduce
    t.reduce((n, s) => Ko(n, s, "", e), {})
  );
}
const Lg = Dg(), el = Symbol("useBodyScrollLock"), jg = /* @__PURE__ */ Ag(() => {
  const e = /* @__PURE__ */ oe(/* @__PURE__ */ new Map()), t = /* @__PURE__ */ oe(), n = ue(() => {
    for (const i of e.value.values()) if (i) return !0;
    return !1;
  }), s = Ci({ scrollBody: /* @__PURE__ */ oe(!0) });
  let r = null;
  const o = () => {
    document.body.style.paddingRight = "", document.body.style.marginRight = "", vu(document, el), document.documentElement.style.removeProperty("--scrollbar-width"), document.body.style.overflow = t.value ?? "", Xa && r?.(), t.value = void 0;
  };
  return je(n, (i, a) => {
    if (!nn) return;
    if (!i) {
      a && o();
      return;
    }
    t.value === void 0 && (t.value = document.body.style.overflow);
    const l = window.innerWidth - document.documentElement.clientWidth, c = {
      padding: l,
      margin: 0
    }, u = s.scrollBody?.value ? typeof s.scrollBody.value == "object" ? Lg({
      padding: s.scrollBody.value.padding === !0 ? l : s.scrollBody.value.padding,
      margin: s.scrollBody.value.margin === !0 ? l : s.scrollBody.value.margin
    }, c) : c : {
      padding: 0,
      margin: 0
    };
    l > 0 && (document.body.style.paddingRight = typeof u.padding == "number" ? `${u.padding}px` : String(u.padding), document.body.style.marginRight = typeof u.margin == "number" ? `${u.margin}px` : String(u.margin), document.documentElement.style.setProperty("--scrollbar-width", `${l}px`), document.body.style.overflow = "hidden"), Xa && (r = gu(document, "touchmove", (f) => Fg(f), { passive: !1 })), St(() => {
      n.value && (yu(document, el), document.body.style.overflow = "hidden");
    });
  }, {
    immediate: !0,
    flush: "sync"
  }), e;
});
function $g(e) {
  const t = Math.random().toString(36).substring(2, 7), n = jg();
  n.value.set(t, e ?? !1);
  const s = ue({
    get: () => n.value.get(t) ?? !1,
    set: (r) => n.value.set(t, r)
  });
  return Og(() => {
    n.value.delete(t);
  }), s;
}
function bu(e) {
  const t = window.getComputedStyle(e);
  if (t.overflowX === "scroll" || t.overflowY === "scroll" || t.overflowX === "auto" && e.clientWidth < e.scrollWidth || t.overflowY === "auto" && e.clientHeight < e.scrollHeight) return !0;
  {
    const n = e.parentNode;
    return !(n instanceof Element) || n.tagName === "BODY" ? !1 : bu(n);
  }
}
function Fg(e) {
  const t = e || window.event, n = t.target;
  return n instanceof Element && bu(n) ? !1 : t.touches.length > 1 ? !0 : (t.preventDefault && t.cancelable && t.preventDefault(), !1);
}
function Ai(e) {
  const t = Ct(), n = t?.type.emits, s = {};
  return n?.length || console.warn(`No emitted event found. Please check component: ${t?.type.__name}`), n?.forEach((r) => {
    s[tr(Ye(r))] = (...o) => e(r, ...o);
  }), s;
}
function bt() {
  const e = Ct(), t = /* @__PURE__ */ oe(), n = ue(() => s());
  Wl(() => {
    n.value !== s() && nf(t);
  });
  function s() {
    return t.value && "$el" in t.value && ["#text", "#comment"].includes(t.value.$el.nodeName) ? t.value.$el.nextElementSibling : Ur(t);
  }
  const r = Object.assign({}, e.exposed), o = {};
  for (const a in e.props) Object.defineProperty(o, a, {
    enumerable: !0,
    configurable: !0,
    get: () => e.props[a]
  });
  if (Object.keys(r).length > 0) for (const a in r) Object.defineProperty(o, a, {
    enumerable: !0,
    configurable: !0,
    get: () => r[a]
  });
  Object.defineProperty(o, "$el", {
    enumerable: !0,
    configurable: !0,
    get: () => e.vnode.el
  }), e.exposed = o;
  function i(a) {
    if (t.value = a, !!a && (Object.defineProperty(o, "$el", {
      enumerable: !0,
      configurable: !0,
      get: () => a instanceof Element ? a : a.$el
    }), !(a instanceof Element) && !Object.hasOwn(a, "$el"))) {
      const l = a.$.exposed, c = Object.assign({}, o);
      for (const u in l) Object.defineProperty(c, u, {
        enumerable: !0,
        configurable: !0,
        get: () => l[u]
      });
      e.exposed = c;
    }
  }
  return {
    forwardRef: i,
    currentRef: t,
    currentElement: n
  };
}
var Vg = function(e) {
  if (typeof document > "u")
    return null;
  var t = Array.isArray(e) ? e[0] : e;
  return t.ownerDocument.body;
}, zn = /* @__PURE__ */ new WeakMap(), Qs = /* @__PURE__ */ new WeakMap(), Xs = {}, _o = 0, _u = function(e) {
  return e && (e.host || _u(e.parentNode));
}, Bg = function(e, t) {
  return t.map(function(n) {
    if (e.contains(n))
      return n;
    var s = _u(n);
    return s && e.contains(s) ? s : (console.error("aria-hidden", n, "in not contained inside", e, ". Doing nothing"), null);
  }).filter(function(n) {
    return !!n;
  });
}, zg = function(e, t, n, s) {
  var r = Bg(t, Array.isArray(e) ? e : [e]);
  Xs[n] || (Xs[n] = /* @__PURE__ */ new WeakMap());
  var o = Xs[n], i = [], a = /* @__PURE__ */ new Set(), l = new Set(r), c = function(f) {
    !f || a.has(f) || (a.add(f), c(f.parentNode));
  };
  r.forEach(c);
  var u = function(f) {
    !f || l.has(f) || Array.prototype.forEach.call(f.children, function(d) {
      if (a.has(d))
        u(d);
      else
        try {
          var h = d.getAttribute(s), y = h !== null && h !== "false", v = (zn.get(d) || 0) + 1, w = (o.get(d) || 0) + 1;
          zn.set(d, v), o.set(d, w), i.push(d), v === 1 && y && Qs.set(d, !0), w === 1 && d.setAttribute(n, "true"), y || d.setAttribute(s, "true");
        } catch (R) {
          console.error("aria-hidden: cannot operate on ", d, R);
        }
    });
  };
  return u(t), a.clear(), _o++, function() {
    i.forEach(function(f) {
      var d = zn.get(f) - 1, h = o.get(f) - 1;
      zn.set(f, d), o.set(f, h), d || (Qs.has(f) || f.removeAttribute(s), Qs.delete(f)), h || f.removeAttribute(n);
    }), _o--, _o || (zn = /* @__PURE__ */ new WeakMap(), zn = /* @__PURE__ */ new WeakMap(), Qs = /* @__PURE__ */ new WeakMap(), Xs = {});
  };
}, Ug = function(e, t, n) {
  n === void 0 && (n = "data-aria-hidden");
  var s = Array.from(Array.isArray(e) ? e : [e]), r = Vg(e);
  return r ? (s.push.apply(s, Array.from(r.querySelectorAll("[aria-live], script"))), zg(s, r, n, "aria-hidden")) : function() {
    return null;
  };
};
function Wg(e) {
  let t;
  je(() => Ur(e), (n) => {
    let s = !1;
    try {
      s = !!n?.closest("[popover]:not(:popover-open)");
    } catch {
    }
    n && !s ? t = Ug(n) : t && t();
  }), jr(() => {
    t && t();
  });
}
function Jo(e, t = "reka") {
  let n;
  const s = Ci({ useId: void 0 });
  return s.useId ? n = s.useId() : n = kf?.(), t ? `${t}-${n}` : n;
}
function Hg(e, t) {
  const n = /* @__PURE__ */ oe(e);
  function s(o) {
    return t[n.value][o] ?? n.value;
  }
  return {
    state: n,
    dispatch: (o) => {
      n.value = s(o);
    }
  };
}
function qg(e, t) {
  const n = /* @__PURE__ */ oe({}), s = /* @__PURE__ */ oe("none"), r = /* @__PURE__ */ oe(e), o = e.value ? "mounted" : "unmounted";
  let i;
  const a = t.value?.ownerDocument.defaultView ?? Si, { state: l, dispatch: c } = Hg(o, {
    mounted: {
      UNMOUNT: "unmounted",
      ANIMATION_OUT: "unmountSuspended"
    },
    unmountSuspended: {
      MOUNT: "mounted",
      ANIMATION_END: "unmounted"
    },
    unmounted: { MOUNT: "mounted" }
  }), u = (w) => {
    if (nn) {
      const R = new CustomEvent(w, {
        bubbles: !1,
        cancelable: !1
      });
      t.value?.dispatchEvent(R);
    }
  };
  je(e, async (w, R) => {
    const x = R !== w;
    if (await St(), x) {
      const N = s.value, O = er(t.value);
      w ? (c("MOUNT"), u("enter"), O === "none" && u("after-enter")) : O === "none" || O === "undefined" || n.value?.display === "none" ? (c("UNMOUNT"), u("leave"), u("after-leave")) : R && N !== O ? (c("ANIMATION_OUT"), u("leave")) : (c("UNMOUNT"), u("after-leave"));
    }
  }, { immediate: !0 });
  const f = (w) => {
    if (w.target !== t.value) return;
    const R = er(t.value), x = R.includes(CSS.escape(w.animationName)), N = l.value === "mounted" ? "enter" : "leave";
    if (x && (u(`after-${N}`), c("ANIMATION_END"), !r.value)) {
      const O = t.value.style.animationFillMode;
      t.value.style.animationFillMode = "forwards", i = a?.setTimeout(() => {
        t.value?.style.animationFillMode === "forwards" && (t.value.style.animationFillMode = O);
      });
    }
    R === "none" && c("ANIMATION_END");
  }, d = (w) => {
    w.target === t.value && (s.value = er(t.value));
  }, h = je(t, (w, R) => {
    w ? (n.value = getComputedStyle(w), w.addEventListener("animationstart", d), w.addEventListener("animationcancel", f), w.addEventListener("animationend", f)) : (c("ANIMATION_END"), i !== void 0 && a?.clearTimeout(i), R?.removeEventListener("animationstart", d), R?.removeEventListener("animationcancel", f), R?.removeEventListener("animationend", f));
  }, { immediate: !0 }), y = je(l, () => {
    const w = er(t.value);
    s.value = l.value === "mounted" ? w : "none";
  });
  return jr(() => {
    h(), y(), t.value && (t.value.removeEventListener("animationstart", d), t.value.removeEventListener("animationcancel", f), t.value.removeEventListener("animationend", f)), i !== void 0 && a?.clearTimeout(i);
  }), { isPresent: ue(() => ["mounted", "unmountSuspended"].includes(l.value)) };
}
function er(e) {
  return e && getComputedStyle(e).animationName || "none";
}
var xu = /* @__PURE__ */ ke({
  name: "Presence",
  props: {
    present: {
      type: Boolean,
      required: !0
    },
    forceMount: { type: Boolean }
  },
  slots: {},
  setup(e, { slots: t, expose: n }) {
    const { present: s, forceMount: r } = /* @__PURE__ */ li(e), o = /* @__PURE__ */ oe(), { isPresent: i } = qg(s, o);
    n({ present: i });
    let a = t.default({ present: i.value });
    a = Ei(a || []);
    const l = Ct();
    if (a && a?.length > 1) {
      const c = l?.parent?.type.name ? `<${l.parent.type.name} />` : "component";
      throw new Error([
        `Detected an invalid children for \`${c}\` for  \`Presence\` component.`,
        "",
        "Note: Presence works similarly to `v-if` directly, but it waits for animation/transition to finished before unmounting. So it expect only one direct child of valid VNode type.",
        "You can apply a few solutions:",
        ["Provide a single child element so that `presence` directive attach correctly.", "Ensure the first child is an actual element instead of a raw text node or comment node."].map((u) => `  - ${u}`).join(`
`)
      ].join(`
`));
    }
    return () => r.value || s.value || i.value ? en(t.default({ present: i.value })[0], { ref: (c) => {
      const u = Ur(c);
      return typeof u?.hasAttribute > "u" || (u?.hasAttribute("data-reka-popper-content-wrapper") ? o.value = u.firstElementChild : o.value = u), u;
    } }) : null;
  }
});
const Zg = /* @__PURE__ */ ke({
  name: "PrimitiveSlot",
  inheritAttrs: !1,
  setup(e, { attrs: t, slots: n }) {
    return () => {
      if (!n.default) return null;
      const s = Ei(n.default()), r = s.findIndex((l) => l.type !== pt);
      if (r === -1) return s;
      const o = s[r];
      delete o.props?.ref;
      const i = o.props ? gt(t, o.props) : t, a = Mn({
        ...o,
        props: {}
      }, i);
      return s.length === 1 ? a : (s[r] = a, s);
    };
  }
}), Gg = [
  "area",
  "img",
  "input"
], Fn = /* @__PURE__ */ ke({
  name: "Primitive",
  inheritAttrs: !1,
  props: {
    asChild: {
      type: Boolean,
      default: !1
    },
    as: {
      type: [String, Object],
      default: "div"
    }
  },
  setup(e, { attrs: t, slots: n }) {
    const s = e.asChild ? "template" : e.as;
    return typeof s == "string" && Gg.includes(s) ? () => en(s, t) : s !== "template" ? () => en(e.as, t, { default: n.default }) : () => en(Zg, t, { default: n.default });
  }
}), [Ut, Kg] = /* @__PURE__ */ hu("DialogRoot");
var Jg = /* @__PURE__ */ ke({
  inheritAttrs: !1,
  __name: "DialogRoot",
  props: {
    open: {
      type: Boolean,
      required: !1,
      default: void 0
    },
    defaultOpen: {
      type: Boolean,
      required: !1,
      default: !1
    },
    modal: {
      type: Boolean,
      required: !1,
      default: !0
    },
    unmountOnHide: {
      type: Boolean,
      required: !1,
      default: !0
    }
  },
  emits: ["update:open"],
  setup(e, { emit: t }) {
    const n = e, r = /* @__PURE__ */ Mg(n, "open", t, {
      defaultValue: n.defaultOpen,
      passive: n.open === void 0
    }), o = /* @__PURE__ */ oe(), i = /* @__PURE__ */ oe(), { modal: a, unmountOnHide: l } = /* @__PURE__ */ li(n);
    return Kg({
      open: r,
      modal: a,
      unmountOnHide: l,
      openModal: () => {
        r.value = !0;
      },
      onOpenChange: (c) => {
        r.value = c;
      },
      onOpenToggle: () => {
        r.value = !r.value;
      },
      contentId: "",
      titleId: "",
      descriptionId: "",
      triggerElement: o,
      contentElement: i
    }), (c, u) => We(c.$slots, "default", {
      open: C(r),
      close: () => r.value = !1
    });
  }
}), Yg = Jg, Qg = /* @__PURE__ */ ke({
  __name: "DialogClose",
  props: {
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1,
      default: "button"
    }
  },
  setup(e) {
    const t = e;
    bt();
    const n = Ut();
    return (s, r) => (fe(), De(C(Fn), gt(t, {
      type: e.as === "button" ? "button" : void 0,
      onClick: r[0] || (r[0] = (o) => C(n).onOpenChange(!1))
    }), {
      default: re(() => [We(s.$slots, "default")]),
      _: 3
    }, 16, ["type"]));
  }
}), Xg = Qg;
const ey = "dismissableLayer.pointerDownOutside", ty = "dismissableLayer.focusOutside";
function ny(e) {
  if (typeof e != "object" || e === null) return !1;
  const t = e.ownerDocument?.defaultView;
  return typeof Element < "u" && e instanceof Element || !!t && e instanceof t.Element;
}
function wu(e, t) {
  if (!ny(t)) return !1;
  if (e.contains(t)) return !0;
  const n = t.closest("[data-dismissable-layer]"), s = e.dataset.dismissableLayer === "" ? e : e.querySelector("[data-dismissable-layer]"), r = Array.from(e.ownerDocument.querySelectorAll("[data-dismissable-layer]"));
  return !!(n && (s === n || r.indexOf(s) < r.indexOf(n)));
}
function sy(e, t, n = !0) {
  const s = /* @__PURE__ */ oe(!1), r = /* @__PURE__ */ oe(() => {
  });
  return Kn((o) => {
    if (!nn || !Qe(n)) return;
    const i = t?.value?.ownerDocument ?? globalThis.document, a = async (c) => {
      const u = c.target;
      if (!(!t?.value || !u)) {
        if (wu(t.value, u)) {
          i.removeEventListener("click", r.value), s.value = !1;
          return;
        }
        if (c.target && !s.value) {
          let d = function() {
            mu(ey, e, f);
          };
          const f = { originalEvent: c };
          c.pointerType === "touch" ? (i.removeEventListener("click", r.value), r.value = d, i.addEventListener("click", r.value, { once: !0 })) : d();
        } else i.removeEventListener("click", r.value);
        s.value = !1;
      }
    }, l = window.setTimeout(() => {
      i.addEventListener("pointerdown", a);
    }, 0);
    o(() => {
      window.clearTimeout(l), i.removeEventListener("pointerdown", a), i.removeEventListener("click", r.value);
    });
  }), { onPointerDownCapture: () => {
    Qe(n) && (s.value = !0);
  } };
}
function ry(e, t, n = !0) {
  const s = /* @__PURE__ */ oe(!1);
  return Kn((r) => {
    if (!nn || !Qe(n)) return;
    const o = t?.value?.ownerDocument ?? globalThis.document, i = async (a) => {
      if (!t?.value) return;
      await St(), await St();
      const l = a.target;
      !t.value || !l || wu(t.value, l) || a.target && !s.value && mu(ty, e, { originalEvent: a });
    };
    o.addEventListener("focusin", i), r(() => o.removeEventListener("focusin", i));
  }), {
    onFocusCapture: () => {
      Qe(n) && (s.value = !0);
    },
    onBlurCapture: () => {
      Qe(n) && (s.value = !1);
    }
  };
}
const ln = /* @__PURE__ */ jn({
  layersRoot: /* @__PURE__ */ new Set(),
  layersWithOutsidePointerEventsDisabled: /* @__PURE__ */ new Set(),
  branches: /* @__PURE__ */ new Set()
});
var oy = /* @__PURE__ */ ke({
  __name: "DismissableLayer",
  props: {
    disableOutsidePointerEvents: {
      type: Boolean,
      required: !1,
      default: !1
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    },
    present: {
      type: Boolean,
      required: !1,
      default: !0
    }
  },
  emits: [
    "escapeKeyDown",
    "pointerDownOutside",
    "focusOutside",
    "interactOutside",
    "dismiss"
  ],
  setup(e, { emit: t }) {
    const n = e, s = t, { forwardRef: r, currentElement: o } = bt(), i = ue(() => o.value?.ownerDocument ?? globalThis.document), a = ue(() => ln.layersRoot), l = ue(() => o.value ? Array.from(a.value).indexOf(o.value) : -1), c = ue(() => ln.layersWithOutsidePointerEventsDisabled.size > 0), u = ue(() => {
      const h = Array.from(a.value), [y] = [...ln.layersWithOutsidePointerEventsDisabled].slice(-1), v = h.indexOf(y);
      return l.value >= v;
    }), f = sy(async (h) => {
      const y = [...ln.branches].some((v) => v?.contains(h.target));
      !n.present || !u.value || y || (s("pointerDownOutside", h), s("interactOutside", h), await St(), h.defaultPrevented || s("dismiss"));
    }, o, () => n.present), d = ry((h) => {
      const y = [...ln.branches].some((v) => v?.contains(h.target));
      !n.present || y || (s("focusOutside", h), s("interactOutside", h), h.defaultPrevented || s("dismiss"));
    }, o);
    return Pg("Escape", (h) => {
      !n.present || !(l.value === a.value.size - 1) || (s("escapeKeyDown", h), h.defaultPrevented || s("dismiss"));
    }, { target: () => i.value?.defaultView ?? globalThis.window }), je([
      o,
      () => n.disableOutsidePointerEvents,
      () => n.present
    ], ([h, y, v], w, R) => {
      if (!(!h || !v) && y) {
        const x = h.ownerDocument;
        yu(x, h), ln.layersWithOutsidePointerEventsDisabled.add(h), R(() => {
          ln.layersWithOutsidePointerEventsDisabled.delete(h), vu(x, h);
        });
      }
    }, { immediate: !0 }), je([o, () => n.present], ([h, y], v, w) => {
      !h || !y || (a.value.add(h), w(() => {
        a.value.delete(h);
      }));
    }, { immediate: !0 }), Kn((h) => {
      h(() => {
        o.value && (a.value.delete(o.value), ln.layersWithOutsidePointerEventsDisabled.delete(o.value));
      });
    }), (h, y) => (fe(), De(C(Fn), {
      ref: C(r),
      "as-child": e.asChild,
      as: e.as,
      "data-dismissable-layer": "",
      style: Ls({ pointerEvents: c.value ? u.value ? "auto" : "none" : void 0 }),
      onFocusCapture: C(d).onFocusCapture,
      onBlurCapture: C(d).onBlurCapture,
      onPointerdownCapture: C(f).onPointerDownCapture
    }, {
      default: re(() => [We(h.$slots, "default")]),
      _: 3
    }, 8, [
      "as-child",
      "as",
      "style",
      "onFocusCapture",
      "onBlurCapture",
      "onPointerdownCapture"
    ]));
  }
}), iy = oy;
const ay = /* @__PURE__ */ xg(() => /* @__PURE__ */ oe([]));
function ly() {
  const e = ay();
  return {
    add(t) {
      const n = e.value[0];
      t !== n && n?.pause(), e.value = tl(e.value, t), e.value.unshift(t);
    },
    remove(t) {
      e.value = tl(e.value, t), e.value[0]?.resume();
    }
  };
}
function tl(e, t) {
  const n = [...e], s = n.indexOf(t);
  return s !== -1 && n.splice(s, 1), n;
}
const xo = "focusScope.autoFocusOnMount", wo = "focusScope.autoFocusOnUnmount", nl = {
  bubbles: !1,
  cancelable: !0
};
function cy(e, t) {
  let n = t;
  for (; n; ) {
    if (e.contains(n)) return !0;
    n = n.getRootNode().host ?? null;
  }
  return !1;
}
function uy(e, { select: t = !1 } = {}) {
  const n = Lt();
  for (const s of e)
    if (Gt(s, { select: t }), Lt() !== n) return !0;
}
function fy(e) {
  const t = ku(e), n = sl(t, e), s = sl(t.reverse(), e);
  return [n, s];
}
function ku(e) {
  const t = [], n = document.createTreeWalker(e, NodeFilter.SHOW_ELEMENT, { acceptNode: (s) => {
    const r = s.tagName === "INPUT" && s.type === "hidden";
    return s.disabled || s.hidden || r ? NodeFilter.FILTER_SKIP : s.tabIndex >= 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
  } });
  for (; n.nextNode(); ) t.push(n.currentNode);
  return t.sort((s, r) => s.tabIndex === r.tabIndex ? 0 : s.tabIndex === 0 ? 1 : r.tabIndex === 0 ? -1 : s.tabIndex - r.tabIndex);
}
function sl(e, t) {
  for (const n of e) if (!dy(n, { upTo: t })) return n;
}
function dy(e, { upTo: t }) {
  if (getComputedStyle(e).visibility === "hidden") return !0;
  for (; e; ) {
    if (t !== void 0 && e === t) return !1;
    if (getComputedStyle(e).display === "none") return !0;
    e = e.parentElement;
  }
  return !1;
}
function py(e) {
  return e instanceof HTMLInputElement && "select" in e;
}
function Gt(e, { select: t = !1 } = {}) {
  if (e && e.focus) {
    const n = Lt();
    e.focus({ preventScroll: !0 }), e !== n && py(e) && t && e.select();
  }
}
var hy = /* @__PURE__ */ ke({
  __name: "FocusScope",
  props: {
    loop: {
      type: Boolean,
      required: !1,
      default: !1
    },
    trapped: {
      type: Boolean,
      required: !1,
      default: !1
    },
    present: {
      type: Boolean,
      required: !1,
      default: !0
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    }
  },
  emits: ["mountAutoFocus", "unmountAutoFocus"],
  setup(e, { emit: t }) {
    const n = e, s = t, { currentRef: r, currentElement: o } = bt(), i = /* @__PURE__ */ oe(null), a = ly(), l = /* @__PURE__ */ jn({
      paused: !1,
      pause() {
        this.paused = !0;
      },
      resume() {
        this.paused = !1;
      }
    });
    Kn((f) => {
      if (!nn) return;
      const d = o.value;
      if (!n.trapped) return;
      const h = d?.ownerDocument ?? document, y = d ? d.getRootNode() : h;
      function v(O) {
        if (l.paused || !d) return;
        const U = O.target;
        d.contains(U) ? i.value = U : Gt(i.value, { select: !0 });
      }
      function w(O) {
        if (l.paused || !d) return;
        const U = O.relatedTarget;
        U !== null && (d.contains(U) || Gt(i.value, { select: !0 }));
      }
      function R(O) {
        const U = i.value;
        if (U === null || !O.some((j) => j.removedNodes.length > 0)) return;
        const F = Lt();
        if (F && d.contains(F)) return;
        d.contains(U) || Gt(d);
      }
      function x(O) {
        if (l.paused || !d) return;
        const U = O.composedPath()[0];
        cy(d, U) || Gt(i.value, { select: !0 });
      }
      y.addEventListener("focusin", v), y.addEventListener("focusout", w), y !== h && h.addEventListener("focusin", x);
      const N = new MutationObserver(R);
      d && N.observe(d, {
        childList: !0,
        subtree: !0
      }), f(() => {
        y.removeEventListener("focusin", v), y.removeEventListener("focusout", w), y !== h && h.removeEventListener("focusin", x), N.disconnect();
      });
    });
    function c(f, d) {
      const h = new CustomEvent(xo, nl), y = (v) => s("mountAutoFocus", v);
      f.addEventListener(xo, y), f.dispatchEvent(h), f.removeEventListener(xo, y), h.defaultPrevented || (uy(ku(f), { select: !0 }), Lt() === d && Gt(f));
    }
    Kn(async (f) => {
      const d = o.value;
      if (await St(), !d) return;
      n.present !== !1 && a.add(l);
      const h = Lt();
      !d.contains(h) && n.present !== !1 && c(d, h), f(() => {
        const v = new CustomEvent(wo, nl), w = (R) => {
          s("unmountAutoFocus", R);
        };
        d.addEventListener(wo, w), d.dispatchEvent(v), d.setAttribute("data-focus-scope-unmounting", ""), setTimeout(() => {
          v.defaultPrevented || Gt(h ?? document.body, { select: !0 }), d.removeEventListener(wo, w), a.remove(l), d.removeAttribute("data-focus-scope-unmounting");
        }, 0);
      });
    }), je(() => n.present, async (f, d) => {
      if (!nn) return;
      if (f === !1 && d === !0) {
        a.remove(l);
        return;
      }
      if (f !== !0 || d !== !1) return;
      a.add(l), await St();
      const h = o.value;
      if (!h) return;
      const y = Lt();
      h.contains(y) || c(h, y);
    });
    function u(f) {
      if (!n.loop && !n.trapped || l.paused) return;
      const d = f.key === "Tab" && !f.altKey && !f.ctrlKey && !f.metaKey, h = Lt();
      if (d && h) {
        const y = f.currentTarget, [v, w] = fy(y);
        v && w ? !f.shiftKey && h === w ? (f.preventDefault(), n.loop && Gt(v, { select: !0 })) : f.shiftKey && h === v && (f.preventDefault(), n.loop && Gt(w, { select: !0 })) : h === y && f.preventDefault();
      }
    }
    return (f, d) => (fe(), De(C(Fn), {
      ref_key: "currentRef",
      ref: r,
      tabindex: "-1",
      "as-child": e.asChild,
      as: e.as,
      onKeydown: u
    }, {
      default: re(() => [We(f.$slots, "default")]),
      _: 3
    }, 8, ["as-child", "as"]));
  }
}), my = hy;
function gy(e) {
  return e ? "open" : "closed";
}
var yy = /* @__PURE__ */ ke({
  __name: "DialogContentImpl",
  props: {
    forceMount: {
      type: Boolean,
      required: !1
    },
    trapFocus: {
      type: Boolean,
      required: !1
    },
    disableOutsidePointerEvents: {
      type: Boolean,
      required: !1
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    },
    present: {
      type: Boolean,
      required: !1
    }
  },
  emits: [
    "escapeKeyDown",
    "pointerDownOutside",
    "focusOutside",
    "interactOutside",
    "openAutoFocus",
    "closeAutoFocus"
  ],
  setup(e, { emit: t }) {
    const n = e, s = t, r = Ut(), { forwardRef: o, currentElement: i } = bt();
    return r.titleId ||= Jo(void 0, "reka-dialog-title"), r.descriptionId ||= Jo(void 0, "reka-dialog-description"), ss(() => {
      r.contentElement = i, Lt() !== document.body && (r.triggerElement.value = Lt());
    }), (a, l) => (fe(), De(C(my), {
      "as-child": "",
      loop: "",
      trapped: n.trapFocus,
      present: n.present,
      onMountAutoFocus: l[5] || (l[5] = (c) => s("openAutoFocus", c)),
      onUnmountAutoFocus: l[6] || (l[6] = (c) => s("closeAutoFocus", c))
    }, {
      default: re(() => [Y(C(iy), gt({
        id: C(r).contentId,
        ref: C(o),
        as: e.as,
        "as-child": e.asChild,
        present: n.present,
        "disable-outside-pointer-events": e.disableOutsidePointerEvents,
        role: "dialog",
        "aria-describedby": C(r).descriptionId,
        "aria-labelledby": C(r).titleId,
        "data-state": C(gy)(C(r).open.value)
      }, a.$attrs, {
        onDismiss: l[0] || (l[0] = (c) => C(r).onOpenChange(!1)),
        onEscapeKeyDown: l[1] || (l[1] = (c) => s("escapeKeyDown", c)),
        onFocusOutside: l[2] || (l[2] = (c) => s("focusOutside", c)),
        onInteractOutside: l[3] || (l[3] = (c) => s("interactOutside", c)),
        onPointerDownOutside: l[4] || (l[4] = (c) => s("pointerDownOutside", c))
      }), {
        default: re(() => [We(a.$slots, "default")]),
        _: 3
      }, 16, [
        "id",
        "as",
        "as-child",
        "present",
        "disable-outside-pointer-events",
        "aria-describedby",
        "aria-labelledby",
        "data-state"
      ])]),
      _: 3
    }, 8, ["trapped", "present"]));
  }
}), Su = yy, vy = /* @__PURE__ */ ke({
  __name: "DialogContentModal",
  props: {
    forceMount: {
      type: Boolean,
      required: !1
    },
    trapFocus: {
      type: Boolean,
      required: !1
    },
    disableOutsidePointerEvents: {
      type: Boolean,
      required: !1,
      default: !0
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    },
    present: {
      type: Boolean,
      required: !0
    }
  },
  emits: [
    "escapeKeyDown",
    "pointerDownOutside",
    "focusOutside",
    "interactOutside",
    "openAutoFocus",
    "closeAutoFocus"
  ],
  setup(e, { emit: t }) {
    const n = e, s = t, r = Ut(), o = Ai(s), { forwardRef: i, currentElement: a } = bt(), l = ue(() => n.present ? a.value : void 0);
    Wg(l);
    const c = ue(() => {
      const { present: u, ...f } = n;
      return f;
    });
    return je(() => n.present, (u, f) => {
      !u && f && r.triggerElement.value?.focus();
    }), (u, f) => (fe(), De(Su, gt({
      ...c.value,
      ...C(o)
    }, {
      ref: C(i),
      present: e.present,
      "trap-focus": C(r).open.value,
      "disable-outside-pointer-events": n.disableOutsidePointerEvents,
      onCloseAutoFocus: f[0] || (f[0] = (d) => {
        d.defaultPrevented || (d.preventDefault(), C(r).triggerElement.value?.focus());
      }),
      onPointerDownOutside: f[1] || (f[1] = (d) => {
        const h = d.detail.originalEvent, y = h.button === 0 && h.ctrlKey === !0;
        (h.button === 2 || y) && d.preventDefault();
      }),
      onFocusOutside: f[2] || (f[2] = (d) => {
        d.preventDefault();
      })
    }), {
      default: re(() => [We(u.$slots, "default")]),
      _: 3
    }, 16, [
      "present",
      "trap-focus",
      "disable-outside-pointer-events"
    ]));
  }
}), by = vy, _y = /* @__PURE__ */ ke({
  __name: "DialogContentNonModal",
  props: {
    forceMount: {
      type: Boolean,
      required: !1
    },
    trapFocus: {
      type: Boolean,
      required: !1
    },
    disableOutsidePointerEvents: {
      type: Boolean,
      required: !1
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    },
    present: {
      type: Boolean,
      required: !0
    }
  },
  emits: [
    "escapeKeyDown",
    "pointerDownOutside",
    "focusOutside",
    "interactOutside",
    "openAutoFocus",
    "closeAutoFocus"
  ],
  setup(e, { emit: t }) {
    const n = e, r = Ai(t);
    bt();
    const o = Ut(), i = /* @__PURE__ */ oe(!1), a = /* @__PURE__ */ oe(!1), l = ue(() => {
      const { present: c, ...u } = n;
      return u;
    });
    return je(() => n.present, (c, u) => {
      !c && u && (i.value || o.triggerElement.value?.focus(), i.value = !1, a.value = !1);
    }), (c, u) => (fe(), De(Su, gt({
      ...l.value,
      ...C(r)
    }, {
      present: e.present,
      "trap-focus": !1,
      "disable-outside-pointer-events": !1,
      onCloseAutoFocus: u[0] || (u[0] = (f) => {
        f.defaultPrevented || (i.value || C(o).triggerElement.value?.focus(), f.preventDefault()), i.value = !1, a.value = !1;
      }),
      onInteractOutside: u[1] || (u[1] = (f) => {
        f.defaultPrevented || (i.value = !0, f.detail.originalEvent.type === "pointerdown" && (a.value = !0));
        const d = f.target;
        C(o).triggerElement.value?.contains(d) && f.preventDefault(), f.detail.originalEvent.type === "focusin" && a.value && f.preventDefault();
      })
    }), {
      default: re(() => [We(c.$slots, "default")]),
      _: 3
    }, 16, ["present"]));
  }
}), xy = _y, wy = /* @__PURE__ */ ke({
  __name: "DialogContent",
  props: {
    forceMount: {
      type: Boolean,
      required: !1
    },
    disableOutsidePointerEvents: {
      type: Boolean,
      required: !1,
      default: void 0
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    }
  },
  emits: [
    "escapeKeyDown",
    "pointerDownOutside",
    "focusOutside",
    "interactOutside",
    "openAutoFocus",
    "closeAutoFocus"
  ],
  setup(e, { emit: t }) {
    const n = e, s = t, r = Ut(), o = Ai(s), { forwardRef: i } = bt(), a = ue(() => n.forceMount || !r.unmountOnHide.value);
    return (l, c) => (fe(), De(C(xu), {
      present: C(r).open.value,
      "force-mount": a.value
    }, {
      default: re(({ present: u }) => [C(r).modal.value ? Cs((fe(), De(by, gt({
        key: 0,
        ref: C(i),
        present: a.value ? u : !0
      }, {
        ...n,
        ...C(o),
        ...l.$attrs
      }), {
        default: re(() => [We(l.$slots, "default")]),
        _: 3
      }, 16, ["present"])), [[Lo, e.forceMount || C(r).unmountOnHide.value || u]]) : Cs((fe(), De(xy, gt({
        key: 1,
        ref: C(i),
        present: a.value ? u : !0
      }, {
        ...n,
        ...C(o),
        ...l.$attrs
      }), {
        default: re(() => [We(l.$slots, "default")]),
        _: 3
      }, 16, ["present"])), [[Lo, e.forceMount || C(r).unmountOnHide.value || u]])]),
      _: 3
    }, 8, ["present", "force-mount"]));
  }
}), ky = wy, Sy = /* @__PURE__ */ ke({
  __name: "DialogDescription",
  props: {
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1,
      default: "p"
    }
  },
  setup(e) {
    const t = e;
    bt();
    const n = Ut();
    return (s, r) => (fe(), De(C(Fn), gt(t, { id: C(n).descriptionId }), {
      default: re(() => [We(s.$slots, "default")]),
      _: 3
    }, 16, ["id"]));
  }
}), Ey = Sy, Cy = /* @__PURE__ */ ke({
  __name: "DialogOverlayImpl",
  props: {
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    },
    present: {
      type: Boolean,
      required: !1,
      default: !0
    }
  },
  setup(e) {
    const t = e, n = Ut(), s = $g(t.present);
    return je(() => t.present, (r) => s.value = r), bt(), (r, o) => (fe(), De(C(Fn), {
      as: e.as,
      "as-child": e.asChild,
      "data-state": C(n).open.value ? "open" : "closed",
      style: { "pointer-events": "auto" },
      onPointerdown: o[0] || (o[0] = Ud(() => {
      }, [
        "left",
        "self",
        "prevent"
      ]))
    }, {
      default: re(() => [We(r.$slots, "default")]),
      _: 3
    }, 8, [
      "as",
      "as-child",
      "data-state"
    ]));
  }
}), Ay = Cy, Oy = /* @__PURE__ */ ke({
  __name: "DialogOverlay",
  props: {
    forceMount: {
      type: Boolean,
      required: !1
    },
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1
    }
  },
  setup(e) {
    const t = e, n = Ut(), { forwardRef: s } = bt(), r = ue(() => t.forceMount || !n.unmountOnHide.value);
    return (o, i) => C(n)?.modal.value ? (fe(), De(C(xu), {
      key: 0,
      present: C(n).open.value,
      "force-mount": r.value
    }, {
      default: re(({ present: a }) => [Cs(Y(Ay, gt(o.$attrs, {
        ref: C(s),
        as: e.as,
        "as-child": e.asChild,
        present: r.value ? a : !0
      }), {
        default: re(() => [We(o.$slots, "default")]),
        _: 3
      }, 16, [
        "as",
        "as-child",
        "present"
      ]), [[Lo, e.forceMount || C(n).unmountOnHide.value || a]])]),
      _: 3
    }, 8, ["present", "force-mount"])) : Os("v-if", !0);
  }
}), Ry = Oy, Ty = /* @__PURE__ */ ke({
  __name: "Teleport",
  props: {
    to: {
      type: null,
      required: !1
    },
    disabled: {
      type: Boolean,
      required: !1
    },
    defer: {
      type: Boolean,
      required: !1
    },
    forceMount: {
      type: Boolean,
      required: !1
    }
  },
  setup(e) {
    const t = e, n = Ci({}), s = ue(() => t.to ?? n.teleportTo?.value ?? "body"), r = /* @__PURE__ */ Tg();
    return (o, i) => C(r) || e.forceMount ? (fe(), De(xf, {
      key: 0,
      to: s.value,
      disabled: e.disabled,
      defer: e.defer
    }, [We(o.$slots, "default")], 8, [
      "to",
      "disabled",
      "defer"
    ])) : Os("v-if", !0);
  }
}), Iy = Ty, Py = /* @__PURE__ */ ke({
  __name: "DialogPortal",
  props: {
    to: {
      type: null,
      required: !1
    },
    disabled: {
      type: Boolean,
      required: !1
    },
    defer: {
      type: Boolean,
      required: !1
    },
    forceMount: {
      type: Boolean,
      required: !1
    }
  },
  setup(e) {
    const t = e;
    return (n, s) => (fe(), De(C(Iy), Nu(pc(t)), {
      default: re(() => [We(n.$slots, "default")]),
      _: 3
    }, 16));
  }
}), Ny = Py, My = /* @__PURE__ */ ke({
  __name: "DialogTitle",
  props: {
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1,
      default: "h2"
    }
  },
  setup(e) {
    const t = e, n = Ut();
    return bt(), (s, r) => (fe(), De(C(Fn), gt(t, { id: C(n).titleId }), {
      default: re(() => [We(s.$slots, "default")]),
      _: 3
    }, 16, ["id"]));
  }
}), Dy = My, Ly = /* @__PURE__ */ ke({
  __name: "DialogTrigger",
  props: {
    asChild: {
      type: Boolean,
      required: !1
    },
    as: {
      type: null,
      required: !1,
      default: "button"
    }
  },
  setup(e) {
    const t = e, n = Ut(), { forwardRef: s, currentElement: r } = bt();
    return n.contentId ||= Jo(void 0, "reka-dialog-content"), ss(() => {
      n.triggerElement.value = r.value;
    }), (o, i) => (fe(), De(C(Fn), gt(t, {
      ref: C(s),
      type: e.as === "button" ? "button" : void 0,
      "aria-haspopup": "dialog",
      "aria-expanded": C(n).open.value || !1,
      "aria-controls": C(n).open.value ? C(n).contentId : void 0,
      "data-state": C(n).open.value ? "open" : "closed",
      onClick: C(n).onOpenToggle
    }), {
      default: re(() => [We(o.$slots, "default")]),
      _: 3
    }, 16, [
      "type",
      "aria-expanded",
      "aria-controls",
      "data-state",
      "onClick"
    ]));
  }
}), jy = Ly;
const $y = /* @__PURE__ */ rs("studio-infrastructure", () => {
  const e = /* @__PURE__ */ oe("unknown"), t = /* @__PURE__ */ oe(null), n = /* @__PURE__ */ oe(null);
  function s(i, a) {
    e.value = i, t.value = a ?? null;
  }
  function r(i) {
    n.value = i;
  }
  function o() {
    e.value = "unknown", t.value = null, n.value = null;
  }
  return { deployState: e, deployMessage: t, syncSummary: n, setDeploy: s, setSyncSummary: r, reset: o };
}), rl = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, ol = Qc, Fy = (e, t) => (n) => {
  var s;
  if (t?.variants == null) return ol(e, n?.class, n?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = n?.[c], f = o?.[c];
    if (u === null) return null;
    const d = rl(u) || rl(f);
    return r[c][d];
  }), a = n && Object.entries(n).reduce((c, u) => {
    let [f, d] = u;
    return d === void 0 || (c[f] = d), c;
  }, {}), l = t == null || (s = t.compoundVariants) === null || s === void 0 ? void 0 : s.reduce((c, u) => {
    let { class: f, className: d, ...h } = u;
    return Object.entries(h).every((y) => {
      let [v, w] = y;
      return Array.isArray(w) ? w.includes({
        ...o,
        ...a
      }[v]) : {
        ...o,
        ...a
      }[v] === w;
    }) ? [
      ...c,
      f,
      d
    ] : c;
  }, []);
  return ol(e, i, l, n?.class, n?.className);
}, Vy = Fy(
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
), By = ["type", "disabled"], gn = /* @__PURE__ */ ke({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, n) => (fe(), it("button", {
      type: e.type,
      disabled: e.disabled,
      class: yt(C(Vy)({ variant: e.variant, size: e.size }))
    }, [
      We(t.$slots, "default")
    ], 10, By));
  }
}), sn = /* @__PURE__ */ ke({
  __name: "StudioCard",
  setup(e) {
    return (t, n) => (fe(), it("div", {
      class: yt(
        C(ki)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      We(t.$slots, "default")
    ], 2));
  }
});
function Fs(e) {
  return ki(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
function zy() {
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
const Uy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Wy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, Hy = { class: "cmst:text-sm cmst:mt-2" }, qy = { key: 0 }, Zy = { class: "cmst:text-sm cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Gy = { class: "cmst:flex cmst:justify-end cmst:mt-4" }, Ky = /* @__PURE__ */ ke({
  __name: "BackendView",
  setup(e) {
    const t = $y(), n = /* @__PURE__ */ oe(!1), s = /* @__PURE__ */ oe(null);
    ss(() => {
      s.value = zy();
    });
    function r() {
      t.setDeploy("idle", "Phase-1 local snapshot (no backend call)."), t.setSyncSummary("sync snapshot: not polled in Phase 1");
    }
    return (o, i) => (fe(), it("section", {
      class: yt(C(Fs)()),
      "data-testid": "vue-page-backend"
    }, [
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          H("h2", Uy, [
            Y(C(Vc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            i[1] || (i[1] = le(" Manage Modal (Phase-1 proof) ", -1))
          ]),
          i[4] || (i[4] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, [
            le(" Route key stays "),
            H("code", null, "backend"),
            le(". Product functionality is intentionally not ported yet. ")
          ], -1)),
          H("div", Wy, [
            Y(gn, {
              variant: "secondary",
              size: "sm",
              onClick: r
            }, {
              default: re(() => [...i[2] || (i[2] = [
                le(" Simulate local snapshot ", -1)
              ])]),
              _: 1
            })
          ]),
          H("p", Hy, [
            i[3] || (i[3] = le(" Deploy: ", -1)),
            H("strong", null, Ne(C(t).deployState), 1),
            C(t).deployMessage ? (fe(), it("span", qy, " — " + Ne(C(t).deployMessage), 1)) : Os("", !0)
          ])
        ]),
        _: 1
      }),
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          H("h3", Zy, [
            Y(C(ph), {
              class: "cmst:size-4",
              "aria-hidden": "true"
            }),
            i[5] || (i[5] = le(" Portalled dialog proof (Reka → Studio portal target) ", -1))
          ]),
          Y(C(Yg), {
            open: n.value,
            "onUpdate:open": i[0] || (i[0] = (a) => n.value = a)
          }, {
            default: re(() => [
              Y(C(jy), { "as-child": "" }, {
                default: re(() => [
                  Y(gn, {
                    variant: "outline",
                    size: "sm",
                    "data-testid": "vue-dialog-open"
                  }, {
                    default: re(() => [...i[6] || (i[6] = [
                      le(" Open Studio dialog ", -1)
                    ])]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              Y(C(Ny), {
                to: s.value ?? void 0
              }, {
                default: re(() => [
                  Y(C(Ry), { class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:bg-black/60" }),
                  Y(C(ky), {
                    class: "cmst:fixed cmst:left-1/2 cmst:top-1/2 cmst:z-[71] cmst:w-[min(28rem,90vw)] cmst:-translate-x-1/2 cmst:-translate-y-1/2 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-5 cmst:text-cmst-fg cmst:shadow-xl",
                    "data-testid": "vue-dialog-content"
                  }, {
                    default: re(() => [
                      Y(C(Dy), { class: "cmst:text-base cmst:font-semibold" }, {
                        default: re(() => [...i[7] || (i[7] = [
                          le(" Contained in [data-studio-portals] ", -1)
                        ])]),
                        _: 1
                      }),
                      Y(C(Ey), { class: "cmst:text-sm cmst:opacity-80 cmst:mt-1" }, {
                        default: re(() => [...i[8] || (i[8] = [
                          le(" This overlay teleports into the Studio portal host, not document.body. Focus returns to the trigger on close. ", -1)
                        ])]),
                        _: 1
                      }),
                      H("div", Gy, [
                        Y(C(Xg), { "as-child": "" }, {
                          default: re(() => [
                            Y(gn, {
                              variant: "default",
                              size: "sm",
                              "data-testid": "vue-dialog-close"
                            }, {
                              default: re(() => [...i[9] || (i[9] = [
                                le(" Close ", -1)
                              ])]),
                              _: 1
                            })
                          ]),
                          _: 1
                        })
                      ])
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["to"])
            ]),
            _: 1
          }, 8, ["open"])
        ]),
        _: 1
      })
    ], 2));
  }
}), Jy = /* @__PURE__ */ rs("studio-history", () => {
  const e = /* @__PURE__ */ oe(null), t = /* @__PURE__ */ oe("");
  function n(o) {
    e.value = o;
  }
  function s(o) {
    t.value = o;
  }
  function r() {
    e.value = null, t.value = "";
  }
  return { focusId: e, query: t, setFocus: n, setQuery: s, clear: r };
});
function Yy() {
  let e = 0, t = null;
  return {
    run: (s) => {
      e += 1;
      const r = e, o = t;
      o && (o.superseded = !0, o.controller.abort());
      const i = new AbortController(), a = { controller: i, superseded: !1 };
      let l;
      const c = new Promise((d) => {
        l = () => d({ stale: !0 });
      }), u = () => l();
      i.signal.addEventListener("abort", u, { once: !0 }), t = a;
      const f = () => {
        i.signal.removeEventListener("abort", u), t === a && (t = null);
      };
      return (async () => {
        try {
          return await Promise.race([
            s(i.signal).then((d) => r !== e || a.superseded || i.signal.aborted ? { stale: !0 } : { stale: !1, value: d }),
            c
          ]);
        } catch (d) {
          if (a.superseded || r !== e || i.signal.aborted)
            return { stale: !0 };
          throw d;
        } finally {
          f();
        }
      })();
    },
    abort: (s) => {
      t?.controller.abort(s);
    },
    get pending() {
      return t !== null;
    }
  };
}
const Qy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Xy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, ev = { class: "cmst:text-sm cmst:mt-2" }, tv = { "data-testid": "vue-history-stale" }, nv = /* @__PURE__ */ ke({
  __name: "HistoryView",
  setup(e) {
    const t = sh(), n = Jy(), s = /* @__PURE__ */ oe(""), r = /* @__PURE__ */ oe(null), o = /* @__PURE__ */ oe(0);
    function i(c, u) {
      return new Promise((f, d) => {
        const h = setTimeout(() => f(`detail:${c}`), 300);
        u.addEventListener(
          "abort",
          () => {
            clearTimeout(h), d(new DOMException("Aborted", "AbortError"));
          },
          { once: !0 }
        );
      });
    }
    const a = Yy();
    async function l() {
      const c = s.value.trim();
      if (!c) return;
      n.setFocus(c), await t.push({ name: "history", query: { focus: c } });
      const u = await a.run((f) => i(c, f));
      if (u.stale) {
        o.value += 1;
        return;
      }
      r.value = u.value;
    }
    return (c, u) => (fe(), it("section", {
      class: yt(C(Fs)()),
      "data-testid": "vue-page-history"
    }, [
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          H("h2", Qy, [
            Y(C(Fc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            u[1] || (u[1] = le(" History (Phase-1 proof) ", -1))
          ]),
          u[6] || (u[6] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Focus identity lives in the history store; detail reads go through the shared latest-read-wins primitive. ", -1)),
          H("div", Xy, [
            Cs(H("input", {
              "onUpdate:modelValue": u[0] || (u[0] = (f) => s.value = f),
              type: "text",
              placeholder: "Focus id (e.g. gen_123)",
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm",
              "data-testid": "vue-history-focus-input"
            }, null, 512), [
              [bc, s.value]
            ]),
            Y(gn, {
              variant: "secondary",
              size: "sm",
              "data-testid": "vue-history-focus-apply",
              onClick: l
            }, {
              default: re(() => [...u[2] || (u[2] = [
                le(" Load focus ", -1)
              ])]),
              _: 1
            })
          ]),
          H("p", ev, [
            u[3] || (u[3] = le(" Store focus: ", -1)),
            H("strong", null, Ne(C(n).focusId ?? "none"), 1),
            u[4] || (u[4] = le(" · Committed read: ", -1)),
            H("strong", null, Ne(r.value ?? "none"), 1),
            u[5] || (u[5] = le(" · Stale drops: ", -1)),
            H("strong", tv, Ne(o.value), 1)
          ]),
          u[7] || (u[7] = H("p", { class: "cmst:text-xs cmst:opacity-70" }, " Tip: click “Load focus” rapidly with different ids — only the newest read commits; older ones are dropped as stale. ", -1))
        ]),
        _: 1
      })
    ], 2));
  }
}), sv = /* @__PURE__ */ rs("studio-playground", () => {
  const e = /* @__PURE__ */ oe("txt2img"), t = /* @__PURE__ */ oe(!1);
  function n(r) {
    e.value = r;
  }
  function s(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: n, setExperimentMode: s };
}), rv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, ov = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, iv = ["checked"], av = { class: "cmst:text-sm cmst:opacity-80" }, lv = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, cv = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, uv = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, fv = { key: 0 }, dv = /* @__PURE__ */ ke({
  __name: "PlaygroundView",
  setup(e) {
    const t = sv(), n = qc(), s = /* @__PURE__ */ oe(null), r = ue(() => s.value ? n.get(s.value)?.progress ?? null : null);
    function o() {
      if (s.value) return;
      const i = n.start({
        kind: "other",
        label: "Synthetic local proof operation",
        status: "running",
        progress: 0,
        message: "Counting to ten locally — no backend involved."
      });
      s.value = i;
      let a = 0;
      const l = setInterval(() => {
        if (a += 1, a >= 10) {
          clearInterval(l), n.finish(i, "Synthetic proof completed."), s.value = null;
          return;
        }
        n.patch(i, { progress: a / 10, message: `Local tick ${a}/10` });
      }, 150);
    }
    return (i, a) => (fe(), it("section", {
      class: yt(C(Fs)()),
      "data-testid": "vue-page-playground"
    }, [
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          H("h2", rv, [
            Y(C(jc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = le(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          H("label", ov, [
            H("input", {
              type: "checkbox",
              checked: C(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => C(t).setExperimentMode(l.target.checked))
            }, null, 40, iv),
            a[2] || (a[2] = le(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          a[5] || (a[5] = H("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          H("p", av, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + Ne(C(n).active.length) + ". ", 1),
          H("div", lv, [
            Y(gn, {
              variant: "default",
              size: "sm",
              disabled: s.value !== null,
              onClick: o
            }, {
              default: re(() => [
                Y(C(vh), { "aria-hidden": "true" }),
                a[4] || (a[4] = le(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? (fe(), it("span", cv, Ne(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : Os("", !0)
          ]),
          H("ul", uv, [
            (fe(!0), it(qe, null, Zl(C(n).all.slice(-5), (l) => (fe(), it("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              H("strong", null, Ne(l.label), 1),
              le(" — " + Ne(l.status), 1),
              l.message ? (fe(), it("span", fv, " — " + Ne(l.message), 1)) : Os("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), pv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, hv = { class: "cmst:text-sm cmst:mt-2" }, mv = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, gv = {
  class: "cmst:text-sm",
  "data-testid": "vue-density-value"
}, yv = /* @__PURE__ */ ke({
  __name: "SettingsView",
  setup(e) {
    const t = Jc();
    function n() {
      t.setDensity(t.density === "compact" ? "comfortable" : "compact");
    }
    return (s, r) => (fe(), it("section", {
      class: yt(C(Fs)()),
      "data-testid": "vue-page-settings"
    }, [
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          H("h2", pv, [
            Y(C(Bc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            r[0] || (r[0] = le(" Settings (Phase-1 proof) ", -1))
          ]),
          r[2] || (r[2] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Section identity lives in the settings store. ", -1)),
          H("p", hv, [
            r[1] || (r[1] = le(" Active section: ", -1)),
            H("strong", null, Ne(C(t).activeSection), 1)
          ])
        ]),
        _: 1
      }),
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          r[4] || (r[4] = H("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Persisted preference proof", -1)),
          r[5] || (r[5] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, [
            le(" Shell density survives reload via the explicit persistence helper (Zod-validated; malformed data falls back to "),
            H("code", null, "comfortable"),
            le("). ")
          ], -1)),
          H("div", mv, [
            Y(gn, {
              variant: "outline",
              size: "sm",
              "data-testid": "vue-density-toggle",
              onClick: n
            }, {
              default: re(() => [...r[3] || (r[3] = [
                le(" Toggle density ", -1)
              ])]),
              _: 1
            }),
            H("span", gv, Ne(C(t).density), 1)
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), vv = /* @__PURE__ */ rs("studio-workflows", () => {
  const e = /* @__PURE__ */ oe(null);
  function t(s) {
    e.value = s;
  }
  function n() {
    e.value = null;
  }
  return { selectedId: e, select: t, clear: n };
});
function bv(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function _v(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((n, s) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), n();
    }, e), o = () => {
      clearTimeout(r), s(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((n) => setTimeout(n, e));
}
async function xv(e) {
  const { intervalMs: t, signal: n, run: s, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    bv(n), i += 1, o && o(i);
    const a = await s(n, i);
    if (r(a)) return a;
    await _v(t, n);
  }
}
const wv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, kv = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, Sv = { class: "cmst:text-sm cmst:mt-2" }, Ev = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, Cv = {
  class: "cmst:text-sm",
  "data-testid": "vue-poll-status"
}, Av = /* @__PURE__ */ ke({
  __name: "WorkflowsView",
  setup(e) {
    const t = vv(), n = /* @__PURE__ */ oe(""), s = /* @__PURE__ */ oe("idle"), r = /* @__PURE__ */ oe(0);
    async function o() {
      s.value = "polling…", r.value = 0;
      let i = 0;
      const a = await xv({
        intervalMs: 120,
        run: async (l, c) => (r.value = c, i += 1, i >= 3 ? "ready" : "warming"),
        done: (l) => l === "ready"
      });
      s.value = a;
    }
    return (i, a) => (fe(), it("section", {
      class: yt(C(Fs)()),
      "data-testid": "vue-page-workflows"
    }, [
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          H("h2", wv, [
            Y(C($c), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[2] || (a[2] = le(" Workflows (Phase-1 proof) ", -1))
          ]),
          a[5] || (a[5] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Selection identity lives in the workflows store. ", -1)),
          H("div", kv, [
            Cs(H("input", {
              "onUpdate:modelValue": a[0] || (a[0] = (l) => n.value = l),
              type: "text",
              placeholder: "Workflow id",
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm"
            }, null, 512), [
              [bc, n.value]
            ]),
            Y(gn, {
              variant: "secondary",
              size: "sm",
              onClick: a[1] || (a[1] = (l) => C(t).select(n.value.trim() || null))
            }, {
              default: re(() => [...a[3] || (a[3] = [
                le(" Select ", -1)
              ])]),
              _: 1
            })
          ]),
          H("p", Sv, [
            a[4] || (a[4] = le(" Store selection: ", -1)),
            H("strong", null, Ne(C(t).selectedId ?? "none"), 1)
          ])
        ]),
        _: 1
      }),
      Y(sn, { class: "cmst:p-4" }, {
        default: re(() => [
          a[7] || (a[7] = H("h3", { class: "cmst:text-sm cmst:font-semibold" }, "polling demo (local only)", -1)),
          a[8] || (a[8] = H("p", { class: "cmst:text-sm cmst:opacity-80" }, " Repeats a local status check until the completion predicate holds. ", -1)),
          H("div", Ev, [
            Y(gn, {
              variant: "outline",
              size: "sm",
              "data-testid": "vue-poll-run",
              onClick: o
            }, {
              default: re(() => [...a[6] || (a[6] = [
                le(" Start local poll ", -1)
              ])]),
              _: 1
            }),
            H("span", Cv, Ne(s.value) + " (" + Ne(r.value) + " attempts) ", 1)
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), Ov = {
  playground: dv,
  history: nv,
  workflows: Av,
  backend: Ky,
  settings: yv
};
function Rv(e = {}) {
  let t;
  return e.memory || !e.win ? t = Lp() : t = bg(e.win, e.initial), nh({
    history: t,
    routes: bi.map((s) => ({
      path: `/${s}`,
      name: s,
      component: Ov[s]
    }))
  });
}
function Tv(e, t = {}) {
  const n = Kd(), s = Rv({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = qd(yg);
  return r.use(n), r.use(s), r.mount(e), {
    app: r,
    router: s,
    pinia: n,
    unmount: () => {
      r.unmount();
    }
  };
}
export {
  Tv as mountStudioPreview
};

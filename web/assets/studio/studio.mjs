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
const ke = {}, Rn = [], jt = () => {
}, ol = () => !1, kr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), Sr = (e) => e.startsWith("onUpdate:"), Ge = Object.assign, Qo = (e, t) => {
  const n = e.indexOf(t);
  n > -1 && e.splice(n, 1);
}, Su = Object.prototype.hasOwnProperty, ye = (e, t) => Su.call(e, t), Y = Array.isArray, hn = (e) => Ds(e) === "[object Map]", rr = (e) => Ds(e) === "[object Set]", Ti = (e) => Ds(e) === "[object Date]", ee = (e) => typeof e == "function", Te = (e) => typeof e == "string", dt = (e) => typeof e == "symbol", be = (e) => e !== null && typeof e == "object", il = (e) => (be(e) || ee(e)) && ee(e.then) && ee(e.catch), al = Object.prototype.toString, Ds = (e) => al.call(e), Eu = (e) => Ds(e).slice(8, -1), ll = (e) => Ds(e) === "[object Object]", Er = (e) => Te(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, ms = /* @__PURE__ */ Yo(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), Cr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((n) => t[n] || (t[n] = e(n)));
}, Cu = /-\w/g, Ye = Cr(
  (e) => e.replace(Cu, (t) => t.slice(1).toUpperCase())
), Au = /\B([A-Z])/g, Ln = Cr(
  (e) => e.replace(Au, "-$1").toLowerCase()
), Ar = Cr((e) => e.charAt(0).toUpperCase() + e.slice(1)), tr = Cr(
  (e) => e ? `on${Ar(e)}` : ""
), Dt = (e, t) => !Object.is(e, t), nr = (e, ...t) => {
  for (let n = 0; n < e.length; n++)
    e[n](...t);
}, cl = (e, t, n, s = !1) => {
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
let Ii;
const Or = () => Ii || (Ii = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Ls(e) {
  if (Y(e)) {
    const t = {};
    for (let n = 0; n < e.length; n++) {
      const s = e[n], r = Te(s) ? Iu(s) : Ls(s);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (Te(e) || be(e))
    return e;
}
const Ou = /;(?![^(]*\))/g, Ru = /:([^]+)/, Tu = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function Iu(e) {
  const t = {};
  return e.replace(Tu, (n) => n.startsWith("/*") ? "" : n).split(Ou).forEach((n) => {
    if (n) {
      const s = n.split(Ru);
      s.length > 1 && (t[s[0].trim()] = s[1].trim());
    }
  }), t;
}
function Se(e) {
  let t = "";
  if (Te(e))
    t = e;
  else if (Y(e))
    for (let n = 0; n < e.length; n++) {
      const s = Se(e[n]);
      s && (t += s + " ");
    }
  else if (be(e))
    for (const n in e)
      e[n] && (t += n + " ");
  return t.trim();
}
function Pu(e) {
  if (!e) return null;
  let { class: t, style: n } = e;
  return t && !Te(t) && (e.class = Se(t)), n && (e.style = Ls(n)), e;
}
const Nu = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", Mu = /* @__PURE__ */ Yo(Nu);
function ul(e) {
  return !!e || e === "";
}
function Du(e, t, n) {
  if (e.length !== t.length) return !1;
  let s = !0;
  for (let r = 0; s && r < e.length; r++)
    s = Rr(e[r], t[r], n);
  return s;
}
function Pi(e, t, n) {
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
function Lu(e, t, n) {
  let s = hn(e), r = hn(t);
  if (s || r || (s = rr(e), r = rr(t), s || r))
    return s && r ? Pi(e, t, n) : !1;
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
function Ni(e, t, n, s) {
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
  let s = Ti(e), r = Ti(t);
  return s || r ? s && r ? e.getTime() === t.getTime() : !1 : (s = dt(e), r = dt(t), s || r ? e === t : (s = Y(e), r = Y(t), s || r ? s && r ? Ni(e, t, n, Du) : !1 : (s = be(e), r = be(t), s || r ? !s || !r ? !1 : Ni(e, t, n, Lu) : String(e) === String(t))));
}
const fl = (e) => !!(e && e.__v_isRef === !0), Me = (e) => Te(e) ? e : e == null ? "" : Y(e) || be(e) && (e.toString === al || !ee(e.toString)) ? fl(e) ? Me(e.value) : JSON.stringify(e, dl, 2) : String(e), dl = (e, t) => fl(t) ? dl(e, t.value) : hn(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (n, [s, r], o) => (n[Hr(s, o) + " =>"] = r, n),
    {}
  )
} : rr(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((n) => Hr(n))
} : dt(t) ? Hr(t) : be(t) && !Y(t) && !ll(t) ? String(t) : t, Hr = (e, t = "") => {
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
let ze;
class pl {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && ze && (ze.active ? (this.parent = ze, this.index = (ze.scopes || (ze.scopes = [])).push(
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
      const n = ze;
      try {
        return ze = this, t();
      } finally {
        ze = n;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = ze, ze = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (ze === this)
        ze = this.prevScope;
      else {
        let t = ze;
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
  return new pl(e);
}
function Ir() {
  return ze;
}
function ei(e, t = !1) {
  ze && ze.cleanups.push(e);
}
let Ee;
const qr = /* @__PURE__ */ new WeakSet();
class hl {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, ze && (ze.active ? ze.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, qr.has(this) && (qr.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || gl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, Mi(this), yl(this);
    const t = Ee, n = wt;
    Ee = this, wt = !0;
    try {
      return this.fn();
    } finally {
      vl(this), Ee = t, wt = n, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        si(t);
      this.deps = this.depsTail = void 0, Mi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? qr.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
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
let ml = 0, gs, ys;
function gl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = ys, ys = e;
    return;
  }
  e.next = gs, gs = e;
}
function ti() {
  ml++;
}
function ni() {
  if (--ml > 0)
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
function yl(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function vl(e) {
  let t, n = e.depsTail, s = n;
  for (; s; ) {
    const r = s.prevDep;
    s.version === -1 ? (s === n && (n = r), si(s), ju(s)) : t = s, s.dep.activeLink = s.prevActiveLink, s.prevActiveLink = void 0, s = r;
  }
  e.deps = t, e.depsTail = n;
}
function ko(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (bl(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function bl(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === ks) || (e.globalVersion = ks, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !ko(e))))
    return;
  e.flags |= 2;
  const t = e.dep, n = Ee, s = wt;
  Ee = e, wt = !0;
  try {
    yl(e);
    const r = e.fn(e._value);
    (t.version === 0 || Dt(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Ee = n, wt = s, vl(e), e.flags &= -3;
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
function ju(e) {
  const { prevDep: t, nextDep: n } = e;
  t && (t.nextDep = n, e.prevDep = void 0), n && (n.prevDep = t, e.nextDep = void 0);
}
let wt = !0;
const _l = [];
function Vt() {
  _l.push(wt), wt = !1;
}
function Bt() {
  const e = _l.pop();
  wt = e === void 0 ? !0 : e;
}
function Mi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const n = Ee;
    Ee = void 0;
    try {
      t();
    } finally {
      Ee = n;
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
    if (!Ee || !wt || Ee === this.computed)
      return;
    let n = this.activeLink;
    if (n === void 0 || n.sub !== Ee)
      n = this.activeLink = new Fu(Ee, this), Ee.deps ? (n.prevDep = Ee.depsTail, Ee.depsTail.nextDep = n, Ee.depsTail = n) : Ee.deps = Ee.depsTail = n, xl(n);
    else if (n.version === -1 && (n.version = this.version, n.nextDep)) {
      const s = n.nextDep;
      s.prevDep = n.prevDep, n.prevDep && (n.prevDep.nextDep = s), n.prevDep = Ee.depsTail, n.nextDep = void 0, Ee.depsTail.nextDep = n, Ee.depsTail = n, Ee.deps === n && (Ee.deps = s);
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
function xl(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let s = t.deps; s; s = s.nextDep)
        xl(s);
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
  if (wt && Ee) {
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
    const l = Y(e), c = l && Er(n);
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
function $u(e, t) {
  const n = or.get(e);
  return n && n.get(t);
}
function Vn(e) {
  const t = /* @__PURE__ */ he(e);
  return t === e || (Ke(t, "iterate", Ss), /* @__PURE__ */ ft(e)) ? t : /* @__PURE__ */ zt(e) ? /* @__PURE__ */ Ft(e) ? t.map((n) => yn(gt(n))) : t.map(yn) : t.map(gt);
}
function Pr(e) {
  return Ke(e = /* @__PURE__ */ he(e), "iterate", Ss), e;
}
function Pt(e, t) {
  return /* @__PURE__ */ zt(e) ? yn(/* @__PURE__ */ Ft(e) ? gt(t) : t) : gt(t);
}
const Vu = {
  __proto__: null,
  [Symbol.iterator]() {
    return Zr(this, Symbol.iterator, (e) => Pt(this, e));
  },
  concat(...e) {
    return Vn(this).concat(
      ...e.map((t) => Y(t) ? Vn(t) : t)
    );
  },
  entries() {
    return Zr(this, "entries", (e) => (e[1] = Pt(this, e[1]), e));
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
    return Gr(this, "includes", e);
  },
  indexOf(...e) {
    return Gr(this, "indexOf", e);
  },
  join(e) {
    return Vn(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return Gr(this, "lastIndexOf", e);
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
    return Li(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return Li(this, "reduceRight", e, t);
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
    return Zr(this, "values", (e) => Pt(this, e));
  }
};
function Zr(e, t, n) {
  const s = Pr(e), r = s[t], o = r.call(s);
  if (s !== e && !/* @__PURE__ */ ft(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => Di(o.next(), n), r !== wl[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => Di(o._next(), n);
  }
  return o;
}
function Di(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const wl = Array.prototype;
function Ht(e, t, n, s, r, o) {
  const i = Pr(e), a = i !== e && !/* @__PURE__ */ ft(e), l = i[t];
  if (l !== wl[t]) {
    const f = l.apply(e, o);
    return a ? gt(f) : f;
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
function Li(e, t, n, s) {
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
function Gr(e, t, n) {
  const s = /* @__PURE__ */ he(e);
  Ke(s, "iterate", Ss);
  const r = s[t](...n);
  return (r === -1 || r === !1) && /* @__PURE__ */ Nr(n[0]) ? (n[0] = /* @__PURE__ */ he(n[0]), s[t](...n)) : r;
}
function is(e, t, n = []) {
  Vt(), ti();
  const s = (/* @__PURE__ */ he(e))[t].apply(e, n);
  return ni(), Bt(), s;
}
const Bu = /* @__PURE__ */ Yo("__proto__,__v_isRef,__isVue"), kl = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(dt)
);
function zu(e) {
  dt(e) || (e = String(e));
  const t = /* @__PURE__ */ he(this);
  return Ke(t, "has", e), t.hasOwnProperty(e);
}
class Sl {
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
      return s === (r ? o ? Qu : Ol : o ? Al : Cl).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(s) ? t : void 0;
    const i = Y(t);
    if (!r) {
      let l;
      if (i && (l = Vu[n]))
        return l;
      if (n === "hasOwnProperty")
        return zu;
    }
    const a = Reflect.get(
      t,
      n,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ De(t) ? t : s
    );
    if ((dt(n) ? kl.has(n) : Bu(n)) || (r || Ke(t, "get", n), o))
      return a;
    if (/* @__PURE__ */ De(a)) {
      const l = i && Er(n) ? a : a.value;
      return r && be(l) ? /* @__PURE__ */ Co(l) : l;
    }
    return be(a) ? r ? /* @__PURE__ */ Co(a) : /* @__PURE__ */ jn(a) : a;
  }
}
class El extends Sl {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, n, s, r) {
    let o = t[n];
    const i = Y(t) && Er(n);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ zt(o);
      if (!/* @__PURE__ */ ft(s) && !/* @__PURE__ */ zt(s) && (o = /* @__PURE__ */ he(o), s = /* @__PURE__ */ he(s)), !i && /* @__PURE__ */ De(o) && !/* @__PURE__ */ De(s))
        return c || (o.value = s), !0;
    }
    const a = i ? Number(n) < t.length : ye(t, n), l = Reflect.set(
      t,
      n,
      s,
      /* @__PURE__ */ De(t) ? t : r
    );
    return t === /* @__PURE__ */ he(r) && l && (a ? Dt(s, o) && Yt(t, "set", n, s) : Yt(t, "add", n, s)), l;
  }
  deleteProperty(t, n) {
    const s = ye(t, n);
    t[n];
    const r = Reflect.deleteProperty(t, n);
    return r && s && Yt(t, "delete", n, void 0), r;
  }
  has(t, n) {
    const s = Reflect.has(t, n);
    return (!dt(n) || !kl.has(n)) && Ke(t, "has", n), s;
  }
  ownKeys(t) {
    return Ke(
      t,
      "iterate",
      Y(t) ? "length" : Pn
    ), Reflect.ownKeys(t);
  }
}
class Uu extends Sl {
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
const Wu = /* @__PURE__ */ new El(), Hu = /* @__PURE__ */ new Uu(), qu = /* @__PURE__ */ new El(!0);
const Eo = (e) => e, Vs = (e) => Reflect.getPrototypeOf(e);
function Zu(e, t, n) {
  return function(...s) {
    const r = this.__v_raw, o = /* @__PURE__ */ he(r), i = hn(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...s), u = n ? Eo : t ? yn : gt;
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
function Gu(e, t) {
  const n = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ he(o), a = /* @__PURE__ */ he(r);
      e || (Dt(r, a) && Ke(i, "get", r), Ke(i, "get", a));
      const { has: l } = Vs(i), c = t ? Eo : e ? yn : gt;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && Ke(/* @__PURE__ */ he(r), "iterate", Pn), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ he(o), a = /* @__PURE__ */ he(r);
      return e || (Dt(r, a) && Ke(i, "has", r), Ke(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ he(a), c = t ? Eo : e ? yn : gt;
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
        const o = /* @__PURE__ */ he(this), i = Vs(o), a = /* @__PURE__ */ he(r), l = !t && !/* @__PURE__ */ ft(r) && !/* @__PURE__ */ zt(r) ? a : r;
        return i.has.call(o, l) || Dt(r, l) && i.has.call(o, r) || Dt(a, l) && i.has.call(o, a) || (o.add(l), Yt(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ ft(o) && !/* @__PURE__ */ zt(o) && (o = /* @__PURE__ */ he(o));
        const i = /* @__PURE__ */ he(this), { has: a, get: l } = Vs(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ he(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? Dt(o, u) && Yt(i, "set", r, o) : Yt(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ he(this), { has: i, get: a } = Vs(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ he(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && Yt(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ he(this), o = r.size !== 0, i = r.clear();
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
    n[r] = Zu(r, e, t);
  }), n;
}
function oi(e, t) {
  const n = Gu(e, t);
  return (s, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? s : Reflect.get(
    ye(n, r) && r in s ? n : s,
    r,
    o
  );
}
const Ku = {
  get: /* @__PURE__ */ oi(!1, !1)
}, Ju = {
  get: /* @__PURE__ */ oi(!1, !0)
}, Yu = {
  get: /* @__PURE__ */ oi(!0, !1)
};
const Cl = /* @__PURE__ */ new WeakMap(), Al = /* @__PURE__ */ new WeakMap(), Ol = /* @__PURE__ */ new WeakMap(), Qu = /* @__PURE__ */ new WeakMap();
function Xu(e) {
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
    Wu,
    Ku,
    Cl
  );
}
// @__NO_SIDE_EFFECTS__
function Rl(e) {
  return ii(
    e,
    !1,
    qu,
    Ju,
    Al
  );
}
// @__NO_SIDE_EFFECTS__
function Co(e) {
  return ii(
    e,
    !0,
    Hu,
    Yu,
    Ol
  );
}
function ii(e, t, n, s, r) {
  if (!be(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = Xu(Eu(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? s : n
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Ft(e) {
  return /* @__PURE__ */ zt(e) ? /* @__PURE__ */ Ft(e.__v_raw) : !!(e && e.__v_isReactive);
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
function he(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ he(t) : e;
}
function ai(e) {
  return !ye(e, "__v_skip") && Object.isExtensible(e) && cl(e, "__v_skip", !0), e;
}
const gt = (e) => be(e) ? /* @__PURE__ */ jn(e) : e, yn = (e) => be(e) ? /* @__PURE__ */ Co(e) : e;
// @__NO_SIDE_EFFECTS__
function De(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function se(e) {
  return Tl(e, !1);
}
// @__NO_SIDE_EFFECTS__
function Zn(e) {
  return Tl(e, !0);
}
function Tl(e, t) {
  return /* @__PURE__ */ De(e) ? e : new ef(e, t);
}
class ef {
  constructor(t, n) {
    this.dep = new ri(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = n ? t : /* @__PURE__ */ he(t), this._value = n ? t : gt(t), this.__v_isShallow = n;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const n = this._rawValue, s = this.__v_isShallow || /* @__PURE__ */ ft(t) || /* @__PURE__ */ zt(t);
    t = s ? t : /* @__PURE__ */ he(t), Dt(t, n) && (this._rawValue = t, this._value = s ? t : gt(t), this.dep.trigger());
  }
}
function tf(e) {
  e.dep && e.dep.trigger();
}
function x(e) {
  return /* @__PURE__ */ De(e) ? e.value : e;
}
function Qe(e) {
  return ee(e) ? e() : x(e);
}
const nf = {
  get: (e, t, n) => t === "__v_raw" ? e : x(Reflect.get(e, t, n)),
  set: (e, t, n, s) => {
    const r = e[t];
    return /* @__PURE__ */ De(r) && !/* @__PURE__ */ De(n) ? (r.value = n, !0) : Reflect.set(e, t, n, s);
  }
};
function Il(e) {
  return /* @__PURE__ */ Ft(e) ? e : new Proxy(e, nf);
}
// @__NO_SIDE_EFFECTS__
function li(e) {
  const t = Y(e) ? new Array(e.length) : {};
  for (const n in e)
    t[n] = rf(e, n);
  return t;
}
class sf {
  constructor(t, n, s) {
    this._object = t, this._defaultValue = s, this.__v_isRef = !0, this._value = void 0, this._key = dt(n) ? n : String(n), this._raw = /* @__PURE__ */ he(t);
    let r = !0, o = t;
    if (!Y(t) || dt(this._key) || !Er(this._key))
      do
        r = !/* @__PURE__ */ Nr(o) || /* @__PURE__ */ ft(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = x(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ De(this._raw[this._key])) {
      const n = this._object[this._key];
      if (/* @__PURE__ */ De(n)) {
        n.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return $u(this._raw, this._key);
  }
}
function rf(e, t, n) {
  return new sf(e, t, n);
}
class of {
  constructor(t, n, s) {
    this.fn = t, this.setter = n, this._value = void 0, this.dep = new ri(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = ks - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !n, this.isSSR = s;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Ee !== this)
      return gl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return bl(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function af(e, t, n = !1) {
  let s, r;
  return ee(e) ? s = e : (s = e.get, r = e.set), new of(s, r, n);
}
const zs = {}, ir = /* @__PURE__ */ new WeakMap();
let An;
function lf(e, t = !1, n = An) {
  if (n) {
    let s = ir.get(n);
    s || ir.set(n, s = []), s.push(e);
  }
}
function cf(e, t, n = ke) {
  const { immediate: s, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = n, c = (O) => r ? O : /* @__PURE__ */ ft(O) || r === !1 || r === 0 ? Qt(O, 1) : Qt(O);
  let u, f, d, h, y = !1, v = !1;
  if (/* @__PURE__ */ De(e) ? (f = () => e.value, y = /* @__PURE__ */ ft(e)) : /* @__PURE__ */ Ft(e) ? (f = () => c(e), y = !0) : Y(e) ? (v = !0, y = e.some((O) => /* @__PURE__ */ Ft(O) || /* @__PURE__ */ ft(O)), f = () => e.map((O) => {
    if (/* @__PURE__ */ De(O))
      return O.value;
    if (/* @__PURE__ */ Ft(O))
      return c(O);
    if (ee(O))
      return l ? l(O, 2) : O();
  })) : ee(e) ? t ? f = l ? () => l(e, 2) : e : f = () => {
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
    const O = f, W = r === !0 ? 1 / 0 : r;
    f = () => Qt(O(), W);
  }
  const k = Ir(), I = () => {
    u.stop(), k && k.active && Qo(k.effects, u);
  };
  if (o && t) {
    const O = t;
    t = (...W) => {
      try {
        return O(...W);
      } finally {
        I();
      }
    };
  }
  let w = v ? new Array(e.length).fill(zs) : zs;
  const N = (O) => {
    if (!(!(u.flags & 1) || !u.dirty && !O))
      if (t) {
        const W = u.run();
        if (O || r || y || (v ? W.some((ge, V) => Dt(ge, w[V])) : Dt(W, w))) {
          const ge = An;
          Vt();
          try {
            d && d(), An = u;
            const V = [
              W,
              // pass undefined as the old value when it's changed for the first time
              w === zs ? void 0 : v && w[0] === zs ? [] : w,
              h
            ];
            w = W, l ? l(t, 3, V) : (
              // @ts-expect-error
              t(...V)
            );
          } finally {
            An = ge, Bt();
          }
        }
      } else
        u.run();
  };
  return a && a(N), u = new hl(f), u.scheduler = i ? () => i(N, !1) : N, h = (O) => lf(O, !1, u), d = u.onStop = () => {
    const O = ir.get(u);
    if (O) {
      if (l)
        l(O, 4);
      else
        for (const W of O) W();
      ir.delete(u);
    }
  }, t ? s ? N(!0) : w = u.run() : i ? i(N.bind(null, !0), !0) : u.run(), I.pause = u.pause.bind(u), I.resume = u.resume.bind(u), I.stop = I, I;
}
function Qt(e, t = 1 / 0, n) {
  if (t <= 0 || !be(e) || e.__v_skip || (n = n || /* @__PURE__ */ new Map(), (n.get(e) || 0) >= t))
    return e;
  if (n.set(e, t), t--, /* @__PURE__ */ De(e))
    Qt(e.value, t, n);
  else if (Y(e))
    for (let s = 0; s < e.length; s++)
      Qt(e[s], t, n);
  else if (rr(e) || hn(e))
    e.forEach((s) => {
      Qt(s, t, n);
    });
  else if (ll(e)) {
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
  if (ee(e)) {
    const r = js(e, t, n, s);
    return r && il(r) && r.catch((o) => {
      Mr(o, t, n);
    }), r;
  }
  if (Y(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(kt(e[o], t, n, s));
    return r;
  }
}
function Mr(e, t, n, s = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || ke;
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
  uf(e, n, r, s, i);
}
function uf(e, t, n, s = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const ot = [];
let xt = -1;
const Nt = [];
let fn = null, Un = 0;
const Pl = /* @__PURE__ */ Promise.resolve();
let ar = null;
function St(e) {
  const t = ar || Pl;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function ff(e) {
  let t = xt + 1, n = ot.length;
  for (; t < n; ) {
    const s = t + n >>> 1, r = ot[s], o = Es(r);
    o < e || o === e && r.flags & 2 ? t = s + 1 : n = s;
  }
  return t;
}
function ci(e) {
  if (!(e.flags & 1)) {
    const t = Es(e), n = ot[ot.length - 1];
    !n || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= Es(n) ? ot.push(e) : ot.splice(ff(t), 0, e), e.flags |= 1, Nl();
  }
}
function Nl() {
  ar || (ar = Pl.then(Ll));
}
function df(e) {
  if (!Y(e))
    fn && e.id === -1 ? fn.splice(Un + 1, 0, e) : e.flags & 1 || (Nt.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Nt.push(e[t]);
  Nl();
}
function Ml(e, t, n, s = xt + 1) {
  for (; s < ot.length; s++) {
    const r = ot[s];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      ot.splice(s, 1), s = e ? s - 1 : xt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function Dl(e, t, n = 0) {
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
let Kr = !1;
function pf(e, t) {
  if (Kr) {
    e();
    return;
  }
  const n = t === void 0 ? void 0 : new Set(Nt);
  e(), Kr = !0;
  try {
    Ml(void 0, t), Dl(void 0, n, t);
  } finally {
    Kr = !1;
  }
}
const Es = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function Ll(e) {
  try {
    for (xt = 0; xt < ot.length; xt++) {
      const t = ot[xt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), js(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; xt < ot.length; xt++) {
      const t = ot[xt];
      t && (t.flags &= -2);
    }
    xt = -1, ot.length = 0, Dl(), ar = null, (ot.length || Nt.length) && Ll();
  }
}
let Ze = null, jl = null;
function lr(e) {
  const t = Ze;
  return Ze = e, jl = e && e.type.__scopeId || null, t;
}
function Ce(e, t = Ze, n) {
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
    let [o, i, a, l = ke] = t[r];
    o && (ee(o) && (o = {
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
function it(e, t, n = !1) {
  const s = Ct();
  if (s || Nn) {
    let r = Nn ? Nn._context.provides : s ? s.parent == null || s.ce ? s.vnode.appContext && s.vnode.appContext.provides : s.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return n && ee(t) ? t.call(s && s.proxy) : t;
  }
}
function ui() {
  return !!(Ct() || Nn);
}
const hf = /* @__PURE__ */ Symbol.for("v-scx"), mf = () => it(hf);
function Kn(e, t) {
  return fi(e, null, t);
}
function Fe(e, t, n) {
  return fi(e, t, n);
}
function fi(e, t, n = ke) {
  const { immediate: s, deep: r, flush: o, once: i } = n, a = Ge({}, n), l = t && s || !t && o !== "post";
  let c;
  if (Ts) {
    if (o === "sync") {
      const h = mf();
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
    h.i = u, st(h, u && u.suspense);
  } : o !== "sync" && (f = !0, a.scheduler = (h, y) => {
    y ? h() : ci(h);
  }), a.augmentJob = (h) => {
    t && (h.flags |= 4), f && (h.flags |= 2, u && (h.id = u.uid, h.i = u));
  };
  const d = cf(e, t, a);
  return Ts && (c ? c.push(d) : l && d()), d;
}
function gf(e, t, n) {
  const s = this.proxy, r = Te(e) ? e.includes(".") ? Fl(s, e) : () => s[e] : e.bind(s, s);
  let o;
  ee(t) ? o = t : (o = t.handler, n = t);
  const i = Fs(this), a = fi(r, o.bind(s), n);
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
const cn = /* @__PURE__ */ new WeakMap(), $l = /* @__PURE__ */ Symbol("_vte"), Dr = (e) => e.__isTeleport, On = (e) => e && (e.disabled || e.disabled === ""), yf = (e) => e && (e.defer || e.defer === ""), ji = (e) => typeof SVGElement < "u" && e instanceof SVGElement, Fi = (e) => typeof MathMLElement == "function" && e instanceof MathMLElement, Ao = (e, t) => {
  const n = e && e.to;
  return Te(n) ? t ? t(n) : null : n;
}, vf = {
  name: "Teleport",
  __isTeleport: !0,
  process(e, t, n, s, r, o, i, a, l, c) {
    const {
      mc: u,
      pc: f,
      pbc: d,
      o: { insert: h, querySelector: y, createText: v, createComment: k, parentNode: I }
    } = c, w = On(t.props);
    let { dynamicChildren: N } = t;
    const O = (V, E, F) => {
      V.shapeFlag & 16 && u(
        V.children,
        E,
        F,
        r,
        o,
        i,
        a,
        l
      );
    }, W = (V = t) => {
      const E = On(V.props), F = V.target = Ao(V.props, y), ce = Oo(F, V, v, h);
      F && (i !== "svg" && ji(F) ? i = "svg" : i !== "mathml" && Fi(F) && (i = "mathml"), r && r.isCE && (r.ce._teleportTargets || (r.ce._teleportTargets = /* @__PURE__ */ new Set())).add(F), E || (O(V, F, ce), fs(V, !1)));
    }, ge = (V) => {
      const E = () => {
        if (cn.get(V) === E) {
          if (cn.delete(V), On(V.props)) {
            const F = I(V.el) || n;
            O(V, F, V.anchor), fs(V, !0);
          }
          W(V);
        }
      };
      cn.set(V, E), st(E, o);
    };
    if (e == null) {
      const V = t.el = v(""), E = t.anchor = v("");
      if (h(V, n, s), h(E, n, s), yf(t.props) || o && o.pendingBranch) {
        ge(t);
        return;
      }
      w && (O(t, n, E), fs(t, !0)), W();
    } else {
      t.el = e.el;
      const V = t.anchor = e.anchor, E = cn.get(e);
      if (E) {
        E.flags |= 8, cn.delete(e), ge(t);
        return;
      }
      t.targetStart = e.targetStart;
      const F = t.target = e.target, ce = t.targetAnchor = e.targetAnchor, Oe = On(e.props), Ie = Oe ? n : F, $e = Oe ? V : ce;
      if (i === "svg" || ji(F) ? i = "svg" : (i === "mathml" || Fi(F)) && (i = "mathml"), N ? (d(
        e.dynamicChildren,
        N,
        Ie,
        r,
        o,
        i,
        a
      ), mi(e, t, !0)) : l || f(
        e,
        t,
        Ie,
        $e,
        r,
        o,
        i,
        a,
        !1
      ), w)
        Oe ? t.props && e.props && t.props.to !== e.props.to && (t.props.to = e.props.to) : Us(
          t,
          n,
          V,
          c,
          1
        );
      else if ((t.props && t.props.to) !== (e.props && e.props.to)) {
        const et = Ao(t.props, y);
        et && (t.target = et, Us(
          t,
          et,
          null,
          c,
          0
        ));
      } else Oe && Us(
        t,
        F,
        ce,
        c,
        1
      );
      fs(t, w);
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
      for (let k = 0; k < a.length; k++) {
        const I = a[k];
        s(
          I,
          t,
          n,
          y,
          !!I.dynamicChildren
        );
      }
  },
  move: Us,
  hydrate: bf
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
function bf(e, t, n, s, r, o, {
  o: { nextSibling: i, parentNode: a, querySelector: l, insert: c, createText: u }
}, f) {
  function d(k, I) {
    let w = I;
    for (; w; ) {
      if (w && w.nodeType === 8) {
        if (w.data === "teleport start anchor")
          t.targetStart = w;
        else if (w.data === "teleport anchor") {
          t.targetAnchor = w, k._lpa = t.targetAnchor && i(t.targetAnchor);
          break;
        }
      }
      w = i(w);
    }
  }
  function h(k, I) {
    I.anchor = f(
      i(k),
      I,
      a(k),
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
    const k = y._lpa || y.firstChild;
    t.shapeFlag & 16 && (v ? (h(e, t), d(y, k), t.targetAnchor || Oo(
      y,
      t,
      u,
      c,
      // if target is the same as the main view, insert anchors before current node
      // to avoid hydrating mismatch
      a(e) === y ? e : null
    )) : (t.anchor = i(e), d(y, k), t.targetAnchor || Oo(y, t, u, c), f(
      k && i(k),
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
const _f = vf;
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
  return o[$l] = i, e && (s(o, e, r), s(i, e, r)), i;
}
const Jr = /* @__PURE__ */ Symbol("_leaveCb");
function xf(e) {
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
function Vl(e) {
  if (!di(e))
    return Dr(e.type) && e.children ? xf(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: n } = e;
  if (n) {
    if (t & 16)
      return n[0];
    if (t & 32 && ee(n.default))
      return n.default();
  }
}
function cr(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const n = e.component.subTree;
    cr(
      Dr(n.type) && Vl(n) || n,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === qe && Y(e.children)) {
    const n = Ql(e.children, !1);
    n && cr(n, t);
  }
}
function Ro(e) {
  if (e.component)
    return Ro(e.component.subTree);
  if (e.type === qe) {
    const t = Y(e.children) && Ql(e.children, !1);
    return t ? Ro(t) : void 0;
  }
  if (e.type !== pt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function Ae(e, t) {
  return ee(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    Ge({ name: e.name }, t, { setup: e })
  ) : e;
}
function wf() {
  const e = Ct();
  return e ? (e.appContext.config.idPrefix || "v") + "-" + e.ids[0] + e.ids[1]++ : "";
}
function Bl(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function $i(e, t) {
  let n;
  return !!((n = Object.getOwnPropertyDescriptor(e, t)) && !n.configurable);
}
const ur = /* @__PURE__ */ new WeakMap();
function bs(e, t, n, s, r = !1) {
  if (Y(e)) {
    e.forEach(
      (v, k) => bs(
        v,
        t && (Y(t) ? t[k] : t),
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
  const o = s.shapeFlag & 4 ? Vr(s.component) : s.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === ke ? a.refs = {} : a.refs, f = a.setupState, d = /* @__PURE__ */ he(f), h = f === ke ? ol : (v) => $i(u, v) ? !1 : ye(d, v), y = (v, k) => !(k && $i(u, k));
  if (c != null && c !== l) {
    if (Vi(t), Te(c))
      u[c] = null, h(c) && (f[c] = null);
    else if (/* @__PURE__ */ De(c)) {
      const v = t;
      y(c, v.k) && (c.value = null), v.k && (u[v.k] = null);
    }
  }
  if (ee(l))
    js(l, a, 12, [i, u]);
  else {
    const v = Te(l), k = /* @__PURE__ */ De(l);
    if (v || k) {
      const I = () => {
        if (e.f) {
          const w = v ? h(l) ? f[l] : u[l] : y() || !e.k ? l.value : u[e.k];
          if (r)
            Y(w) && Qo(w, o);
          else if (Y(w))
            w.includes(o) || w.push(o);
          else if (v)
            u[l] = [o], h(l) && (f[l] = u[l]);
          else {
            const N = [o];
            y(l, e.k) && (l.value = N), e.k && (u[e.k] = N);
          }
        } else v ? (u[l] = i, h(l) && (f[l] = i)) : k && (y(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const w = () => {
          I(), ur.delete(e);
        };
        w.id = -1, ur.set(e, w), st(w, n);
      } else
        Vi(e), I();
    }
  }
}
function Vi(e) {
  const t = ur.get(e);
  t && (t.flags |= 8, ur.delete(e));
}
Or().requestIdleCallback;
Or().cancelIdleCallback;
const Gn = (e) => !!e.type.__asyncLoader, di = (e) => e.type.__isKeepAlive;
function kf(e, t) {
  zl(e, "a", t);
}
function Sf(e, t) {
  zl(e, "da", t);
}
function zl(e, t, n = Je) {
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
      di(r.parent.vnode) && Ef(s, t, n, r), r = r.parent;
  }
}
function Ef(e, t, n, s) {
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
      const a = Fs(n), l = kt(t, n, e, i);
      return a(), Bt(), l;
    });
    return s ? r.unshift(o) : r.push(o), o;
  }
}
const rn = (e) => (t, n = Je) => {
  (!Ts || e === "sp") && Lr(e, (...s) => t(...s), n);
}, Cf = rn("bm"), ss = rn("m"), Af = rn(
  "bu"
), Ul = rn("u"), Wl = rn(
  "bum"
), jr = rn("um"), Of = rn(
  "sp"
), Rf = rn("rtg"), Tf = rn("rtc");
function If(e, t = Je) {
  Lr("ec", e, t);
}
const Pf = "components", Hl = /* @__PURE__ */ Symbol.for("v-ndc");
function Nf(e) {
  return Te(e) ? Mf(Pf, e, !1) || e : e || Hl;
}
function Mf(e, t, n = !0, s = !1) {
  const r = Ze || Je;
  if (r) {
    const o = r.type;
    {
      const a = md(
        o,
        !1
      );
      if (a && (a === t || a === Ye(t) || a === Ar(Ye(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      Bi(r[e] || o[e], t) || // global registration
      Bi(r.appContext[e], t)
    );
    return !i && s ? o : i;
  }
}
function Bi(e, t) {
  return e && (e[t] || e[Ye(t)] || e[Ar(Ye(t))]);
}
function ql(e, t, n, s) {
  let r;
  const o = n, i = Y(e);
  if (i || Te(e)) {
    const a = i && /* @__PURE__ */ Ft(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ ft(e), c = /* @__PURE__ */ zt(e), e = Pr(e)), r = new Array(e.length);
    for (let u = 0, f = e.length; u < f; u++)
      r[u] = t(
        l ? c ? yn(gt(e[u])) : gt(e[u]) : e[u],
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
  else if (be(e))
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
function Xe(e, t, n, s, r, o) {
  if (n == null && (n = {}), Ze.ce || Ze.parent && Gn(Ze.parent) && Ze.parent.ce) {
    const c = n, u = Object.keys(c).length > 0;
    return de(), Le(
      qe,
      null,
      [fe("slot", c, s)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = Xt.length;
  de();
  let l;
  try {
    const c = i && Zl(i(n)), u = n.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = Le(
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
function Zl(e) {
  return e.some((t) => Jn(t) ? !(t.type === pt || t.type === qe && !Zl(t.children)) : !0) ? e : null;
}
const To = (e) => e ? hc(e) ? Vr(e) : To(e.parent) : null, _s = (
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
    $options: (e) => Kl(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      ci(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = St.bind(e.proxy)),
    $watch: (e) => gf.bind(e)
  })
), Yr = (e, t) => e !== ke && !e.__isScriptSetup && ye(e, t), Df = {
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
        if (Yr(s, t))
          return i[t] = 1, s[t];
        if (r !== ke && ye(r, t))
          return i[t] = 2, r[t];
        if (ye(o, t))
          return i[t] = 3, o[t];
        if (n !== ke && ye(n, t))
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
    if (n !== ke && ye(n, t))
      return i[t] = 4, n[t];
    if (
      // global properties
      f = l.config.globalProperties, ye(f, t)
    )
      return f[t];
  },
  set({ _: e }, t, n) {
    const { data: s, setupState: r, ctx: o } = e;
    return Yr(r, t) ? (r[t] = n, !0) : s !== ke && ye(s, t) ? (s[t] = n, !0) : ye(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = n, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: n, ctx: s, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(n[a] || e !== ke && a[0] !== "$" && ye(e, a) || Yr(t, a) || ye(o, a) || ye(s, a) || ye(_s, a) || ye(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, n) {
    return n.get != null ? e._.accessCache[t] = 0 : ye(n, "value") && this.set(e, t, n.value, null), Reflect.defineProperty(e, t, n);
  }
};
function zi(e) {
  return Y(e) ? e.reduce(
    (t, n) => (t[n] = null, t),
    {}
  ) : e;
}
let Io = !0;
function Lf(e) {
  const t = Kl(e), n = e.proxy, s = e.ctx;
  Io = !1, t.beforeCreate && Ui(t.beforeCreate, e, "bc");
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
    deactivated: k,
    beforeDestroy: I,
    beforeUnmount: w,
    destroyed: N,
    unmounted: O,
    render: W,
    renderTracked: ge,
    renderTriggered: V,
    errorCaptured: E,
    serverPrefetch: F,
    // public API
    expose: ce,
    inheritAttrs: Oe,
    // assets
    components: Ie,
    directives: $e,
    filters: et
  } = t;
  if (c && jf(c, s, null), i)
    for (const Q in i) {
      const le = i[Q];
      ee(le) && (s[Q] = le.bind(n));
    }
  if (r) {
    const Q = r.call(n, n);
    be(Q) && (e.data = /* @__PURE__ */ jn(Q));
  }
  if (Io = !0, o)
    for (const Q in o) {
      const le = o[Q], at = ee(le) ? le.bind(n, n) : ee(le.get) ? le.get.bind(n, n) : jt, q = !ee(le) && ee(le.set) ? le.set.bind(n) : jt, lt = ae({
        get: at,
        set: q
      });
      Object.defineProperty(s, Q, {
        enumerable: !0,
        configurable: !0,
        get: () => lt.value,
        set: (We) => lt.value = We
      });
    }
  if (a)
    for (const Q in a)
      Gl(a[Q], s, n, Q);
  if (l) {
    const Q = ee(l) ? l.call(n) : l;
    Reflect.ownKeys(Q).forEach((le) => {
      vs(le, Q[le]);
    });
  }
  u && Ui(u, e, "c");
  function ie(Q, le) {
    Y(le) ? le.forEach((at) => Q(at.bind(n))) : le && Q(le.bind(n));
  }
  if (ie(Cf, f), ie(ss, d), ie(Af, h), ie(Ul, y), ie(kf, v), ie(Sf, k), ie(If, E), ie(Tf, ge), ie(Rf, V), ie(Wl, w), ie(jr, O), ie(Of, F), Y(ce))
    if (ce.length) {
      const Q = e.exposed || (e.exposed = {});
      ce.forEach((le) => {
        Object.defineProperty(Q, le, {
          get: () => n[le],
          set: (at) => n[le] = at,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  W && e.render === jt && (e.render = W), Oe != null && (e.inheritAttrs = Oe), Ie && (e.components = Ie), $e && (e.directives = $e), F && Bl(e);
}
function jf(e, t, n = jt) {
  Y(e) && (e = Po(e));
  for (const s in e) {
    const r = e[s];
    let o;
    be(r) ? "default" in r ? o = it(
      r.from || s,
      r.default,
      !0
    ) : o = it(r.from || s) : o = it(r), /* @__PURE__ */ De(o) ? Object.defineProperty(t, s, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[s] = o;
  }
}
function Ui(e, t, n) {
  kt(
    Y(e) ? e.map((s) => s.bind(t.proxy)) : e.bind(t.proxy),
    t,
    n
  );
}
function Gl(e, t, n, s) {
  let r = s.includes(".") ? Fl(n, s) : () => n[s];
  if (Te(e)) {
    const o = t[e];
    ee(o) && Fe(r, o);
  } else if (ee(e))
    Fe(r, e.bind(n));
  else if (be(e))
    if (Y(e))
      e.forEach((o) => Gl(o, t, n, s));
    else {
      const o = ee(e.handler) ? e.handler.bind(n) : t[e.handler];
      ee(o) && Fe(r, o, e);
    }
}
function Kl(e) {
  const t = e.type, { mixins: n, extends: s } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !n && !s ? l = t : (l = {}, r.length && r.forEach(
    (c) => fr(l, c, i, !0)
  ), fr(l, t, i)), be(t) && o.set(t, l), l;
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
  data: Wi,
  props: Hi,
  emits: Hi,
  // objects
  methods: ds,
  computed: ds,
  // lifecycle
  beforeCreate: nt,
  created: nt,
  beforeMount: nt,
  mounted: nt,
  beforeUpdate: nt,
  updated: nt,
  beforeDestroy: nt,
  beforeUnmount: nt,
  destroyed: nt,
  unmounted: nt,
  activated: nt,
  deactivated: nt,
  errorCaptured: nt,
  serverPrefetch: nt,
  // assets
  components: ds,
  directives: ds,
  // watch
  watch: Vf,
  // provide / inject
  provide: Wi,
  inject: $f
};
function Wi(e, t) {
  return t ? e ? function() {
    return Ge(
      ee(e) ? e.call(this, this) : e,
      ee(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function $f(e, t) {
  return ds(Po(e), Po(t));
}
function Po(e) {
  if (Y(e)) {
    const t = {};
    for (let n = 0; n < e.length; n++)
      t[e[n]] = e[n];
    return t;
  }
  return e;
}
function nt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function ds(e, t) {
  return e ? Ge(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function Hi(e, t) {
  return e ? Y(e) && Y(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : Ge(
    /* @__PURE__ */ Object.create(null),
    zi(e),
    zi(t ?? {})
  ) : t;
}
function Vf(e, t) {
  if (!e) return t;
  if (!t) return e;
  const n = Ge(/* @__PURE__ */ Object.create(null), e);
  for (const s in t)
    n[s] = nt(e[s], t[s]);
  return n;
}
function Jl() {
  return {
    app: null,
    config: {
      isNativeTag: ol,
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
let Bf = 0;
function zf(e, t) {
  return function(s, r = null) {
    ee(s) || (s = Ge({}, s)), r != null && !be(r) && (r = null);
    const o = Jl(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: Bf++,
      _component: s,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: yd,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...f) {
        return i.has(u) || (u && ee(u.install) ? (i.add(u), u.install(c, ...f)) : ee(u) && (i.add(u), u(c, ...f))), c;
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
          const h = c._ceVNode || fe(s, r);
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
const Uf = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${Ye(t)}Modifiers`] || e[`${Ln(t)}Modifiers`];
function Wf(e, t, ...n) {
  if (e.isUnmounted) return;
  const s = e.vnode.props || ke;
  let r = n;
  const o = t.startsWith("update:"), i = o && Uf(s, t.slice(7));
  i && (i.trim && (r = n.map((u) => Te(u) ? u.trim() : u)), i.number && (r = r.map(Xo)));
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
const Hf = /* @__PURE__ */ new WeakMap();
function Yl(e, t, n = !1) {
  const s = n ? Hf : t.emitsCache, r = s.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!ee(e)) {
    const l = (c) => {
      const u = Yl(c, t, !0);
      u && (a = !0, Ge(i, u));
    };
    !n && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (be(e) && s.set(e, null), null) : (Y(o) ? o.forEach((l) => i[l] = null) : Ge(i, o), be(e) && s.set(e, i), i);
}
function Fr(e, t) {
  return !e || !kr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), ye(e, t[0].toLowerCase() + t.slice(1)) || ye(e, Ln(t)) || ye(e, t));
}
function qi(e) {
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
  } = e, k = lr(e);
  let I, w;
  try {
    if (n.shapeFlag & 4) {
      const O = r || s, W = O;
      I = Mt(
        c.call(
          W,
          O,
          u,
          f,
          h,
          d,
          y
        )
      ), w = a;
    } else {
      const O = t;
      I = Mt(
        O.length > 1 ? O(
          f,
          { attrs: a, slots: i, emit: l }
        ) : O(
          f,
          null
        )
      ), w = t.props ? a : qf(a);
    }
  } catch (O) {
    Xt.length = 0, Mr(O, e, 1), I = fe(pt);
  }
  let N = I;
  if (w && v !== !1) {
    const O = Object.keys(w), { shapeFlag: W } = N;
    O.length && W & 7 && (o && O.some(Sr) && (w = Zf(
      w,
      o
    )), N = Mn(N, w, !1, !0));
  }
  if (n.dirs && (N = Mn(N, null, !1, !0), N.dirs = N.dirs ? N.dirs.concat(n.dirs) : n.dirs), n.transition) {
    const O = Dr(N.type) && Vl(N) || N;
    cr(O, n.transition);
  }
  return I = N, lr(k), I;
}
function Ql(e, t = !0) {
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
const qf = (e) => {
  let t;
  for (const n in e)
    (n === "class" || n === "style" || kr(n)) && ((t || (t = {}))[n] = e[n]);
  return t;
}, Zf = (e, t) => {
  const n = {};
  for (const s in e)
    (!Sr(s) || !(s.slice(9) in t)) && (n[s] = e[s]);
  return n;
};
function Gf(e, t, n) {
  const { props: s, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (n && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return s ? Zi(s, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let f = 0; f < u.length; f++) {
        const d = u[f];
        if (Xl(i, s, d) && !Fr(c, d))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : s === i ? !1 : s ? i ? Zi(s, i, c) : !0 : !!i;
  return !1;
}
function Zi(e, t, n) {
  const s = Object.keys(t);
  if (s.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < s.length; r++) {
    const o = s[r];
    if (!ye(e, o) || Xl(t, e, o) && !Fr(n, o))
      return !0;
  }
  return !1;
}
function Xl(e, t, n) {
  const s = e[n], r = t[n];
  return n === "style" && be(s) && be(r) ? !Rr(s, r) : s !== r;
}
function Kf({ vnode: e, parent: t, suspense: n }, s) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = s, e = r), r === e)
      (e = t.vnode).el = s, t = t.parent;
    else
      break;
  }
  n && n.activeBranch === e && (n.vnode.el = s);
}
const ec = {}, tc = () => Object.create(ec), nc = (e) => Object.getPrototypeOf(e) === ec;
function Jf(e, t, n, s = !1) {
  const r = {}, o = tc();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), sc(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  n ? e.props = s ? r : /* @__PURE__ */ Rl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function Yf(e, t, n, s) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ he(r), [l] = e.propsOptions;
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
        if (Fr(e.emitsOptions, d))
          continue;
        const h = t[d];
        if (l)
          if (ye(o, d))
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
    sc(e, t, r, o) && (c = !0);
    let u;
    for (const f in a)
      (!t || // for camelCase
      !ye(t, f) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = Ln(f)) === f || !ye(t, u))) && (l ? n && // for camelCase
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
        (!t || !ye(t, f)) && (delete o[f], c = !0);
  }
  c && Yt(e.attrs, "set", "");
}
function sc(e, t, n, s) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (ms(l))
        continue;
      const c = t[l];
      let u;
      r && ye(r, u = Ye(l)) ? !o || !o.includes(u) ? n[u] = c : (a || (a = {}))[u] = c : Fr(e.emitsOptions, l) || (!(l in s) || c !== s[l]) && (s[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ he(n), c = a || ke;
    for (let u = 0; u < o.length; u++) {
      const f = o[u];
      n[f] = No(
        r,
        l,
        f,
        c[f],
        e,
        !ye(c, f)
      );
    }
  }
  return i;
}
function No(e, t, n, s, r, o) {
  const i = e[n];
  if (i != null) {
    const a = ye(i, "default");
    if (a && s === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && ee(l)) {
        const { propsDefaults: c } = r;
        if (n in c)
          s = c[n];
        else {
          const u = Fs(r);
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
const Qf = /* @__PURE__ */ new WeakMap();
function rc(e, t, n = !1) {
  const s = n ? Qf : t.propsCache, r = s.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!ee(e)) {
    const u = (f) => {
      l = !0;
      const [d, h] = rc(f, t, !0);
      Ge(i, d), h && a.push(...h);
    };
    !n && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return be(e) && s.set(e, Rn), Rn;
  if (Y(o))
    for (let u = 0; u < o.length; u++) {
      const f = Ye(o[u]);
      Gi(f) && (i[f] = ke);
    }
  else if (o)
    for (const u in o) {
      const f = Ye(u);
      if (Gi(f)) {
        const d = o[u], h = i[f] = Y(d) || ee(d) ? { type: d } : Ge({}, d), y = h.type;
        let v = !1, k = !0;
        if (Y(y))
          for (let I = 0; I < y.length; ++I) {
            const w = y[I], N = ee(w) && w.name;
            if (N === "Boolean") {
              v = !0;
              break;
            } else N === "String" && (k = !1);
          }
        else
          v = ee(y) && y.name === "Boolean";
        h[
          0
          /* shouldCast */
        ] = v, h[
          1
          /* shouldCastTrue */
        ] = k, (v || ye(h, "default")) && a.push(f);
      }
    }
  const c = [i, a];
  return be(e) && s.set(e, c), c;
}
function Gi(e) {
  return e[0] !== "$" && !ms(e);
}
const pi = (e) => e === "_" || e === "_ctx" || e === "$stable", hi = (e) => Y(e) ? e.map(Mt) : [Mt(e)], Xf = (e, t, n) => {
  if (t._n)
    return t;
  const s = Ce((...r) => hi(t(...r)), n);
  return s._c = !1, s;
}, oc = (e, t, n) => {
  const s = e._ctx;
  for (const r in e) {
    if (pi(r)) continue;
    const o = e[r];
    if (ee(o))
      t[r] = Xf(r, o, s);
    else if (o != null) {
      const i = hi(o);
      t[r] = () => i;
    }
  }
}, ic = (e, t) => {
  const n = hi(t);
  e.slots.default = () => n;
}, ac = (e, t, n) => {
  for (const s in t)
    (n || !pi(s)) && (e[s] = t[s]);
}, ed = (e, t, n) => {
  const s = e.slots = tc();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (ac(s, t, n), n && cl(s, "_", r, !0)) : oc(t, s);
  } else t && ic(e, t);
}, td = (e, t, n) => {
  const { vnode: s, slots: r } = e;
  let o = !0, i = ke;
  if (s.shapeFlag & 32) {
    const a = t._;
    a ? n && a === 1 ? o = !1 : ac(r, t, n) : (o = !t.$stable, oc(t, r)), i = t;
  } else t && (ic(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !pi(a) && i[a] == null && delete r[a];
}, st = id;
function nd(e) {
  return sd(e);
}
function sd(e, t) {
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
  } = e, v = (p, m, g, b = null, _ = null, C = null, R = void 0, D = null, M = !!m.dynamicChildren) => {
    if (p === m)
      return;
    p && !as(p, m) && (b = S(p), We(p, _, C, !0), p = null), m.patchFlag === -2 && (M = !1, m.dynamicChildren = null), m.dynamicChildren && p && p.dynamicChildren && p.dynamicChildren.hasOnce && (m.dynamicChildren === Rn && (m.dynamicChildren = []), m.dynamicChildren.hasOnce = !0);
    const { type: A, ref: G, shapeFlag: j } = m;
    switch (A) {
      case $r:
        k(p, m, g, b);
        break;
      case pt:
        I(p, m, g, b);
        break;
      case Xr:
        p == null && w(m, g, b, R);
        break;
      case qe:
        Ie(
          p,
          m,
          g,
          b,
          _,
          C,
          R,
          D,
          M
        );
        break;
      default:
        j & 1 ? W(
          p,
          m,
          g,
          b,
          _,
          C,
          R,
          D,
          M
        ) : j & 6 ? $e(
          p,
          m,
          g,
          b,
          _,
          C,
          R,
          D,
          M
        ) : (j & 64 || j & 128) && A.process(
          p,
          m,
          g,
          b,
          _,
          C,
          R,
          D,
          M,
          T
        );
    }
    G != null && _ ? bs(G, p && p.ref, C, m || p, !m) : G == null && p && p.ref != null && bs(p.ref, null, C, p, !0);
  }, k = (p, m, g, b) => {
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
  }, I = (p, m, g, b) => {
    p == null ? s(
      m.el = l(m.children || ""),
      g,
      b
    ) : m.el = p.el;
  }, w = (p, m, g, b) => {
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
  }, W = (p, m, g, b, _, C, R, D, M) => {
    if (m.type === "svg" ? R = "svg" : m.type === "math" && (R = "mathml"), p == null)
      ge(
        m,
        g,
        b,
        _,
        C,
        R,
        D,
        M
      );
    else {
      const A = p.el && p.el._isVueCE ? p.el : null;
      try {
        A && A._beginPatch(), F(
          p,
          m,
          _,
          C,
          R,
          D,
          M
        );
      } finally {
        A && A._endPatch();
      }
    }
  }, ge = (p, m, g, b, _, C, R, D) => {
    let M, A;
    const { props: G, shapeFlag: j, transition: K, dirs: X } = p;
    if (M = p.el = i(
      p.type,
      C,
      G && G.is,
      G
    ), j & 8 ? u(M, p.children) : j & 16 && E(
      p.children,
      M,
      null,
      b,
      _,
      Qr(p, C),
      R,
      D
    ), X && kn(p, null, b, "created"), V(M, p, p.scopeId, R, b), G) {
      for (const we in G)
        we !== "value" && !ms(we) && o(M, we, null, G[we], C, b);
      "value" in G && o(M, "value", null, G.value, C), (A = G.onVnodeBeforeMount) && Tt(A, b, p);
    }
    X && kn(p, null, b, "beforeMount");
    const ue = rd(_, K);
    ue && K.beforeEnter(M), s(M, m, g), ((A = G && G.onVnodeMounted) || ue || X) && st(() => {
      try {
        A && Tt(A, b, p), ue && K.enter(M), X && kn(p, null, b, "mounted");
      } finally {
      }
    }, _);
  }, V = (p, m, g, b, _) => {
    if (g && h(p, g), b)
      for (let C = 0; C < b.length; C++)
        h(p, b[C]);
    if (_) {
      let C = _.subTree;
      if (m === C || cc(C.type) && (C.ssContent === m || C.ssFallback === m)) {
        const R = _.vnode;
        V(
          p,
          R,
          R.scopeId,
          R.slotScopeIds,
          _.parent
        );
      }
    }
  }, E = (p, m, g, b, _, C, R, D, M = 0) => {
    for (let A = M; A < p.length; A++) {
      const G = p[A] = D ? Jt(p[A]) : Mt(p[A]);
      v(
        null,
        G,
        m,
        g,
        b,
        _,
        C,
        R,
        D
      );
    }
  }, F = (p, m, g, b, _, C, R) => {
    const D = m.el = p.el;
    let { patchFlag: M, dynamicChildren: A, dirs: G } = m;
    M |= p.patchFlag & 16;
    const j = p.props || ke, K = m.props || ke;
    let X;
    if (g && Sn(g, !1), (X = K.onVnodeBeforeUpdate) && Tt(X, g, m, p), G && kn(m, p, g, "beforeUpdate"), g && Sn(g, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    A && (!p.dynamicChildren || p.dynamicChildren.length !== A.length) && (M = 0, R = !1, A = null), (j.innerHTML && K.innerHTML == null || j.textContent && K.textContent == null) && u(D, ""), A ? ce(
      p.dynamicChildren,
      A,
      D,
      g,
      b,
      Qr(m, _),
      C
    ) : R || le(
      p,
      m,
      D,
      null,
      g,
      b,
      Qr(m, _),
      C,
      !1
    ), M > 0) {
      if (M & 16)
        Oe(D, j, K, g, _);
      else if (M & 2 && j.class !== K.class && o(D, "class", null, K.class, _), M & 4 && o(D, "style", j.style, K.style, _), M & 8) {
        const ue = m.dynamicProps;
        for (let we = 0; we < ue.length; we++) {
          const xe = ue[we], je = j[xe], He = K[xe];
          (He !== je || xe === "value") && o(D, xe, je, He, _, g);
        }
      }
      M & 1 && p.children !== m.children && u(D, m.children);
    } else !R && A == null && Oe(D, j, K, g, _);
    ((X = K.onVnodeUpdated) || G) && st(() => {
      X && Tt(X, g, m, p), G && kn(m, p, g, "updated");
    }, b);
  }, ce = (p, m, g, b, _, C, R) => {
    for (let D = 0; D < m.length; D++) {
      const M = p[D], A = m[D], G = M.el || Mo(M), j = (
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
        j,
        null,
        b,
        _,
        C,
        R,
        !0
      );
    }
  }, Oe = (p, m, g, b, _) => {
    if (m !== g) {
      if (m !== ke)
        for (const C in m)
          !ms(C) && !(C in g) && o(
            p,
            C,
            m[C],
            null,
            _,
            b
          );
      for (const C in g) {
        if (ms(C)) continue;
        const R = g[C], D = m[C];
        R !== D && C !== "value" && o(p, C, D, R, _, b);
      }
      "value" in g && o(p, "value", m.value, g.value, _);
    }
  }, Ie = (p, m, g, b, _, C, R, D, M) => {
    const A = m.el = p ? p.el : a(""), G = m.anchor = p ? p.anchor : a("");
    let { patchFlag: j, dynamicChildren: K, slotScopeIds: X } = m;
    X && (D = D ? D.concat(X) : X), p == null ? (s(A, g, b), s(G, g, b), E(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      m.children || [],
      g,
      G,
      _,
      C,
      R,
      D,
      M
    )) : j > 0 && j & 64 && K && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    p.dynamicChildren && p.dynamicChildren.length === K.length ? (ce(
      p.dynamicChildren,
      K,
      g,
      _,
      C,
      R,
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
    )) : le(
      p,
      m,
      g,
      G,
      _,
      C,
      R,
      D,
      M
    );
  }, $e = (p, m, g, b, _, C, R, D, M) => {
    m.slotScopeIds = D, p == null ? m.shapeFlag & 512 ? _.ctx.activate(
      m,
      g,
      b,
      R,
      M
    ) : et(
      m,
      g,
      b,
      _,
      C,
      R,
      M
    ) : tt(p, m, M);
  }, et = (p, m, g, b, _, C, R) => {
    const D = p.component = ud(
      p,
      b,
      _
    );
    if (di(p) && (D.ctx.renderer = T), fd(D, !1, R), D.asyncDep) {
      if (_ && _.registerDep(
        D,
        ie,
        R,
        C
      ), !p.el) {
        const M = D.subTree = fe(pt);
        I(null, M, m, g), p.placeholder = M.el;
      }
    } else
      ie(
        D,
        p,
        m,
        g,
        _,
        C,
        R
      );
  }, tt = (p, m, g) => {
    const b = m.component = p.component;
    if (Gf(p, m, g))
      if (b.asyncDep && !b.asyncResolved) {
        m.el = p.el, m.placeholder = p.placeholder, Q(b, m, g);
        return;
      } else
        b.next = m, b.update();
    else
      m.el = p.el, m.placeholder = p.placeholder, b.vnode = m;
  }, ie = (p, m, g, b, _, C, R) => {
    const D = () => {
      if (p.isMounted) {
        let { next: j, bu: K, u: X, parent: ue, vnode: we } = p;
        {
          const Ot = lc(p);
          if (Ot) {
            j && (j.el = we.el, Q(p, j, R)), Ot.asyncDep.then(() => {
              st(() => {
                p.isUnmounted || A();
              }, _);
            });
            return;
          }
        }
        let xe = j, je;
        Sn(p, !1), j ? (j.el = we.el, Q(p, j, R)) : j = we, K && nr(K), (je = j.props && j.props.onVnodeBeforeUpdate) && Tt(je, ue, j, we), Sn(p, !0);
        const He = qi(p), At = p.subTree;
        p.subTree = He, v(
          At,
          He,
          // parent may have changed if it's in a teleport
          f(At.el),
          // anchor may have changed if it's in a fragment
          S(At),
          p,
          _,
          C
        ), j.el = He.el, xe === null && Kf(p, He.el), X && st(X, _), (je = j.props && j.props.onVnodeUpdated) && st(
          () => Tt(je, ue, j, we),
          _
        );
      } else {
        let j;
        const { el: K, props: X } = m, { bm: ue, m: we, parent: xe, root: je, type: He } = p, At = Gn(m);
        Sn(p, !1), ue && nr(ue), !At && (j = X && X.onVnodeBeforeMount) && Tt(j, xe, m), Sn(p, !0);
        {
          je.ce && je.ce._hasShadowRoot() && je.ce._injectChildStyle(
            He,
            p.parent ? p.parent.type : void 0
          );
          const Ot = p.subTree = qi(p);
          v(
            null,
            Ot,
            g,
            b,
            p,
            _,
            C
          ), m.el = Ot.el;
        }
        if (we && st(we, _), !At && (j = X && X.onVnodeMounted)) {
          const Ot = m;
          st(
            () => Tt(j, xe, Ot),
            _
          );
        }
        (m.shapeFlag & 256 || xe && Gn(xe.vnode) && xe.vnode.shapeFlag & 256) && p.a && st(p.a, _), p.isMounted = !0, m = g = b = null;
      }
    };
    p.scope.on();
    const M = p.effect = new hl(D);
    p.scope.off();
    const A = p.update = M.run.bind(M), G = p.job = M.runIfDirty.bind(M);
    G.i = p, G.id = p.uid, M.scheduler = () => ci(G), Sn(p, !0), A();
  }, Q = (p, m, g) => {
    m.component = p;
    const b = p.vnode.props;
    p.vnode = m, p.next = null, Yf(p, m.props, b, g), td(p, m.children, g), Vt(), Ml(p), Bt();
  }, le = (p, m, g, b, _, C, R, D, M = !1) => {
    const A = p && p.children, G = p ? p.shapeFlag : 0, j = m.children, { patchFlag: K, shapeFlag: X } = m;
    if (K > 0) {
      if (K & 128) {
        q(
          A,
          j,
          g,
          b,
          _,
          C,
          R,
          D,
          M
        );
        return;
      } else if (K & 256) {
        at(
          A,
          j,
          g,
          b,
          _,
          C,
          R,
          D,
          M
        );
        return;
      }
    }
    X & 8 ? (G & 16 && _e(A, _, C), j !== A && u(g, j)) : G & 16 ? X & 16 ? q(
      A,
      j,
      g,
      b,
      _,
      C,
      R,
      D,
      M
    ) : _e(A, _, C, !0) : (G & 8 && u(g, ""), X & 16 && E(
      j,
      g,
      b,
      _,
      C,
      R,
      D,
      M
    ));
  }, at = (p, m, g, b, _, C, R, D, M) => {
    p = p || Rn, m = m || Rn;
    const A = p.length, G = m.length, j = Math.min(A, G);
    let K;
    for (K = 0; K < j; K++) {
      const X = m[K] = M ? Jt(m[K]) : Mt(m[K]);
      v(
        p[K],
        X,
        g,
        null,
        _,
        C,
        R,
        D,
        M
      );
    }
    A > G ? _e(
      p,
      _,
      C,
      !0,
      !1,
      j
    ) : E(
      m,
      g,
      b,
      _,
      C,
      R,
      D,
      M,
      j
    );
  }, q = (p, m, g, b, _, C, R, D, M) => {
    let A = 0;
    const G = m.length;
    let j = p.length - 1, K = G - 1;
    for (; A <= j && A <= K; ) {
      const X = p[A], ue = m[A] = M ? Jt(m[A]) : Mt(m[A]);
      if (as(X, ue))
        v(
          X,
          ue,
          g,
          null,
          _,
          C,
          R,
          D,
          M
        );
      else
        break;
      A++;
    }
    for (; A <= j && A <= K; ) {
      const X = p[j], ue = m[K] = M ? Jt(m[K]) : Mt(m[K]);
      if (as(X, ue))
        v(
          X,
          ue,
          g,
          null,
          _,
          C,
          R,
          D,
          M
        );
      else
        break;
      j--, K--;
    }
    if (A > j) {
      if (A <= K) {
        const X = K + 1, ue = X < G ? m[X].el : b;
        for (; A <= K; )
          v(
            null,
            m[A] = M ? Jt(m[A]) : Mt(m[A]),
            g,
            ue,
            _,
            C,
            R,
            D,
            M
          ), A++;
      }
    } else if (A > K)
      for (; A <= j; )
        We(p[A], _, C, !0), A++;
    else {
      const X = A, ue = A, we = /* @__PURE__ */ new Map();
      for (A = ue; A <= K; A++) {
        const ct = m[A] = M ? Jt(m[A]) : Mt(m[A]);
        ct.key != null && we.set(ct.key, A);
      }
      let xe, je = 0;
      const He = K - ue + 1;
      let At = !1, Ot = 0;
      const os = new Array(He);
      for (A = 0; A < He; A++) os[A] = 0;
      for (A = X; A <= j; A++) {
        const ct = p[A];
        if (je >= He) {
          We(ct, _, C, !0);
          continue;
        }
        let Rt;
        if (ct.key != null)
          Rt = we.get(ct.key);
        else
          for (xe = ue; xe <= K; xe++)
            if (os[xe - ue] === 0 && as(ct, m[xe])) {
              Rt = xe;
              break;
            }
        Rt === void 0 ? We(ct, _, C, !0) : (os[Rt - ue] = A + 1, Rt >= Ot ? Ot = Rt : At = !0, v(
          ct,
          m[Rt],
          g,
          null,
          _,
          C,
          R,
          D,
          M
        ), je++);
      }
      const Ai = At ? od(os) : Rn;
      for (xe = Ai.length - 1, A = He - 1; A >= 0; A--) {
        const ct = ue + A, Rt = m[ct], Oi = m[ct + 1], Ri = ct + 1 < G ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          Oi.el || Mo(Oi)
        ) : b;
        os[A] === 0 ? v(
          null,
          Rt,
          g,
          Ri,
          _,
          C,
          R,
          D,
          M
        ) : At && (xe < 0 || A !== Ai[xe] ? lt(Rt, g, Ri, 2) : xe--);
      }
    }
  }, lt = (p, m, g, b, _ = null) => {
    const { el: C, type: R, transition: D, children: M, shapeFlag: A } = p;
    if (A & 6) {
      lt(p.component.subTree, m, g, b);
      return;
    }
    if (A & 128) {
      p.suspense.move(m, g, b);
      return;
    }
    if (A & 64) {
      R.move(p, m, g, T);
      return;
    }
    if (R === qe) {
      s(C, m, g);
      for (let j = 0; j < M.length; j++)
        lt(M[j], m, g, b);
      s(p.anchor, m, g);
      return;
    }
    if (R === Xr) {
      N(p, m, g);
      return;
    }
    if (b !== 2 && A & 1 && D)
      if (b === 0)
        D.persisted && !C[Jr] ? s(C, m, g) : (D.beforeEnter(C), s(C, m, g), st(() => D.enter(C), _));
      else {
        const { leave: j, delayLeave: K, afterLeave: X } = D, ue = () => {
          p.ctx.isUnmounted ? r(C) : s(C, m, g);
        }, we = () => {
          const xe = C._isLeaving || !!C[Jr];
          C._isLeaving && C[Jr](
            !0
            /* cancelled */
          ), D.persisted && !xe ? ue() : j(C, () => {
            ue(), X && X();
          });
        };
        K ? K(C, ue, we) : we();
      }
    else
      s(C, m, g);
  }, We = (p, m, g, b = !1, _ = !1) => {
    const {
      type: C,
      props: R,
      ref: D,
      children: M,
      dynamicChildren: A,
      shapeFlag: G,
      patchFlag: j,
      dirs: K,
      cacheIndex: X,
      memo: ue
    } = p;
    if ((j === -2 || A && A.hasOnce) && (_ = !1), D != null && (Vt(), bs(D, null, g, p, !0), Bt()), X != null && (!p.ctx || p.ctx === m) && (m.renderCache[X] = void 0), G & 256) {
      m.ctx.deactivate(p);
      return;
    }
    const we = G & 1 && K, xe = !Gn(p);
    let je;
    if (xe && (je = R && R.onVnodeBeforeUnmount) && Tt(je, m, p), G & 6)
      Pe(p.component, g, b);
    else {
      if (G & 128) {
        p.suspense.unmount(g, b);
        return;
      }
      we && kn(p, null, m, "beforeUnmount"), G & 64 ? p.type.remove(
        p,
        m,
        g,
        T,
        b
      ) : A && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !A.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (C !== qe || j > 0 && j & 64) ? _e(
        A,
        m,
        g,
        !1,
        !0
      ) : (C === qe && j & 384 || !_ && G & 16) && _e(M, m, g), b && Wt(p);
    }
    const He = ue != null && X == null;
    (xe && (je = R && R.onVnodeUnmounted) || we || He) && st(() => {
      je && Tt(je, m, p), we && kn(p, null, m, "unmounted"), He && (p.el = null);
    }, g);
  }, Wt = (p) => {
    const { type: m, el: g, anchor: b, transition: _ } = p, C = m === qe;
    if (C && !_) {
      _t(g, b);
      return;
    }
    if (m === Xr) {
      O(p), _ && !_.persisted && _.afterLeave && _.afterLeave();
      return;
    }
    const R = C ? Ro(p) : p, D = () => {
      C ? f(g) && _t(g, b) : r(g), _ && !_.persisted && _.afterLeave && _.afterLeave();
    };
    if (R && R.shapeFlag & 1 && _ && !_.persisted) {
      const { leave: M, delayLeave: A } = _, G = R.el, j = () => M(G, D);
      A ? A(G, D, j) : j();
    } else
      D();
  }, _t = (p, m) => {
    let g;
    for (; p !== m; )
      g = d(p), r(p), p = g;
    r(m);
  }, Pe = (p, m, g) => {
    const { bum: b, scope: _, job: C, subTree: R, um: D, m: M, a: A } = p;
    Ki(M), Ki(A), b && nr(b), _.stop(), C ? (C.flags |= 8, We(R, p, m, g)) : p.vnode.el && R && (R.transition = p.vnode.transition, We(R, p, m, g)), D && st(D, m), st(() => {
      p.isUnmounted = !0;
    }, m);
  }, _e = (p, m, g, b = !1, _ = !1, C = 0) => {
    for (let R = C; R < p.length; R++)
      We(p[R], m, g, b, _);
  }, S = (p) => {
    if (p.shapeFlag & 6)
      return S(p.component.subTree);
    if (p.shapeFlag & 128)
      return p.suspense.next();
    const m = d(p.anchor || p.el), g = m && m[$l];
    return g ? d(g) : m;
  }, z = (p, m, g) => {
    const b = p && m._vnode ? void 0 : p && p.component ? p.component.uid : cd();
    pf(() => {
      p == null ? m._vnode && We(m._vnode, null, null, !0) : v(
        m._vnode || null,
        p,
        m,
        null,
        null,
        null,
        g
      ), m._vnode = p;
    }, b);
  }, T = {
    p: v,
    um: We,
    m: lt,
    r: Wt,
    mt: et,
    mc: E,
    pc: le,
    pbc: ce,
    n: S,
    o: e
  };
  return {
    render: z,
    hydrate: void 0,
    createApp: zf(z)
  };
}
function Qr({ type: e, props: t }, n) {
  return n === "svg" && e === "foreignObject" || n === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : n;
}
function Sn({ effect: e, job: t }, n) {
  n ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function rd(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function mi(e, t, n = !1) {
  const s = e.children, r = t.children;
  if (Y(s) && Y(r))
    for (let o = 0; o < s.length; o++) {
      const i = s[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = Jt(r[o]), a.el = i.el), !n && a.patchFlag !== -2 && mi(i, a)), a.type === $r && (a.patchFlag === -1 && (a = r[o] = Jt(a)), a.el = i.el), a.type === pt && !a.el && (a.el = i.el);
    }
}
function od(e) {
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
function lc(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : lc(t);
}
function Ki(e) {
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
const cc = (e) => e.__isSuspense;
function id(e, t) {
  t && t.pendingBranch ? Y(e) ? t.effects.push(...e) : t.effects.push(e) : df(e);
}
const qe = /* @__PURE__ */ Symbol.for("v-fgt"), $r = /* @__PURE__ */ Symbol.for("v-txt"), pt = /* @__PURE__ */ Symbol.for("v-cmt"), Xr = /* @__PURE__ */ Symbol.for("v-stc"), Xt = [];
let ut = null;
function de(e = !1) {
  Xt.push(ut = e ? null : []);
}
function gi() {
  Xt.pop(), ut = Xt[Xt.length - 1] || null;
}
let As = 1;
function dr(e, t = !1) {
  As += e, e < 0 && ut && t && (ut.hasOnce = !0);
}
function uc(e) {
  return e.dynamicChildren = As > 0 ? ut || Rn : null, gi(), As > 0 && ut && ut.push(e), e;
}
function mt(e, t, n, s, r, o) {
  return uc(
    L(
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
function Le(e, t, n, s, r) {
  return uc(
    fe(
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
const fc = ({ key: e }) => e ?? null, sr = ({
  ref: e,
  ref_key: t,
  ref_for: n
}) => (typeof e == "number" && (e = "" + e), e != null ? Te(e) || /* @__PURE__ */ De(e) || ee(e) ? { i: Ze, r: e, k: t, f: !!n } : e : null);
function L(e, t = null, n = null, s = 0, r = null, o = e === qe ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && fc(t),
    ref: t && sr(t),
    scopeId: jl,
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
  return a ? (pr(l, n), o & 128 && e.normalize(l)) : n && (l.shapeFlag |= Te(n) ? 8 : 16), As > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  ut && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && ut.push(l), l;
}
const fe = ad;
function ad(e, t = null, n = null, s = 0, r = null, o = !1) {
  if ((!e || e === Hl) && (e = pt), Jn(e)) {
    const a = Mn(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return n && pr(a, n), As > 0 && !o && ut && (a.shapeFlag & 6 ? ut[ut.indexOf(e)] = a : ut.push(a)), a.patchFlag = -2, a;
  }
  if (gd(e) && (e = e.__vccOpts), t) {
    t = dc(t);
    let { class: a, style: l } = t;
    a && !Te(a) && (t.class = Se(a)), be(l) && (/* @__PURE__ */ Nr(l) && !Y(l) && (l = Ge({}, l)), t.style = Ls(l));
  }
  const i = Te(e) ? 1 : cc(e) ? 128 : Dr(e) ? 64 : be(e) ? 4 : ee(e) ? 2 : 0;
  return L(
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
function dc(e) {
  return e ? /* @__PURE__ */ Nr(e) || nc(e) ? Ge({}, e) : e : null;
}
function Mn(e, t, n = !1, s = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? yt(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && fc(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      n && o ? Y(o) ? o.concat(sr(t)) : [o, sr(t)] : sr(t)
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
function ve(e = " ", t = 0) {
  return fe($r, null, e, t);
}
function Os(e = "", t = !1) {
  return t ? (de(), Le(pt, null, e)) : fe(pt, null, e);
}
function Mt(e) {
  return e == null || typeof e == "boolean" ? fe(pt) : Y(e) ? fe(
    qe,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : Jn(e) ? Jt(e) : fe($r, null, String(e));
}
function Jt(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : Mn(e);
}
function pr(e, t) {
  let n = 0;
  const { shapeFlag: s } = e;
  if (t == null)
    t = null;
  else if (Y(t))
    n = 16;
  else if (typeof t == "object")
    if (s & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), pr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      n = 32;
      const r = t._;
      !r && !nc(t) ? t._ctx = Ze : r === 3 && Ze && (Ze.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (ee(t)) {
    if (s & 65) {
      pr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: Ze }, n = 32;
  } else
    t = String(t), s & 64 ? (n = 16, t = [ve(t)]) : n = 8;
  e.children = t, e.shapeFlag |= n;
}
function yt(...e) {
  const t = {};
  for (let n = 0; n < e.length; n++) {
    const s = e[n];
    for (const r in s)
      if (r === "class")
        t.class !== s.class && (t.class = Se([t.class, s.class]));
      else if (r === "style")
        t.style = Ls([t.style, s.style]);
      else if (kr(r)) {
        const o = t[r], i = s[r];
        i && o !== i && !(Y(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
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
const ld = Jl();
let pc = 0;
function cd() {
  return pc;
}
function ud(e, t, n) {
  const s = e.type, r = (t ? t.appContext : e.appContext) || ld, o = {
    uid: pc++,
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
    scope: new pl(
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
    propsOptions: rc(s, r),
    emitsOptions: Yl(s, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: ke,
    // inheritAttrs
    inheritAttrs: s.inheritAttrs,
    // state
    ctx: ke,
    data: ke,
    props: ke,
    attrs: ke,
    slots: ke,
    refs: ke,
    setupState: ke,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = Wf.bind(null, o), e.ce && e.ce(o), o;
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
const Fs = (e) => {
  const t = Je;
  return hr(e), e.scope.on(), () => {
    e.scope.off(), hr(t);
  };
}, Ji = () => {
  Je && Je.scope.off(), hr(null);
};
function hc(e) {
  return e.vnode.shapeFlag & 4;
}
let Ts = !1;
function fd(e, t = !1, n = !1) {
  t && Rs(t);
  const { props: s, children: r } = e.vnode, o = hc(e);
  Jf(e, s, o, t), ed(e, r, n || t);
  const i = o ? dd(e, t) : void 0;
  return t && Rs(!1), i;
}
function dd(e, t) {
  const n = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Df);
  const { setup: s } = n;
  if (s) {
    Vt();
    const r = e.setupContext = s.length > 1 ? hd(e) : null, o = Fs(e), i = js(
      s,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = il(i);
    if (Bt(), o(), (a || e.sp) && !Gn(e) && Bl(e), a) {
      if (i.then(Ji, Ji), t)
        return i.then((l) => {
          Rs(!0);
          try {
            Yi(e, l, t);
          } finally {
            Rs(!1);
          }
        }).catch((l) => {
          Mr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      Yi(e, i);
  } else
    mc(e);
}
function Yi(e, t, n) {
  ee(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : be(t) && (e.setupState = Il(t)), mc(e);
}
function mc(e, t, n) {
  const s = e.type;
  e.render || (e.render = s.render || jt);
  {
    const r = Fs(e);
    Vt();
    try {
      Lf(e);
    } finally {
      Bt(), r();
    }
  }
}
const pd = {
  get(e, t) {
    return Ke(e, "get", ""), e[t];
  }
};
function hd(e) {
  const t = (n) => {
    e.exposed = n || {};
  };
  return {
    attrs: new Proxy(e.attrs, pd),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Vr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(Il(ai(e.exposed)), {
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
function md(e, t = !0) {
  return ee(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function gd(e) {
  return ee(e) && "__vccOpts" in e;
}
const ae = (e, t) => /* @__PURE__ */ af(e, t, Ts);
function en(e, t, n) {
  try {
    dr(-1);
    const s = arguments.length;
    return s === 2 ? be(t) && !Y(t) ? Jn(t) ? fe(e, null, [t]) : fe(e, t) : fe(e, null, t) : (s > 3 ? n = Array.prototype.slice.call(arguments, 2) : s === 3 && Jn(n) && (n = [n]), fe(e, t, n));
  } finally {
    dr(1);
  }
}
const yd = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Do;
const Qi = typeof window < "u" && window.trustedTypes;
if (Qi)
  try {
    Do = /* @__PURE__ */ Qi.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const gc = Do ? (e) => Do.createHTML(e) : (e) => e, vd = "http://www.w3.org/2000/svg", bd = "http://www.w3.org/1998/Math/MathML", Kt = typeof document < "u" ? document : null, Xi = Kt && /* @__PURE__ */ Kt.createElement("template"), _d = {
  insert: (e, t, n) => {
    t.insertBefore(e, n || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, n, s) => {
    const r = t === "svg" ? Kt.createElementNS(vd, e) : t === "mathml" ? Kt.createElementNS(bd, e) : n ? Kt.createElement(e, { is: n }) : Kt.createElement(e);
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
      Xi.innerHTML = gc(
        s === "svg" ? `<svg>${e}</svg>` : s === "mathml" ? `<math>${e}</math>` : e
      );
      const a = Xi.content;
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
}, xd = /* @__PURE__ */ Symbol("_vtc");
function wd(e, t, n) {
  const s = e[xd];
  s && (t = (t ? [t, ...s] : [...s]).join(" ")), t == null ? e.removeAttribute("class") : n ? e.setAttribute("class", t) : e.className = t;
}
const mr = /* @__PURE__ */ Symbol("_vod"), yc = /* @__PURE__ */ Symbol("_vsh"), Lo = {
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
  e.style.display = t ? e[mr] : "none", e[yc] = !t;
}
const kd = /* @__PURE__ */ Symbol(""), Sd = /(?:^|;)\s*display\s*:/;
function Ed(e, t, n) {
  const s = e.style, r = Te(n);
  let o = !1;
  if (n && !r) {
    if (t)
      if (Te(t))
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
      a != null ? Ad(
        e,
        i,
        !Te(t) && t ? t[i] : void 0,
        a
      ) || ps(s, i, a) : ps(s, i, "");
    }
  } else if (r) {
    if (t !== n) {
      const i = s[kd];
      i && (n += ";" + i), s.cssText = n, o = Sd.test(n);
    }
  } else t && e.removeAttribute("style");
  mr in e && ((!r || t !== n) && (e[mr] = o ? s.display : ""), e[yc] && (s.display = "none"));
}
const Ws = /\s*!important$/;
function ps(e, t, n) {
  if (Y(n))
    n.forEach((s) => ps(e, t, s));
  else if (n == null && (n = ""), t.startsWith("--"))
    Ws.test(n) ? e.setProperty(t, n.replace(Ws, ""), "important") : e.setProperty(t, n);
  else {
    const s = Cd(e, t);
    Ws.test(n) ? e.setProperty(
      Ln(s),
      n.replace(Ws, ""),
      "important"
    ) : e[s] = n;
  }
}
const ea = ["Webkit", "Moz", "ms"], eo = {};
function Cd(e, t) {
  const n = eo[t];
  if (n)
    return n;
  let s = Ye(t);
  if (s !== "filter" && s in e)
    return eo[t] = s;
  s = Ar(s);
  for (let r = 0; r < ea.length; r++) {
    const o = ea[r] + s;
    if (o in e)
      return eo[t] = o;
  }
  return t;
}
function Ad(e, t, n, s) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && Te(s) && n === s;
}
const ta = "http://www.w3.org/1999/xlink";
function na(e, t, n, s, r, o = Mu(t)) {
  s && t.startsWith("xlink:") ? n == null ? e.removeAttributeNS(ta, t.slice(6, t.length)) : e.setAttributeNS(ta, t, n) : n == null || o && !ul(n) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : dt(n) ? String(n) : n
  );
}
function sa(e, t, n, s, r) {
  if (t === "innerHTML" || t === "textContent") {
    n != null && (e[t] = t === "innerHTML" ? gc(n) : n);
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
    a === "boolean" ? n = ul(n) : n == null && a === "string" ? (n = "", i = !0) : a === "number" && (n = 0, i = !0);
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
function Od(e, t, n, s) {
  e.removeEventListener(t, n, s);
}
const ra = /* @__PURE__ */ Symbol("_vei");
function Rd(e, t, n, s, r = null) {
  const o = e[ra] || (e[ra] = {}), i = o[t];
  if (s && i)
    i.value = s;
  else {
    const [a, l] = Pd(t);
    if (s) {
      const c = o[t] = Dd(
        s,
        r
      );
      Wn(e, a, c, l);
    } else i && (Od(e, a, i, l), o[t] = void 0);
  }
}
const Td = /(Once|Passive|Capture)$/, Id = /^on:?(?:Once|Passive|Capture)$/;
function Pd(e) {
  let t, n;
  for (; (n = e.match(Td)) && !Id.test(e); )
    t || (t = {}), e = e.slice(0, e.length - n[1].length), t[n[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Ln(e.slice(2)), t];
}
let to = 0;
const Nd = /* @__PURE__ */ Promise.resolve(), Md = () => to || (Nd.then(() => to = 0), to = Date.now());
function Dd(e, t) {
  const n = (s) => {
    if (!s._vts)
      s._vts = Date.now();
    else if (s._vts <= n.attached)
      return;
    const r = n.value;
    if (Y(r)) {
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
  return n.value = e, n.attached = Md(), n;
}
const oa = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, Ld = (e, t, n, s, r, o) => {
  const i = r === "svg";
  t === "class" ? wd(e, s, i) : t === "style" ? Ed(e, n, s) : kr(t) ? Sr(t) || Rd(e, t, n, s, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : jd(e, t, s, i)) ? (sa(e, t, s), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && na(e, t, s, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (Fd(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !Te(s))) ? sa(e, Ye(t), s, o, t) : (t === "true-value" ? e._trueValue = s : t === "false-value" && (e._falseValue = s), na(e, t, s, i));
};
function jd(e, t, n, s) {
  if (s)
    return !!(t === "innerHTML" || t === "textContent" || t in e && oa(t) && ee(n));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return oa(t) && Te(n) ? !1 : t in e;
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
const ia = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return Y(t) ? (n) => nr(t, n) : t;
};
function $d(e) {
  e.target.composing = !0;
}
function aa(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const Hs = /* @__PURE__ */ Symbol("_assign"), qs = /* @__PURE__ */ Symbol("_initialValue");
function no(e, t, n) {
  return t && (e = e.trim()), n && (e = Xo(e)), e;
}
const vc = {
  created(e, { modifiers: { lazy: t, trim: n, number: s } }, r) {
    e.parentNode && (e.type === "text" ? e[qs] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[qs] = e.defaultValue.replace(/\r\n?/g, `
`))), e[Hs] = ia(r);
    const o = s || r.props && r.props.type === "number";
    Wn(e, t ? "change" : "input", (i) => {
      i.target.composing || e[Hs](no(e.value, n, o));
    }), (n || o) && Wn(e, "change", () => {
      e.value = no(e.value, n, o);
    }), t || (Wn(e, "compositionstart", $d), Wn(e, "compositionend", aa), Wn(e, "change", aa));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: n, number: s } }) {
    const r = t ?? "", o = e[qs];
    delete e[qs], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[Hs](no(e.value, n, s)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: n, modifiers: { lazy: s, trim: r, number: o } }, i) {
    if (e[Hs] = ia(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? Xo(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (s && t === n || r && e.value.trim() === l) || (e.value = l);
  }
}, Vd = ["ctrl", "shift", "alt", "meta"], Bd = {
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
  exact: (e, t) => Vd.some((n) => e[`${n}Key`] && !t.includes(n))
}, zd = (e, t) => {
  if (!e) return e;
  const n = e._withMods || (e._withMods = {}), s = t.join(".");
  return n[s] || (n[s] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = Bd[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, Ud = /* @__PURE__ */ Ge({ patchProp: Ld }, _d);
let la;
function Wd() {
  return la || (la = nd(Ud));
}
const Hd = ((...e) => {
  const t = Wd().createApp(...e), { mount: n } = t;
  return t.mount = (s) => {
    const r = Zd(s);
    if (!r) return;
    const o = t._component;
    !ee(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = n(r, !1, qd(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function qd(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function Zd(e) {
  return Te(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let bc;
const Br = (e) => bc = e, _c = (
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
function Gd() {
  const e = Tr(!0), t = e.run(() => /* @__PURE__ */ se({}));
  let n = [], s = [];
  const r = ai({
    install(o) {
      Br(r), r._a = o, o.provide(_c, r), o.config.globalProperties.$pinia = r, s.forEach((i) => n.push(i)), s = [];
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
const xc = () => {
};
function ca(e, t, n, s = xc) {
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
const Kd = (e) => e(), ua = Symbol(), so = Symbol();
function Fo(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((n, s) => e.set(s, n)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const n in t) {
    if (!t.hasOwnProperty(n))
      continue;
    const s = t[n], r = e[n];
    jo(r) && jo(s) && e.hasOwnProperty(n) && !/* @__PURE__ */ De(s) && !/* @__PURE__ */ Ft(s) ? e[n] = Fo(r, s) : e[n] = s;
  }
  return e;
}
const Jd = (
  /* istanbul ignore next */
  Symbol()
);
function Yd(e) {
  return !jo(e) || !Object.prototype.hasOwnProperty.call(e, Jd);
}
const { assign: un } = Object;
function Qd(e) {
  return !!(/* @__PURE__ */ De(e) && e.effect);
}
function Xd(e, t, n, s) {
  const { state: r, actions: o, getters: i } = t, a = n.state.value[e];
  let l;
  function c() {
    a || (n.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ li(n.state.value[e]);
    return un(u, o, Object.keys(i || {}).reduce((f, d) => (f[d] = ai(ae(() => {
      Br(n);
      const h = n._s.get(e);
      return i[d].call(h, h);
    })), f), {}));
  }
  return l = wc(e, c, t, n, s, !0), l;
}
function wc(e, t, n = {}, s, r, o) {
  let i;
  const a = un({ actions: {} }, n), l = { deep: !0 };
  let c, u, f = /* @__PURE__ */ new Set(), d = /* @__PURE__ */ new Set(), h;
  const y = s.state.value[e];
  !o && !y && (s.state.value[e] = {});
  let v;
  function k(E) {
    let F;
    c = u = !1, typeof E == "function" ? (E(s.state.value[e]), F = {
      type: xs.patchFunction,
      storeId: e,
      events: h
    }) : (Fo(s.state.value[e], E), F = {
      type: xs.patchObject,
      payload: E,
      storeId: e,
      events: h
    });
    const ce = v = Symbol();
    St().then(() => {
      v === ce && (c = !0);
    }), u = !0, Bn(f, F, s.state.value[e]);
  }
  const I = o ? function() {
    const { state: F } = n, ce = F ? F() : {};
    this.$patch((Oe) => {
      un(Oe, ce);
    });
  } : (
    /* istanbul ignore next */
    xc
  );
  function w() {
    i.stop(), f.clear(), d.clear(), s._s.delete(e);
  }
  const N = (E, F = "") => {
    if (ua in E)
      return E[so] = F, E;
    const ce = function() {
      Br(s);
      const Oe = Array.from(arguments), Ie = /* @__PURE__ */ new Set(), $e = /* @__PURE__ */ new Set();
      function et(Q) {
        Ie.add(Q);
      }
      function tt(Q) {
        $e.add(Q);
      }
      Bn(d, {
        args: Oe,
        name: ce[so],
        store: W,
        after: et,
        onError: tt
      });
      let ie;
      try {
        ie = E.apply(this && this.$id === e ? this : W, Oe);
      } catch (Q) {
        throw Bn($e, Q), Q;
      }
      return ie instanceof Promise ? ie.then((Q) => (Bn(Ie, Q), Q)).catch((Q) => (Bn($e, Q), Promise.reject(Q))) : (Bn(Ie, ie), ie);
    };
    return ce[ua] = !0, ce[so] = F, ce;
  }, O = {
    _p: s,
    // _s: scope,
    $id: e,
    $onAction: ca.bind(null, d),
    $patch: k,
    $reset: I,
    $subscribe(E, F = {}) {
      const ce = ca(f, E, F.detached, () => Oe()), Oe = i.run(() => Fe(() => s.state.value[e], (Ie) => {
        (F.flush === "sync" ? u : c) && E({
          storeId: e,
          type: xs.direct,
          events: h
        }, Ie);
      }, un({}, l, F)));
      return ce;
    },
    $dispose: w
  }, W = /* @__PURE__ */ jn(O);
  s._s.set(e, W);
  const V = (s._a && s._a.runWithContext || Kd)(() => s._e.run(() => (i = Tr()).run(() => t({ action: N }))));
  for (const E in V) {
    const F = V[E];
    if (/* @__PURE__ */ De(F) && !Qd(F) || /* @__PURE__ */ Ft(F))
      o || (y && Yd(F) && (/* @__PURE__ */ De(F) ? F.value = y[E] : Fo(F, y[E])), s.state.value[e][E] = F);
    else if (typeof F == "function") {
      const ce = N(F, E);
      V[E] = ce, a.actions[E] = F;
    }
  }
  return un(W, V), un(/* @__PURE__ */ he(W), V), Object.defineProperty(W, "$state", {
    get: () => s.state.value[e],
    set: (E) => {
      k((F) => {
        un(F, E);
      });
    }
  }), s._p.forEach((E) => {
    un(W, i.run(() => E({
      store: W,
      app: s._a,
      pinia: s,
      options: a
    })));
  }), y && o && n.hydrate && n.hydrate(W.$state, y), c = !0, u = !0, W;
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
    i || (l ? it(_c, null) : null), i && Br(i), i = bc, i._s.has(e) || (r ? wc(e, t, s, i) : Xd(e, s, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const Hn = typeof document < "u";
function kc(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function ep(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && kc(e.default);
}
const Re = Object.assign;
function ro(e, t) {
  const n = {};
  for (const s in t) {
    const r = t[s];
    n[s] = Et(r) ? r.map(e) : e(r);
  }
  return n;
}
const ws = () => {
}, Et = Array.isArray;
function fa(e, t) {
  const n = {};
  for (const s in e) n[s] = s in t ? t[s] : e[s];
  return n;
}
const Sc = /#/g, tp = /&/g, np = /\//g, sp = /=/g, rp = /\?/g, Ec = /\+/g, op = /%5B/g, ip = /%5D/g, Cc = /%5E/g, ap = /%60/g, Ac = /%7B/g, lp = /%7C/g, Oc = /%7D/g, cp = /%20/g;
function yi(e) {
  return e == null ? "" : encodeURI("" + e).replace(lp, "|").replace(op, "[").replace(ip, "]");
}
function up(e) {
  return yi(e).replace(Ac, "{").replace(Oc, "}").replace(Cc, "^");
}
function $o(e) {
  return yi(e).replace(Ec, "%2B").replace(cp, "+").replace(Sc, "%23").replace(tp, "%26").replace(ap, "`").replace(Ac, "{").replace(Oc, "}").replace(Cc, "^");
}
function fp(e) {
  return $o(e).replace(sp, "%3D");
}
function dp(e) {
  return yi(e).replace(Sc, "%23").replace(rp, "%3F");
}
function pp(e) {
  return dp(e).replace(np, "%2F");
}
function Is(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const hp = /\/$/, mp = (e) => e.replace(hp, "");
function oo(e, t, n = "/") {
  let s, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (s = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (s = s || t.slice(0, a), i = t.slice(a, t.length)), s = bp(s ?? t, n), {
    fullPath: s + o + i,
    path: s,
    query: r,
    hash: Is(i)
  };
}
function gp(e, t) {
  const n = t.query ? e(t.query) : "";
  return t.path + (n && "?") + n + (t.hash || "");
}
function yp(e, t, n) {
  const s = t.matched.length - 1, r = n.matched.length - 1;
  return s > -1 && s === r && Yn(t.matched[s], n.matched[r]) && Rc(t.params, n.params) && e(t.query) === e(n.query) && t.hash === n.hash;
}
function Yn(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function Rc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var n in e) if (!vp(e[n], t[n])) return !1;
  return !0;
}
function vp(e, t) {
  return Et(e) ? da(e, t) : Et(t) ? da(t, e) : e?.valueOf() === t?.valueOf();
}
function da(e, t) {
  return Et(t) ? e.length === t.length && e.every((n, s) => n === t[s]) : e.length === 1 && e[0] === t;
}
function bp(e, t) {
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
})({}), pa = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const io = "";
function _p(e) {
  if (!e) if (Hn) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), mp(e);
}
const xp = /^[^#]+#/;
function wp(e, t) {
  return e.replace(xp, "#") + t;
}
function kp(e, t) {
  const n = document.documentElement.getBoundingClientRect(), s = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: s.left - n.left - (t.left || 0),
    top: s.top - n.top - (t.top || 0)
  };
}
const Sp = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function Ep(e) {
  let t;
  if ("el" in e) {
    const n = e.el, s = typeof n == "string" && n.startsWith("#"), r = typeof n == "string" ? s ? document.getElementById(n.slice(1)) : document.querySelector(n) : n;
    if (!r)
      return;
    t = kp(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function ha(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Bo = /* @__PURE__ */ new Map();
function Cp(e, t) {
  Bo.set(e, t);
}
function Ap(e) {
  const t = Bo.get(e);
  return Bo.delete(e), t;
}
function Op(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function Tc(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let Ne = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const Ic = Symbol("");
Ne.MATCHER_NOT_FOUND + "", Ne.NAVIGATION_GUARD_REDIRECT + "", Ne.NAVIGATION_ABORTED + "", Ne.NAVIGATION_CANCELLED + "", Ne.NAVIGATION_DUPLICATED + "";
function Qn(e, t) {
  return Re(/* @__PURE__ */ new Error(), {
    type: e,
    [Ic]: !0
  }, t);
}
function qt(e, t) {
  return e instanceof Error && Ic in e && (t == null || !!(e.type & t));
}
const Rp = [
  "params",
  "query",
  "hash"
];
function Tp(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const n of Rp) n in e && (t[n] = e[n]);
  return JSON.stringify(t, null, 2);
}
function Ip(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const n = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let s = 0; s < n.length; ++s) {
    const r = n[s].replace(Ec, " "), o = r.indexOf("="), i = Is(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : Is(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      Et(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function ma(e) {
  let t = "";
  for (let n in e) {
    const s = e[n];
    if (n = fp(n), s == null) {
      s !== void 0 && (t += (t.length ? "&" : "") + n);
      continue;
    }
    (Et(s) ? s.map((r) => r && $o(r)) : [s && $o(s)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + n, r != null && (t += "=" + r));
    });
  }
  return t;
}
function Pp(e) {
  const t = {};
  for (const n in e) {
    const s = e[n];
    s !== void 0 && (t[n] = Et(s) ? s.map((r) => r == null ? null : "" + r) : s == null ? s : "" + s);
  }
  return t;
}
const Np = Symbol(""), ga = Symbol(""), zr = Symbol(""), vi = Symbol(""), zo = Symbol("");
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
      d === !1 ? l(Qn(Ne.NAVIGATION_ABORTED, {
        from: n,
        to: t
      })) : d instanceof Error ? l(d) : Op(d) ? l(Qn(Ne.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: d
      })) : (i && s.enterCallbacks[r] === i && typeof d == "function" && i.push(d), a());
    }, u = o(() => e.call(s && s.instances[r], t, n, c));
    let f = Promise.resolve(u);
    e.length < 3 && (f = f.then(c)), f.catch((d) => l(d));
  });
}
function ao(e, t, n, s, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (kc(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(dn(c, n, s, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const f = ep(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = f;
            const d = (f.__vccOpts || f)[t];
            return d && dn(d, n, s, i, a, r)();
          }));
        }
    }
  return o;
}
function Mp(e, t) {
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
function Dp(e = "") {
  let t = [], n = [[io, {}]], s = 0;
  e = _p(e);
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
    location: io,
    state: {},
    base: e,
    createHref: wp.bind(null, e),
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
      t = [], n = [[io, {}]], s = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? pa.back : pa.forward;
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
var Be = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(Be || {});
const Lp = {
  type: Tn.Static,
  value: ""
}, jp = /[a-zA-Z0-9_]/;
function Fp(e) {
  if (!e) return [[]];
  if (e === "/") return [[Lp]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(h) {
    throw new Error(`ERR (${n})/"${c}": ${h}`);
  }
  let n = Be.Static, s = n;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function f() {
    c && (n === Be.Static ? o.push({
      type: Tn.Static,
      value: c
    }) : n === Be.Param || n === Be.ParamRegExp || n === Be.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
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
    if (l = e[a++], l === "\\" && n !== Be.ParamRegExp) {
      s = n, n = Be.EscapeNext;
      continue;
    }
    switch (n) {
      case Be.Static:
        l === "/" ? (c && f(), i()) : l === ":" ? (f(), n = Be.Param) : d();
        break;
      case Be.EscapeNext:
        d(), n = s;
        break;
      case Be.Param:
        l === "(" ? n = Be.ParamRegExp : jp.test(l) ? d() : (f(), n = Be.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case Be.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : n = Be.ParamRegExpEnd : u += l;
        break;
      case Be.ParamRegExpEnd:
        f(), n = Be.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return n === Be.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), f(), i(), r;
}
const ya = "[^/]+?", $p = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var rt = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(rt || {});
const Vp = /[.+*?^${}()[\]/\\]/g;
function Bp(e, t) {
  const n = Re({}, $p, t), s = [];
  let r = n.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [rt.Root];
    n.strict && !c.length && (r += "/");
    for (let f = 0; f < c.length; f++) {
      const d = c[f];
      let h = rt.Segment + (n.sensitive ? rt.BonusCaseSensitive : 0);
      if (d.type === Tn.Static)
        f || (r += "/"), r += d.value.replace(Vp, "\\$&"), h += rt.Static;
      else if (d.type === Tn.Param) {
        const { value: y, repeatable: v, optional: k, regexp: I } = d;
        o.push({
          name: y,
          repeatable: v,
          optional: k
        });
        const w = I || ya;
        if (w !== ya) {
          h += rt.BonusCustomRegExp;
          try {
            `${w}`;
          } catch (O) {
            throw new Error(`Invalid custom RegExp for param "${y}" (${w}): ` + O.message);
          }
        }
        let N = v ? `((?:${w})(?:/(?:${w}))*)` : `(${w})`;
        f || (N = k && c.length < 2 ? `(?:/${N})` : "/" + N), k && (N += "?"), r += N, h += rt.Dynamic, k && (h += rt.BonusOptional), v && (h += rt.BonusRepeatable), w === ".*" && (h += rt.BonusWildcard);
      }
      u.push(h);
    }
    s.push(u);
  }
  if (n.strict && n.end) {
    const c = s.length - 1;
    s[c][s[c].length - 1] += rt.BonusStrict;
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
        const { value: y, repeatable: v, optional: k } = h, I = y in c ? c[y] : "";
        if (Et(I) && !v) throw new Error(`Provided param "${y}" is an array but it is not repeatable (* or + modifiers)`);
        const w = Et(I) ? I.join("/") : I;
        if (!w) if (k)
          d.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : f = !0);
        else throw new Error(`Missing required param "${y}"`);
        u += w;
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
function zp(e, t) {
  let n = 0;
  for (; n < e.length && n < t.length; ) {
    const s = t[n] - e[n];
    if (s) return s;
    n++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === rt.Static + rt.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === rt.Static + rt.Segment ? 1 : -1 : 0;
}
function Pc(e, t) {
  let n = 0;
  const s = e.score, r = t.score;
  for (; n < s.length && n < r.length; ) {
    const o = zp(s[n], r[n]);
    if (o) return o;
    n++;
  }
  if (Math.abs(r.length - s.length) === 1) {
    if (va(s)) return 1;
    if (va(r)) return -1;
  }
  return r.length - s.length;
}
function va(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const Up = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function Wp(e, t, n) {
  const s = Bp(Fp(e.path), n), r = Re(s, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function Hp(e, t) {
  const n = [], s = /* @__PURE__ */ new Map();
  t = fa(Up, t);
  function r(f) {
    return s.get(f);
  }
  function o(f, d, h) {
    const y = !h, v = _a(f);
    v.aliasOf = h && h.record;
    const k = fa(t, f), I = [v];
    if ("alias" in f) {
      const O = typeof f.alias == "string" ? [f.alias] : f.alias;
      for (const W of O) I.push(_a(Re({}, v, {
        components: h ? h.record.components : v.components,
        path: W,
        aliasOf: h ? h.record : v
      })));
    }
    let w, N;
    for (const O of I) {
      const { path: W } = O;
      if (d && W[0] !== "/") {
        const ge = d.record.path, V = ge[ge.length - 1] === "/" ? "" : "/";
        O.path = d.record.path + (W && V + W);
      }
      if (w = Wp(O, d, k), h ? h.alias.push(w) : (N = N || w, N !== w && N.alias.push(w), y && f.name && !xa(w) && i(f.name)), Nc(w) && l(w), v.children) {
        const ge = v.children;
        for (let V = 0; V < ge.length; V++) o(ge[V], w, h && h.children[V]);
      }
      h = h || w;
    }
    return N ? () => {
      i(N);
    } : ws;
  }
  function i(f) {
    if (Tc(f)) {
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
    const d = Gp(f, n);
    n.splice(d, 0, f), f.record.name && !xa(f) && s.set(f.record.name, f);
  }
  function c(f, d) {
    let h, y = {}, v, k;
    if ("name" in f && f.name) {
      if (h = s.get(f.name), !h) throw Qn(Ne.MATCHER_NOT_FOUND, { location: f });
      k = h.record.name, y = Re(ba(d.params, h.keys.filter((N) => !N.optional).concat(h.parent ? h.parent.keys.filter((N) => N.optional) : []).map((N) => N.name)), f.params && ba(f.params, h.keys.map((N) => N.name))), v = h.stringify(y);
    } else if (f.path != null)
      v = f.path, h = n.find((N) => N.re.test(v)), h && (y = h.parse(v), k = h.record.name);
    else {
      if (h = d.name ? s.get(d.name) : n.find((N) => N.re.test(d.path)), !h) throw Qn(Ne.MATCHER_NOT_FOUND, {
        location: f,
        currentLocation: d
      });
      k = h.record.name, y = Re({}, d.params, f.params), v = h.stringify(y);
    }
    const I = [];
    let w = h;
    for (; w; )
      I.unshift(w.record), w = w.parent;
    return {
      name: k,
      path: v,
      params: y,
      matched: I,
      meta: Zp(I)
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
function ba(e, t) {
  const n = {};
  for (const s of t) s in e && (n[s] = e[s]);
  return n;
}
function _a(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: qp(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function qp(e) {
  const t = {}, n = e.props || !1;
  if ("component" in e) t.default = n;
  else for (const s in e.components) t[s] = typeof n == "object" ? n[s] : n;
  return t;
}
function xa(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function Zp(e) {
  return e.reduce((t, n) => Re(t, n.meta), {});
}
function Gp(e, t) {
  let n = 0, s = t.length;
  for (; n !== s; ) {
    const o = n + s >> 1;
    Pc(e, t[o]) < 0 ? s = o : n = o + 1;
  }
  const r = Kp(e);
  return r && (s = t.lastIndexOf(r, s - 1)), s;
}
function Kp(e) {
  let t = e;
  for (; t = t.parent; ) if (Nc(t) && Pc(e, t) === 0) return t;
}
function Nc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function wa(e) {
  const t = it(zr), n = it(vi), s = ae(() => {
    const l = x(e.to);
    return t.resolve(l);
  }), r = ae(() => {
    const { matched: l } = s.value, { length: c } = l, u = l[c - 1], f = n.matched;
    if (!u || !f.length) return -1;
    const d = f.findIndex(Yn.bind(null, u));
    if (d > -1) return d;
    const h = ka(l[c - 2]);
    return c > 1 && ka(u) === h && f[f.length - 1].path !== h ? f.findIndex(Yn.bind(null, l[c - 2])) : d;
  }), o = ae(() => r.value > -1 && Xp(n.params, s.value.params)), i = ae(() => r.value > -1 && r.value === n.matched.length - 1 && Rc(n.params, s.value.params));
  function a(l = {}) {
    if (Qp(l)) {
      const c = t[x(e.replace) ? "replace" : "push"](x(e.to)).catch(ws);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: s,
    href: ae(() => s.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function Jp(e) {
  return e.length === 1 ? e[0] : e;
}
const Yp = /* @__PURE__ */ Ae({
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
  useLink: wa,
  setup(e, { slots: t }) {
    const n = /* @__PURE__ */ jn(wa(e)), { options: s } = it(zr), r = ae(() => ({
      [Sa(e.activeClass, s.linkActiveClass, "router-link-active")]: n.isActive,
      [Sa(e.exactActiveClass, s.linkExactActiveClass, "router-link-exact-active")]: n.isExactActive
    }));
    return () => {
      const o = t.default && Jp(t.default(n));
      return e.custom ? o : en("a", {
        "aria-current": n.isExactActive ? e.ariaCurrentValue : null,
        href: n.href,
        onClick: n.navigate,
        class: r.value
      }, o);
    };
  }
}), Mc = Yp;
function Qp(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function Xp(e, t) {
  for (const n in t) {
    const s = t[n], r = e[n];
    if (typeof s == "string") {
      if (s !== r) return !1;
    } else if (!Et(r) || r.length !== s.length || s.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function ka(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const Sa = (e, t, n) => e ?? t ?? n, eh = /* @__PURE__ */ Ae({
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
    const s = it(zo), r = ae(() => e.route || s.value), o = it(ga, 0), i = ae(() => {
      let c = x(o);
      const { matched: u } = r.value;
      let f;
      for (; (f = u[c]) && !f.components; ) c++;
      return c;
    }), a = ae(() => r.value.matched[i.value]);
    vs(ga, ae(() => i.value + 1)), vs(Np, a), vs(zo, r);
    const l = /* @__PURE__ */ se();
    return Fe(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, f], [d, h, y]) => {
      u && (u.instances[f] = c, h && h !== u && c && c === d && (u.leaveGuards.size || (u.leaveGuards = h.leaveGuards), u.updateGuards.size || (u.updateGuards = h.updateGuards))), c && u && (!h || !Yn(u, h) || !d) && (u.enterCallbacks[f] || []).forEach((v) => v(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, f = a.value, d = f && f.components[u];
      if (!d) return Ea(n.default, {
        Component: d,
        route: c
      });
      const h = f.props[u], y = h ? h === !0 ? c.params : typeof h == "function" ? h(c) : h : null, k = en(d, Re({}, y, t, {
        onVnodeUnmounted: (I) => {
          I.component.isUnmounted && (f.instances[u] = null);
        },
        ref: l
      }));
      return Ea(n.default, {
        Component: k,
        route: c
      }) || k;
    };
  }
});
function Ea(e, t) {
  if (!e) return null;
  const n = e(t);
  return n.length === 1 ? n[0] : n;
}
const Dc = eh;
function th(e) {
  const t = Hp(e.routes, e), n = e.parseQuery || Ip, s = e.stringifyQuery || ma, r = e.history, o = cs(), i = cs(), a = cs(), l = /* @__PURE__ */ Zn(on);
  let c = on;
  Hn && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = ro.bind(null, (S) => "" + S), f = ro.bind(null, pp), d = ro.bind(null, Is);
  function h(S, z) {
    let T, J;
    return Tc(S) ? (T = t.getRecordMatcher(S), J = z) : J = S, t.addRoute(J, T);
  }
  function y(S) {
    const z = t.getRecordMatcher(S);
    z && t.removeRoute(z);
  }
  function v() {
    return t.getRoutes().map((S) => S.record);
  }
  function k(S) {
    return !!t.getRecordMatcher(S);
  }
  function I(S, z) {
    if (z = Re({}, z || l.value), typeof S == "string") {
      const b = oo(n, S, z.path), _ = t.resolve({ path: b.path }, z), C = r.createHref(b.fullPath);
      return Re(b, _, {
        params: d(_.params),
        hash: Is(b.hash),
        redirectedFrom: void 0,
        href: C
      });
    }
    let T;
    if (S.path != null)
      T = Re({}, S, { path: oo(n, S.path, z.path).path });
    else {
      const b = Re({}, S.params);
      for (const _ in b) b[_] == null && delete b[_];
      T = Re({}, S, { params: f(b) }), z.params = f(z.params);
    }
    const J = t.resolve(T, z), p = S.hash || "";
    J.params = u(d(J.params));
    const m = gp(s, Re({}, S, {
      hash: up(p),
      path: J.path
    })), g = r.createHref(m);
    return Re({
      fullPath: m,
      hash: p,
      query: s === ma ? Pp(S.query) : S.query || {}
    }, J, {
      redirectedFrom: void 0,
      href: g
    });
  }
  function w(S) {
    return typeof S == "string" ? oo(n, S, l.value.path) : Re({}, S);
  }
  function N(S, z) {
    if (c !== S) return Qn(Ne.NAVIGATION_CANCELLED, {
      from: z,
      to: S
    });
  }
  function O(S) {
    return V(S);
  }
  function W(S) {
    return O(Re(w(S), { replace: !0 }));
  }
  function ge(S, z) {
    const T = S.matched[S.matched.length - 1];
    if (T && T.redirect) {
      const { redirect: J } = T;
      let p = typeof J == "function" ? J(S, z) : J;
      return typeof p == "string" && (p = p.includes("?") || p.includes("#") ? p = w(p) : { path: p }, p.params = {}), Re({
        query: S.query,
        hash: S.hash,
        params: p.path != null ? {} : S.params
      }, p);
    }
  }
  function V(S, z) {
    const T = c = I(S), J = l.value, p = S.state, m = S.force, g = S.replace === !0, b = ge(T, J);
    if (b) return V(Re(w(b), {
      state: typeof b == "object" ? Re({}, p, b.state) : p,
      force: m,
      replace: g
    }), z || T);
    const _ = T;
    _.redirectedFrom = z;
    let C;
    return !m && yp(s, J, T) && (C = Qn(Ne.NAVIGATION_DUPLICATED, {
      to: _,
      from: J
    }), lt(J, J, !0, !1)), (C ? Promise.resolve(C) : ce(_, J)).catch((R) => qt(R) ? qt(R, Ne.NAVIGATION_GUARD_REDIRECT) ? R : q(R) : le(R, _, J)).then((R) => {
      if (R) {
        if (qt(R, Ne.NAVIGATION_GUARD_REDIRECT))
          return V(Re({ replace: g }, w(R.to), {
            state: typeof R.to == "object" ? Re({}, p, R.to.state) : p,
            force: m
          }), z || _);
      } else R = Ie(_, J, !0, g, p);
      return Oe(_, J, R), R;
    });
  }
  function E(S, z) {
    const T = N(S, z);
    return T ? Promise.reject(T) : Promise.resolve();
  }
  function F(S) {
    const z = _t.values().next().value;
    return z && typeof z.runWithContext == "function" ? z.runWithContext(S) : S();
  }
  function ce(S, z) {
    let T;
    const [J, p, m] = Mp(S, z);
    T = ao(J.reverse(), "beforeRouteLeave", S, z);
    for (const b of J) b.leaveGuards.forEach((_) => {
      T.push(dn(_, S, z));
    });
    const g = E.bind(null, S, z);
    return T.push(g), _e(T).then(() => {
      T = [];
      for (const b of o.list()) T.push(dn(b, S, z));
      return T.push(g), _e(T);
    }).then(() => {
      T = ao(p, "beforeRouteUpdate", S, z);
      for (const b of p) b.updateGuards.forEach((_) => {
        T.push(dn(_, S, z));
      });
      return T.push(g), _e(T);
    }).then(() => {
      T = [];
      for (const b of m) if (b.beforeEnter) if (Et(b.beforeEnter)) for (const _ of b.beforeEnter) T.push(dn(_, S, z));
      else T.push(dn(b.beforeEnter, S, z));
      return T.push(g), _e(T);
    }).then(() => (S.matched.forEach((b) => b.enterCallbacks = {}), T = ao(m, "beforeRouteEnter", S, z, F), T.push(g), _e(T))).then(() => {
      T = [];
      for (const b of i.list()) T.push(dn(b, S, z));
      return T.push(g), _e(T);
    }).catch((b) => qt(b, Ne.NAVIGATION_CANCELLED) ? b : Promise.reject(b));
  }
  function Oe(S, z, T) {
    a.list().forEach((J) => F(() => J(S, z, T)));
  }
  function Ie(S, z, T, J, p) {
    const m = N(S, z);
    if (m) return m;
    const g = z === on, b = Hn ? history.state : {};
    T && (J || g ? r.replace(S.fullPath, Re({ scroll: g && b && b.scroll }, p)) : r.push(S.fullPath, p)), l.value = S, lt(S, z, T, g), q();
  }
  let $e;
  function et() {
    $e || ($e = r.listen((S, z, T) => {
      if (!Pe.listening) return;
      const J = I(S), p = ge(J, Pe.currentRoute.value);
      if (p) {
        V(Re(p, {
          replace: !0,
          force: !0
        }), J).catch(ws);
        return;
      }
      c = J;
      const m = l.value;
      Hn && Cp(ha(m.fullPath, T.delta), Sp()), ce(J, m).catch((g) => qt(g, Ne.NAVIGATION_ABORTED | Ne.NAVIGATION_CANCELLED) ? g : qt(g, Ne.NAVIGATION_GUARD_REDIRECT) ? (V(Re(w(g.to), { force: !0 }), J).then((b) => {
        qt(b, Ne.NAVIGATION_ABORTED | Ne.NAVIGATION_DUPLICATED) && !T.delta && T.type === Vo.pop && r.go(-1, !1);
      }).catch(ws), Promise.reject()) : (T.delta && r.go(-T.delta, !1), le(g, J, m))).then((g) => {
        g = g || Ie(J, m, !1), g && (T.delta && !qt(g, Ne.NAVIGATION_CANCELLED) ? r.go(-T.delta, !1) : T.type === Vo.pop && qt(g, Ne.NAVIGATION_ABORTED | Ne.NAVIGATION_DUPLICATED) && r.go(-1, !1)), Oe(J, m, g);
      }).catch(ws);
    }));
  }
  let tt = cs(), ie = cs(), Q;
  function le(S, z, T) {
    q(S);
    const J = ie.list();
    return J.length ? J.forEach((p) => p(S, z, T)) : console.error(S), Promise.reject(S);
  }
  function at() {
    return Q && l.value !== on ? Promise.resolve() : new Promise((S, z) => {
      tt.add([S, z]);
    });
  }
  function q(S) {
    return Q || (Q = !S, et(), tt.list().forEach(([z, T]) => S ? T(S) : z()), tt.reset()), S;
  }
  function lt(S, z, T, J) {
    const { scrollBehavior: p } = e;
    if (!Hn || !p) return Promise.resolve();
    const m = !T && Ap(ha(S.fullPath, 0)) || (J || !T) && history.state && history.state.scroll || null;
    return St().then(() => p(S, z, m)).then((g) => g && Ep(g)).catch((g) => le(g, S, z));
  }
  const We = (S) => r.go(S);
  let Wt;
  const _t = /* @__PURE__ */ new Set(), Pe = {
    currentRoute: l,
    listening: !0,
    addRoute: h,
    removeRoute: y,
    clearRoutes: t.clearRoutes,
    hasRoute: k,
    getRoutes: v,
    resolve: I,
    options: e,
    push: O,
    replace: W,
    go: We,
    back: () => We(-1),
    forward: () => We(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: ie.add,
    isReady: at,
    install(S) {
      S.component("RouterLink", Mc), S.component("RouterView", Dc), S.config.globalProperties.$router = Pe, Object.defineProperty(S.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => x(l)
      }), Hn && !Wt && l.value === on && (Wt = !0, O(r.location).catch((J) => {
      }));
      const z = {};
      for (const J in on) Object.defineProperty(z, J, {
        get: () => l.value[J],
        enumerable: !0
      });
      S.provide(zr, Pe), S.provide(vi, /* @__PURE__ */ Rl(z)), S.provide(zo, l);
      const T = S.unmount;
      _t.add(S), S.unmount = function() {
        _t.delete(S), _t.size < 1 && (c = on, $e && $e(), $e = null, l.value = on, Wt = !1, Q = !1), T();
      };
    }
  };
  function _e(S) {
    return S.reduce((z, T) => z.then(() => F(T)), Promise.resolve());
  }
  return Pe;
}
function nh() {
  return it(zr);
}
function sh(e) {
  return it(vi);
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
const Ca = (...e) => e.filter((t, n, s) => !!t && t.trim() !== "" && s.indexOf(t) === n).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function lo(e) {
  return e != null;
}
function rh(e, t = {}) {
  const n = t.attributeNames ?? {}, s = (d) => n[d] ?? d, r = e.size ?? e.width ?? En.width, o = e.size ?? e.height ?? En.height, i = e.aliases?.filter((d) => typeof d == "string" && d.trim() !== "").map((d) => `lucide-${d}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? Ca(...l) : Ca("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? En["stroke-width"]) * Number(e.size ?? e.width ?? En.width) / Number(t.size ?? t.width ?? En.width) : t.strokeWidth ?? En["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(En).reduce((d, [h, y]) => (d[s(h)] = y, d), {}),
      ..."color" in t && t.color && {
        [s("stroke")]: t.color
      },
      ..."size" in t && lo(t.size) && {
        [s("width")]: t.size,
        [s("height")]: t.size
      },
      ..."width" in t && lo(t.width) && {
        [s("width")]: t.width
      },
      ..."height" in t && lo(t.height) && {
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
      const [h, y, v] = d, k = t.nonScalingStroke ? { [s("vector-effect")]: "non-scaling-stroke", ...y } : y;
      return v ? [h, k, v] : [h, k];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const oh = (e) => {
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
const ih = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ah = /* @__PURE__ */ Symbol("lucide-icons");
function lh() {
  return it(ah, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ch = ({
  name: e,
  iconNode: t,
  "icon-node": n,
  icon: s = {
    name: e && ih(e),
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
    size: k,
    color: I,
    strokeWidth: w = 2,
    absoluteStrokeWidth: N = !1,
    nonScalingStroke: O = !1,
    class: W = ""
  } = lh(), ge = Zs(r) || Zs(o) || r === !0 || o === !0 || N === !0, V = Zs(i) || Zs(a) || i === !0 || a === !0 || O === !0;
  delete y.class;
  const E = v.default?.(), [, F, ce = []] = rh(s, {
    color: h ?? I,
    width: f ?? u ?? k,
    height: d ?? u ?? k,
    strokeWidth: l ?? c ?? w,
    absoluteStrokeWidth: ge,
    nonScalingStroke: V,
    className: W,
    hasA11yProp: E != null && E.length > 0 || oh(y),
    attributes: y
  });
  return en("svg", F, [
    ...ce.map(([Oe, Ie]) => en(Oe, Ie)),
    ...E ?? []
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
    ch,
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
const uh = {
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
}, Lc = xn(uh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const fh = {
  name: "info",
  size: 24,
  node: [
    ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
    ["path", { d: "M12 16v-4", key: "1dtifu" }],
    ["path", { d: "M12 8h.01", key: "e9boi3" }]
  ]
}, dh = xn(fh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ph = {
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
}, jc = xn(ph);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const hh = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, mh = xn(hh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const gh = {
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
}, yh = xn(gh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const vh = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, Fc = xn(vh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const bh = {
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
}, $c = xn(bh);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const _h = {
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
}, Vc = xn(_h);
function xh(e) {
  return Ir() ? (ei(e), !0) : !1;
}
const co = /* @__PURE__ */ new WeakMap(), wh = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const n = e[0], s = (t = Ct()) == null ? void 0 : t.proxy;
  if (s == null && !ui())
    throw new Error("injectLocal must be called in setup");
  return s && co.has(s) && n in co.get(s) ? co.get(s)[n] : it(...e);
}, kh = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const Sh = Object.prototype.toString, Eh = (e) => Sh.call(e) === "[object Object]";
function Aa(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function uo(e) {
  return Array.isArray(e) ? e : [e];
}
function Ch(e, t, n) {
  return Fe(
    e,
    t,
    {
      ...n,
      immediate: !0
    }
  );
}
const Bc = kh ? window : void 0;
function Ah(e) {
  var t;
  const n = Qe(e);
  return (t = n?.$el) != null ? t : n;
}
function Oh(...e) {
  const t = [], n = () => {
    t.forEach((a) => a()), t.length = 0;
  }, s = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = ae(() => {
    const a = uo(Qe(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = Ch(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => Ah(c))) != null ? l : [Bc].filter((c) => c != null),
        uo(Qe(r.value ? e[1] : e[0])),
        uo(x(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Qe(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (n(), !a?.length || !l?.length || !c?.length)
        return;
      const f = Eh(u) ? { ...u } : u;
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
  return xh(n), i;
}
// @__NO_SIDE_EFFECTS__
function Rh() {
  const e = /* @__PURE__ */ Zn(!1), t = Ct();
  return t && ss(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function Th(e) {
  const t = /* @__PURE__ */ Rh();
  return ae(() => (t.value, !!e()));
}
const Ih = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function Ph() {
  const e = ui() ? /* @__PURE__ */ wh(Ih, null) : null;
  return typeof e == "number" ? e : void 0;
}
function Nh(e, t = {}) {
  const { window: n = Bc, ssrWidth: s = /* @__PURE__ */ Ph() } = t, r = /* @__PURE__ */ Th(() => n && "matchMedia" in n && typeof n.matchMedia == "function"), o = /* @__PURE__ */ Zn(typeof s == "number"), i = /* @__PURE__ */ Zn(), a = /* @__PURE__ */ Zn(!1), l = (c) => {
    a.value = c.matches;
  };
  return Kn(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Qe(e).split(",");
      a.value = c.some((u) => {
        const f = u.includes("not all"), d = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), h = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let y = !!(d || h);
        return d && y && (y = s >= Aa(d[1])), h && y && (y = s <= Aa(h[1])), f ? !y : y;
      });
      return;
    }
    r.value && (i.value = n.matchMedia(Qe(e)), a.value = i.value.matches);
  }), Oh(i, "change", l, { passive: !0 }), ae(() => a.value);
}
const zc = "comfymodal", bi = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], Mh = {
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
function Uc(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const n = e.charAt(0) === "#" ? e.slice(1) : e;
  if (n === "") return t;
  const s = n.split("&"), r = s[0], o = r.indexOf("=");
  if (o === -1 || Gs(r.slice(0, o)) !== zc) return t;
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
function Wc(e) {
  if (!vn(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + zc + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function Oa(e, t) {
  if (!t || !vn(t.page)) return "none";
  if (!e || !vn(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const n = e.focus || null, s = t.focus || null;
  return n === s ? "none" : "replace";
}
function Dh(e, t) {
  if (e && vn(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const n = Uc(t);
  return n.matched && vn(n.page) ? { page: n.page, focus: n.focus } : { page: "playground", focus: null };
}
let Ra = 0;
function Lh() {
  return Ra += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${Ra}`;
}
const Hc = /* @__PURE__ */ rs("studio-operations", () => {
  const e = /* @__PURE__ */ se(/* @__PURE__ */ new Map()), t = ae(() => [...e.value.values()]), n = ae(
    () => t.value.filter((d) => d.status === "pending" || d.status === "running")
  );
  function s(d) {
    return e.value.get(d);
  }
  function r(d) {
    const h = Date.now(), y = Lh();
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
    y && e.value.set(d, { ...y, ...h });
  }
  function i(d, h, y) {
    const v = e.value.get(d);
    v && e.value.set(d, {
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
var me;
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
})(me || (me = {}));
var Ta;
(function(e) {
  e.mergeShapes = (t, n) => ({
    ...t,
    ...n
    // second overwrites first
  });
})(Ta || (Ta = {}));
const H = me.arrayToEnum([
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
}, P = me.arrayToEnum([
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
    return JSON.stringify(this.issues, me.jsonStringifyReplacer, 2);
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
      e.received === H.undefined ? n = "Required" : n = `Expected ${e.expected}, received ${e.received}`;
      break;
    case P.invalid_literal:
      n = `Invalid literal value, expected ${JSON.stringify(e.expected, me.jsonStringifyReplacer)}`;
      break;
    case P.unrecognized_keys:
      n = `Unrecognized key(s) in object: ${me.joinValues(e.keys, ", ")}`;
      break;
    case P.invalid_union:
      n = "Invalid input";
      break;
    case P.invalid_union_discriminator:
      n = `Invalid discriminator value. Expected ${me.joinValues(e.options)}`;
      break;
    case P.invalid_enum_value:
      n = `Invalid enum value. Expected ${me.joinValues(e.options)}, received '${e.received}'`;
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
      typeof e.validation == "object" ? "includes" in e.validation ? (n = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (n = `${n} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? n = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? n = `Invalid input: must end with "${e.validation.endsWith}"` : me.assertNever(e.validation) : e.validation !== "regex" ? n = `Invalid ${e.validation}` : n = "Invalid";
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
      n = t.defaultError, me.assertNever(e);
  }
  return { message: n };
};
let jh = Uo;
function Fh() {
  return jh;
}
const $h = (e) => {
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
  const n = Fh(), s = $h({
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
        return te;
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
        return te;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (s[o.value] = i.value);
    }
    return { status: t.value, value: s };
  }
}
const te = Object.freeze({
  status: "aborted"
}), hs = (e) => ({ status: "dirty", value: e }), vt = (e) => ({ status: "valid", value: e }), Ia = (e) => e.status === "aborted", Pa = (e) => e.status === "dirty", Xn = (e) => e.status === "valid", gr = (e) => typeof Promise < "u" && e instanceof Promise;
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
const Na = (e, t) => {
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
function oe(e) {
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
class pe {
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
    return Na(s, r);
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
    return Na(s, o);
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
      typeName: ne.ZodEffects,
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
    return $t.create(this);
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
      ...oe(this._def),
      schema: this,
      typeName: ne.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const n = typeof t == "function" ? t : () => t;
    return new Ho({
      ...oe(this._def),
      innerType: this,
      defaultValue: n,
      typeName: ne.ZodDefault
    });
  }
  brand() {
    return new lm({
      typeName: ne.ZodBranded,
      type: this,
      ...oe(this._def)
    });
  }
  catch(t) {
    const n = typeof t == "function" ? t : () => t;
    return new qo({
      ...oe(this._def),
      innerType: this,
      catchValue: n,
      typeName: ne.ZodCatch
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
const Vh = /^c[^\s-]{8,}$/i, Bh = /^[0-9a-z]+$/, zh = /^[0-9A-HJKMNP-TV-Z]{26}$/i, Uh = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, Wh = /^[a-z0-9_-]{21}$/i, Hh = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, qh = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, Zh = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, Gh = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let fo;
const Kh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, Jh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, Yh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, Qh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, Xh = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, em = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, qc = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", tm = new RegExp(`^${qc}$`);
function Zc(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const n = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${n}`;
}
function nm(e) {
  return new RegExp(`^${Zc(e)}$`);
}
function sm(e) {
  let t = `${qc}T${Zc(e)}`;
  const n = [];
  return n.push(e.local ? "Z?" : "Z"), e.offset && n.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${n.join("|")})`, new RegExp(`^${t}$`);
}
function rm(e, t) {
  return !!((t === "v4" || !t) && Kh.test(e) || (t === "v6" || !t) && Yh.test(e));
}
function om(e, t) {
  if (!Hh.test(e))
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
function im(e, t) {
  return !!((t === "v4" || !t) && Jh.test(e) || (t === "v6" || !t) && Qh.test(e));
}
class In extends pe {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== H.string) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_type,
        expected: H.string,
        received: o.parsedType
      }), te;
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
        Zh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "email",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "emoji")
        fo || (fo = new RegExp(Gh, "u")), fo.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "emoji",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "uuid")
        Uh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "uuid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "nanoid")
        Wh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "nanoid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "cuid")
        Vh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "cuid",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "cuid2")
        Bh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
          validation: "cuid2",
          code: P.invalid_string,
          message: o.message
        }), s.dirty());
      else if (o.kind === "ulid")
        zh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
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
      }), s.dirty()) : o.kind === "datetime" ? sm(o).test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: "datetime",
        message: o.message
      }), s.dirty()) : o.kind === "date" ? tm.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: "date",
        message: o.message
      }), s.dirty()) : o.kind === "time" ? nm(o).test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        code: P.invalid_string,
        validation: "time",
        message: o.message
      }), s.dirty()) : o.kind === "duration" ? qh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "duration",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "ip" ? rm(t.data, o.version) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "ip",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "jwt" ? om(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "jwt",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "cidr" ? im(t.data, o.version) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "cidr",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "base64" ? Xh.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "base64",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : o.kind === "base64url" ? em.test(t.data) || (r = this._getOrReturnCtx(t, r), $(r, {
        validation: "base64url",
        code: P.invalid_string,
        message: o.message
      }), s.dirty()) : me.assertNever(o);
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
  typeName: ne.ZodString,
  coerce: e?.coerce ?? !1,
  ...oe(e)
});
function am(e, t) {
  const n = (e.toString().split(".")[1] || "").length, s = (t.toString().split(".")[1] || "").length, r = n > s ? n : s, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class Ps extends pe {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== H.number) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_type,
        expected: H.number,
        received: o.parsedType
      }), te;
    }
    let s;
    const r = new ht();
    for (const o of this._def.checks)
      o.kind === "int" ? me.isInteger(t.data) || (s = this._getOrReturnCtx(t, s), $(s, {
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
      }), r.dirty()) : o.kind === "multipleOf" ? am(t.data, o.value) !== 0 && (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (s = this._getOrReturnCtx(t, s), $(s, {
        code: P.not_finite,
        message: o.message
      }), r.dirty()) : me.assertNever(o);
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && me.isInteger(t.value));
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
  typeName: ne.ZodNumber,
  coerce: e?.coerce || !1,
  ...oe(e)
});
class Ns extends pe {
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
      }), r.dirty()) : me.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const n = this._getOrReturnCtx(t);
    return $(n, {
      code: P.invalid_type,
      expected: H.bigint,
      received: n.parsedType
    }), te;
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
  typeName: ne.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...oe(e)
});
class Ma extends pe {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== H.boolean) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: H.boolean,
        received: s.parsedType
      }), te;
    }
    return vt(t.data);
  }
}
Ma.create = (e) => new Ma({
  typeName: ne.ZodBoolean,
  coerce: e?.coerce || !1,
  ...oe(e)
});
class yr extends pe {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== H.date) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_type,
        expected: H.date,
        received: o.parsedType
      }), te;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return $(o, {
        code: P.invalid_date
      }), te;
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
      }), s.dirty()) : me.assertNever(o);
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
  typeName: ne.ZodDate,
  ...oe(e)
});
class Da extends pe {
  _parse(t) {
    if (this._getType(t) !== H.symbol) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: H.symbol,
        received: s.parsedType
      }), te;
    }
    return vt(t.data);
  }
}
Da.create = (e) => new Da({
  typeName: ne.ZodSymbol,
  ...oe(e)
});
class La extends pe {
  _parse(t) {
    if (this._getType(t) !== H.undefined) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: H.undefined,
        received: s.parsedType
      }), te;
    }
    return vt(t.data);
  }
}
La.create = (e) => new La({
  typeName: ne.ZodUndefined,
  ...oe(e)
});
class ja extends pe {
  _parse(t) {
    if (this._getType(t) !== H.null) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: H.null,
        received: s.parsedType
      }), te;
    }
    return vt(t.data);
  }
}
ja.create = (e) => new ja({
  typeName: ne.ZodNull,
  ...oe(e)
});
class Fa extends pe {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return vt(t.data);
  }
}
Fa.create = (e) => new Fa({
  typeName: ne.ZodAny,
  ...oe(e)
});
class $a extends pe {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return vt(t.data);
  }
}
$a.create = (e) => new $a({
  typeName: ne.ZodUnknown,
  ...oe(e)
});
class _n extends pe {
  _parse(t) {
    const n = this._getOrReturnCtx(t);
    return $(n, {
      code: P.invalid_type,
      expected: H.never,
      received: n.parsedType
    }), te;
  }
}
_n.create = (e) => new _n({
  typeName: ne.ZodNever,
  ...oe(e)
});
class Va extends pe {
  _parse(t) {
    if (this._getType(t) !== H.undefined) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: H.void,
        received: s.parsedType
      }), te;
    }
    return vt(t.data);
  }
}
Va.create = (e) => new Va({
  typeName: ne.ZodVoid,
  ...oe(e)
});
class $t extends pe {
  _parse(t) {
    const { ctx: n, status: s } = this._processInputParams(t), r = this._def;
    if (n.parsedType !== H.array)
      return $(n, {
        code: P.invalid_type,
        expected: H.array,
        received: n.parsedType
      }), te;
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
    return new $t({
      ...this._def,
      minLength: { value: t, message: Z.toString(n) }
    });
  }
  max(t, n) {
    return new $t({
      ...this._def,
      maxLength: { value: t, message: Z.toString(n) }
    });
  }
  length(t, n) {
    return new $t({
      ...this._def,
      exactLength: { value: t, message: Z.toString(n) }
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
  typeName: ne.ZodArray,
  ...oe(t)
});
function qn(e) {
  if (e instanceof Ue) {
    const t = {};
    for (const n in e.shape) {
      const s = e.shape[n];
      t[n] = mn.create(qn(s));
    }
    return new Ue({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof $t ? new $t({
    ...e._def,
    type: qn(e.element)
  }) : e instanceof mn ? mn.create(qn(e.unwrap())) : e instanceof ns ? ns.create(qn(e.unwrap())) : e instanceof Dn ? Dn.create(e.items.map((t) => qn(t))) : e;
}
class Ue extends pe {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), n = me.objectKeys(t);
    return this._cached = { shape: t, keys: n }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== H.object) {
      const c = this._getOrReturnCtx(t);
      return $(c, {
        code: P.invalid_type,
        expected: H.object,
        received: c.parsedType
      }), te;
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
    return Z.errToObj, new Ue({
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
      typeName: ne.ZodObject
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
    return new Ue({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const n = {};
    for (const s of me.objectKeys(t))
      t[s] && this.shape[s] && (n[s] = this.shape[s]);
    return new Ue({
      ...this._def,
      shape: () => n
    });
  }
  omit(t) {
    const n = {};
    for (const s of me.objectKeys(this.shape))
      t[s] || (n[s] = this.shape[s]);
    return new Ue({
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
    for (const s of me.objectKeys(this.shape)) {
      const r = this.shape[s];
      t && !t[s] ? n[s] = r : n[s] = r.optional();
    }
    return new Ue({
      ...this._def,
      shape: () => n
    });
  }
  required(t) {
    const n = {};
    for (const s of me.objectKeys(this.shape))
      if (t && !t[s])
        n[s] = this.shape[s];
      else {
        let o = this.shape[s];
        for (; o instanceof mn; )
          o = o._def.innerType;
        n[s] = o;
      }
    return new Ue({
      ...this._def,
      shape: () => n
    });
  }
  keyof() {
    return Gc(me.objectKeys(this.shape));
  }
}
Ue.create = (e, t) => new Ue({
  shape: () => e,
  unknownKeys: "strip",
  catchall: _n.create(),
  typeName: ne.ZodObject,
  ...oe(t)
});
Ue.strictCreate = (e, t) => new Ue({
  shape: () => e,
  unknownKeys: "strict",
  catchall: _n.create(),
  typeName: ne.ZodObject,
  ...oe(t)
});
Ue.lazycreate = (e, t) => new Ue({
  shape: e,
  unknownKeys: "strip",
  catchall: _n.create(),
  typeName: ne.ZodObject,
  ...oe(t)
});
class vr extends pe {
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
      }), te;
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
      }), te;
    }
  }
  get options() {
    return this._def.options;
  }
}
vr.create = (e, t) => new vr({
  options: e,
  typeName: ne.ZodUnion,
  ...oe(t)
});
function Wo(e, t) {
  const n = pn(e), s = pn(t);
  if (e === t)
    return { valid: !0, data: e };
  if (n === H.object && s === H.object) {
    const r = me.objectKeys(t), o = me.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = Wo(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (n === H.array && s === H.array) {
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
  } else return n === H.date && s === H.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class br extends pe {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t), r = (o, i) => {
      if (Ia(o) || Ia(i))
        return te;
      const a = Wo(o.value, i.value);
      return a.valid ? ((Pa(o) || Pa(i)) && n.dirty(), { status: n.value, value: a.data }) : ($(s, {
        code: P.invalid_intersection_types
      }), te);
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
  typeName: ne.ZodIntersection,
  ...oe(n)
});
class Dn extends pe {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.parsedType !== H.array)
      return $(s, {
        code: P.invalid_type,
        expected: H.array,
        received: s.parsedType
      }), te;
    if (s.data.length < this._def.items.length)
      return $(s, {
        code: P.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), te;
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
    typeName: ne.ZodTuple,
    rest: null,
    ...oe(t)
  });
};
class Ba extends pe {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.parsedType !== H.map)
      return $(s, {
        code: P.invalid_type,
        expected: H.map,
        received: s.parsedType
      }), te;
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
            return te;
          (c.status === "dirty" || u.status === "dirty") && n.dirty(), a.set(c.value, u.value);
        }
        return { status: n.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return te;
        (c.status === "dirty" || u.status === "dirty") && n.dirty(), a.set(c.value, u.value);
      }
      return { status: n.value, value: a };
    }
  }
}
Ba.create = (e, t, n) => new Ba({
  valueType: t,
  keyType: e,
  typeName: ne.ZodMap,
  ...oe(n)
});
class Ms extends pe {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.parsedType !== H.set)
      return $(s, {
        code: P.invalid_type,
        expected: H.set,
        received: s.parsedType
      }), te;
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
          return te;
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
  typeName: ne.ZodSet,
  ...oe(t)
});
class za extends pe {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: n } = this._processInputParams(t);
    return this._def.getter()._parse({ data: n.data, path: n.path, parent: n });
  }
}
za.create = (e, t) => new za({
  getter: e,
  typeName: ne.ZodLazy,
  ...oe(t)
});
class Ua extends pe {
  _parse(t) {
    if (t.data !== this._def.value) {
      const n = this._getOrReturnCtx(t);
      return $(n, {
        received: n.data,
        code: P.invalid_literal,
        expected: this._def.value
      }), te;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Ua.create = (e, t) => new Ua({
  value: e,
  typeName: ne.ZodLiteral,
  ...oe(t)
});
function Gc(e, t) {
  return new es({
    values: e,
    typeName: ne.ZodEnum,
    ...oe(t)
  });
}
class es extends pe {
  _parse(t) {
    if (typeof t.data != "string") {
      const n = this._getOrReturnCtx(t), s = this._def.values;
      return $(n, {
        expected: me.joinValues(s),
        received: n.parsedType,
        code: P.invalid_type
      }), te;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const n = this._getOrReturnCtx(t), s = this._def.values;
      return $(n, {
        received: n.data,
        code: P.invalid_enum_value,
        options: s
      }), te;
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
es.create = Gc;
class Wa extends pe {
  _parse(t) {
    const n = me.getValidEnumValues(this._def.values), s = this._getOrReturnCtx(t);
    if (s.parsedType !== H.string && s.parsedType !== H.number) {
      const r = me.objectValues(n);
      return $(s, {
        expected: me.joinValues(r),
        received: s.parsedType,
        code: P.invalid_type
      }), te;
    }
    if (this._cache || (this._cache = new Set(me.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = me.objectValues(n);
      return $(s, {
        received: s.data,
        code: P.invalid_enum_value,
        options: r
      }), te;
    }
    return vt(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
Wa.create = (e, t) => new Wa({
  values: e,
  typeName: ne.ZodNativeEnum,
  ...oe(t)
});
class _r extends pe {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: n } = this._processInputParams(t);
    if (n.parsedType !== H.promise && n.common.async === !1)
      return $(n, {
        code: P.invalid_type,
        expected: H.promise,
        received: n.parsedType
      }), te;
    const s = n.parsedType === H.promise ? n.data : Promise.resolve(n.data);
    return vt(s.then((r) => this._def.type.parseAsync(r, {
      path: n.path,
      errorMap: n.common.contextualErrorMap
    })));
  }
}
_r.create = (e, t) => new _r({
  type: e,
  typeName: ne.ZodPromise,
  ...oe(t)
});
class ts extends pe {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === ne.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
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
            return te;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: s.path,
            parent: s
          });
          return l.status === "aborted" ? te : l.status === "dirty" || n.value === "dirty" ? hs(l.value) : l;
        });
      {
        if (n.value === "aborted")
          return te;
        const a = this._def.schema._parseSync({
          data: i,
          path: s.path,
          parent: s
        });
        return a.status === "aborted" ? te : a.status === "dirty" || n.value === "dirty" ? hs(a.value) : a;
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
        return a.status === "aborted" ? te : (a.status === "dirty" && n.dirty(), i(a.value), { status: n.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: s.data, path: s.path, parent: s }).then((a) => a.status === "aborted" ? te : (a.status === "dirty" && n.dirty(), i(a.value).then(() => ({ status: n.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (s.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: s.data,
          path: s.path,
          parent: s
        });
        if (!Xn(i))
          return te;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: n.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: s.data, path: s.path, parent: s }).then((i) => Xn(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: n.value,
          value: a
        })) : te);
    me.assertNever(r);
  }
}
ts.create = (e, t, n) => new ts({
  schema: e,
  typeName: ne.ZodEffects,
  effect: t,
  ...oe(n)
});
ts.createWithPreprocess = (e, t, n) => new ts({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: ne.ZodEffects,
  ...oe(n)
});
class mn extends pe {
  _parse(t) {
    return this._getType(t) === H.undefined ? vt(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
mn.create = (e, t) => new mn({
  innerType: e,
  typeName: ne.ZodOptional,
  ...oe(t)
});
class ns extends pe {
  _parse(t) {
    return this._getType(t) === H.null ? vt(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
ns.create = (e, t) => new ns({
  innerType: e,
  typeName: ne.ZodNullable,
  ...oe(t)
});
class Ho extends pe {
  _parse(t) {
    const { ctx: n } = this._processInputParams(t);
    let s = n.data;
    return n.parsedType === H.undefined && (s = this._def.defaultValue()), this._def.innerType._parse({
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
  typeName: ne.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...oe(t)
});
class qo extends pe {
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
  typeName: ne.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...oe(t)
});
class Ha extends pe {
  _parse(t) {
    if (this._getType(t) !== H.nan) {
      const s = this._getOrReturnCtx(t);
      return $(s, {
        code: P.invalid_type,
        expected: H.nan,
        received: s.parsedType
      }), te;
    }
    return { status: "valid", value: t.data };
  }
}
Ha.create = (e) => new Ha({
  typeName: ne.ZodNaN,
  ...oe(e)
});
class lm extends pe {
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
class _i extends pe {
  _parse(t) {
    const { status: n, ctx: s } = this._processInputParams(t);
    if (s.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: s.data,
          path: s.path,
          parent: s
        });
        return o.status === "aborted" ? te : o.status === "dirty" ? (n.dirty(), hs(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? te : r.status === "dirty" ? (n.dirty(), {
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
      typeName: ne.ZodPipeline
    });
  }
}
class Zo extends pe {
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
  typeName: ne.ZodReadonly,
  ...oe(t)
});
var ne;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(ne || (ne = {}));
_n.create;
$t.create;
vr.create;
br.create;
Dn.create;
const cm = es.create;
_r.create;
mn.create;
ns.create;
const um = "comfymodal.studio.vue.";
function fm() {
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
function dm() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return fm();
}
function pm(e, t, n, s) {
  const r = um + e, o = dm();
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
const hm = cm(["comfortable", "compact"]), po = pm(
  "shell.density",
  "comfortable",
  hm
), Kc = /* @__PURE__ */ rs("studio-settings", () => {
  const e = /* @__PURE__ */ se("studio"), t = /* @__PURE__ */ se(po.read());
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
function Jc(e) {
  var t, n, s = "";
  if (typeof e == "string" || typeof e == "number") s += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (n = Jc(e[t])) && (s && (s += " "), s += n);
  } else for (n in e) e[n] && (s && (s += " "), s += n);
  return s;
}
function Yc() {
  for (var e, t, n = 0, s = "", r = arguments.length; n < r; n++) (e = arguments[n]) && (t = Jc(e)) && (s && (s += " "), s += t);
  return s;
}
const mm = (e, t) => {
  const n = new Array(e.length + t.length);
  for (let s = 0; s < e.length; s++)
    n[s] = e[s];
  for (let s = 0; s < t.length; s++)
    n[e.length + s] = t[s];
  return n;
}, gm = (e, t) => ({
  classGroupId: e,
  validator: t
}), Qc = (e = /* @__PURE__ */ new Map(), t = null, n) => ({
  nextPart: e,
  validators: t,
  classGroupId: n
}), xr = "-", qa = [], ym = "arbitrary..", vm = (e) => {
  const t = _m(e), {
    conflictingClassGroups: n,
    conflictingClassGroupModifiers: s
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return bm(i);
      const a = i.split(xr), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return Xc(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = s[i], c = n[i];
        return l ? c ? mm(c, l) : l : c || qa;
      }
      return n[i] || qa;
    }
  };
}, Xc = (e, t, n) => {
  if (e.length - t === 0)
    return n.classGroupId;
  const r = e[t], o = n.nextPart.get(r);
  if (o) {
    const c = Xc(e, t + 1, o);
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
}, bm = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), n = t.indexOf(":"), s = t.slice(0, n);
  return s ? ym + s : void 0;
})(), _m = (e) => {
  const {
    theme: t,
    classGroups: n
  } = e;
  return xm(n, t);
}, xm = (e, t) => {
  const n = Qc();
  for (const s in e) {
    const r = e[s];
    xi(r, n, s, t);
  }
  return n;
}, xi = (e, t, n, s) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    wm(i, t, n, s);
  }
}, wm = (e, t, n, s) => {
  if (typeof e == "string") {
    km(e, t, n);
    return;
  }
  if (typeof e == "function") {
    Sm(e, t, n, s);
    return;
  }
  Em(e, t, n, s);
}, km = (e, t, n) => {
  const s = e === "" ? t : eu(t, e);
  s.classGroupId = n;
}, Sm = (e, t, n, s) => {
  if (Cm(e)) {
    xi(e(s), t, n, s);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(gm(n, e));
}, Em = (e, t, n, s) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    xi(l, eu(t, a), n, s);
  }
}, eu = (e, t) => {
  let n = e;
  const s = t.split(xr), r = s.length;
  for (let o = 0; o < r; o++) {
    const i = s[o];
    let a = n.nextPart.get(i);
    a || (a = Qc(), n.nextPart.set(i, a)), n = a;
  }
  return n;
}, Cm = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Am = (e) => {
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
}, Go = "!", Za = ":", Om = [], Ga = (e, t, n, s, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: n,
  maybePostfixModifierPosition: s,
  isExternal: r
}), Rm = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: n
  } = e;
  let s = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let v = 0; v < u; v++) {
      const k = r[v];
      if (i === 0 && a === 0) {
        if (k === Za) {
          o.push(r.slice(l, v)), l = v + 1;
          continue;
        }
        if (k === "/") {
          c = v;
          continue;
        }
      }
      k === "[" ? i++ : k === "]" ? i-- : k === "(" ? a++ : k === ")" && a--;
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
    return Ga(o, h, d, y);
  };
  if (t) {
    const r = t + Za, o = s;
    s = (i) => i.startsWith(r) ? o(i.slice(r.length)) : Ga(Om, !1, i, void 0, !0);
  }
  if (n) {
    const r = s;
    s = (o) => n({
      className: o,
      parseClassName: r
    });
  }
  return s;
}, Tm = (e) => {
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
}, Im = (e) => ({
  cache: Am(e.cacheSize),
  parseClassName: Rm(e),
  sortModifiers: Tm(e),
  postfixLookupClassGroupIds: Pm(e),
  ...vm(e)
}), Pm = (e) => {
  const t = /* @__PURE__ */ Object.create(null), n = e.postfixLookupClassGroups;
  if (n)
    for (let s = 0; s < n.length; s++)
      t[n[s]] = !0;
  return t;
}, Nm = /\s+/, Mm = (e, t) => {
  const {
    parseClassName: n,
    getClassGroupId: s,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Nm);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const f = l[u], {
      isExternal: d,
      modifiers: h,
      hasImportantModifier: y,
      baseClassName: v,
      maybePostfixModifierPosition: k
    } = n(f);
    if (d) {
      c = f + (c.length > 0 ? " " + c : c);
      continue;
    }
    let I = !!k, w;
    if (I) {
      const V = v.substring(0, k);
      w = s(V);
      const E = w && i[w] ? s(v) : void 0;
      E && E !== w && (w = E, I = !1);
    } else
      w = s(v);
    if (!w) {
      if (!I) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (w = s(v), !w) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      I = !1;
    }
    const N = h.length === 0 ? "" : h.length === 1 ? h[0] : o(h).join(":"), O = y ? N + Go : N, W = O + w;
    if (a.indexOf(W) > -1)
      continue;
    a.push(W);
    const ge = r(w, I);
    for (let V = 0; V < ge.length; ++V) {
      const E = ge[V];
      a.push(O + E);
    }
    c = f + (c.length > 0 ? " " + c : c);
  }
  return c;
}, Dm = (...e) => {
  let t = 0, n, s, r = "";
  for (; t < e.length; )
    (n = e[t++]) && (s = tu(n)) && (r && (r += " "), r += s);
  return r;
}, tu = (e) => {
  if (typeof e == "string")
    return e;
  let t, n = "";
  for (let s = 0; s < e.length; s++)
    e[s] && (t = tu(e[s])) && (n && (n += " "), n += t);
  return n;
}, Lm = (e, ...t) => {
  let n, s, r, o;
  const i = (l) => {
    const c = t.reduce((u, f) => f(u), e());
    return n = Im(c), s = n.cache.get, r = n.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = s(l);
    if (c)
      return c;
    const u = Mm(l, n);
    return r(l, u), u;
  };
  return o = i, (...l) => o(Dm(...l));
}, jm = [], Ve = (e) => {
  const t = (n) => n[e] || jm;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, nu = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, su = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Fm = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, $m = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, Vm = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Bm = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, zm = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, Um = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, an = (e) => Fm.test(e), re = (e) => !!e && !Number.isNaN(Number(e)), It = (e) => !!e && Number.isInteger(Number(e)), ho = (e) => e.endsWith("%") && re(e.slice(0, -1)), Zt = (e) => $m.test(e), ru = () => !0, Wm = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  Vm.test(e) && !Bm.test(e)
), wi = () => !1, Hm = (e) => zm.test(e), qm = (e) => Um.test(e), Zm = (e) => !B(e) && !U(e), Gm = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), Km = (e) => wn(e, au, wi), B = (e) => nu.test(e), Cn = (e) => wn(e, lu, Wm), Ka = (e) => wn(e, sg, re), Jm = (e) => wn(e, uu, ru), Ym = (e) => wn(e, cu, wi), Ja = (e) => wn(e, ou, wi), Qm = (e) => wn(e, iu, qm), Ks = (e) => wn(e, fu, Hm), U = (e) => su.test(e), us = (e) => Fn(e, lu), Xm = (e) => Fn(e, cu), Ya = (e) => Fn(e, ou), eg = (e) => Fn(e, au), tg = (e) => Fn(e, iu), Js = (e) => Fn(e, fu, !0), ng = (e) => Fn(e, uu, !0), wn = (e, t, n) => {
  const s = nu.exec(e);
  return s ? s[1] ? t(s[1]) : n(s[2]) : !1;
}, Fn = (e, t, n = !1) => {
  const s = su.exec(e);
  return s ? s[1] ? t(s[1]) : n : !1;
}, ou = (e) => e === "position" || e === "percentage", iu = (e) => e === "image" || e === "url", au = (e) => e === "length" || e === "size" || e === "bg-size", lu = (e) => e === "length", sg = (e) => e === "number", cu = (e) => e === "family-name", uu = (e) => e === "number" || e === "weight", fu = (e) => e === "shadow", rg = () => {
  const e = Ve("color"), t = Ve("font"), n = Ve("text"), s = Ve("font-weight"), r = Ve("tracking"), o = Ve("leading"), i = Ve("breakpoint"), a = Ve("container"), l = Ve("spacing"), c = Ve("radius"), u = Ve("shadow"), f = Ve("inset-shadow"), d = Ve("text-shadow"), h = Ve("drop-shadow"), y = Ve("blur"), v = Ve("perspective"), k = Ve("aspect"), I = Ve("ease"), w = Ve("animate"), N = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], O = () => [
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
  ], W = () => [...O(), U, B], ge = () => ["auto", "hidden", "clip", "visible", "scroll"], V = () => ["auto", "contain", "none"], E = () => [U, B, l], F = () => [an, "full", "auto", ...E()], ce = () => [It, "none", "subgrid", U, B], Oe = () => ["auto", {
    span: ["full", It, U, B]
  }, It, U, B], Ie = () => [It, "auto", U, B], $e = () => ["auto", "min", "max", "fr", U, B], et = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], tt = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], ie = () => ["auto", ...E()], Q = () => [an, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...E()], le = () => [a, an, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...E()], at = () => [an, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...E()], q = () => [e, U, B], lt = () => [...O(), Ya, Ja, {
    position: [U, B]
  }], We = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], Wt = () => ["auto", "cover", "contain", eg, Km, {
    size: [U, B]
  }], _t = () => [ho, us, Cn], Pe = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    U,
    B
  ], _e = () => ["", re, us, Cn], S = () => ["solid", "dashed", "dotted", "double"], z = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], T = () => [re, ho, Ya, Ja], J = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    y,
    U,
    B
  ], p = () => ["none", re, U, B], m = () => ["none", re, U, B], g = () => [re, U, B], b = () => [an, "full", ...E()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [Zt],
      breakpoint: [Zt],
      color: [ru],
      container: [Zt],
      "drop-shadow": [Zt],
      ease: ["in", "out", "in-out"],
      font: [Zm],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [Zt],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [Zt],
      shadow: [Zt],
      spacing: ["px", re],
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
        aspect: ["auto", "square", an, B, U, k]
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
        "@container": ["", "normal", "size", U, B]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [Gm],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [re, "auto", B, U, a]
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
        object: W()
      }],
      /**
       * Overflow
       * @see https://tailwindcss.com/docs/overflow
       */
      overflow: [{
        overflow: ge()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": ge()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": ge()
      }],
      /**
       * Overscroll Behavior
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      overscroll: [{
        overscroll: V()
      }],
      /**
       * Overscroll Behavior X
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-x": [{
        "overscroll-x": V()
      }],
      /**
       * Overscroll Behavior Y
       * @see https://tailwindcss.com/docs/overscroll-behavior
       */
      "overscroll-y": [{
        "overscroll-y": V()
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
        inset: F()
      }],
      /**
       * Inset Inline
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-x": [{
        "inset-x": F()
      }],
      /**
       * Inset Block
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-y": [{
        "inset-y": F()
      }],
      /**
       * Inset Inline Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-s` in next major release
       */
      start: [{
        "inset-s": F(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        start: F()
      }],
      /**
       * Inset Inline End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       * @todo class group will be renamed to `inset-e` in next major release
       */
      end: [{
        "inset-e": F(),
        /**
         * @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
         * @see https://github.com/tailwindlabs/tailwindcss/pull/19613
         */
        end: F()
      }],
      /**
       * Inset Block Start
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-bs": [{
        "inset-bs": F()
      }],
      /**
       * Inset Block End
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      "inset-be": [{
        "inset-be": F()
      }],
      /**
       * Top
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      top: [{
        top: F()
      }],
      /**
       * Right
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      right: [{
        right: F()
      }],
      /**
       * Bottom
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      bottom: [{
        bottom: F()
      }],
      /**
       * Left
       * @see https://tailwindcss.com/docs/top-right-bottom-left
       */
      left: [{
        left: F()
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
        z: [It, "auto", U, B]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [an, "full", "auto", a, ...E()]
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
        flex: [re, an, "auto", "initial", "none", B]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", re, U, B]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", re, U, B]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [It, "first", "last", "none", U, B]
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
        col: Oe()
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
        "grid-rows": ce()
      }],
      /**
       * Grid Row Start / End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start-end": [{
        row: Oe()
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
        gap: E()
      }],
      /**
       * Gap X
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-x": [{
        "gap-x": E()
      }],
      /**
       * Gap Y
       * @see https://tailwindcss.com/docs/gap
       */
      "gap-y": [{
        "gap-y": E()
      }],
      /**
       * Justify Content
       * @see https://tailwindcss.com/docs/justify-content
       */
      "justify-content": [{
        justify: [...et(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...tt(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...tt()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...et()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...tt(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...tt(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": et()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...tt(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...tt()]
      }],
      // Spacing
      /**
       * Padding
       * @see https://tailwindcss.com/docs/padding
       */
      p: [{
        p: E()
      }],
      /**
       * Padding Inline
       * @see https://tailwindcss.com/docs/padding
       */
      px: [{
        px: E()
      }],
      /**
       * Padding Block
       * @see https://tailwindcss.com/docs/padding
       */
      py: [{
        py: E()
      }],
      /**
       * Padding Inline Start
       * @see https://tailwindcss.com/docs/padding
       */
      ps: [{
        ps: E()
      }],
      /**
       * Padding Inline End
       * @see https://tailwindcss.com/docs/padding
       */
      pe: [{
        pe: E()
      }],
      /**
       * Padding Block Start
       * @see https://tailwindcss.com/docs/padding
       */
      pbs: [{
        pbs: E()
      }],
      /**
       * Padding Block End
       * @see https://tailwindcss.com/docs/padding
       */
      pbe: [{
        pbe: E()
      }],
      /**
       * Padding Top
       * @see https://tailwindcss.com/docs/padding
       */
      pt: [{
        pt: E()
      }],
      /**
       * Padding Right
       * @see https://tailwindcss.com/docs/padding
       */
      pr: [{
        pr: E()
      }],
      /**
       * Padding Bottom
       * @see https://tailwindcss.com/docs/padding
       */
      pb: [{
        pb: E()
      }],
      /**
       * Padding Left
       * @see https://tailwindcss.com/docs/padding
       */
      pl: [{
        pl: E()
      }],
      /**
       * Margin
       * @see https://tailwindcss.com/docs/margin
       */
      m: [{
        m: ie()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: ie()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: ie()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: ie()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: ie()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: ie()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: ie()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: ie()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: ie()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: ie()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: ie()
      }],
      /**
       * Space Between X
       * @see https://tailwindcss.com/docs/margin#adding-space-between-children
       */
      "space-x": [{
        "space-x": E()
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
        "space-y": E()
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
        size: Q()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ...le()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...le()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...le()]
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
        w: [a, "screen", ...Q()]
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
          ...Q()
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
          ...Q()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...Q()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...Q()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...Q()]
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
        font: [s, ng, Jm]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", ho, B]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [Xm, Ym, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [B]
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
        tracking: [r, U, B]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [re, "none", U, Ka]
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
          ...E()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", U, B]
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
        list: ["disc", "decimal", "none", U, B]
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
        decoration: [...S(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [re, "from-font", "auto", U, Cn]
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
        "underline-offset": [re, "auto", U, B]
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
        indent: E()
      }],
      /**
       * Tab Size
       * @see https://tailwindcss.com/docs/tab-size
       */
      "tab-size": [{
        tab: [It, U, B]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", U, B]
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
        content: ["none", U, B]
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
        bg: We()
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
          }, It, U, B],
          radial: ["", U, B],
          conic: ["", It, U, B]
        }, tg, Qm]
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
        rounded: Pe()
      }],
      /**
       * Border Radius Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-s": [{
        "rounded-s": Pe()
      }],
      /**
       * Border Radius End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-e": [{
        "rounded-e": Pe()
      }],
      /**
       * Border Radius Top
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-t": [{
        "rounded-t": Pe()
      }],
      /**
       * Border Radius Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-r": [{
        "rounded-r": Pe()
      }],
      /**
       * Border Radius Bottom
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-b": [{
        "rounded-b": Pe()
      }],
      /**
       * Border Radius Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-l": [{
        "rounded-l": Pe()
      }],
      /**
       * Border Radius Start Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ss": [{
        "rounded-ss": Pe()
      }],
      /**
       * Border Radius Start End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-se": [{
        "rounded-se": Pe()
      }],
      /**
       * Border Radius End End
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-ee": [{
        "rounded-ee": Pe()
      }],
      /**
       * Border Radius End Start
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-es": [{
        "rounded-es": Pe()
      }],
      /**
       * Border Radius Top Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tl": [{
        "rounded-tl": Pe()
      }],
      /**
       * Border Radius Top Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-tr": [{
        "rounded-tr": Pe()
      }],
      /**
       * Border Radius Bottom Right
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-br": [{
        "rounded-br": Pe()
      }],
      /**
       * Border Radius Bottom Left
       * @see https://tailwindcss.com/docs/border-radius
       */
      "rounded-bl": [{
        "rounded-bl": Pe()
      }],
      /**
       * Border Width
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w": [{
        border: _e()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": _e()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": _e()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": _e()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": _e()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": _e()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": _e()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": _e()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": _e()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": _e()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": _e()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": _e()
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
        "divide-y": _e()
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
        outline: [...S(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [re, U, B]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", re, us, Cn]
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
        ring: _e()
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
        "ring-offset": [re, Cn]
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
        "inset-ring": _e()
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
        opacity: [re, U, B]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...z(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": z()
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
        "mask-linear": [re]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": T()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": T()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": q()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": q()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": T()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": T()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": q()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": q()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": T()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": T()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": q()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": q()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": T()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": T()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": q()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": q()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": T()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": T()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": q()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": q()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": T()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": T()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": q()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": q()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": T()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": T()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": q()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": q()
      }],
      "mask-image-radial": [{
        "mask-radial": [U, B]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": T()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": T()
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
        "mask-conic": [re]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": T()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": T()
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
        mask: We()
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
        mask: ["none", U, B]
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
          B
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
        brightness: [re, U, B]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [re, U, B]
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
        grayscale: ["", re, U, B]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [re, U, B]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", re, U, B]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [re, U, B]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", re, U, B]
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
          B
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
        "backdrop-brightness": [re, U, B]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [re, U, B]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", re, U, B]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [re, U, B]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", re, U, B]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [re, U, B]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [re, U, B]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", re, U, B]
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
        "border-spacing": E()
      }],
      /**
       * Border Spacing X
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-x": [{
        "border-spacing-x": E()
      }],
      /**
       * Border Spacing Y
       * @see https://tailwindcss.com/docs/border-spacing
       */
      "border-spacing-y": [{
        "border-spacing-y": E()
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", U, B]
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
        duration: [re, "initial", U, B]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", I, U, B]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [re, U, B]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", w, U, B]
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
        perspective: [v, U, B]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": W()
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
        transform: [U, B, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: W()
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
        zoom: [It, U, B]
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", U, B]
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
        "scroll-m": E()
      }],
      /**
       * Scroll Margin Inline
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mx": [{
        "scroll-mx": E()
      }],
      /**
       * Scroll Margin Block
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-my": [{
        "scroll-my": E()
      }],
      /**
       * Scroll Margin Inline Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ms": [{
        "scroll-ms": E()
      }],
      /**
       * Scroll Margin Inline End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-me": [{
        "scroll-me": E()
      }],
      /**
       * Scroll Margin Block Start
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbs": [{
        "scroll-mbs": E()
      }],
      /**
       * Scroll Margin Block End
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mbe": [{
        "scroll-mbe": E()
      }],
      /**
       * Scroll Margin Top
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mt": [{
        "scroll-mt": E()
      }],
      /**
       * Scroll Margin Right
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mr": [{
        "scroll-mr": E()
      }],
      /**
       * Scroll Margin Bottom
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-mb": [{
        "scroll-mb": E()
      }],
      /**
       * Scroll Margin Left
       * @see https://tailwindcss.com/docs/scroll-margin
       */
      "scroll-ml": [{
        "scroll-ml": E()
      }],
      /**
       * Scroll Padding
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-p": [{
        "scroll-p": E()
      }],
      /**
       * Scroll Padding Inline
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-px": [{
        "scroll-px": E()
      }],
      /**
       * Scroll Padding Block
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-py": [{
        "scroll-py": E()
      }],
      /**
       * Scroll Padding Inline Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-ps": [{
        "scroll-ps": E()
      }],
      /**
       * Scroll Padding Inline End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pe": [{
        "scroll-pe": E()
      }],
      /**
       * Scroll Padding Block Start
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbs": [{
        "scroll-pbs": E()
      }],
      /**
       * Scroll Padding Block End
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pbe": [{
        "scroll-pbe": E()
      }],
      /**
       * Scroll Padding Top
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pt": [{
        "scroll-pt": E()
      }],
      /**
       * Scroll Padding Right
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pr": [{
        "scroll-pr": E()
      }],
      /**
       * Scroll Padding Bottom
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pb": [{
        "scroll-pb": E()
      }],
      /**
       * Scroll Padding Left
       * @see https://tailwindcss.com/docs/scroll-padding
       */
      "scroll-pl": [{
        "scroll-pl": E()
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
        "will-change": ["auto", "scroll", "contents", "transform", U, B]
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
        stroke: [re, us, Cn, Ka]
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
}, og = /* @__PURE__ */ Lm(rg);
function Ur(...e) {
  return og(Yc(e));
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
}, fg = { "data-testid": "vue-status-route" }, dg = { "data-testid": "vue-status-ops" }, pg = { "data-testid": "vue-status-density" }, hg = { class: "cmst:flex cmst:items-center cmst:gap-1" }, mg = /* @__PURE__ */ Ae({
  __name: "StudioApp",
  setup(e) {
    const t = sh(), n = Hc(), s = Kc(), r = Nh("(min-width: 768px)"), o = {
      playground: Lc,
      history: Fc,
      workflows: jc,
      backend: $c,
      settings: Vc
    }, i = ae(() => String(t.name ?? "playground"));
    function a(l) {
      const c = i.value === l;
      return Ur(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        c ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (l, c) => (de(), mt("div", ig, [
      L("header", ag, [
        c[0] || (c[0] = L("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          ve(" Modal Studio "),
          L("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        L("nav", lg, [
          (de(!0), mt(qe, null, ql(x(bi), (u) => (de(), Le(x(Mc), {
            key: u,
            to: { name: u },
            class: Se(a(u)),
            "data-testid": `vue-nav-${u}`
          }, {
            default: Ce(() => [
              (de(), Le(Nf(o[u]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              ve(" " + Me(x(Mh)[u]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      L("main", cg, [
        fe(x(Dc))
      ]),
      L("footer", ug, [
        L("span", null, [
          c[1] || (c[1] = ve("route: ", -1)),
          L("strong", fg, Me(i.value), 1)
        ]),
        L("span", null, [
          c[2] || (c[2] = ve(" operations: ", -1)),
          L("strong", dg, Me(x(n).active.length) + " active", 1),
          ve(" / " + Me(x(n).all.length) + " total ", 1)
        ]),
        L("span", null, [
          c[3] || (c[3] = ve(" density: ", -1)),
          L("strong", pg, Me(x(s).density), 1)
        ]),
        L("span", hg, [
          fe(x(mh), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          c[4] || (c[4] = ve(" viewport: ", -1)),
          L("strong", null, Me(x(r) ? "wide" : "narrow"), 1),
          c[5] || (c[5] = ve(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), gg = "/", du = { page: "playground", focus: null };
function Ys(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function mo(e) {
  const [t, n] = e.split("?"), s = t.replace(/^\//, ""), r = vn(s) ? s : du.page;
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
  const t = Uc(e.location.hash);
  return !t.matched || !vn(t.page) ? null : { page: t.page, focus: t.focus };
}
function yo(e, t, n) {
  const s = Wc(t);
  if (!s) return;
  const r = e.location.pathname + e.location.search + s;
  n === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function yg(e, t) {
  let n = Dh(t, e.location.hash), s = Ys(n), r = {};
  const o = s, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = s;
    n = go(e) ?? { ...du }, s = Ys(n), i.forEach((d) => d(s, u));
  }, c = (u, f) => u === null && f === o;
  return {
    get base() {
      return gg;
    },
    get location() {
      return s;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const f = Wc(mo(u));
      return f === "" ? "#" + u : f;
    },
    replace: (u, f) => {
      const d = go(e), h = mo(u), y = Ys(h);
      n = h, f !== void 0 && (r = f), s = y, !c(d, y) && Oa(d, h) !== "none" && yo(e, h, "replace");
    },
    push: (u, f) => {
      const d = go(e), h = mo(u), y = Ys(h);
      if (n = h, f !== void 0 && (r = f), s = y, c(d, y)) return;
      const v = Oa(d, h);
      v === "push" ? yo(e, h, "push") : v === "replace" && yo(e, h, "replace");
    },
    go: () => {
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
function pu(e, t) {
  const n = typeof e == "string" && !t ? `${e}Context` : t, s = Symbol(n);
  return [(i) => {
    const a = it(s, i);
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
function hu(e, t, n) {
  const s = n.originalEvent.target, r = new CustomEvent(e, {
    bubbles: !1,
    cancelable: !0,
    detail: n
  });
  t && s.addEventListener(e, t, { once: !0 }), s.dispatchEvent(r);
}
function vg(e, t) {
  return Ir() ? (ei(e, t), !0) : !1;
}
// @__NO_SIDE_EFFECTS__
function bg(e) {
  let t = !1, n;
  const s = Tr(!0);
  return ((...r) => (t || (n = s.run(() => e(...r)), t = !0), n));
}
const nn = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const _g = (e) => typeof e < "u", xg = Object.prototype.toString, wg = (e) => xg.call(e) === "[object Object]", Qa = /* @__PURE__ */ kg();
function kg() {
  var e, t, n;
  return nn && !!(!((e = window) === null || e === void 0 || (e = e.navigator) === null || e === void 0) && e.userAgent) && (/iP(?:ad|hone|od)/.test(window.navigator.userAgent) || ((t = window) === null || t === void 0 || (t = t.navigator) === null || t === void 0 ? void 0 : t.maxTouchPoints) > 2 && /iPad|Macintosh/.test((n = window) === null || n === void 0 ? void 0 : n.navigator.userAgent));
}
function vo(e) {
  return Array.isArray(e) ? e : [e];
}
function Sg(e) {
  return Ct();
}
// @__NO_SIDE_EFFECTS__
function Eg(e) {
  if (!nn) return e;
  let t = 0, n, s;
  const r = () => {
    t -= 1, s && t <= 0 && (s.stop(), n = void 0, s = void 0);
  };
  return ((...o) => (t += 1, s || (s = Tr(!0), n = s.run(() => e(...o))), vg(r), n));
}
function Cg(e, t) {
  Sg() && Wl(e, t);
}
function Ag(e, t, n) {
  return Fe(e, t, {
    ...n,
    immediate: !0
  });
}
const ki = nn ? window : void 0;
function Wr(e) {
  var t;
  const n = Qe(e);
  return (t = n?.$el) !== null && t !== void 0 ? t : n;
}
function mu(...e) {
  const t = (s, r, o, i) => (s.addEventListener(r, o, i), () => s.removeEventListener(r, o, i)), n = ae(() => {
    const s = vo(Qe(e[0])).filter((r) => r != null);
    return s.every((r) => typeof r != "string") ? s : void 0;
  });
  return Ag(() => {
    var s, r;
    return [
      (s = (r = n.value) === null || r === void 0 ? void 0 : r.map((o) => Wr(o))) !== null && s !== void 0 ? s : [ki].filter((o) => o != null),
      vo(Qe(n.value ? e[1] : e[0])),
      vo(x(n.value ? e[2] : e[1])),
      Qe(n.value ? e[3] : e[2])
    ];
  }, ([s, r, o, i], a, l) => {
    if (!s?.length || !r?.length || !o?.length) return;
    const c = wg(i) ? { ...i } : i, u = s.flatMap((f) => r.flatMap((d) => o.map((h) => t(f, d, h, c))));
    l(() => {
      u.forEach((f) => f());
    });
  }, { flush: "post" });
}
// @__NO_SIDE_EFFECTS__
function Og() {
  const e = /* @__PURE__ */ Zn(!1), t = Ct();
  return t && ss(() => {
    e.value = !0;
  }, t), e;
}
function Rg(e) {
  return typeof e == "function" ? e : typeof e == "string" ? (t) => t.key === e : Array.isArray(e) ? (t) => e.includes(t.key) : () => !0;
}
function Tg(...e) {
  let t, n, s = {};
  e.length === 3 ? (t = e[0], n = e[1], s = e[2]) : e.length === 2 ? typeof e[1] == "object" ? (t = !0, n = e[0], s = e[1]) : (t = e[0], n = e[1]) : (t = !0, n = e[0]);
  const { target: r = ki, eventName: o = "keydown", passive: i = !1, dedupe: a = !1 } = s, l = Rg(t);
  return mu(r, o, (u) => {
    u.repeat && Qe(a) || l(u) && n(u);
  }, i);
}
function Ig(e) {
  return JSON.parse(JSON.stringify(e));
}
// @__NO_SIDE_EFFECTS__
function Pg(e, t, n, s = {}) {
  var r, o;
  const { clone: i = !1, passive: a = !1, eventName: l, deep: c = !1, defaultValue: u, shouldEmit: f } = s, d = Ct(), h = n || d?.emit || (d == null || (r = d.$emit) === null || r === void 0 ? void 0 : r.bind(d)) || (d == null || (o = d.proxy) === null || o === void 0 || (o = o.$emit) === null || o === void 0 ? void 0 : o.bind(d?.proxy));
  let y = l;
  y = y || `update:${t.toString()}`;
  const v = (w) => i ? typeof i == "function" ? i(w) : Ig(w) : w, k = () => _g(e[t]) ? v(e[t]) : u, I = (w) => {
    f ? f(w) && h(y, w) : h(y, w);
  };
  if (a) {
    const w = /* @__PURE__ */ se(k());
    let N = !1;
    return Fe(() => e[t], (O) => {
      N || (N = !0, w.value = v(O), St(() => N = !1));
    }), Fe(w, (O) => {
      !N && (O !== e[t] || c) && I(O);
    }, { deep: c }), w;
  } else return ae({
    get() {
      return k();
    },
    set(w) {
      I(w);
    }
  });
}
function Si(e) {
  return e ? e.flatMap((t) => t.type === qe ? Si(t.children) : [t]) : [];
}
const [Ei] = /* @__PURE__ */ pu("ConfigProvider"), wr = /* @__PURE__ */ new WeakMap();
function gu(e, t) {
  let n = wr.get(e);
  n || (n = {
    owners: /* @__PURE__ */ new Set(),
    original: e.body.style.pointerEvents
  }, wr.set(e, n)), n.owners.add(t), e.body.style.pointerEvents = "none";
}
function yu(e, t) {
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
function Ng(e) {
  return (...t) => (
    // eslint-disable-next-line unicorn/no-array-reduce
    t.reduce((n, s) => Ko(n, s, "", e), {})
  );
}
const Mg = Ng(), Xa = Symbol("useBodyScrollLock"), Dg = /* @__PURE__ */ Eg(() => {
  const e = /* @__PURE__ */ se(/* @__PURE__ */ new Map()), t = /* @__PURE__ */ se(), n = ae(() => {
    for (const i of e.value.values()) if (i) return !0;
    return !1;
  }), s = Ei({ scrollBody: /* @__PURE__ */ se(!0) });
  let r = null;
  const o = () => {
    document.body.style.paddingRight = "", document.body.style.marginRight = "", yu(document, Xa), document.documentElement.style.removeProperty("--scrollbar-width"), document.body.style.overflow = t.value ?? "", Qa && r?.(), t.value = void 0;
  };
  return Fe(n, (i, a) => {
    if (!nn) return;
    if (!i) {
      a && o();
      return;
    }
    t.value === void 0 && (t.value = document.body.style.overflow);
    const l = window.innerWidth - document.documentElement.clientWidth, c = {
      padding: l,
      margin: 0
    }, u = s.scrollBody?.value ? typeof s.scrollBody.value == "object" ? Mg({
      padding: s.scrollBody.value.padding === !0 ? l : s.scrollBody.value.padding,
      margin: s.scrollBody.value.margin === !0 ? l : s.scrollBody.value.margin
    }, c) : c : {
      padding: 0,
      margin: 0
    };
    l > 0 && (document.body.style.paddingRight = typeof u.padding == "number" ? `${u.padding}px` : String(u.padding), document.body.style.marginRight = typeof u.margin == "number" ? `${u.margin}px` : String(u.margin), document.documentElement.style.setProperty("--scrollbar-width", `${l}px`), document.body.style.overflow = "hidden"), Qa && (r = mu(document, "touchmove", (f) => jg(f), { passive: !1 })), St(() => {
      n.value && (gu(document, Xa), document.body.style.overflow = "hidden");
    });
  }, {
    immediate: !0,
    flush: "sync"
  }), e;
});
function Lg(e) {
  const t = Math.random().toString(36).substring(2, 7), n = Dg();
  n.value.set(t, e ?? !1);
  const s = ae({
    get: () => n.value.get(t) ?? !1,
    set: (r) => n.value.set(t, r)
  });
  return Cg(() => {
    n.value.delete(t);
  }), s;
}
function vu(e) {
  const t = window.getComputedStyle(e);
  if (t.overflowX === "scroll" || t.overflowY === "scroll" || t.overflowX === "auto" && e.clientWidth < e.scrollWidth || t.overflowY === "auto" && e.clientHeight < e.scrollHeight) return !0;
  {
    const n = e.parentNode;
    return !(n instanceof Element) || n.tagName === "BODY" ? !1 : vu(n);
  }
}
function jg(e) {
  const t = e || window.event, n = t.target;
  return n instanceof Element && vu(n) ? !1 : t.touches.length > 1 ? !0 : (t.preventDefault && t.cancelable && t.preventDefault(), !1);
}
function Ci(e) {
  const t = Ct(), n = t?.type.emits, s = {};
  return n?.length || console.warn(`No emitted event found. Please check component: ${t?.type.__name}`), n?.forEach((r) => {
    s[tr(Ye(r))] = (...o) => e(r, ...o);
  }), s;
}
function bt() {
  const e = Ct(), t = /* @__PURE__ */ se(), n = ae(() => s());
  Ul(() => {
    n.value !== s() && tf(t);
  });
  function s() {
    return t.value && "$el" in t.value && ["#text", "#comment"].includes(t.value.$el.nodeName) ? t.value.$el.nextElementSibling : Wr(t);
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
var Fg = function(e) {
  if (typeof document > "u")
    return null;
  var t = Array.isArray(e) ? e[0] : e;
  return t.ownerDocument.body;
}, zn = /* @__PURE__ */ new WeakMap(), Qs = /* @__PURE__ */ new WeakMap(), Xs = {}, _o = 0, bu = function(e) {
  return e && (e.host || bu(e.parentNode));
}, $g = function(e, t) {
  return t.map(function(n) {
    if (e.contains(n))
      return n;
    var s = bu(n);
    return s && e.contains(s) ? s : (console.error("aria-hidden", n, "in not contained inside", e, ". Doing nothing"), null);
  }).filter(function(n) {
    return !!n;
  });
}, Vg = function(e, t, n, s) {
  var r = $g(t, Array.isArray(e) ? e : [e]);
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
          var h = d.getAttribute(s), y = h !== null && h !== "false", v = (zn.get(d) || 0) + 1, k = (o.get(d) || 0) + 1;
          zn.set(d, v), o.set(d, k), i.push(d), v === 1 && y && Qs.set(d, !0), k === 1 && d.setAttribute(n, "true"), y || d.setAttribute(s, "true");
        } catch (I) {
          console.error("aria-hidden: cannot operate on ", d, I);
        }
    });
  };
  return u(t), a.clear(), _o++, function() {
    i.forEach(function(f) {
      var d = zn.get(f) - 1, h = o.get(f) - 1;
      zn.set(f, d), o.set(f, h), d || (Qs.has(f) || f.removeAttribute(s), Qs.delete(f)), h || f.removeAttribute(n);
    }), _o--, _o || (zn = /* @__PURE__ */ new WeakMap(), zn = /* @__PURE__ */ new WeakMap(), Qs = /* @__PURE__ */ new WeakMap(), Xs = {});
  };
}, Bg = function(e, t, n) {
  n === void 0 && (n = "data-aria-hidden");
  var s = Array.from(Array.isArray(e) ? e : [e]), r = Fg(e);
  return r ? (s.push.apply(s, Array.from(r.querySelectorAll("[aria-live], script"))), Vg(s, r, n, "aria-hidden")) : function() {
    return null;
  };
};
function zg(e) {
  let t;
  Fe(() => Wr(e), (n) => {
    let s = !1;
    try {
      s = !!n?.closest("[popover]:not(:popover-open)");
    } catch {
    }
    n && !s ? t = Bg(n) : t && t();
  }), jr(() => {
    t && t();
  });
}
function Jo(e, t = "reka") {
  let n;
  const s = Ei({ useId: void 0 });
  return s.useId ? n = s.useId() : n = wf?.(), t ? `${t}-${n}` : n;
}
function Ug(e, t) {
  const n = /* @__PURE__ */ se(e);
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
function Wg(e, t) {
  const n = /* @__PURE__ */ se({}), s = /* @__PURE__ */ se("none"), r = /* @__PURE__ */ se(e), o = e.value ? "mounted" : "unmounted";
  let i;
  const a = t.value?.ownerDocument.defaultView ?? ki, { state: l, dispatch: c } = Ug(o, {
    mounted: {
      UNMOUNT: "unmounted",
      ANIMATION_OUT: "unmountSuspended"
    },
    unmountSuspended: {
      MOUNT: "mounted",
      ANIMATION_END: "unmounted"
    },
    unmounted: { MOUNT: "mounted" }
  }), u = (k) => {
    if (nn) {
      const I = new CustomEvent(k, {
        bubbles: !1,
        cancelable: !1
      });
      t.value?.dispatchEvent(I);
    }
  };
  Fe(e, async (k, I) => {
    const w = I !== k;
    if (await St(), w) {
      const N = s.value, O = er(t.value);
      k ? (c("MOUNT"), u("enter"), O === "none" && u("after-enter")) : O === "none" || O === "undefined" || n.value?.display === "none" ? (c("UNMOUNT"), u("leave"), u("after-leave")) : I && N !== O ? (c("ANIMATION_OUT"), u("leave")) : (c("UNMOUNT"), u("after-leave"));
    }
  }, { immediate: !0 });
  const f = (k) => {
    if (k.target !== t.value) return;
    const I = er(t.value), w = I.includes(CSS.escape(k.animationName)), N = l.value === "mounted" ? "enter" : "leave";
    if (w && (u(`after-${N}`), c("ANIMATION_END"), !r.value)) {
      const O = t.value.style.animationFillMode;
      t.value.style.animationFillMode = "forwards", i = a?.setTimeout(() => {
        t.value?.style.animationFillMode === "forwards" && (t.value.style.animationFillMode = O);
      });
    }
    I === "none" && c("ANIMATION_END");
  }, d = (k) => {
    k.target === t.value && (s.value = er(t.value));
  }, h = Fe(t, (k, I) => {
    k ? (n.value = getComputedStyle(k), k.addEventListener("animationstart", d), k.addEventListener("animationcancel", f), k.addEventListener("animationend", f)) : (c("ANIMATION_END"), i !== void 0 && a?.clearTimeout(i), I?.removeEventListener("animationstart", d), I?.removeEventListener("animationcancel", f), I?.removeEventListener("animationend", f));
  }, { immediate: !0 }), y = Fe(l, () => {
    const k = er(t.value);
    s.value = l.value === "mounted" ? k : "none";
  });
  return jr(() => {
    h(), y(), t.value && (t.value.removeEventListener("animationstart", d), t.value.removeEventListener("animationcancel", f), t.value.removeEventListener("animationend", f)), i !== void 0 && a?.clearTimeout(i);
  }), { isPresent: ae(() => ["mounted", "unmountSuspended"].includes(l.value)) };
}
function er(e) {
  return e && getComputedStyle(e).animationName || "none";
}
var _u = /* @__PURE__ */ Ae({
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
    const { present: s, forceMount: r } = /* @__PURE__ */ li(e), o = /* @__PURE__ */ se(), { isPresent: i } = Wg(s, o);
    n({ present: i });
    let a = t.default({ present: i.value });
    a = Si(a || []);
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
      const u = Wr(c);
      return typeof u?.hasAttribute > "u" || (u?.hasAttribute("data-reka-popper-content-wrapper") ? o.value = u.firstElementChild : o.value = u), u;
    } }) : null;
  }
});
const Hg = /* @__PURE__ */ Ae({
  name: "PrimitiveSlot",
  inheritAttrs: !1,
  setup(e, { attrs: t, slots: n }) {
    return () => {
      if (!n.default) return null;
      const s = Si(n.default()), r = s.findIndex((l) => l.type !== pt);
      if (r === -1) return s;
      const o = s[r];
      delete o.props?.ref;
      const i = o.props ? yt(t, o.props) : t, a = Mn({
        ...o,
        props: {}
      }, i);
      return s.length === 1 ? a : (s[r] = a, s);
    };
  }
}), qg = [
  "area",
  "img",
  "input"
], $n = /* @__PURE__ */ Ae({
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
    return typeof s == "string" && qg.includes(s) ? () => en(s, t) : s !== "template" ? () => en(e.as, t, { default: n.default }) : () => en(Hg, t, { default: n.default });
  }
}), [Ut, Zg] = /* @__PURE__ */ pu("DialogRoot");
var Gg = /* @__PURE__ */ Ae({
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
    const n = e, r = /* @__PURE__ */ Pg(n, "open", t, {
      defaultValue: n.defaultOpen,
      passive: n.open === void 0
    }), o = /* @__PURE__ */ se(), i = /* @__PURE__ */ se(), { modal: a, unmountOnHide: l } = /* @__PURE__ */ li(n);
    return Zg({
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
    }), (c, u) => Xe(c.$slots, "default", {
      open: x(r),
      close: () => r.value = !1
    });
  }
}), Kg = Gg, Jg = /* @__PURE__ */ Ae({
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
    return (s, r) => (de(), Le(x($n), yt(t, {
      type: e.as === "button" ? "button" : void 0,
      onClick: r[0] || (r[0] = (o) => x(n).onOpenChange(!1))
    }), {
      default: Ce(() => [Xe(s.$slots, "default")]),
      _: 3
    }, 16, ["type"]));
  }
}), Yg = Jg;
const Qg = "dismissableLayer.pointerDownOutside", Xg = "dismissableLayer.focusOutside";
function ey(e) {
  if (typeof e != "object" || e === null) return !1;
  const t = e.ownerDocument?.defaultView;
  return typeof Element < "u" && e instanceof Element || !!t && e instanceof t.Element;
}
function xu(e, t) {
  if (!ey(t)) return !1;
  if (e.contains(t)) return !0;
  const n = t.closest("[data-dismissable-layer]"), s = e.dataset.dismissableLayer === "" ? e : e.querySelector("[data-dismissable-layer]"), r = Array.from(e.ownerDocument.querySelectorAll("[data-dismissable-layer]"));
  return !!(n && (s === n || r.indexOf(s) < r.indexOf(n)));
}
function ty(e, t, n = !0) {
  const s = /* @__PURE__ */ se(!1), r = /* @__PURE__ */ se(() => {
  });
  return Kn((o) => {
    if (!nn || !Qe(n)) return;
    const i = t?.value?.ownerDocument ?? globalThis.document, a = async (c) => {
      const u = c.target;
      if (!(!t?.value || !u)) {
        if (xu(t.value, u)) {
          i.removeEventListener("click", r.value), s.value = !1;
          return;
        }
        if (c.target && !s.value) {
          let d = function() {
            hu(Qg, e, f);
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
function ny(e, t, n = !0) {
  const s = /* @__PURE__ */ se(!1);
  return Kn((r) => {
    if (!nn || !Qe(n)) return;
    const o = t?.value?.ownerDocument ?? globalThis.document, i = async (a) => {
      if (!t?.value) return;
      await St(), await St();
      const l = a.target;
      !t.value || !l || xu(t.value, l) || a.target && !s.value && hu(Xg, e, { originalEvent: a });
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
var sy = /* @__PURE__ */ Ae({
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
    const n = e, s = t, { forwardRef: r, currentElement: o } = bt(), i = ae(() => o.value?.ownerDocument ?? globalThis.document), a = ae(() => ln.layersRoot), l = ae(() => o.value ? Array.from(a.value).indexOf(o.value) : -1), c = ae(() => ln.layersWithOutsidePointerEventsDisabled.size > 0), u = ae(() => {
      const h = Array.from(a.value), [y] = [...ln.layersWithOutsidePointerEventsDisabled].slice(-1), v = h.indexOf(y);
      return l.value >= v;
    }), f = ty(async (h) => {
      const y = [...ln.branches].some((v) => v?.contains(h.target));
      !n.present || !u.value || y || (s("pointerDownOutside", h), s("interactOutside", h), await St(), h.defaultPrevented || s("dismiss"));
    }, o, () => n.present), d = ny((h) => {
      const y = [...ln.branches].some((v) => v?.contains(h.target));
      !n.present || y || (s("focusOutside", h), s("interactOutside", h), h.defaultPrevented || s("dismiss"));
    }, o);
    return Tg("Escape", (h) => {
      !n.present || !(l.value === a.value.size - 1) || (s("escapeKeyDown", h), h.defaultPrevented || s("dismiss"));
    }, { target: () => i.value?.defaultView ?? globalThis.window }), Fe([
      o,
      () => n.disableOutsidePointerEvents,
      () => n.present
    ], ([h, y, v], k, I) => {
      if (!(!h || !v) && y) {
        const w = h.ownerDocument;
        gu(w, h), ln.layersWithOutsidePointerEventsDisabled.add(h), I(() => {
          ln.layersWithOutsidePointerEventsDisabled.delete(h), yu(w, h);
        });
      }
    }, { immediate: !0 }), Fe([o, () => n.present], ([h, y], v, k) => {
      !h || !y || (a.value.add(h), k(() => {
        a.value.delete(h);
      }));
    }, { immediate: !0 }), Kn((h) => {
      h(() => {
        o.value && (a.value.delete(o.value), ln.layersWithOutsidePointerEventsDisabled.delete(o.value));
      });
    }), (h, y) => (de(), Le(x($n), {
      ref: x(r),
      "as-child": e.asChild,
      as: e.as,
      "data-dismissable-layer": "",
      style: Ls({ pointerEvents: c.value ? u.value ? "auto" : "none" : void 0 }),
      onFocusCapture: x(d).onFocusCapture,
      onBlurCapture: x(d).onBlurCapture,
      onPointerdownCapture: x(f).onPointerDownCapture
    }, {
      default: Ce(() => [Xe(h.$slots, "default")]),
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
}), ry = sy;
const oy = /* @__PURE__ */ bg(() => /* @__PURE__ */ se([]));
function iy() {
  const e = oy();
  return {
    add(t) {
      const n = e.value[0];
      t !== n && n?.pause(), e.value = el(e.value, t), e.value.unshift(t);
    },
    remove(t) {
      e.value = el(e.value, t), e.value[0]?.resume();
    }
  };
}
function el(e, t) {
  const n = [...e], s = n.indexOf(t);
  return s !== -1 && n.splice(s, 1), n;
}
const xo = "focusScope.autoFocusOnMount", wo = "focusScope.autoFocusOnUnmount", tl = {
  bubbles: !1,
  cancelable: !0
};
function ay(e, t) {
  let n = t;
  for (; n; ) {
    if (e.contains(n)) return !0;
    n = n.getRootNode().host ?? null;
  }
  return !1;
}
function ly(e, { select: t = !1 } = {}) {
  const n = Lt();
  for (const s of e)
    if (Gt(s, { select: t }), Lt() !== n) return !0;
}
function cy(e) {
  const t = wu(e), n = nl(t, e), s = nl(t.reverse(), e);
  return [n, s];
}
function wu(e) {
  const t = [], n = document.createTreeWalker(e, NodeFilter.SHOW_ELEMENT, { acceptNode: (s) => {
    const r = s.tagName === "INPUT" && s.type === "hidden";
    return s.disabled || s.hidden || r ? NodeFilter.FILTER_SKIP : s.tabIndex >= 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
  } });
  for (; n.nextNode(); ) t.push(n.currentNode);
  return t.sort((s, r) => s.tabIndex === r.tabIndex ? 0 : s.tabIndex === 0 ? 1 : r.tabIndex === 0 ? -1 : s.tabIndex - r.tabIndex);
}
function nl(e, t) {
  for (const n of e) if (!uy(n, { upTo: t })) return n;
}
function uy(e, { upTo: t }) {
  if (getComputedStyle(e).visibility === "hidden") return !0;
  for (; e; ) {
    if (t !== void 0 && e === t) return !1;
    if (getComputedStyle(e).display === "none") return !0;
    e = e.parentElement;
  }
  return !1;
}
function fy(e) {
  return e instanceof HTMLInputElement && "select" in e;
}
function Gt(e, { select: t = !1 } = {}) {
  if (e && e.focus) {
    const n = Lt();
    e.focus({ preventScroll: !0 }), e !== n && fy(e) && t && e.select();
  }
}
var dy = /* @__PURE__ */ Ae({
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
    const n = e, s = t, { currentRef: r, currentElement: o } = bt(), i = /* @__PURE__ */ se(null), a = iy(), l = /* @__PURE__ */ jn({
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
        const W = O.target;
        d.contains(W) ? i.value = W : Gt(i.value, { select: !0 });
      }
      function k(O) {
        if (l.paused || !d) return;
        const W = O.relatedTarget;
        W !== null && (d.contains(W) || Gt(i.value, { select: !0 }));
      }
      function I(O) {
        const W = i.value;
        if (W === null || !O.some((F) => F.removedNodes.length > 0)) return;
        const V = Lt();
        if (V && d.contains(V)) return;
        d.contains(W) || Gt(d);
      }
      function w(O) {
        if (l.paused || !d) return;
        const W = O.composedPath()[0];
        ay(d, W) || Gt(i.value, { select: !0 });
      }
      y.addEventListener("focusin", v), y.addEventListener("focusout", k), y !== h && h.addEventListener("focusin", w);
      const N = new MutationObserver(I);
      d && N.observe(d, {
        childList: !0,
        subtree: !0
      }), f(() => {
        y.removeEventListener("focusin", v), y.removeEventListener("focusout", k), y !== h && h.removeEventListener("focusin", w), N.disconnect();
      });
    });
    function c(f, d) {
      const h = new CustomEvent(xo, tl), y = (v) => s("mountAutoFocus", v);
      f.addEventListener(xo, y), f.dispatchEvent(h), f.removeEventListener(xo, y), h.defaultPrevented || (ly(wu(f), { select: !0 }), Lt() === d && Gt(f));
    }
    Kn(async (f) => {
      const d = o.value;
      if (await St(), !d) return;
      n.present !== !1 && a.add(l);
      const h = Lt();
      !d.contains(h) && n.present !== !1 && c(d, h), f(() => {
        const v = new CustomEvent(wo, tl), k = (I) => {
          s("unmountAutoFocus", I);
        };
        d.addEventListener(wo, k), d.dispatchEvent(v), d.setAttribute("data-focus-scope-unmounting", ""), setTimeout(() => {
          v.defaultPrevented || Gt(h ?? document.body, { select: !0 }), d.removeEventListener(wo, k), a.remove(l), d.removeAttribute("data-focus-scope-unmounting");
        }, 0);
      });
    }), Fe(() => n.present, async (f, d) => {
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
        const y = f.currentTarget, [v, k] = cy(y);
        v && k ? !f.shiftKey && h === k ? (f.preventDefault(), n.loop && Gt(v, { select: !0 })) : f.shiftKey && h === v && (f.preventDefault(), n.loop && Gt(k, { select: !0 })) : h === y && f.preventDefault();
      }
    }
    return (f, d) => (de(), Le(x($n), {
      ref_key: "currentRef",
      ref: r,
      tabindex: "-1",
      "as-child": e.asChild,
      as: e.as,
      onKeydown: u
    }, {
      default: Ce(() => [Xe(f.$slots, "default")]),
      _: 3
    }, 8, ["as-child", "as"]));
  }
}), py = dy;
function hy(e) {
  return e ? "open" : "closed";
}
var my = /* @__PURE__ */ Ae({
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
    }), (a, l) => (de(), Le(x(py), {
      "as-child": "",
      loop: "",
      trapped: n.trapFocus,
      present: n.present,
      onMountAutoFocus: l[5] || (l[5] = (c) => s("openAutoFocus", c)),
      onUnmountAutoFocus: l[6] || (l[6] = (c) => s("closeAutoFocus", c))
    }, {
      default: Ce(() => [fe(x(ry), yt({
        id: x(r).contentId,
        ref: x(o),
        as: e.as,
        "as-child": e.asChild,
        present: n.present,
        "disable-outside-pointer-events": e.disableOutsidePointerEvents,
        role: "dialog",
        "aria-describedby": x(r).descriptionId,
        "aria-labelledby": x(r).titleId,
        "data-state": x(hy)(x(r).open.value)
      }, a.$attrs, {
        onDismiss: l[0] || (l[0] = (c) => x(r).onOpenChange(!1)),
        onEscapeKeyDown: l[1] || (l[1] = (c) => s("escapeKeyDown", c)),
        onFocusOutside: l[2] || (l[2] = (c) => s("focusOutside", c)),
        onInteractOutside: l[3] || (l[3] = (c) => s("interactOutside", c)),
        onPointerDownOutside: l[4] || (l[4] = (c) => s("pointerDownOutside", c))
      }), {
        default: Ce(() => [Xe(a.$slots, "default")]),
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
}), ku = my, gy = /* @__PURE__ */ Ae({
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
    const n = e, s = t, r = Ut(), o = Ci(s), { forwardRef: i, currentElement: a } = bt(), l = ae(() => n.present ? a.value : void 0);
    zg(l);
    const c = ae(() => {
      const { present: u, ...f } = n;
      return f;
    });
    return Fe(() => n.present, (u, f) => {
      !u && f && r.triggerElement.value?.focus();
    }), (u, f) => (de(), Le(ku, yt({
      ...c.value,
      ...x(o)
    }, {
      ref: x(i),
      present: e.present,
      "trap-focus": x(r).open.value,
      "disable-outside-pointer-events": n.disableOutsidePointerEvents,
      onCloseAutoFocus: f[0] || (f[0] = (d) => {
        d.defaultPrevented || (d.preventDefault(), x(r).triggerElement.value?.focus());
      }),
      onPointerDownOutside: f[1] || (f[1] = (d) => {
        const h = d.detail.originalEvent, y = h.button === 0 && h.ctrlKey === !0;
        (h.button === 2 || y) && d.preventDefault();
      }),
      onFocusOutside: f[2] || (f[2] = (d) => {
        d.preventDefault();
      })
    }), {
      default: Ce(() => [Xe(u.$slots, "default")]),
      _: 3
    }, 16, [
      "present",
      "trap-focus",
      "disable-outside-pointer-events"
    ]));
  }
}), yy = gy, vy = /* @__PURE__ */ Ae({
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
    const n = e, r = Ci(t);
    bt();
    const o = Ut(), i = /* @__PURE__ */ se(!1), a = /* @__PURE__ */ se(!1), l = ae(() => {
      const { present: c, ...u } = n;
      return u;
    });
    return Fe(() => n.present, (c, u) => {
      !c && u && (i.value || o.triggerElement.value?.focus(), i.value = !1, a.value = !1);
    }), (c, u) => (de(), Le(ku, yt({
      ...l.value,
      ...x(r)
    }, {
      present: e.present,
      "trap-focus": !1,
      "disable-outside-pointer-events": !1,
      onCloseAutoFocus: u[0] || (u[0] = (f) => {
        f.defaultPrevented || (i.value || x(o).triggerElement.value?.focus(), f.preventDefault()), i.value = !1, a.value = !1;
      }),
      onInteractOutside: u[1] || (u[1] = (f) => {
        f.defaultPrevented || (i.value = !0, f.detail.originalEvent.type === "pointerdown" && (a.value = !0));
        const d = f.target;
        x(o).triggerElement.value?.contains(d) && f.preventDefault(), f.detail.originalEvent.type === "focusin" && a.value && f.preventDefault();
      })
    }), {
      default: Ce(() => [Xe(c.$slots, "default")]),
      _: 3
    }, 16, ["present"]));
  }
}), by = vy, _y = /* @__PURE__ */ Ae({
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
    const n = e, s = t, r = Ut(), o = Ci(s), { forwardRef: i } = bt(), a = ae(() => n.forceMount || !r.unmountOnHide.value);
    return (l, c) => (de(), Le(x(_u), {
      present: x(r).open.value,
      "force-mount": a.value
    }, {
      default: Ce(({ present: u }) => [x(r).modal.value ? Cs((de(), Le(yy, yt({
        key: 0,
        ref: x(i),
        present: a.value ? u : !0
      }, {
        ...n,
        ...x(o),
        ...l.$attrs
      }), {
        default: Ce(() => [Xe(l.$slots, "default")]),
        _: 3
      }, 16, ["present"])), [[Lo, e.forceMount || x(r).unmountOnHide.value || u]]) : Cs((de(), Le(by, yt({
        key: 1,
        ref: x(i),
        present: a.value ? u : !0
      }, {
        ...n,
        ...x(o),
        ...l.$attrs
      }), {
        default: Ce(() => [Xe(l.$slots, "default")]),
        _: 3
      }, 16, ["present"])), [[Lo, e.forceMount || x(r).unmountOnHide.value || u]])]),
      _: 3
    }, 8, ["present", "force-mount"]));
  }
}), xy = _y, wy = /* @__PURE__ */ Ae({
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
    return (s, r) => (de(), Le(x($n), yt(t, { id: x(n).descriptionId }), {
      default: Ce(() => [Xe(s.$slots, "default")]),
      _: 3
    }, 16, ["id"]));
  }
}), ky = wy, Sy = /* @__PURE__ */ Ae({
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
    const t = e, n = Ut(), s = Lg(t.present);
    return Fe(() => t.present, (r) => s.value = r), bt(), (r, o) => (de(), Le(x($n), {
      as: e.as,
      "as-child": e.asChild,
      "data-state": x(n).open.value ? "open" : "closed",
      style: { "pointer-events": "auto" },
      onPointerdown: o[0] || (o[0] = zd(() => {
      }, [
        "left",
        "self",
        "prevent"
      ]))
    }, {
      default: Ce(() => [Xe(r.$slots, "default")]),
      _: 3
    }, 8, [
      "as",
      "as-child",
      "data-state"
    ]));
  }
}), Ey = Sy, Cy = /* @__PURE__ */ Ae({
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
    const t = e, n = Ut(), { forwardRef: s } = bt(), r = ae(() => t.forceMount || !n.unmountOnHide.value);
    return (o, i) => x(n)?.modal.value ? (de(), Le(x(_u), {
      key: 0,
      present: x(n).open.value,
      "force-mount": r.value
    }, {
      default: Ce(({ present: a }) => [Cs(fe(Ey, yt(o.$attrs, {
        ref: x(s),
        as: e.as,
        "as-child": e.asChild,
        present: r.value ? a : !0
      }), {
        default: Ce(() => [Xe(o.$slots, "default")]),
        _: 3
      }, 16, [
        "as",
        "as-child",
        "present"
      ]), [[Lo, e.forceMount || x(n).unmountOnHide.value || a]])]),
      _: 3
    }, 8, ["present", "force-mount"])) : Os("v-if", !0);
  }
}), Ay = Cy, Oy = /* @__PURE__ */ Ae({
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
    const t = e, n = Ei({}), s = ae(() => t.to ?? n.teleportTo?.value ?? "body"), r = /* @__PURE__ */ Og();
    return (o, i) => x(r) || e.forceMount ? (de(), Le(_f, {
      key: 0,
      to: s.value,
      disabled: e.disabled,
      defer: e.defer
    }, [Xe(o.$slots, "default")], 8, [
      "to",
      "disabled",
      "defer"
    ])) : Os("v-if", !0);
  }
}), Ry = Oy, Ty = /* @__PURE__ */ Ae({
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
    return (n, s) => (de(), Le(x(Ry), Pu(dc(t)), {
      default: Ce(() => [Xe(n.$slots, "default")]),
      _: 3
    }, 16));
  }
}), Iy = Ty, Py = /* @__PURE__ */ Ae({
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
    return bt(), (s, r) => (de(), Le(x($n), yt(t, { id: x(n).titleId }), {
      default: Ce(() => [Xe(s.$slots, "default")]),
      _: 3
    }, 16, ["id"]));
  }
}), Ny = Py, My = /* @__PURE__ */ Ae({
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
    }), (o, i) => (de(), Le(x($n), yt(t, {
      ref: x(s),
      type: e.as === "button" ? "button" : void 0,
      "aria-haspopup": "dialog",
      "aria-expanded": x(n).open.value || !1,
      "aria-controls": x(n).open.value ? x(n).contentId : void 0,
      "data-state": x(n).open.value ? "open" : "closed",
      onClick: x(n).onOpenToggle
    }), {
      default: Ce(() => [Xe(o.$slots, "default")]),
      _: 3
    }, 16, [
      "type",
      "aria-expanded",
      "aria-controls",
      "data-state",
      "onClick"
    ]));
  }
}), Dy = My;
const Ly = /* @__PURE__ */ rs("studio-infrastructure", () => {
  const e = /* @__PURE__ */ se("unknown"), t = /* @__PURE__ */ se(null), n = /* @__PURE__ */ se(null);
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
}), sl = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, rl = Yc, jy = (e, t) => (n) => {
  var s;
  if (t?.variants == null) return rl(e, n?.class, n?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = n?.[c], f = o?.[c];
    if (u === null) return null;
    const d = sl(u) || sl(f);
    return r[c][d];
  }), a = n && Object.entries(n).reduce((c, u) => {
    let [f, d] = u;
    return d === void 0 || (c[f] = d), c;
  }, {}), l = t == null || (s = t.compoundVariants) === null || s === void 0 ? void 0 : s.reduce((c, u) => {
    let { class: f, className: d, ...h } = u;
    return Object.entries(h).every((y) => {
      let [v, k] = y;
      return Array.isArray(k) ? k.includes({
        ...o,
        ...a
      }[v]) : {
        ...o,
        ...a
      }[v] === k;
    }) ? [
      ...c,
      f,
      d
    ] : c;
  }, []);
  return rl(e, i, l, n?.class, n?.className);
}, Fy = jy(
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
);
function gn(e, t, n) {
  return Ur(Fy({ variant: e, size: t }), n);
}
function sn(e) {
  return Ur(
    "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm",
    e
  );
}
function $s(e) {
  return Ur(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const $y = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Vy = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, By = { class: "cmst:text-sm cmst:mt-2" }, zy = { key: 0 }, Uy = { class: "cmst:text-sm cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Wy = { class: "cmst:flex cmst:justify-end cmst:mt-4" }, Hy = /* @__PURE__ */ Ae({
  __name: "BackendView",
  setup(e) {
    const t = Ly(), n = /* @__PURE__ */ se(!1), s = /* @__PURE__ */ se(null);
    ss(() => {
      s.value = document.querySelector("[data-studio-portals]") ?? document.body;
    });
    function r() {
      t.setDeploy("idle", "Phase-1 local snapshot (no backend call)."), t.setSyncSummary("sync snapshot: not polled in Phase 1");
    }
    return (o, i) => (de(), mt("section", {
      class: Se(x($s)()),
      "data-testid": "vue-page-backend"
    }, [
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        L("h2", $y, [
          fe(x($c), {
            class: "cmst:size-5",
            "aria-hidden": "true"
          }),
          i[1] || (i[1] = ve(" Manage Modal (Phase-1 proof) ", -1))
        ]),
        i[3] || (i[3] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, [
          ve(" Route key stays "),
          L("code", null, "backend"),
          ve(". Product functionality is intentionally not ported yet. ")
        ], -1)),
        L("div", Vy, [
          L("button", {
            type: "button",
            class: Se(x(gn)("secondary", "sm")),
            onClick: r
          }, " Simulate local snapshot ", 2)
        ]),
        L("p", By, [
          i[2] || (i[2] = ve(" Deploy: ", -1)),
          L("strong", null, Me(x(t).deployState), 1),
          x(t).deployMessage ? (de(), mt("span", zy, " — " + Me(x(t).deployMessage), 1)) : Os("", !0)
        ])
      ], 2),
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        L("h3", Uy, [
          fe(x(dh), {
            class: "cmst:size-4",
            "aria-hidden": "true"
          }),
          i[4] || (i[4] = ve(" Portalled dialog proof (Reka → Studio portal target) ", -1))
        ]),
        fe(x(Kg), {
          open: n.value,
          "onUpdate:open": i[0] || (i[0] = (a) => n.value = a)
        }, {
          default: Ce(() => [
            fe(x(Dy), { "as-child": "" }, {
              default: Ce(() => [
                L("button", {
                  type: "button",
                  class: Se(x(gn)("outline", "sm")),
                  "data-testid": "vue-dialog-open"
                }, " Open Studio dialog ", 2)
              ]),
              _: 1
            }),
            fe(x(Iy), {
              to: s.value ?? void 0
            }, {
              default: Ce(() => [
                fe(x(Ay), { class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:bg-black/60" }),
                fe(x(xy), {
                  class: "cmst:fixed cmst:left-1/2 cmst:top-1/2 cmst:z-[71] cmst:w-[min(28rem,90vw)] cmst:-translate-x-1/2 cmst:-translate-y-1/2 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-5 cmst:text-cmst-fg cmst:shadow-xl",
                  "data-testid": "vue-dialog-content"
                }, {
                  default: Ce(() => [
                    fe(x(Ny), { class: "cmst:text-base cmst:font-semibold" }, {
                      default: Ce(() => [...i[5] || (i[5] = [
                        ve(" Contained in [data-studio-portals] ", -1)
                      ])]),
                      _: 1
                    }),
                    fe(x(ky), { class: "cmst:text-sm cmst:opacity-80 cmst:mt-1" }, {
                      default: Ce(() => [...i[6] || (i[6] = [
                        ve(" This overlay teleports into the Studio portal host, not document.body. Focus returns to the trigger on close. ", -1)
                      ])]),
                      _: 1
                    }),
                    L("div", Wy, [
                      fe(x(Yg), { "as-child": "" }, {
                        default: Ce(() => [
                          L("button", {
                            type: "button",
                            class: Se(x(gn)("default", "sm")),
                            "data-testid": "vue-dialog-close"
                          }, " Close ", 2)
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
      ], 2)
    ], 2));
  }
}), qy = /* @__PURE__ */ rs("studio-history", () => {
  const e = /* @__PURE__ */ se(null), t = /* @__PURE__ */ se("");
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
function Zy() {
  let e = 0, t = null;
  return {
    run: async (s) => {
      e += 1;
      const r = e;
      t && t.abort();
      const o = new AbortController();
      t = o;
      try {
        const i = await s(o.signal);
        return r !== e || o.signal.aborted ? { stale: !0 } : { stale: !1, value: i };
      } catch (i) {
        if (r !== e) return { stale: !0 };
        throw i;
      } finally {
        t === o && (t = null);
      }
    },
    abort: () => {
      t && t.abort();
    },
    get pending() {
      return t !== null;
    }
  };
}
const Gy = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Ky = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, Jy = { class: "cmst:text-sm cmst:mt-2" }, Yy = { "data-testid": "vue-history-stale" }, Qy = /* @__PURE__ */ Ae({
  __name: "HistoryView",
  setup(e) {
    const t = nh(), n = qy(), s = /* @__PURE__ */ se(""), r = /* @__PURE__ */ se(null), o = /* @__PURE__ */ se(0);
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
    const a = Zy();
    async function l() {
      const c = s.value.trim();
      if (c) {
        n.setFocus(c), await t.push({ name: "history", query: { focus: c } });
        try {
          const u = await a.run((f) => i(c, f));
          if (u.stale) {
            o.value += 1;
            return;
          }
          r.value = u.value;
        } catch {
          o.value += 1;
        }
      }
    }
    return (c, u) => (de(), mt("section", {
      class: Se(x($s)()),
      "data-testid": "vue-page-history"
    }, [
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        L("h2", Gy, [
          fe(x(Fc), {
            class: "cmst:size-5",
            "aria-hidden": "true"
          }),
          u[1] || (u[1] = ve(" History (Phase-1 proof) ", -1))
        ]),
        u[5] || (u[5] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Focus identity lives in the history store; detail reads go through the shared latest-read-wins primitive. ", -1)),
        L("div", Ky, [
          Cs(L("input", {
            "onUpdate:modelValue": u[0] || (u[0] = (f) => s.value = f),
            type: "text",
            placeholder: "Focus id (e.g. gen_123)",
            class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm",
            "data-testid": "vue-history-focus-input"
          }, null, 512), [
            [vc, s.value]
          ]),
          L("button", {
            type: "button",
            class: Se(x(gn)("secondary", "sm")),
            "data-testid": "vue-history-focus-apply",
            onClick: l
          }, " Load focus ", 2)
        ]),
        L("p", Jy, [
          u[2] || (u[2] = ve(" Store focus: ", -1)),
          L("strong", null, Me(x(n).focusId ?? "none"), 1),
          u[3] || (u[3] = ve(" · Committed read: ", -1)),
          L("strong", null, Me(r.value ?? "none"), 1),
          u[4] || (u[4] = ve(" · Stale drops: ", -1)),
          L("strong", Yy, Me(o.value), 1)
        ]),
        u[6] || (u[6] = L("p", { class: "cmst:text-xs cmst:opacity-70" }, " Tip: click “Load focus” rapidly with different ids — only the newest read commits; older ones are dropped as stale. ", -1))
      ], 2)
    ], 2));
  }
}), Xy = /* @__PURE__ */ rs("studio-playground", () => {
  const e = /* @__PURE__ */ se("txt2img"), t = /* @__PURE__ */ se(!1);
  function n(r) {
    e.value = r;
  }
  function s(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: n, setExperimentMode: s };
}), ev = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, tv = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, nv = ["checked"], sv = { class: "cmst:text-sm cmst:opacity-80" }, rv = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, ov = ["disabled"], iv = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, av = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, lv = { key: 0 }, cv = /* @__PURE__ */ Ae({
  __name: "PlaygroundView",
  setup(e) {
    const t = Xy(), n = Hc(), s = /* @__PURE__ */ se(null), r = ae(() => s.value ? n.get(s.value)?.progress ?? null : null);
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
    return (i, a) => (de(), mt("section", {
      class: Se(x($s)()),
      "data-testid": "vue-page-playground"
    }, [
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        L("h2", ev, [
          fe(x(Lc), {
            class: "cmst:size-5",
            "aria-hidden": "true"
          }),
          a[1] || (a[1] = ve(" Playground (Phase-1 proof) ", -1))
        ]),
        a[3] || (a[3] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
        L("label", tv, [
          L("input", {
            type: "checkbox",
            checked: x(t).experimentMode,
            onChange: a[0] || (a[0] = (l) => x(t).setExperimentMode(l.target.checked))
          }, null, 40, nv),
          a[2] || (a[2] = ve(" Experiment mode (playground store) ", -1))
        ])
      ], 2),
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        a[5] || (a[5] = L("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
        L("p", sv, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + Me(x(n).active.length) + ". ", 1),
        L("div", rv, [
          L("button", {
            type: "button",
            class: Se(x(gn)("default", "sm")),
            disabled: s.value !== null,
            onClick: o
          }, [
            fe(x(yh), { "aria-hidden": "true" }),
            a[4] || (a[4] = ve(" Run synthetic operation ", -1))
          ], 10, ov),
          r.value !== null ? (de(), mt("span", iv, Me(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : Os("", !0)
        ]),
        L("ul", av, [
          (de(!0), mt(qe, null, ql(x(n).all.slice(-5), (l) => (de(), mt("li", {
            key: l.id,
            "data-testid": "vue-op-row"
          }, [
            L("strong", null, Me(l.label), 1),
            ve(" — " + Me(l.status), 1),
            l.message ? (de(), mt("span", lv, " — " + Me(l.message), 1)) : Os("", !0)
          ]))), 128))
        ])
      ], 2)
    ], 2));
  }
}), uv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, fv = { class: "cmst:text-sm cmst:mt-2" }, dv = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, pv = {
  class: "cmst:text-sm",
  "data-testid": "vue-density-value"
}, hv = /* @__PURE__ */ Ae({
  __name: "SettingsView",
  setup(e) {
    const t = Kc();
    function n() {
      t.setDensity(t.density === "compact" ? "comfortable" : "compact");
    }
    return (s, r) => (de(), mt("section", {
      class: Se(x($s)()),
      "data-testid": "vue-page-settings"
    }, [
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        L("h2", uv, [
          fe(x(Vc), {
            class: "cmst:size-5",
            "aria-hidden": "true"
          }),
          r[0] || (r[0] = ve(" Settings (Phase-1 proof) ", -1))
        ]),
        r[2] || (r[2] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Section identity lives in the settings store. ", -1)),
        L("p", fv, [
          r[1] || (r[1] = ve(" Active section: ", -1)),
          L("strong", null, Me(x(t).activeSection), 1)
        ])
      ], 2),
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        r[3] || (r[3] = L("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Persisted preference proof", -1)),
        r[4] || (r[4] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, [
          ve(" Shell density survives reload via the explicit persistence helper (Zod-validated; malformed data falls back to "),
          L("code", null, "comfortable"),
          ve("). ")
        ], -1)),
        L("div", dv, [
          L("button", {
            type: "button",
            class: Se(x(gn)("outline", "sm")),
            "data-testid": "vue-density-toggle",
            onClick: n
          }, " Toggle density ", 2),
          L("span", pv, Me(x(t).density), 1)
        ])
      ], 2)
    ], 2));
  }
}), mv = /* @__PURE__ */ rs("studio-workflows", () => {
  const e = /* @__PURE__ */ se(null);
  function t(s) {
    e.value = s;
  }
  function n() {
    e.value = null;
  }
  return { selectedId: e, select: t, clear: n };
});
function gv(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function yv(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((n, s) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), n();
    }, e), o = () => {
      clearTimeout(r), s(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((n) => setTimeout(n, e));
}
async function vv(e) {
  const { intervalMs: t, signal: n, run: s, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    gv(n), i += 1, o && o(i);
    const a = await s(n, i);
    if (r(a)) return a;
    await yv(t, n);
  }
}
const bv = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, _v = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3" }, xv = { class: "cmst:text-sm cmst:mt-2" }, wv = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, kv = {
  class: "cmst:text-sm",
  "data-testid": "vue-poll-status"
}, Sv = /* @__PURE__ */ Ae({
  __name: "WorkflowsView",
  setup(e) {
    const t = mv(), n = /* @__PURE__ */ se(""), s = /* @__PURE__ */ se("idle"), r = /* @__PURE__ */ se(0);
    async function o() {
      s.value = "polling…", r.value = 0;
      let i = 0;
      const a = await vv({
        intervalMs: 120,
        run: async (l, c) => (r.value = c, i += 1, i >= 3 ? "ready" : "warming"),
        done: (l) => l === "ready"
      });
      s.value = a;
    }
    return (i, a) => (de(), mt("section", {
      class: Se(x($s)()),
      "data-testid": "vue-page-workflows"
    }, [
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        L("h2", bv, [
          fe(x(jc), {
            class: "cmst:size-5",
            "aria-hidden": "true"
          }),
          a[2] || (a[2] = ve(" Workflows (Phase-1 proof) ", -1))
        ]),
        a[4] || (a[4] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. Selection identity lives in the workflows store. ", -1)),
        L("div", _v, [
          Cs(L("input", {
            "onUpdate:modelValue": a[0] || (a[0] = (l) => n.value = l),
            type: "text",
            placeholder: "Workflow id",
            class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm"
          }, null, 512), [
            [vc, n.value]
          ]),
          L("button", {
            type: "button",
            class: Se(x(gn)("secondary", "sm")),
            onClick: a[1] || (a[1] = (l) => x(t).select(n.value.trim() || null))
          }, " Select ", 2)
        ]),
        L("p", xv, [
          a[3] || (a[3] = ve(" Store selection: ", -1)),
          L("strong", null, Me(x(t).selectedId ?? "none"), 1)
        ])
      ], 2),
      L("div", {
        class: Se(x(sn)("cmst:p-4"))
      }, [
        a[5] || (a[5] = L("h3", { class: "cmst:text-sm cmst:font-semibold" }, "polling demo (local only)", -1)),
        a[6] || (a[6] = L("p", { class: "cmst:text-sm cmst:opacity-80" }, " Repeats a local status check until the completion predicate holds. ", -1)),
        L("div", wv, [
          L("button", {
            type: "button",
            class: Se(x(gn)("outline", "sm")),
            "data-testid": "vue-poll-run",
            onClick: o
          }, " Start local poll ", 2),
          L("span", kv, Me(s.value) + " (" + Me(r.value) + " attempts) ", 1)
        ])
      ], 2)
    ], 2));
  }
}), Ev = {
  playground: cv,
  history: Qy,
  workflows: Sv,
  backend: Hy,
  settings: hv
};
function Cv(e = {}) {
  let t;
  return e.memory || !e.win ? t = Dp() : t = yg(e.win, e.initial), th({
    history: t,
    routes: bi.map((s) => ({
      path: `/${s}`,
      name: s,
      component: Ev[s]
    }))
  });
}
function Av(e, t = {}) {
  const n = Gd(), s = Cv({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = Hd(mg);
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
  Av as mountStudioPreview
};

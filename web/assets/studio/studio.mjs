/**
* @vue/shared v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function ii(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const qe = {}, Ds = [], Gt = () => {
}, wl = () => !1, Nr = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), Mr = (e) => e.startsWith("onUpdate:"), pt = Object.assign, ai = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, $u = Object.prototype.hasOwnProperty, Ue = (e, t) => $u.call(e, t), ge = Array.isArray, xs = (e) => Hn(e) === "[object Map]", ls = (e) => Hn(e) === "[object Set]", Vi = (e) => Hn(e) === "[object Date]", Ae = (e) => typeof e == "function", et = (e) => typeof e == "string", Et = (e) => typeof e == "symbol", Ge = (e) => e !== null && typeof e == "object", _l = (e) => (Ge(e) || Ae(e)) && Ae(e.then) && Ae(e.catch), xl = Object.prototype.toString, Hn = (e) => xl.call(e), Pu = (e) => Hn(e).slice(8, -1), kl = (e) => Hn(e) === "[object Object]", zr = (e) => et(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, Rn = /* @__PURE__ */ ii(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), Dr = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return ((s) => t[s] || (t[s] = e(s)));
}, Nu = /-\w/g, _t = Dr(
  (e) => e.replace(Nu, (t) => t.slice(1).toUpperCase())
), Mu = /\B([A-Z])/g, Es = Dr(
  (e) => e.replace(Mu, "-$1").toLowerCase()
), jr = Dr((e) => e.charAt(0).toUpperCase() + e.slice(1)), to = Dr(
  (e) => e ? `on${jr(e)}` : ""
), Wt = (e, t) => !Object.is(e, t), fr = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Sl = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, Vr = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let Li;
const Lr = () => Li || (Li = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function li(e) {
  if (ge(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], r = et(n) ? Vu(n) : li(n);
      if (r)
        for (const o in r)
          t[o] = r[o];
    }
    return t;
  } else if (et(e) || Ge(e))
    return e;
}
const zu = /;(?![^(]*\))/g, Du = /:([^]+)/, ju = /"(?:[^"\\]|\\[^])*"|'(?:[^'\\]|\\[^])*'|\\[^]|\/\*[^]*?\*\//g;
function Vu(e) {
  const t = {};
  return e.replace(ju, (s) => s.startsWith("/*") ? "" : s).split(zu).forEach((s) => {
    if (s) {
      const n = s.split(Du);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function xt(e) {
  let t = "";
  if (et(e))
    t = e;
  else if (ge(e))
    for (let s = 0; s < e.length; s++) {
      const n = xt(e[s]);
      n && (t += n + " ");
    }
  else if (Ge(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const Lu = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,playsinline,readonly", Uu = /* @__PURE__ */ ii(Lu);
function Cl(e) {
  return !!e || e === "";
}
function Fu(e, t, s) {
  if (e.length !== t.length) return !1;
  let n = !0;
  for (let r = 0; n && r < e.length; r++)
    n = cs(e[r], t[r], s);
  return n;
}
function Ui(e, t, s) {
  if (e.size !== t.size) return !1;
  const n = Array.from(t), r = new Uint8Array(n.length);
  for (const o of e) {
    let i = -1;
    for (let a = 0; a < n.length; a++)
      if (!r[a] && cs(o, n[a], s)) {
        i = a;
        break;
      }
    if (i < 0) return !1;
    r[i] = 1;
  }
  return !0;
}
function Wu(e, t, s) {
  let n = xs(e), r = xs(t);
  if (n || r || (n = ls(e), r = ls(t), n || r))
    return n && r ? Ui(e, t, s) : !1;
  const o = Object.keys(e).length, i = Object.keys(t).length;
  if (o !== i)
    return !1;
  for (const a in e) {
    const l = e.hasOwnProperty(a), c = t.hasOwnProperty(a);
    if (l && !c || !l && c || !cs(e[a], t[a], s))
      return !1;
  }
  return String(e) === String(t);
}
function Fi(e, t, s, n) {
  s || (s = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()]);
  const [r, o] = s;
  if (r.has(e) || o.has(t))
    return r.get(e) === t && o.get(t) === e;
  r.set(e, t), o.set(t, e);
  const i = n(e, t, s);
  return r.delete(e), o.delete(t), i;
}
function cs(e, t, s) {
  if (e === t) return !0;
  let n = Vi(e), r = Vi(t);
  return n || r ? n && r ? e.getTime() === t.getTime() : !1 : (n = Et(e), r = Et(t), n || r ? e === t : (n = ge(e), r = ge(t), n || r ? n && r ? Fi(e, t, s, Fu) : !1 : (n = Ge(e), r = Ge(t), n || r ? !n || !r ? !1 : Fi(e, t, s, Wu) : String(e) === String(t))));
}
function ci(e, t) {
  return e.findIndex((s) => cs(s, t));
}
const Rl = (e) => !!(e && e.__v_isRef === !0), K = (e) => et(e) ? e : e == null ? "" : ge(e) || Ge(e) && (e.toString === xl || !Ae(e.toString)) ? Rl(e) ? K(e.value) : JSON.stringify(e, Al, 2) : String(e), Al = (e, t) => Rl(t) ? Al(e, t.value) : xs(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, r], o) => (s[so(n, o) + " =>"] = r, s),
    {}
  )
} : ls(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => so(s))
} : Et(t) ? so(t) : Ge(t) && !ge(t) && !kl(t) ? String(t) : t, so = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    Et(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let ut;
class El {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t = !1) {
    this.detached = t, this._active = !0, this._on = 0, this.effects = [], this.cleanups = [], this._isPaused = !1, this._warnOnRun = !0, this.__v_skip = !0, !t && ut && (ut.active ? (this.parent = ut, this.index = (ut.scopes || (ut.scopes = [])).push(
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
      const s = ut;
      try {
        return ut = this, t();
      } finally {
        ut = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    ++this._on === 1 && (this.prevScope = ut, ut = this);
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      if (ut === this)
        ut = this.prevScope;
      else {
        let t = ut;
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
function Il(e) {
  return new El(e);
}
function ui() {
  return ut;
}
function Ol(e, t = !1) {
  ut && ut.cleanups.push(e);
}
let Je;
const no = /* @__PURE__ */ new WeakSet();
class Tl {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, ut && (ut.active ? ut.effects.push(this) : this.flags &= -2);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, no.has(this) && (no.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || Pl(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, Wi(this), Nl(this);
    const t = Je, s = Nt;
    Je = this, Nt = !0;
    try {
      return this.fn();
    } finally {
      Ml(this), Je = t, Nt = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        mi(t);
      this.deps = this.depsTail = void 0, Wi(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? no.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    $o(this) && this.run();
  }
  get dirty() {
    return $o(this);
  }
}
let $l = 0, An, En;
function Pl(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = En, En = e;
    return;
  }
  e.next = An, An = e;
}
function di() {
  $l++;
}
function fi() {
  if (--$l > 0)
    return;
  if (En) {
    let t = En;
    for (En = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; An; ) {
    let t = An;
    for (An = void 0; t; ) {
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
function Nl(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function Ml(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const r = n.prevDep;
    n.version === -1 ? (n === s && (s = r), mi(n), Bu(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = r;
  }
  e.deps = t, e.depsTail = s;
}
function $o(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (zl(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function zl(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === Nn) || (e.globalVersion = Nn, !e.isSSR && e.flags & 128 && (!e.deps && !e._dirty || !$o(e))))
    return;
  e.flags |= 2;
  const t = e.dep, s = Je, n = Nt;
  Je = e, Nt = !0;
  try {
    Nl(e);
    const r = e.fn(e._value);
    (t.version === 0 || Wt(r, e._value)) && (e.flags |= 128, e._value = r, t.version++);
  } catch (r) {
    throw t.version++, r;
  } finally {
    Je = s, Nt = n, Ml(e), e.flags &= -3;
  }
}
function mi(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: r } = e;
  if (n && (n.nextSub = r, e.prevSub = void 0), r && (r.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let o = s.computed.deps; o; o = o.nextDep)
      mi(o, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function Bu(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let Nt = !0;
const Dl = [];
function Zt() {
  Dl.push(Nt), Nt = !1;
}
function Kt() {
  const e = Dl.pop();
  Nt = e === void 0 ? !0 : e;
}
function Wi(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = Je;
    Je = void 0;
    try {
      t();
    } finally {
      Je = s;
    }
  }
}
let Nn = 0;
class Gu {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class pi {
  // TODO isolatedDeclarations "__v_skip"
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0, this.__v_skip = !0;
  }
  track(t) {
    if (!Je || !Nt || Je === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== Je)
      s = this.activeLink = new Gu(Je, this), Je.deps ? (s.prevDep = Je.depsTail, Je.depsTail.nextDep = s, Je.depsTail = s) : Je.deps = Je.depsTail = s, jl(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = Je.depsTail, s.nextDep = void 0, Je.depsTail.nextDep = s, Je.depsTail = s, Je.deps === s && (Je.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, Nn++, this.notify(t);
  }
  notify(t) {
    di();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      fi();
    }
  }
}
function jl(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        jl(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const gr = /* @__PURE__ */ new WeakMap(), Vs = /* @__PURE__ */ Symbol(
  ""
), Po = /* @__PURE__ */ Symbol(
  ""
), Mn = /* @__PURE__ */ Symbol(
  ""
);
function ht(e, t, s) {
  if (Nt && Je) {
    let n = gr.get(e);
    n || gr.set(e, n = /* @__PURE__ */ new Map());
    let r = n.get(s);
    r || (n.set(s, r = new pi()), r.map = n, r.key = s), r.track();
  }
}
function ns(e, t, s, n, r, o) {
  const i = gr.get(e);
  if (!i) {
    Nn++;
    return;
  }
  const a = (l) => {
    l && l.trigger();
  };
  if (di(), t === "clear")
    i.forEach(a);
  else {
    const l = ge(e), c = l && zr(s);
    if (l && s === "length") {
      const u = Number(n);
      i.forEach((f, h) => {
        (h === "length" || h === Mn || !Et(h) && h >= u) && a(f);
      });
    } else
      switch ((s !== void 0 || i.has(void 0)) && a(i.get(s)), c && a(i.get(Mn)), t) {
        case "add":
          l ? c && a(i.get("length")) : (a(i.get(Vs)), xs(e) && a(i.get(Po)));
          break;
        case "delete":
          l || (a(i.get(Vs)), xs(e) && a(i.get(Po)));
          break;
        case "set":
          xs(e) && a(i.get(Vs));
          break;
      }
  }
  fi();
}
function Hu(e, t) {
  const s = gr.get(e);
  return s && s.get(t);
}
function Gs(e) {
  const t = /* @__PURE__ */ De(e);
  return t === e || (ht(t, "iterate", Mn), /* @__PURE__ */ At(e)) ? t : /* @__PURE__ */ Jt(e) ? /* @__PURE__ */ Ht(e) ? t.map((s) => Cs(Ot(s))) : t.map(Cs) : t.map(Ot);
}
function Ur(e) {
  return ht(e = /* @__PURE__ */ De(e), "iterate", Mn), e;
}
function Lt(e, t) {
  return /* @__PURE__ */ Jt(e) ? Cs(/* @__PURE__ */ Ht(e) ? Ot(t) : t) : Ot(t);
}
const qu = {
  __proto__: null,
  [Symbol.iterator]() {
    return ro(this, Symbol.iterator, (e) => Lt(this, e));
  },
  concat(...e) {
    return Gs(this).concat(
      ...e.map((t) => ge(t) ? Gs(t) : t)
    );
  },
  entries() {
    return ro(this, "entries", (e) => (e[1] = Lt(this, e[1]), e));
  },
  every(e, t) {
    return Yt(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return Yt(
      this,
      "filter",
      e,
      t,
      (s) => s.map((n) => Lt(this, n)),
      arguments
    );
  },
  find(e, t) {
    return Yt(
      this,
      "find",
      e,
      t,
      (s) => Lt(this, s),
      arguments
    );
  },
  findIndex(e, t) {
    return Yt(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return Yt(
      this,
      "findLast",
      e,
      t,
      (s) => Lt(this, s),
      arguments
    );
  },
  findLastIndex(e, t) {
    return Yt(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return Yt(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return oo(this, "includes", e);
  },
  indexOf(...e) {
    return oo(this, "indexOf", e);
  },
  join(e) {
    return Gs(this).join(e);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...e) {
    return oo(this, "lastIndexOf", e);
  },
  map(e, t) {
    return Yt(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return pn(this, "pop");
  },
  push(...e) {
    return pn(this, "push", e);
  },
  reduce(e, ...t) {
    return Gi(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return Gi(this, "reduceRight", e, t);
  },
  shift() {
    return pn(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return Yt(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return pn(this, "splice", e);
  },
  toReversed() {
    return Gs(this).toReversed();
  },
  toSorted(e) {
    return Gs(this).toSorted(e);
  },
  toSpliced(...e) {
    return Gs(this).toSpliced(...e);
  },
  unshift(...e) {
    return pn(this, "unshift", e);
  },
  values() {
    return ro(this, "values", (e) => Lt(this, e));
  }
};
function ro(e, t, s) {
  const n = Ur(e), r = n[t], o = r.call(n);
  if (n !== e && !/* @__PURE__ */ At(e)) {
    if (o[Symbol.toStringTag] === "Array Iterator") {
      const i = Object.create(Object.getPrototypeOf(o));
      return i.next = () => Bi(o.next(), s), r !== Vl[t] && Object.defineProperties(i, {
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
    o._next = o.next, o.next = () => Bi(o._next(), s);
  }
  return o;
}
function Bi(e, t) {
  return e.done || (e.value = t(e.value)), e;
}
const Vl = Array.prototype;
function Yt(e, t, s, n, r, o) {
  const i = Ur(e), a = i !== e && !/* @__PURE__ */ At(e), l = i[t];
  if (l !== Vl[t]) {
    const f = l.apply(e, o);
    return a ? Ot(f) : f;
  }
  let c = s;
  i !== e && (a ? c = function(f, h) {
    return s.call(this, Lt(e, f), h, e);
  } : s.length > 2 && (c = function(f, h) {
    return s.call(this, f, h, e);
  }));
  const u = l.call(i, c, n);
  return a && r ? r(u) : u;
}
function Gi(e, t, s, n) {
  const r = Ur(e), o = r !== e && !/* @__PURE__ */ At(e);
  let i = s, a = !1;
  r !== e && (o ? (a = n.length === 0, i = function(c, u, f) {
    return a && (a = !1, c = Lt(e, c)), s.call(this, c, Lt(e, u), f, e);
  }) : s.length > 3 && (i = function(c, u, f) {
    return s.call(this, c, u, f, e);
  }));
  const l = r[t](i, ...n);
  return a ? Lt(e, l) : l;
}
function oo(e, t, s) {
  const n = /* @__PURE__ */ De(e);
  ht(n, "iterate", Mn);
  const r = n[t](...s);
  return (r === -1 || r === !1) && /* @__PURE__ */ Fr(s[0]) ? (s[0] = /* @__PURE__ */ De(s[0]), n[t](...s)) : r;
}
function pn(e, t, s = []) {
  Zt(), di();
  const n = (/* @__PURE__ */ De(e))[t].apply(e, s);
  return fi(), Kt(), n;
}
const Zu = /* @__PURE__ */ ii("__proto__,__v_isRef,__isVue"), Ll = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(Et)
);
function Ku(e) {
  Et(e) || (e = String(e));
  const t = /* @__PURE__ */ De(this);
  return ht(t, "has", e), t.hasOwnProperty(e);
}
class Ul {
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
      return n === (r ? o ? od : Gl : o ? Bl : Wl).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const i = ge(t);
    if (!r) {
      let l;
      if (i && (l = qu[s]))
        return l;
      if (s === "hasOwnProperty")
        return Ku;
    }
    const a = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      /* @__PURE__ */ ot(t) ? t : n
    );
    if ((Et(s) ? Ll.has(s) : Zu(s)) || (r || ht(t, "get", s), o))
      return a;
    if (/* @__PURE__ */ ot(a)) {
      const l = i && zr(s) ? a : a.value;
      return r && Ge(l) ? /* @__PURE__ */ Mo(l) : l;
    }
    return Ge(a) ? r ? /* @__PURE__ */ Mo(a) : /* @__PURE__ */ qn(a) : a;
  }
}
class Fl extends Ul {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, r) {
    let o = t[s];
    const i = ge(t) && zr(s);
    if (!this._isShallow) {
      const c = /* @__PURE__ */ Jt(o);
      if (!/* @__PURE__ */ At(n) && !/* @__PURE__ */ Jt(n) && (o = /* @__PURE__ */ De(o), n = /* @__PURE__ */ De(n)), !i && /* @__PURE__ */ ot(o) && !/* @__PURE__ */ ot(n))
        return c || (o.value = n), !0;
    }
    const a = i ? Number(s) < t.length : Ue(t, s), l = Reflect.set(
      t,
      s,
      n,
      /* @__PURE__ */ ot(t) ? t : r
    );
    return t === /* @__PURE__ */ De(r) && l && (a ? Wt(n, o) && ns(t, "set", s, n) : ns(t, "add", s, n)), l;
  }
  deleteProperty(t, s) {
    const n = Ue(t, s);
    t[s];
    const r = Reflect.deleteProperty(t, s);
    return r && n && ns(t, "delete", s, void 0), r;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!Et(s) || !Ll.has(s)) && ht(t, "has", s), n;
  }
  ownKeys(t) {
    return ht(
      t,
      "iterate",
      ge(t) ? "length" : Vs
    ), Reflect.ownKeys(t);
  }
}
class Ju extends Ul {
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
const Qu = /* @__PURE__ */ new Fl(), Yu = /* @__PURE__ */ new Ju(), Xu = /* @__PURE__ */ new Fl(!0);
const No = (e) => e, Yn = (e) => Reflect.getPrototypeOf(e);
function ed(e, t, s) {
  return function(...n) {
    const r = this.__v_raw, o = /* @__PURE__ */ De(r), i = xs(o), a = e === "entries" || e === Symbol.iterator && i, l = e === "keys" && i, c = r[e](...n), u = s ? No : t ? Cs : Ot;
    return !t && ht(
      o,
      "iterate",
      l ? Po : Vs
    ), pt(
      // inheriting all iterator properties
      Object.create(c),
      {
        // iterator protocol
        next() {
          const { value: f, done: h } = c.next();
          return h ? { value: f, done: h } : {
            value: a ? [u(f[0]), u(f[1])] : u(f),
            done: h
          };
        }
      }
    );
  };
}
function Xn(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function td(e, t) {
  const s = {
    get(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ De(o), a = /* @__PURE__ */ De(r);
      e || (Wt(r, a) && ht(i, "get", r), ht(i, "get", a));
      const { has: l } = Yn(i), c = t ? No : e ? Cs : Ot;
      if (l.call(i, r))
        return c(o.get(r));
      if (l.call(i, a))
        return c(o.get(a));
      o !== i && o.get(r);
    },
    get size() {
      const r = this.__v_raw;
      return !e && ht(/* @__PURE__ */ De(r), "iterate", Vs), r.size;
    },
    has(r) {
      const o = this.__v_raw, i = /* @__PURE__ */ De(o), a = /* @__PURE__ */ De(r);
      return e || (Wt(r, a) && ht(i, "has", r), ht(i, "has", a)), r === a ? o.has(r) : o.has(r) || o.has(a);
    },
    forEach(r, o) {
      const i = this, a = i.__v_raw, l = /* @__PURE__ */ De(a), c = t ? No : e ? Cs : Ot;
      return !e && ht(l, "iterate", Vs), a.forEach((u, f) => r.call(o, c(u), c(f), i));
    }
  };
  return pt(
    s,
    e ? {
      add: Xn("add"),
      set: Xn("set"),
      delete: Xn("delete"),
      clear: Xn("clear")
    } : {
      add(r) {
        const o = /* @__PURE__ */ De(this), i = Yn(o), a = /* @__PURE__ */ De(r), l = !t && !/* @__PURE__ */ At(r) && !/* @__PURE__ */ Jt(r) ? a : r;
        return i.has.call(o, l) || Wt(r, l) && i.has.call(o, r) || Wt(a, l) && i.has.call(o, a) || (o.add(l), ns(o, "add", l, l)), this;
      },
      set(r, o) {
        !t && !/* @__PURE__ */ At(o) && !/* @__PURE__ */ Jt(o) && (o = /* @__PURE__ */ De(o));
        const i = /* @__PURE__ */ De(this), { has: a, get: l } = Yn(i);
        let c = a.call(i, r);
        c || (r = /* @__PURE__ */ De(r), c = a.call(i, r));
        const u = l.call(i, r);
        return i.set(r, o), c ? Wt(o, u) && ns(i, "set", r, o) : ns(i, "add", r, o), this;
      },
      delete(r) {
        const o = /* @__PURE__ */ De(this), { has: i, get: a } = Yn(o);
        let l = i.call(o, r);
        l || (r = /* @__PURE__ */ De(r), l = i.call(o, r)), a && a.call(o, r);
        const c = o.delete(r);
        return l && ns(o, "delete", r, void 0), c;
      },
      clear() {
        const r = /* @__PURE__ */ De(this), o = r.size !== 0, i = r.clear();
        return o && ns(
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
    s[r] = ed(r, e, t);
  }), s;
}
function hi(e, t) {
  const s = td(e, t);
  return (n, r, o) => r === "__v_isReactive" ? !e : r === "__v_isReadonly" ? e : r === "__v_isShallow" ? t : r === "__v_raw" ? n : Reflect.get(
    Ue(s, r) && r in n ? s : n,
    r,
    o
  );
}
const sd = {
  get: /* @__PURE__ */ hi(!1, !1)
}, nd = {
  get: /* @__PURE__ */ hi(!1, !0)
}, rd = {
  get: /* @__PURE__ */ hi(!0, !1)
};
const Wl = /* @__PURE__ */ new WeakMap(), Bl = /* @__PURE__ */ new WeakMap(), Gl = /* @__PURE__ */ new WeakMap(), od = /* @__PURE__ */ new WeakMap();
function id(e) {
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
function qn(e) {
  return /* @__PURE__ */ Jt(e) ? e : gi(
    e,
    !1,
    Qu,
    sd,
    Wl
  );
}
// @__NO_SIDE_EFFECTS__
function Hl(e) {
  return gi(
    e,
    !1,
    Xu,
    nd,
    Bl
  );
}
// @__NO_SIDE_EFFECTS__
function Mo(e) {
  return gi(
    e,
    !0,
    Yu,
    rd,
    Gl
  );
}
function gi(e, t, s, n, r) {
  if (!Ge(e) || e.__v_raw && !(t && e.__v_isReactive) || e.__v_skip || !Object.isExtensible(e))
    return e;
  const o = r.get(e);
  if (o)
    return o;
  const i = id(Pu(e));
  if (i === 0)
    return e;
  const a = new Proxy(
    e,
    i === 2 ? n : s
  );
  return r.set(e, a), a;
}
// @__NO_SIDE_EFFECTS__
function Ht(e) {
  return /* @__PURE__ */ Jt(e) ? /* @__PURE__ */ Ht(e.__v_raw) : !!(e && e.__v_isReactive);
}
// @__NO_SIDE_EFFECTS__
function Jt(e) {
  return !!(e && e.__v_isReadonly);
}
// @__NO_SIDE_EFFECTS__
function At(e) {
  return !!(e && e.__v_isShallow);
}
// @__NO_SIDE_EFFECTS__
function Fr(e) {
  return e ? !!e.__v_raw : !1;
}
// @__NO_SIDE_EFFECTS__
function De(e) {
  const t = e && e.__v_raw;
  return t ? /* @__PURE__ */ De(t) : e;
}
function vi(e) {
  return !Ue(e, "__v_skip") && Object.isExtensible(e) && Sl(e, "__v_skip", !0), e;
}
const Ot = (e) => Ge(e) ? /* @__PURE__ */ qn(e) : e, Cs = (e) => Ge(e) ? /* @__PURE__ */ Mo(e) : e;
// @__NO_SIDE_EFFECTS__
function ot(e) {
  return e ? e.__v_isRef === !0 : !1;
}
// @__NO_SIDE_EFFECTS__
function E(e) {
  return ql(e, !1);
}
// @__NO_SIDE_EFFECTS__
function In(e) {
  return ql(e, !0);
}
function ql(e, t) {
  return /* @__PURE__ */ ot(e) ? e : new ad(e, t);
}
class ad {
  constructor(t, s) {
    this.dep = new pi(), this.__v_isRef = !0, this.__v_isShallow = !1, this._rawValue = s ? t : /* @__PURE__ */ De(t), this._value = s ? t : Ot(t), this.__v_isShallow = s;
  }
  get value() {
    return this.dep.track(), this._value;
  }
  set value(t) {
    const s = this._rawValue, n = this.__v_isShallow || /* @__PURE__ */ At(t) || /* @__PURE__ */ Jt(t);
    t = n ? t : /* @__PURE__ */ De(t), Wt(t, s) && (this._rawValue = t, this._value = n ? t : Ot(t), this.dep.trigger());
  }
}
function g(e) {
  return /* @__PURE__ */ ot(e) ? e.value : e;
}
function Ys(e) {
  return Ae(e) ? e() : g(e);
}
const ld = {
  get: (e, t, s) => t === "__v_raw" ? e : g(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const r = e[t];
    return /* @__PURE__ */ ot(r) && !/* @__PURE__ */ ot(s) ? (r.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function Zl(e) {
  return /* @__PURE__ */ Ht(e) ? e : new Proxy(e, ld);
}
// @__NO_SIDE_EFFECTS__
function cd(e) {
  const t = ge(e) ? new Array(e.length) : {};
  for (const s in e)
    t[s] = dd(e, s);
  return t;
}
class ud {
  constructor(t, s, n) {
    this._object = t, this._defaultValue = n, this.__v_isRef = !0, this._value = void 0, this._key = Et(s) ? s : String(s), this._raw = /* @__PURE__ */ De(t);
    let r = !0, o = t;
    if (!ge(t) || Et(this._key) || !zr(this._key))
      do
        r = !/* @__PURE__ */ Fr(o) || /* @__PURE__ */ At(o);
      while (r && (o = o.__v_raw));
    this._shallow = r;
  }
  get value() {
    let t = this._object[this._key];
    return this._shallow && (t = g(t)), this._value = t === void 0 ? this._defaultValue : t;
  }
  set value(t) {
    if (this._shallow && /* @__PURE__ */ ot(this._raw[this._key])) {
      const s = this._object[this._key];
      if (/* @__PURE__ */ ot(s)) {
        s.value = t;
        return;
      }
    }
    this._object[this._key] = t;
  }
  get dep() {
    return Hu(this._raw, this._key);
  }
}
function dd(e, t, s) {
  return new ud(e, t, s);
}
class fd {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new pi(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = Nn - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    Je !== this)
      return Pl(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return zl(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
// @__NO_SIDE_EFFECTS__
function md(e, t, s = !1) {
  let n, r;
  return Ae(e) ? n = e : (n = e.get, r = e.set), new fd(n, r, s);
}
const er = {}, vr = /* @__PURE__ */ new WeakMap();
let Ms;
function pd(e, t = !1, s = Ms) {
  if (s) {
    let n = vr.get(s);
    n || vr.set(s, n = []), n.push(e);
  }
}
function hd(e, t, s = qe) {
  const { immediate: n, deep: r, once: o, scheduler: i, augmentJob: a, call: l } = s, c = (q) => r ? q : /* @__PURE__ */ At(q) || r === !1 || r === 0 ? rs(q, 1) : rs(q);
  let u, f, h, d, y = !1, C = !1;
  if (/* @__PURE__ */ ot(e) ? (f = () => e.value, y = /* @__PURE__ */ At(e)) : /* @__PURE__ */ Ht(e) ? (f = () => c(e), y = !0) : ge(e) ? (C = !0, y = e.some((q) => /* @__PURE__ */ Ht(q) || /* @__PURE__ */ At(q)), f = () => e.map((q) => {
    if (/* @__PURE__ */ ot(q))
      return q.value;
    if (/* @__PURE__ */ Ht(q))
      return c(q);
    if (Ae(q))
      return l ? l(q, 2) : q();
  })) : Ae(e) ? t ? f = l ? () => l(e, 2) : e : f = () => {
    if (h) {
      Zt();
      try {
        h();
      } finally {
        Kt();
      }
    }
    const q = Ms;
    Ms = u;
    try {
      return l ? l(e, 3, [d]) : e(d);
    } finally {
      Ms = q;
    }
  } : f = Gt, t && r) {
    const q = f, ae = r === !0 ? 1 / 0 : r;
    f = () => rs(q(), ae);
  }
  const U = ui(), Q = () => {
    u.stop(), U && U.active && ai(U.effects, u);
  };
  if (o && t) {
    const q = t;
    t = (...ae) => {
      try {
        return q(...ae);
      } finally {
        Q();
      }
    };
  }
  let B = C ? new Array(e.length).fill(er) : er;
  const Y = (q) => {
    if (!(!(u.flags & 1) || !u.dirty && !q))
      if (t) {
        const ae = u.run();
        if (q || r || y || (C ? ae.some((ye, re) => Wt(ye, B[re])) : Wt(ae, B))) {
          const ye = Ms;
          Zt();
          try {
            h && h(), Ms = u;
            const re = [
              ae,
              // pass undefined as the old value when it's changed for the first time
              B === er ? void 0 : C && B[0] === er ? [] : B,
              d
            ];
            B = ae, l ? l(t, 3, re) : (
              // @ts-expect-error
              t(...re)
            );
          } finally {
            Ms = ye, Kt();
          }
        }
      } else
        u.run();
  };
  return a && a(Y), u = new Tl(f), u.scheduler = i ? () => i(Y, !1) : Y, d = (q) => pd(q, !1, u), h = u.onStop = () => {
    const q = vr.get(u);
    if (q) {
      if (l)
        l(q, 4);
      else
        for (const ae of q) ae();
      vr.delete(u);
    }
  }, t ? n ? Y(!0) : B = u.run() : i ? i(Y.bind(null, !0), !0) : u.run(), Q.pause = u.pause.bind(u), Q.resume = u.resume.bind(u), Q.stop = Q, Q;
}
function rs(e, t = 1 / 0, s) {
  if (t <= 0 || !Ge(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Map(), (s.get(e) || 0) >= t))
    return e;
  if (s.set(e, t), t--, /* @__PURE__ */ ot(e))
    rs(e.value, t, s);
  else if (ge(e))
    for (let n = 0; n < e.length; n++)
      rs(e[n], t, s);
  else if (ls(e) || xs(e))
    e.forEach((n) => {
      rs(n, t, s);
    });
  else if (kl(e)) {
    for (const n in e)
      rs(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && rs(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function Zn(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (r) {
    Wr(r, t, s);
  }
}
function Mt(e, t, s, n) {
  if (Ae(e)) {
    const r = Zn(e, t, s, n);
    return r && _l(r) && r.catch((o) => {
      Wr(o, t, s);
    }), r;
  }
  if (ge(e)) {
    const r = [];
    for (let o = 0; o < e.length; o++)
      r.push(Mt(e[o], t, s, n));
    return r;
  }
}
function Wr(e, t, s, n = !0) {
  const r = t ? t.vnode : null, { errorHandler: o, throwUnhandledErrorInProduction: i } = t && t.appContext.config || qe;
  if (t) {
    let a = t.parent;
    const l = t.proxy, c = `https://vuejs.org/error-reference/#runtime-${s}`;
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
      Zt(), Zn(o, null, 10, [
        e,
        l,
        c
      ]), Kt();
      return;
    }
  }
  gd(e, s, r, n, i);
}
function gd(e, t, s, n = !0, r = !1) {
  if (r)
    throw e;
  console.error(e);
}
const wt = [];
let Pt = -1;
const Ut = [];
let ys = null, Zs = 0;
const Kl = /* @__PURE__ */ Promise.resolve();
let yr = null;
function Br(e) {
  const t = yr || Kl;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function vd(e) {
  let t = Pt + 1, s = wt.length;
  for (; t < s; ) {
    const n = t + s >>> 1, r = wt[n], o = zn(r);
    o < e || o === e && r.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function yi(e) {
  if (!(e.flags & 1)) {
    const t = zn(e), s = wt[wt.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= zn(s) ? wt.push(e) : wt.splice(vd(t), 0, e), e.flags |= 1, Jl();
  }
}
function Jl() {
  yr || (yr = Kl.then(Xl));
}
function yd(e) {
  if (!ge(e))
    ys && e.id === -1 ? ys.splice(Zs + 1, 0, e) : e.flags & 1 || (Ut.push(e), e.flags |= 1);
  else
    for (let t = 0; t < e.length; t++)
      Ut.push(e[t]);
  Jl();
}
function Ql(e, t, s, n = Pt + 1) {
  for (; n < wt.length; n++) {
    const r = wt[n];
    if (r && r.flags & 2) {
      if (e && r.id !== e.uid || t !== void 0 && !(r.id >= t))
        continue;
      wt.splice(n, 1), n = e ? n - 1 : Pt, r.flags & 4 && (r.flags &= -2), r(), r.flags & 4 || (r.flags &= -2);
    }
  }
}
function Yl(e, t, s = 0) {
  if (Ut.length) {
    let n = Ut, r = 0;
    if (t) {
      n = [];
      for (let i = 0; i < Ut.length; i++) {
        const a = Ut[i];
        (a.i !== void 0 ? !a.i || a.i.uid < s : t.has(a)) ? Ut[r++] = a : n.push(a);
      }
    }
    const o = [...new Set(n)].sort((i, a) => zn(i) - zn(a));
    if (Ut.length = r, ys) {
      for (let i = 0; i < o.length; i++)
        ys.push(o[i]);
      return;
    }
    for (ys = o, Zs = 0; Zs < ys.length; Zs++) {
      const i = ys[Zs];
      i.flags & 4 && (i.flags &= -2), i.flags & 8 || i(), i.flags &= -2;
    }
    ys = null, Zs = 0;
  }
}
let io = !1;
function bd(e, t) {
  if (io) {
    e();
    return;
  }
  const s = t === void 0 ? void 0 : new Set(Ut);
  e(), io = !0;
  try {
    Ql(void 0, t), Yl(void 0, s, t);
  } finally {
    io = !1;
  }
}
const zn = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function Xl(e) {
  try {
    for (Pt = 0; Pt < wt.length; Pt++) {
      const t = wt[Pt];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), Zn(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; Pt < wt.length; Pt++) {
      const t = wt[Pt];
      t && (t.flags &= -2);
    }
    Pt = -1, wt.length = 0, Yl(), yr = null, (wt.length || Ut.length) && Xl();
  }
}
let mt = null, ec = null;
function br(e) {
  const t = mt;
  return mt = e, ec = e && e.type.__scopeId || null, t;
}
function F(e, t = mt, s) {
  if (!t || e._n)
    return e;
  const n = (...r) => {
    n._d && kr(-1);
    const o = br(t), i = as.length;
    let a;
    try {
      a = e(...r);
    } finally {
      for (let l = as.length; l > i; l--) Ri();
      br(o), n._d && kr(1);
    }
    return a;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Pe(e, t) {
  if (mt === null)
    return e;
  const s = Jr(mt), n = e.dirs || (e.dirs = []);
  for (let r = 0; r < t.length; r++) {
    let [o, i, a, l = qe] = t[r];
    o && (Ae(o) && (o = {
      mounted: o,
      updated: o
    }), o.deep && rs(i), n.push({
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
function Ts(e, t, s, n) {
  const r = e.dirs, o = t && t.dirs;
  for (let i = 0; i < r.length; i++) {
    const a = r[i];
    o && (a.oldValue = o[i].value);
    let l = a.dir[n];
    l && (Zt(), Mt(l, s, 8, [
      e.el,
      a,
      e,
      t
    ]), Kt());
  }
}
function mr(e, t) {
  if (gt) {
    let s = gt.provides;
    const n = gt.parent && gt.parent.provides;
    n === s && (s = gt.provides = Object.create(n)), s[e] = t;
  }
}
function Ct(e, t, s = !1) {
  const n = Kr();
  if (n || Ls) {
    let r = Ls ? Ls._context.provides : n ? n.parent == null || n.ce ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (r && e in r)
      return r[e];
    if (arguments.length > 1)
      return s && Ae(t) ? t.call(n && n.proxy) : t;
  }
}
function bi() {
  return !!(Kr() || Ls);
}
const wd = /* @__PURE__ */ Symbol.for("v-scx"), _d = () => Ct(wd);
function xd(e, t) {
  return wi(e, null, t);
}
function ks(e, t, s) {
  return wi(e, t, s);
}
function wi(e, t, s = qe) {
  const { immediate: n, deep: r, flush: o, once: i } = s, a = pt({}, s), l = t && n || !t && o !== "post";
  let c;
  if (Vn) {
    if (o === "sync") {
      const d = _d();
      c = d.__watcherHandles || (d.__watcherHandles = []);
    } else if (!l) {
      const d = () => {
      };
      return d.stop = Gt, d.resume = Gt, d.pause = Gt, d;
    }
  }
  const u = gt;
  a.call = (d, y, C) => Mt(d, u, y, C);
  let f = !1;
  o === "post" ? a.scheduler = (d) => {
    d.i = u, yt(d, u && u.suspense);
  } : o !== "sync" && (f = !0, a.scheduler = (d, y) => {
    y ? d() : yi(d);
  }), a.augmentJob = (d) => {
    t && (d.flags |= 4), f && (d.flags |= 2, u && (d.id = u.uid, d.i = u));
  };
  const h = hd(e, t, a);
  return Vn && (c ? c.push(h) : l && h()), h;
}
function kd(e, t, s) {
  const n = this.proxy, r = et(e) ? e.includes(".") ? tc(n, e) : () => n[e] : e.bind(n, n);
  let o;
  Ae(t) ? o = t : (o = t.handler, s = t);
  const i = Kn(this), a = wi(r, o.bind(n), s);
  return i(), a;
}
function tc(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let r = 0; r < s.length && n; r++)
      n = n[s[r]];
    return n;
  };
}
const hs = /* @__PURE__ */ new WeakMap(), sc = /* @__PURE__ */ Symbol("_vte"), Gr = (e) => e.__isTeleport, zs = (e) => e && (e.disabled || e.disabled === ""), Sd = (e) => e && (e.defer || e.defer === ""), Hi = (e) => typeof SVGElement < "u" && e instanceof SVGElement, qi = (e) => typeof MathMLElement == "function" && e instanceof MathMLElement, zo = (e, t) => {
  const s = e && e.to;
  return et(s) ? t ? t(s) : null : s;
}, Cd = {
  name: "Teleport",
  __isTeleport: !0,
  process(e, t, s, n, r, o, i, a, l, c) {
    const {
      mc: u,
      pc: f,
      pbc: h,
      o: { insert: d, querySelector: y, createText: C, createComment: U, parentNode: Q }
    } = c, B = zs(t.props);
    let { dynamicChildren: Y } = t;
    const q = (re, j, H) => {
      re.shapeFlag & 16 && u(
        re.children,
        j,
        H,
        r,
        o,
        i,
        a,
        l
      );
    }, ae = (re = t) => {
      const j = zs(re.props), H = re.target = zo(re.props, y), x = Do(H, re, C, d);
      H && (i !== "svg" && Hi(H) ? i = "svg" : i !== "mathml" && qi(H) && (i = "mathml"), r && r.isCE && (r.ce._teleportTargets || (r.ce._teleportTargets = /* @__PURE__ */ new Set())).add(H), j || (q(re, H, x), _n(re, !1)));
    }, ye = (re) => {
      const j = () => {
        if (hs.get(re) === j) {
          if (hs.delete(re), zs(re.props)) {
            const H = Q(re.el) || s;
            q(re, H, re.anchor), _n(re, !0);
          }
          ae(re);
        }
      };
      hs.set(re, j), yt(j, o);
    };
    if (e == null) {
      const re = t.el = C(""), j = t.anchor = C("");
      if (d(re, s, n), d(j, s, n), Sd(t.props) || o && o.pendingBranch) {
        ye(t);
        return;
      }
      B && (q(t, s, j), _n(t, !0)), ae();
    } else {
      t.el = e.el;
      const re = t.anchor = e.anchor, j = hs.get(e);
      if (j) {
        j.flags |= 8, hs.delete(e), ye(t);
        return;
      }
      t.targetStart = e.targetStart;
      const H = t.target = e.target, x = t.targetAnchor = e.targetAnchor, G = zs(e.props), S = G ? s : H, X = G ? re : x;
      if (i === "svg" || Hi(H) ? i = "svg" : (i === "mathml" || qi(H)) && (i = "mathml"), Y ? (h(
        e.dynamicChildren,
        Y,
        S,
        r,
        o,
        i,
        a
      ), Ci(e, t, !0)) : l || f(
        e,
        t,
        S,
        X,
        r,
        o,
        i,
        a,
        !1
      ), B)
        G ? t.props && e.props && t.props.to !== e.props.to && (t.props.to = e.props.to) : tr(
          t,
          s,
          re,
          c,
          1
        );
      else if ((t.props && t.props.to) !== (e.props && e.props.to)) {
        const ke = zo(t.props, y);
        ke && (t.target = ke, tr(
          t,
          ke,
          null,
          c,
          0
        ));
      } else G && tr(
        t,
        H,
        x,
        c,
        1
      );
      _n(t, B);
    }
  },
  remove(e, t, s, { um: n, o: { remove: r } }, o) {
    const {
      shapeFlag: i,
      children: a,
      anchor: l,
      targetStart: c,
      targetAnchor: u,
      target: f,
      props: h
    } = e, d = zs(h), y = o || !d, C = hs.get(e);
    if (C && (C.flags |= 8, hs.delete(e)), f && (r(c), r(u)), o && r(l), !C && (d || f) && i & 16)
      for (let U = 0; U < a.length; U++) {
        const Q = a[U];
        n(
          Q,
          t,
          s,
          y,
          !!Q.dynamicChildren
        );
      }
  },
  move: tr,
  hydrate: Rd
};
function tr(e, t, s, { o: { insert: n }, m: r }, o = 2) {
  o === 0 && (e.targetStart && n(e.targetStart, t, s), n(e.targetAnchor, t, s), s = e.targetAnchor);
  const { el: i, anchor: a, shapeFlag: l, children: c, props: u } = e, f = o === 2;
  if (f && n(i, t, s), !hs.has(e) && (!f || zs(u)) && l & 16)
    for (let h = 0; h < c.length; h++)
      r(
        c[h],
        t,
        s,
        2
      );
  f && n(a, t, s);
}
function Rd(e, t, s, n, r, o, {
  o: { nextSibling: i, parentNode: a, querySelector: l, insert: c, createText: u }
}, f) {
  function h(U, Q) {
    let B = Q;
    for (; B; ) {
      if (B && B.nodeType === 8) {
        if (B.data === "teleport start anchor")
          t.targetStart = B;
        else if (B.data === "teleport anchor") {
          t.targetAnchor = B, U._lpa = t.targetAnchor && i(t.targetAnchor);
          break;
        }
      }
      B = i(B);
    }
  }
  function d(U, Q) {
    Q.anchor = f(
      i(U),
      Q,
      a(U),
      s,
      n,
      r,
      o
    );
  }
  const y = t.target = zo(
    t.props,
    l
  ), C = zs(t.props);
  if (y) {
    const U = y._lpa || y.firstChild;
    t.shapeFlag & 16 && (C ? (d(e, t), h(y, U), t.targetAnchor || Do(
      y,
      t,
      u,
      c,
      // if target is the same as the main view, insert anchors before current node
      // to avoid hydrating mismatch
      a(e) === y ? e : null
    )) : (t.anchor = i(e), h(y, U), t.targetAnchor || Do(y, t, u, c), f(
      U && i(U),
      t,
      y,
      s,
      n,
      r,
      o
    ))), _n(t, C);
  } else C && t.shapeFlag & 16 && (d(e, t), t.targetStart = e, t.targetAnchor = i(e));
  return t.anchor && i(t.anchor);
}
const Ad = Cd;
function _n(e, t) {
  const s = e.ctx;
  if (s && s.ut) {
    let n, r;
    for (t ? (n = e.el, r = e.anchor) : (n = e.targetStart, r = e.targetAnchor); n && n !== r; )
      n.nodeType === 1 && n.setAttribute("data-v-owner", s.uid), n = n.nextSibling;
    s.ut();
  }
}
function Do(e, t, s, n, r = null) {
  const o = t.targetStart = s(""), i = t.targetAnchor = s("");
  return o[sc] = i, e && (n(o, e, r), n(i, e, r)), i;
}
const ao = /* @__PURE__ */ Symbol("_leaveCb");
function Ed(e) {
  let t = e[0];
  if (e.length > 1) {
    for (const s of e)
      if (s.type !== Tt) {
        t = s;
        break;
      }
  }
  return t;
}
function nc(e) {
  if (!_i(e))
    return Gr(e.type) && e.children ? Ed(e.children) : e;
  if (e.component)
    return e.component.subTree;
  const { shapeFlag: t, children: s } = e;
  if (s) {
    if (t & 16)
      return s[0];
    if (t & 32 && Ae(s.default))
      return s.default();
  }
}
function wr(e, t) {
  if (e.shapeFlag & 6 && e.component) {
    e.transition = t;
    const s = e.component.subTree;
    wr(
      Gr(s.type) && nc(s) || s,
      t
    );
  } else if (e.shapeFlag & 128)
    e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback);
  else if (e.transition = t, e.type === Ce && ge(e.children)) {
    const s = mc(e.children, !1);
    s && wr(s, t);
  }
}
function jo(e) {
  if (e.component)
    return jo(e.component.subTree);
  if (e.type === Ce) {
    const t = ge(e.children) && mc(e.children, !1);
    return t ? jo(t) : void 0;
  }
  if (e.type !== Tt)
    return e;
}
// @__NO_SIDE_EFFECTS__
function St(e, t) {
  return Ae(e) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    pt({ name: e.name }, t, { setup: e })
  ) : e;
}
function rc(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function Zi(e, t) {
  let s;
  return !!((s = Object.getOwnPropertyDescriptor(e, t)) && !s.configurable);
}
const _r = /* @__PURE__ */ new WeakMap();
function On(e, t, s, n, r = !1) {
  if (ge(e)) {
    e.forEach(
      (C, U) => On(
        C,
        t && (ge(t) ? t[U] : t),
        s,
        n,
        r
      )
    );
    return;
  }
  if (Xs(n) && !r) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && On(e, t, s, n.component.subTree);
    return;
  }
  const o = n.shapeFlag & 4 ? Jr(n.component) : n.el, i = r ? null : o, { i: a, r: l } = e, c = t && t.r, u = a.refs === qe ? a.refs = {} : a.refs, f = a.setupState, h = /* @__PURE__ */ De(f), d = f === qe ? wl : (C) => Zi(u, C) ? !1 : Ue(h, C), y = (C, U) => !(U && Zi(u, U));
  if (c != null && c !== l) {
    if (Ki(t), et(c))
      u[c] = null, d(c) && (f[c] = null);
    else if (/* @__PURE__ */ ot(c)) {
      const C = t;
      y(c, C.k) && (c.value = null), C.k && (u[C.k] = null);
    }
  }
  if (Ae(l))
    Zn(l, a, 12, [i, u]);
  else {
    const C = et(l), U = /* @__PURE__ */ ot(l);
    if (C || U) {
      const Q = () => {
        if (e.f) {
          const B = C ? d(l) ? f[l] : u[l] : y() || !e.k ? l.value : u[e.k];
          if (r)
            ge(B) && ai(B, o);
          else if (ge(B))
            B.includes(o) || B.push(o);
          else if (C)
            u[l] = [o], d(l) && (f[l] = u[l]);
          else {
            const Y = [o];
            y(l, e.k) && (l.value = Y), e.k && (u[e.k] = Y);
          }
        } else C ? (u[l] = i, d(l) && (f[l] = i)) : U && (y(l, e.k) && (l.value = i), e.k && (u[e.k] = i));
      };
      if (i) {
        const B = () => {
          Q(), _r.delete(e);
        };
        B.id = -1, _r.set(e, B), yt(B, s);
      } else
        Ki(e), Q();
    }
  }
}
function Ki(e) {
  const t = _r.get(e);
  t && (t.flags |= 8, _r.delete(e));
}
Lr().requestIdleCallback;
Lr().cancelIdleCallback;
const Xs = (e) => !!e.type.__asyncLoader, _i = (e) => e.type.__isKeepAlive;
function Id(e, t) {
  oc(e, "a", t);
}
function Od(e, t) {
  oc(e, "da", t);
}
function oc(e, t, s = gt) {
  const n = e.__wdc || (e.__wdc = () => {
    let r = s;
    for (; r; ) {
      if (r.isDeactivated)
        return;
      r = r.parent;
    }
    return e();
  });
  if (Hr(t, n, s), s) {
    let r = s.parent;
    for (; r && r.parent; )
      _i(r.parent.vnode) && Td(n, t, s, r), r = r.parent;
  }
}
function Td(e, t, s, n) {
  const r = Hr(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  xi(() => {
    ai(n[t], r);
  }, s);
}
function Hr(e, t, s = gt, n = !1) {
  if (s) {
    const r = s[e] || (s[e] = []), o = t.__weh || (t.__weh = (...i) => {
      Zt();
      const a = Kn(s), l = Mt(t, s, e, i);
      return a(), Kt(), l;
    });
    return n ? r.unshift(o) : r.push(o), o;
  }
}
const ds = (e) => (t, s = gt) => {
  (!Vn || e === "sp") && Hr(e, (...n) => t(...n), s);
}, $d = ds("bm"), fs = ds("m"), Pd = ds(
  "bu"
), Nd = ds("u"), Md = ds(
  "bum"
), xi = ds("um"), zd = ds(
  "sp"
), Dd = ds("rtg"), jd = ds("rtc");
function Vd(e, t = gt) {
  Hr("ec", e, t);
}
const Ld = "components", ic = /* @__PURE__ */ Symbol.for("v-ndc");
function Ud(e) {
  return et(e) ? Fd(Ld, e, !1) || e : e || ic;
}
function Fd(e, t, s = !0, n = !1) {
  const r = mt || gt;
  if (r) {
    const o = r.type;
    {
      const a = Rf(
        o,
        !1
      );
      if (a && (a === t || a === _t(t) || a === jr(_t(t))))
        return o;
    }
    const i = (
      // local registration
      // check instance[type] first which is resolved for options API
      Ji(r[e] || o[e], t) || // global registration
      Ji(r.appContext[e], t)
    );
    return !i && n ? o : i;
  }
}
function Ji(e, t) {
  return e && (e[t] || e[_t(t)] || e[jr(_t(t))]);
}
function tt(e, t, s, n) {
  let r;
  const o = s, i = ge(e);
  if (i || et(e)) {
    const a = i && /* @__PURE__ */ Ht(e);
    let l = !1, c = !1;
    a && (l = !/* @__PURE__ */ At(e), c = /* @__PURE__ */ Jt(e), e = Ur(e)), r = new Array(e.length);
    for (let u = 0, f = e.length; u < f; u++)
      r[u] = t(
        l ? c ? Cs(Ot(e[u])) : Ot(e[u]) : e[u],
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
  else if (Ge(e))
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
function ac(e, t, s, n, r, o) {
  if (s == null && (s = {}), mt.ce || mt.parent && Xs(mt.parent) && mt.parent.ce) {
    const c = s, u = Object.keys(c).length > 0;
    return D(), Be(
      Ce,
      null,
      [z("slot", c, n)],
      u ? -2 : 64
    );
  }
  let i = e[t];
  i && i._c && (i._d = !1);
  const a = as.length;
  D();
  let l;
  try {
    const c = i && lc(i(s)), u = s.key || o || // slot content array of a dynamic conditional slot may have a branch
    // key attached in the `createSlots` helper, respect that
    c && c.key;
    l = Be(
      Ce,
      {
        key: (u && !Et(u) ? u : `_${t}`) + // #7256 force differentiate fallback content from actual content
        (!c && n ? "_fb" : "")
      },
      c || (n ? n() : []),
      c && e._ === 1 ? 64 : -2
    );
  } catch (c) {
    for (let u = as.length; u > a; u--) Ri();
    throw c;
  } finally {
    i && i._c && (i._d = !0);
  }
  return l.scopeId && (l.slotScopeIds = [l.scopeId + "-s"]), l;
}
function lc(e) {
  return e.some((t) => tn(t) ? !(t.type === Tt || t.type === Ce && !lc(t.children)) : !0) ? e : null;
}
const Vo = (e) => e ? Ec(e) ? Jr(e) : Vo(e.parent) : null, Tn = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ pt(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => Vo(e.parent),
    $root: (e) => Vo(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => uc(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      yi(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = Br.bind(e.proxy)),
    $watch: (e) => kd.bind(e)
  })
), lo = (e, t) => e !== qe && !e.__isScriptSetup && Ue(e, t), Wd = {
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
        if (lo(n, t))
          return i[t] = 1, n[t];
        if (r !== qe && Ue(r, t))
          return i[t] = 2, r[t];
        if (Ue(o, t))
          return i[t] = 3, o[t];
        if (s !== qe && Ue(s, t))
          return i[t] = 4, s[t];
        Lo && (i[t] = 0);
      }
    }
    const c = Tn[t];
    let u, f;
    if (c)
      return t === "$attrs" && ht(e.attrs, "get", ""), c(e);
    if (
      // css module (injected by vue-loader)
      (u = a.__cssModules) && (u = u[t])
    )
      return u;
    if (s !== qe && Ue(s, t))
      return i[t] = 4, s[t];
    if (
      // global properties
      f = l.config.globalProperties, Ue(f, t)
    )
      return f[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: r, ctx: o } = e;
    return lo(r, t) ? (r[t] = s, !0) : n !== qe && Ue(n, t) ? (n[t] = s, !0) : Ue(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (o[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: r, props: o, type: i }
  }, a) {
    let l;
    return !!(s[a] || e !== qe && a[0] !== "$" && Ue(e, a) || lo(t, a) || Ue(o, a) || Ue(n, a) || Ue(Tn, a) || Ue(r.config.globalProperties, a) || (l = i.__cssModules) && l[a]);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : Ue(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function Qi(e) {
  return ge(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let Lo = !0;
function Bd(e) {
  const t = uc(e), s = e.proxy, n = e.ctx;
  Lo = !1, t.beforeCreate && Yi(t.beforeCreate, e, "bc");
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
    mounted: h,
    beforeUpdate: d,
    updated: y,
    activated: C,
    deactivated: U,
    beforeDestroy: Q,
    beforeUnmount: B,
    destroyed: Y,
    unmounted: q,
    render: ae,
    renderTracked: ye,
    renderTriggered: re,
    errorCaptured: j,
    serverPrefetch: H,
    // public API
    expose: x,
    inheritAttrs: G,
    // assets
    components: S,
    directives: X,
    filters: ke
  } = t;
  if (c && Gd(c, n, null), i)
    for (const $ in i) {
      const ve = i[$];
      Ae(ve) && (n[$] = ve.bind(s));
    }
  if (r) {
    const $ = r.call(s, s);
    Ge($) && (e.data = /* @__PURE__ */ qn($));
  }
  if (Lo = !0, o)
    for (const $ in o) {
      const ve = o[$], Fe = Ae(ve) ? ve.bind(s, s) : Ae(ve.get) ? ve.get.bind(s, s) : Gt, oe = !Ae(ve) && Ae(ve.set) ? ve.set.bind(s) : Gt, Xe = Ve({
        get: Fe,
        set: oe
      });
      Object.defineProperty(n, $, {
        enumerable: !0,
        configurable: !0,
        get: () => Xe.value,
        set: (Ke) => Xe.value = Ke
      });
    }
  if (a)
    for (const $ in a)
      cc(a[$], n, s, $);
  if (l) {
    const $ = Ae(l) ? l.call(s) : l;
    Reflect.ownKeys($).forEach((ve) => {
      mr(ve, $[ve]);
    });
  }
  u && Yi(u, e, "c");
  function b($, ve) {
    ge(ve) ? ve.forEach((Fe) => $(Fe.bind(s))) : ve && $(ve.bind(s));
  }
  if (b($d, f), b(fs, h), b(Pd, d), b(Nd, y), b(Id, C), b(Od, U), b(Vd, j), b(jd, ye), b(Dd, re), b(Md, B), b(xi, q), b(zd, H), ge(x))
    if (x.length) {
      const $ = e.exposed || (e.exposed = {});
      x.forEach((ve) => {
        Object.defineProperty($, ve, {
          get: () => s[ve],
          set: (Fe) => s[ve] = Fe,
          enumerable: !0
        });
      });
    } else e.exposed || (e.exposed = {});
  ae && e.render === Gt && (e.render = ae), G != null && (e.inheritAttrs = G), S && (e.components = S), X && (e.directives = X), H && rc(e);
}
function Gd(e, t, s = Gt) {
  ge(e) && (e = Uo(e));
  for (const n in e) {
    const r = e[n];
    let o;
    Ge(r) ? "default" in r ? o = Ct(
      r.from || n,
      r.default,
      !0
    ) : o = Ct(r.from || n) : o = Ct(r), /* @__PURE__ */ ot(o) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => o.value,
      set: (i) => o.value = i
    }) : t[n] = o;
  }
}
function Yi(e, t, s) {
  Mt(
    ge(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function cc(e, t, s, n) {
  let r = n.includes(".") ? tc(s, n) : () => s[n];
  if (et(e)) {
    const o = t[e];
    Ae(o) && ks(r, o);
  } else if (Ae(e))
    ks(r, e.bind(s));
  else if (Ge(e))
    if (ge(e))
      e.forEach((o) => cc(o, t, s, n));
    else {
      const o = Ae(e.handler) ? e.handler.bind(s) : t[e.handler];
      Ae(o) && ks(r, o, e);
    }
}
function uc(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: r,
    optionsCache: o,
    config: { optionMergeStrategies: i }
  } = e.appContext, a = o.get(t);
  let l;
  return a ? l = a : !r.length && !s && !n ? l = t : (l = {}, r.length && r.forEach(
    (c) => xr(l, c, i, !0)
  ), xr(l, t, i)), Ge(t) && o.set(t, l), l;
}
function xr(e, t, s, n = !1) {
  const { mixins: r, extends: o } = t;
  o && xr(e, o, s, !0), r && r.forEach(
    (i) => xr(e, i, s, !0)
  );
  for (const i in t)
    if (!(n && i === "expose")) {
      const a = Hd[i] || s && s[i];
      e[i] = a ? a(e[i], t[i]) : t[i];
    }
  return e;
}
const Hd = {
  data: Xi,
  props: ea,
  emits: ea,
  // objects
  methods: xn,
  computed: xn,
  // lifecycle
  beforeCreate: vt,
  created: vt,
  beforeMount: vt,
  mounted: vt,
  beforeUpdate: vt,
  updated: vt,
  beforeDestroy: vt,
  beforeUnmount: vt,
  destroyed: vt,
  unmounted: vt,
  activated: vt,
  deactivated: vt,
  errorCaptured: vt,
  serverPrefetch: vt,
  // assets
  components: xn,
  directives: xn,
  // watch
  watch: Zd,
  // provide / inject
  provide: Xi,
  inject: qd
};
function Xi(e, t) {
  return t ? e ? function() {
    return pt(
      Ae(e) ? e.call(this, this) : e,
      Ae(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function qd(e, t) {
  return xn(Uo(e), Uo(t));
}
function Uo(e) {
  if (ge(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function vt(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function xn(e, t) {
  return e ? pt(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function ea(e, t) {
  return e ? ge(e) && ge(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : pt(
    /* @__PURE__ */ Object.create(null),
    Qi(e),
    Qi(t ?? {})
  ) : t;
}
function Zd(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = pt(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = vt(e[n], t[n]);
  return s;
}
function dc() {
  return {
    app: null,
    config: {
      isNativeTag: wl,
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
let Kd = 0;
function Jd(e, t) {
  return function(n, r = null) {
    Ae(n) || (n = pt({}, n)), r != null && !Ge(r) && (r = null);
    const o = dc(), i = /* @__PURE__ */ new WeakSet(), a = [];
    let l = !1;
    const c = o.app = {
      _uid: Kd++,
      _component: n,
      _props: r,
      _container: null,
      _context: o,
      _instance: null,
      version: Ef,
      get config() {
        return o.config;
      },
      set config(u) {
      },
      use(u, ...f) {
        return i.has(u) || (u && Ae(u.install) ? (i.add(u), u.install(c, ...f)) : Ae(u) && (i.add(u), u(c, ...f))), c;
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
      mount(u, f, h) {
        if (!l) {
          const d = c._ceVNode || z(n, r);
          return d.appContext = o, h === !0 ? h = "svg" : h === !1 && (h = void 0), e(d, u, h), l = !0, c._container = u, u.__vue_app__ = c, Jr(d.component);
        }
      },
      onUnmount(u) {
        a.push(u);
      },
      unmount() {
        l && (Mt(
          a,
          c._instance,
          16
        ), e(null, c._container), delete c._container.__vue_app__);
      },
      provide(u, f) {
        return o.provides[u] = f, c;
      },
      runWithContext(u) {
        const f = Ls;
        Ls = c;
        try {
          return u();
        } finally {
          Ls = f;
        }
      }
    };
    return c;
  };
}
let Ls = null;
const Qd = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${_t(t)}Modifiers`] || e[`${Es(t)}Modifiers`];
function Yd(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || qe;
  let r = s;
  const o = t.startsWith("update:"), i = o && Qd(n, t.slice(7));
  i && (i.trim && (r = s.map((u) => et(u) ? u.trim() : u)), i.number && (r = r.map(Vr)));
  let a, l = n[a = to(t)] || // also try camelCase event handler (#2249)
  n[a = to(_t(t))];
  !l && o && (l = n[a = to(Es(t))]), l && Mt(
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
    e.emitted[a] = !0, Mt(
      c,
      e,
      6,
      r
    );
  }
}
const Xd = /* @__PURE__ */ new WeakMap();
function fc(e, t, s = !1) {
  const n = s ? Xd : t.emitsCache, r = n.get(e);
  if (r !== void 0)
    return r;
  const o = e.emits;
  let i = {}, a = !1;
  if (!Ae(e)) {
    const l = (c) => {
      const u = fc(c, t, !0);
      u && (a = !0, pt(i, u));
    };
    !s && t.mixins.length && t.mixins.forEach(l), e.extends && l(e.extends), e.mixins && e.mixins.forEach(l);
  }
  return !o && !a ? (Ge(e) && n.set(e, null), null) : (ge(o) ? o.forEach((l) => i[l] = null) : pt(i, o), Ge(e) && n.set(e, i), i);
}
function qr(e, t) {
  return !e || !Nr(t) ? !1 : (t = t.slice(2), t = t === "Once" ? t : t.replace(/Once$/, ""), Ue(e, t[0].toLowerCase() + t.slice(1)) || Ue(e, Es(t)) || Ue(e, t));
}
function ta(e) {
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
    props: f,
    data: h,
    setupState: d,
    ctx: y,
    inheritAttrs: C
  } = e, U = br(e);
  let Q, B;
  try {
    if (s.shapeFlag & 4) {
      const q = r || n, ae = q;
      Q = Ft(
        c.call(
          ae,
          q,
          u,
          f,
          d,
          h,
          y
        )
      ), B = a;
    } else {
      const q = t;
      Q = Ft(
        q.length > 1 ? q(
          f,
          { attrs: a, slots: i, emit: l }
        ) : q(
          f,
          null
        )
      ), B = t.props ? a : ef(a);
    }
  } catch (q) {
    as.length = 0, Wr(q, e, 1), Q = z(Tt);
  }
  let Y = Q;
  if (B && C !== !1) {
    const q = Object.keys(B), { shapeFlag: ae } = Y;
    q.length && ae & 7 && (o && q.some(Mr) && (B = tf(
      B,
      o
    )), Y = sn(Y, B, !1, !0));
  }
  if (s.dirs && (Y = sn(Y, null, !1, !0), Y.dirs = Y.dirs ? Y.dirs.concat(s.dirs) : s.dirs), s.transition) {
    const q = Gr(Y.type) && nc(Y) || Y;
    wr(q, s.transition);
  }
  return Q = Y, br(U), Q;
}
function mc(e, t = !0) {
  let s;
  for (let n = 0; n < e.length; n++) {
    const r = e[n];
    if (tn(r)) {
      if (r.type !== Tt || r.children === "v-if") {
        if (s)
          return;
        s = r;
      }
    } else
      return;
  }
  return s;
}
const ef = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || Nr(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, tf = (e, t) => {
  const s = {};
  for (const n in e)
    (!Mr(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function sf(e, t, s) {
  const { props: n, children: r, component: o } = e, { props: i, children: a, patchFlag: l } = t, c = o.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && l >= 0) {
    if (l & 1024)
      return !0;
    if (l & 16)
      return n ? sa(n, i, c) : !!i;
    if (l & 8) {
      const u = t.dynamicProps;
      for (let f = 0; f < u.length; f++) {
        const h = u[f];
        if (pc(i, n, h) && !qr(c, h))
          return !0;
      }
    }
  } else
    return (r || a) && (!a || !a.$stable) ? !0 : n === i ? !1 : n ? i ? sa(n, i, c) : !0 : !!i;
  return !1;
}
function sa(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let r = 0; r < n.length; r++) {
    const o = n[r];
    if (!Ue(e, o) || pc(t, e, o) && !qr(s, o))
      return !0;
  }
  return !1;
}
function pc(e, t, s) {
  const n = e[s], r = t[s];
  return s === "style" && Ge(n) && Ge(r) ? !cs(n, r) : n !== r;
}
function nf({ vnode: e, parent: t, suspense: s }, n) {
  for (; t; ) {
    const r = t.subTree;
    if (r.suspense && r.suspense.activeBranch === e && (r.suspense.vnode.el = r.el = n, e = r), r === e)
      (e = t.vnode).el = n, t = t.parent;
    else
      break;
  }
  s && s.activeBranch === e && (s.vnode.el = n);
}
const hc = {}, gc = () => Object.create(hc), vc = (e) => Object.getPrototypeOf(e) === hc;
function rf(e, t, s, n = !1) {
  const r = {}, o = gc();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), yc(e, t, r, o);
  for (const i in e.propsOptions[0])
    i in r || (r[i] = void 0);
  s ? e.props = n ? r : /* @__PURE__ */ Hl(r) : e.type.props ? e.props = r : e.props = o, e.attrs = o;
}
function of(e, t, s, n) {
  const {
    props: r,
    attrs: o,
    vnode: { patchFlag: i }
  } = e, a = /* @__PURE__ */ De(r), [l] = e.propsOptions;
  let c = !1;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (n || i > 0) && !(i & 16)
  ) {
    if (i & 8) {
      const u = e.vnode.dynamicProps;
      for (let f = 0; f < u.length; f++) {
        let h = u[f];
        if (qr(e.emitsOptions, h))
          continue;
        const d = t[h];
        if (l)
          if (Ue(o, h))
            d !== o[h] && (o[h] = d, c = !0);
          else {
            const y = _t(h);
            r[y] = Fo(
              l,
              a,
              y,
              d,
              e,
              !1
            );
          }
        else
          d !== o[h] && (o[h] = d, c = !0);
      }
    }
  } else {
    yc(e, t, r, o) && (c = !0);
    let u;
    for (const f in a)
      (!t || // for camelCase
      !Ue(t, f) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((u = Es(f)) === f || !Ue(t, u))) && (l ? s && // for camelCase
      (s[f] !== void 0 || // for kebab-case
      s[u] !== void 0) && (r[f] = Fo(
        l,
        a,
        f,
        void 0,
        e,
        !0
      )) : delete r[f]);
    if (o !== a)
      for (const f in o)
        (!t || !Ue(t, f)) && (delete o[f], c = !0);
  }
  c && ns(e.attrs, "set", "");
}
function yc(e, t, s, n) {
  const [r, o] = e.propsOptions;
  let i = !1, a;
  if (t)
    for (let l in t) {
      if (Rn(l))
        continue;
      const c = t[l];
      let u;
      r && Ue(r, u = _t(l)) ? !o || !o.includes(u) ? s[u] = c : (a || (a = {}))[u] = c : qr(e.emitsOptions, l) || (!(l in n) || c !== n[l]) && (n[l] = c, i = !0);
    }
  if (o) {
    const l = /* @__PURE__ */ De(s), c = a || qe;
    for (let u = 0; u < o.length; u++) {
      const f = o[u];
      s[f] = Fo(
        r,
        l,
        f,
        c[f],
        e,
        !Ue(c, f)
      );
    }
  }
  return i;
}
function Fo(e, t, s, n, r, o) {
  const i = e[s];
  if (i != null) {
    const a = Ue(i, "default");
    if (a && n === void 0) {
      const l = i.default;
      if (i.type !== Function && !i.skipFactory && Ae(l)) {
        const { propsDefaults: c } = r;
        if (s in c)
          n = c[s];
        else {
          const u = Kn(r);
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
    ] && (n === "" || n === Es(s)) && (n = !0));
  }
  return n;
}
const af = /* @__PURE__ */ new WeakMap();
function bc(e, t, s = !1) {
  const n = s ? af : t.propsCache, r = n.get(e);
  if (r)
    return r;
  const o = e.props, i = {}, a = [];
  let l = !1;
  if (!Ae(e)) {
    const u = (f) => {
      l = !0;
      const [h, d] = bc(f, t, !0);
      pt(i, h), d && a.push(...d);
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  if (!o && !l)
    return Ge(e) && n.set(e, Ds), Ds;
  if (ge(o))
    for (let u = 0; u < o.length; u++) {
      const f = _t(o[u]);
      na(f) && (i[f] = qe);
    }
  else if (o)
    for (const u in o) {
      const f = _t(u);
      if (na(f)) {
        const h = o[u], d = i[f] = ge(h) || Ae(h) ? { type: h } : pt({}, h), y = d.type;
        let C = !1, U = !0;
        if (ge(y))
          for (let Q = 0; Q < y.length; ++Q) {
            const B = y[Q], Y = Ae(B) && B.name;
            if (Y === "Boolean") {
              C = !0;
              break;
            } else Y === "String" && (U = !1);
          }
        else
          C = Ae(y) && y.name === "Boolean";
        d[
          0
          /* shouldCast */
        ] = C, d[
          1
          /* shouldCastTrue */
        ] = U, (C || Ue(d, "default")) && a.push(f);
      }
    }
  const c = [i, a];
  return Ge(e) && n.set(e, c), c;
}
function na(e) {
  return e[0] !== "$" && !Rn(e);
}
const ki = (e) => e === "_" || e === "_ctx" || e === "$stable", Si = (e) => ge(e) ? e.map(Ft) : [Ft(e)], lf = (e, t, s) => {
  if (t._n)
    return t;
  const n = F((...r) => Si(t(...r)), s);
  return n._c = !1, n;
}, wc = (e, t, s) => {
  const n = e._ctx;
  for (const r in e) {
    if (ki(r)) continue;
    const o = e[r];
    if (Ae(o))
      t[r] = lf(r, o, n);
    else if (o != null) {
      const i = Si(o);
      t[r] = () => i;
    }
  }
}, _c = (e, t) => {
  const s = Si(t);
  e.slots.default = () => s;
}, xc = (e, t, s) => {
  for (const n in t)
    (s || !ki(n)) && (e[n] = t[n]);
}, cf = (e, t, s) => {
  const n = e.slots = gc();
  if (e.vnode.shapeFlag & 32) {
    const r = t._;
    r ? (xc(n, t, s), s && Sl(n, "_", r, !0)) : wc(t, n);
  } else t && _c(e, t);
}, uf = (e, t, s) => {
  const { vnode: n, slots: r } = e;
  let o = !0, i = qe;
  if (n.shapeFlag & 32) {
    const a = t._;
    a ? s && a === 1 ? o = !1 : xc(r, t, s) : (o = !t.$stable, wc(t, r)), i = t;
  } else t && (_c(e, t), i = { default: 1 });
  if (o)
    for (const a in r)
      !ki(a) && i[a] == null && delete r[a];
}, yt = hf;
function df(e) {
  return ff(e);
}
function ff(e, t) {
  const s = Lr();
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
    parentNode: f,
    nextSibling: h,
    setScopeId: d = Gt,
    insertStaticContent: y
  } = e, C = (p, v, k, R = null, P = null, W = null, _ = void 0, T = null, N = !!v.dynamicChildren) => {
    if (p === v)
      return;
    p && !hn(p, v) && (R = L(p), Ke(p, P, W, !0), p = null), v.patchFlag === -2 && (N = !1, v.dynamicChildren = null), v.dynamicChildren && p && p.dynamicChildren && p.dynamicChildren.hasOnce && (v.dynamicChildren === Ds && (v.dynamicChildren = []), v.dynamicChildren.hasOnce = !0);
    const { type: V, ref: fe, shapeFlag: ne } = v;
    switch (V) {
      case Zr:
        U(p, v, k, R);
        break;
      case Tt:
        Q(p, v, k, R);
        break;
      case uo:
        p == null && B(v, k, R, _);
        break;
      case Ce:
        S(
          p,
          v,
          k,
          R,
          P,
          W,
          _,
          T,
          N
        );
        break;
      default:
        ne & 1 ? ae(
          p,
          v,
          k,
          R,
          P,
          W,
          _,
          T,
          N
        ) : ne & 6 ? X(
          p,
          v,
          k,
          R,
          P,
          W,
          _,
          T,
          N
        ) : (ne & 64 || ne & 128) && V.process(
          p,
          v,
          k,
          R,
          P,
          W,
          _,
          T,
          N,
          O
        );
    }
    fe != null && P ? On(fe, p && p.ref, W, v || p, !v) : fe == null && p && p.ref != null && On(p.ref, null, W, p, !0);
  }, U = (p, v, k, R) => {
    if (p == null)
      n(
        v.el = a(v.children),
        k,
        R
      );
    else {
      const P = v.el = p.el;
      v.children !== p.children && c(P, v.children);
    }
  }, Q = (p, v, k, R) => {
    p == null ? n(
      v.el = l(v.children || ""),
      k,
      R
    ) : v.el = p.el;
  }, B = (p, v, k, R) => {
    [p.el, p.anchor] = y(
      p.children,
      v,
      k,
      R,
      p.el,
      p.anchor
    );
  }, Y = ({ el: p, anchor: v }, k, R) => {
    let P;
    for (; p && p !== v; )
      P = h(p), n(p, k, R), p = P;
    n(v, k, R);
  }, q = ({ el: p, anchor: v }) => {
    let k;
    for (; p && p !== v; )
      k = h(p), r(p), p = k;
    r(v);
  }, ae = (p, v, k, R, P, W, _, T, N) => {
    if (v.type === "svg" ? _ = "svg" : v.type === "math" && (_ = "mathml"), p == null)
      ye(
        v,
        k,
        R,
        P,
        W,
        _,
        T,
        N
      );
    else {
      const V = p.el && p.el._isVueCE ? p.el : null;
      try {
        V && V._beginPatch(), H(
          p,
          v,
          P,
          W,
          _,
          T,
          N
        );
      } finally {
        V && V._endPatch();
      }
    }
  }, ye = (p, v, k, R, P, W, _, T) => {
    let N, V;
    const { props: fe, shapeFlag: ne, transition: he, dirs: _e } = p;
    if (N = p.el = i(
      p.type,
      W,
      fe && fe.is,
      fe
    ), ne & 8 ? u(N, p.children) : ne & 16 && j(
      p.children,
      N,
      null,
      R,
      P,
      co(p, W),
      _,
      T
    ), _e && Ts(p, null, R, "created"), re(N, p, p.scopeId, _, R), fe) {
      for (const Le in fe)
        Le !== "value" && !Rn(Le) && o(N, Le, null, fe[Le], W, R);
      "value" in fe && o(N, "value", null, fe.value, W), (V = fe.onVnodeBeforeMount) && jt(V, R, p);
    }
    _e && Ts(p, null, R, "beforeMount");
    const $e = mf(P, he);
    $e && he.beforeEnter(N), n(N, v, k), ((V = fe && fe.onVnodeMounted) || $e || _e) && yt(() => {
      try {
        V && jt(V, R, p), $e && he.enter(N), _e && Ts(p, null, R, "mounted");
      } finally {
      }
    }, P);
  }, re = (p, v, k, R, P) => {
    if (k && d(p, k), R)
      for (let W = 0; W < R.length; W++)
        d(p, R[W]);
    if (P) {
      let W = P.subTree;
      if (v === W || Sc(W.type) && (W.ssContent === v || W.ssFallback === v)) {
        const _ = P.vnode;
        re(
          p,
          _,
          _.scopeId,
          _.slotScopeIds,
          P.parent
        );
      }
    }
  }, j = (p, v, k, R, P, W, _, T, N = 0) => {
    for (let V = N; V < p.length; V++) {
      const fe = p[V] = T ? ss(p[V]) : Ft(p[V]);
      C(
        null,
        fe,
        v,
        k,
        R,
        P,
        W,
        _,
        T
      );
    }
  }, H = (p, v, k, R, P, W, _) => {
    const T = v.el = p.el;
    let { patchFlag: N, dynamicChildren: V, dirs: fe } = v;
    N |= p.patchFlag & 16;
    const ne = p.props || qe, he = v.props || qe;
    let _e;
    if (k && $s(k, !1), (_e = he.onVnodeBeforeUpdate) && jt(_e, k, v, p), fe && Ts(v, p, k, "beforeUpdate"), k && $s(k, !0), // #6385 the old vnode may be a user-wrapped non-isomorphic block
    // Force full diff when block metadata is unstable.
    V && (!p.dynamicChildren || p.dynamicChildren.length !== V.length) && (N = 0, _ = !1, V = null), (ne.innerHTML && he.innerHTML == null || ne.textContent && he.textContent == null) && u(T, ""), V ? x(
      p.dynamicChildren,
      V,
      T,
      k,
      R,
      co(v, P),
      W
    ) : _ || ve(
      p,
      v,
      T,
      null,
      k,
      R,
      co(v, P),
      W,
      !1
    ), N > 0) {
      if (N & 16)
        G(T, ne, he, k, P);
      else if (N & 2 && ne.class !== he.class && o(T, "class", null, he.class, P), N & 4 && o(T, "style", ne.style, he.style, P), N & 8) {
        const $e = v.dynamicProps;
        for (let Le = 0; Le < $e.length; Le++) {
          const w = $e[Le], M = ne[w], Z = he[w];
          (Z !== M || w === "value") && o(T, w, M, Z, P, k);
        }
      }
      N & 1 && p.children !== v.children && u(T, v.children);
    } else !_ && V == null && G(T, ne, he, k, P);
    ((_e = he.onVnodeUpdated) || fe) && yt(() => {
      _e && jt(_e, k, v, p), fe && Ts(v, p, k, "updated");
    }, R);
  }, x = (p, v, k, R, P, W, _) => {
    for (let T = 0; T < v.length; T++) {
      const N = p[T], V = v[T], fe = N.el || Wo(N), ne = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        fe && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (N.type === Ce || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !hn(N, V) || // - In the case of a component, it could contain anything.
        N.shapeFlag & 198) ? f(fe) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          k
        )
      );
      C(
        N,
        V,
        ne,
        null,
        R,
        P,
        W,
        _,
        !0
      );
    }
  }, G = (p, v, k, R, P) => {
    if (v !== k) {
      if (v !== qe)
        for (const W in v)
          !Rn(W) && !(W in k) && o(
            p,
            W,
            v[W],
            null,
            P,
            R
          );
      for (const W in k) {
        if (Rn(W)) continue;
        const _ = k[W], T = v[W];
        _ !== T && W !== "value" && o(p, W, T, _, P, R);
      }
      "value" in k && o(p, "value", v.value, k.value, P);
    }
  }, S = (p, v, k, R, P, W, _, T, N) => {
    const V = v.el = p ? p.el : a(""), fe = v.anchor = p ? p.anchor : a("");
    let { patchFlag: ne, dynamicChildren: he, slotScopeIds: _e } = v;
    _e && (T = T ? T.concat(_e) : _e), p == null ? (n(V, k, R), n(fe, k, R), j(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      v.children || [],
      k,
      fe,
      P,
      W,
      _,
      T,
      N
    )) : ne > 0 && ne & 64 && he && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    p.dynamicChildren && p.dynamicChildren.length === he.length ? (x(
      p.dynamicChildren,
      he,
      k,
      P,
      W,
      _,
      T
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (v.key != null || P && v === P.subTree) && Ci(
      p,
      v,
      !0
      /* shallow */
    )) : ve(
      p,
      v,
      k,
      fe,
      P,
      W,
      _,
      T,
      N
    );
  }, X = (p, v, k, R, P, W, _, T, N) => {
    v.slotScopeIds = T, p == null ? v.shapeFlag & 512 ? P.ctx.activate(
      v,
      k,
      R,
      _,
      N
    ) : ke(
      v,
      k,
      R,
      P,
      W,
      _,
      N
    ) : xe(p, v, N);
  }, ke = (p, v, k, R, P, W, _) => {
    const T = p.component = _f(
      p,
      R,
      P
    );
    if (_i(p) && (T.ctx.renderer = O), xf(T, !1, _), T.asyncDep) {
      if (P && P.registerDep(
        T,
        b,
        _,
        W
      ), !p.el) {
        const N = T.subTree = z(Tt);
        Q(null, N, v, k), p.placeholder = N.el;
      }
    } else
      b(
        T,
        p,
        v,
        k,
        P,
        W,
        _
      );
  }, xe = (p, v, k) => {
    const R = v.component = p.component;
    if (sf(p, v, k))
      if (R.asyncDep && !R.asyncResolved) {
        v.el = p.el, v.placeholder = p.placeholder, $(R, v, k);
        return;
      } else
        R.next = v, R.update();
    else
      v.el = p.el, v.placeholder = p.placeholder, R.vnode = v;
  }, b = (p, v, k, R, P, W, _) => {
    const T = () => {
      if (p.isMounted) {
        let { next: ne, bu: he, u: _e, parent: $e, vnode: Le } = p;
        {
          const Ee = kc(p);
          if (Ee) {
            ne && (ne.el = Le.el, $(p, ne, _)), Ee.asyncDep.then(() => {
              yt(() => {
                p.isUnmounted || V();
              }, P);
            });
            return;
          }
        }
        let w = ne, M;
        $s(p, !1), ne ? (ne.el = Le.el, $(p, ne, _)) : ne = Le, he && fr(he), (M = ne.props && ne.props.onVnodeBeforeUpdate) && jt(M, $e, ne, Le), $s(p, !0);
        const Z = ta(p), ce = p.subTree;
        p.subTree = Z, C(
          ce,
          Z,
          // parent may have changed if it's in a teleport
          f(ce.el),
          // anchor may have changed if it's in a fragment
          L(ce),
          p,
          P,
          W
        ), ne.el = Z.el, w === null && nf(p, Z.el), _e && yt(_e, P), (M = ne.props && ne.props.onVnodeUpdated) && yt(
          () => jt(M, $e, ne, Le),
          P
        );
      } else {
        let ne;
        const { el: he, props: _e } = v, { bm: $e, m: Le, parent: w, root: M, type: Z } = p, ce = Xs(v);
        $s(p, !1), $e && fr($e), !ce && (ne = _e && _e.onVnodeBeforeMount) && jt(ne, w, v), $s(p, !0);
        {
          M.ce && M.ce._hasShadowRoot() && M.ce._injectChildStyle(
            Z,
            p.parent ? p.parent.type : void 0
          );
          const Ee = p.subTree = ta(p);
          C(
            null,
            Ee,
            k,
            R,
            p,
            P,
            W
          ), v.el = Ee.el;
        }
        if (Le && yt(Le, P), !ce && (ne = _e && _e.onVnodeMounted)) {
          const Ee = v;
          yt(
            () => jt(ne, w, Ee),
            P
          );
        }
        (v.shapeFlag & 256 || w && Xs(w.vnode) && w.vnode.shapeFlag & 256) && p.a && yt(p.a, P), p.isMounted = !0, v = k = R = null;
      }
    };
    p.scope.on();
    const N = p.effect = new Tl(T);
    p.scope.off();
    const V = p.update = N.run.bind(N), fe = p.job = N.runIfDirty.bind(N);
    fe.i = p, fe.id = p.uid, N.scheduler = () => yi(fe), $s(p, !0), V();
  }, $ = (p, v, k) => {
    v.component = p;
    const R = p.vnode.props;
    p.vnode = v, p.next = null, of(p, v.props, R, k), uf(p, v.children, k), Zt(), Ql(p), Kt();
  }, ve = (p, v, k, R, P, W, _, T, N = !1) => {
    const V = p && p.children, fe = p ? p.shapeFlag : 0, ne = v.children, { patchFlag: he, shapeFlag: _e } = v;
    if (he > 0) {
      if (he & 128) {
        oe(
          V,
          ne,
          k,
          R,
          P,
          W,
          _,
          T,
          N
        );
        return;
      } else if (he & 256) {
        Fe(
          V,
          ne,
          k,
          R,
          P,
          W,
          _,
          T,
          N
        );
        return;
      }
    }
    _e & 8 ? (fe & 16 && Ne(V, P, W), ne !== V && u(k, ne)) : fe & 16 ? _e & 16 ? oe(
      V,
      ne,
      k,
      R,
      P,
      W,
      _,
      T,
      N
    ) : Ne(V, P, W, !0) : (fe & 8 && u(k, ""), _e & 16 && j(
      ne,
      k,
      R,
      P,
      W,
      _,
      T,
      N
    ));
  }, Fe = (p, v, k, R, P, W, _, T, N) => {
    p = p || Ds, v = v || Ds;
    const V = p.length, fe = v.length, ne = Math.min(V, fe);
    let he;
    for (he = 0; he < ne; he++) {
      const _e = v[he] = N ? ss(v[he]) : Ft(v[he]);
      C(
        p[he],
        _e,
        k,
        null,
        P,
        W,
        _,
        T,
        N
      );
    }
    V > fe ? Ne(
      p,
      P,
      W,
      !0,
      !1,
      ne
    ) : j(
      v,
      k,
      R,
      P,
      W,
      _,
      T,
      N,
      ne
    );
  }, oe = (p, v, k, R, P, W, _, T, N) => {
    let V = 0;
    const fe = v.length;
    let ne = p.length - 1, he = fe - 1;
    for (; V <= ne && V <= he; ) {
      const _e = p[V], $e = v[V] = N ? ss(v[V]) : Ft(v[V]);
      if (hn(_e, $e))
        C(
          _e,
          $e,
          k,
          null,
          P,
          W,
          _,
          T,
          N
        );
      else
        break;
      V++;
    }
    for (; V <= ne && V <= he; ) {
      const _e = p[ne], $e = v[he] = N ? ss(v[he]) : Ft(v[he]);
      if (hn(_e, $e))
        C(
          _e,
          $e,
          k,
          null,
          P,
          W,
          _,
          T,
          N
        );
      else
        break;
      ne--, he--;
    }
    if (V > ne) {
      if (V <= he) {
        const _e = he + 1, $e = _e < fe ? v[_e].el : R;
        for (; V <= he; )
          C(
            null,
            v[V] = N ? ss(v[V]) : Ft(v[V]),
            k,
            $e,
            P,
            W,
            _,
            T,
            N
          ), V++;
      }
    } else if (V > he)
      for (; V <= ne; )
        Ke(p[V], P, W, !0), V++;
    else {
      const _e = V, $e = V, Le = /* @__PURE__ */ new Map();
      for (V = $e; V <= he; V++) {
        const Oe = v[V] = N ? ss(v[V]) : Ft(v[V]);
        Oe.key != null && Le.set(Oe.key, V);
      }
      let w, M = 0;
      const Z = he - $e + 1;
      let ce = !1, Ee = 0;
      const we = new Array(Z);
      for (V = 0; V < Z; V++) we[V] = 0;
      for (V = _e; V <= ne; V++) {
        const Oe = p[V];
        if (M >= Z) {
          Ke(Oe, P, W, !0);
          continue;
        }
        let st;
        if (Oe.key != null)
          st = Le.get(Oe.key);
        else
          for (w = $e; w <= he; w++)
            if (we[w - $e] === 0 && hn(Oe, v[w])) {
              st = w;
              break;
            }
        st === void 0 ? Ke(Oe, P, W, !0) : (we[st - $e] = V + 1, st >= Ee ? Ee = st : ce = !0, C(
          Oe,
          v[st],
          k,
          null,
          P,
          W,
          _,
          T,
          N
        ), M++);
      }
      const We = ce ? pf(we) : Ds;
      for (w = We.length - 1, V = Z - 1; V >= 0; V--) {
        const Oe = $e + V, st = v[Oe], Os = v[Oe + 1], Ws = Oe + 1 < fe ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          Os.el || Wo(Os)
        ) : R;
        we[V] === 0 ? C(
          null,
          st,
          k,
          Ws,
          P,
          W,
          _,
          T,
          N
        ) : ce && (w < 0 || V !== We[w] ? Xe(st, k, Ws, 2) : w--);
      }
    }
  }, Xe = (p, v, k, R, P = null) => {
    const { el: W, type: _, transition: T, children: N, shapeFlag: V } = p;
    if (V & 6) {
      Xe(p.component.subTree, v, k, R);
      return;
    }
    if (V & 128) {
      p.suspense.move(v, k, R);
      return;
    }
    if (V & 64) {
      _.move(p, v, k, O);
      return;
    }
    if (_ === Ce) {
      n(W, v, k);
      for (let ne = 0; ne < N.length; ne++)
        Xe(N[ne], v, k, R);
      n(p.anchor, v, k);
      return;
    }
    if (_ === uo) {
      Y(p, v, k);
      return;
    }
    if (R !== 2 && V & 1 && T)
      if (R === 0)
        T.persisted && !W[ao] ? n(W, v, k) : (T.beforeEnter(W), n(W, v, k), yt(() => T.enter(W), P));
      else {
        const { leave: ne, delayLeave: he, afterLeave: _e } = T, $e = () => {
          p.ctx.isUnmounted ? r(W) : n(W, v, k);
        }, Le = () => {
          const w = W._isLeaving || !!W[ao];
          W._isLeaving && W[ao](
            !0
            /* cancelled */
          ), T.persisted && !w ? $e() : ne(W, () => {
            $e(), _e && _e();
          });
        };
        he ? he(W, $e, Le) : Le();
      }
    else
      n(W, v, k);
  }, Ke = (p, v, k, R = !1, P = !1) => {
    const {
      type: W,
      props: _,
      ref: T,
      children: N,
      dynamicChildren: V,
      shapeFlag: fe,
      patchFlag: ne,
      dirs: he,
      cacheIndex: _e,
      memo: $e
    } = p;
    if ((ne === -2 || V && V.hasOnce) && (P = !1), T != null && (Zt(), On(T, null, k, p, !0), Kt()), _e != null && (!p.ctx || p.ctx === v) && (v.renderCache[_e] = void 0), fe & 256) {
      v.ctx.deactivate(p);
      return;
    }
    const Le = fe & 1 && he, w = !Xs(p);
    let M;
    if (w && (M = _ && _.onVnodeBeforeUnmount) && jt(M, v, p), fe & 6)
      ze(p.component, k, R);
    else {
      if (fe & 128) {
        p.suspense.unmount(k, R);
        return;
      }
      Le && Ts(p, null, v, "beforeUnmount"), fe & 64 ? p.type.remove(
        p,
        v,
        k,
        O,
        R
      ) : V && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !V.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (W !== Ce || ne > 0 && ne & 64) ? Ne(
        V,
        v,
        k,
        !1,
        !0
      ) : (W === Ce && ne & 384 || !P && fe & 16) && Ne(N, v, k), R && ft(p);
    }
    const Z = $e != null && _e == null;
    (w && (M = _ && _.onVnodeUnmounted) || Le || Z) && yt(() => {
      M && jt(M, v, p), Le && Ts(p, null, v, "unmounted"), Z && (p.el = null);
    }, k);
  }, ft = (p) => {
    const { type: v, el: k, anchor: R, transition: P } = p, W = v === Ce;
    if (W && !P) {
      at(k, R);
      return;
    }
    if (v === uo) {
      q(p), P && !P.persisted && P.afterLeave && P.afterLeave();
      return;
    }
    const _ = W ? jo(p) : p, T = () => {
      W ? f(k) && at(k, R) : r(k), P && !P.persisted && P.afterLeave && P.afterLeave();
    };
    if (_ && _.shapeFlag & 1 && P && !P.persisted) {
      const { leave: N, delayLeave: V } = P, fe = _.el, ne = () => N(fe, T);
      V ? V(fe, T, ne) : ne();
    } else
      T();
  }, at = (p, v) => {
    let k;
    for (; p !== v; )
      k = h(p), r(p), p = k;
    r(v);
  }, ze = (p, v, k) => {
    const { bum: R, scope: P, job: W, subTree: _, um: T, m: N, a: V } = p;
    ra(N), ra(V), R && fr(R), P.stop(), W ? (W.flags |= 8, Ke(_, p, v, k)) : p.vnode.el && _ && (_.transition = p.vnode.transition, Ke(_, p, v, k)), T && yt(T, v), yt(() => {
      p.isUnmounted = !0;
    }, v);
  }, Ne = (p, v, k, R = !1, P = !1, W = 0) => {
    for (let _ = W; _ < p.length; _++)
      Ke(p[_], v, k, R, P);
  }, L = (p) => {
    if (p.shapeFlag & 6)
      return L(p.component.subTree);
    if (p.shapeFlag & 128)
      return p.suspense.next();
    const v = h(p.anchor || p.el), k = v && v[sc];
    return k ? h(k) : v;
  }, A = (p, v, k) => {
    const R = p && v._vnode ? void 0 : p && p.component ? p.component.uid : wf();
    bd(() => {
      p == null ? v._vnode && Ke(v._vnode, null, null, !0) : C(
        v._vnode || null,
        p,
        v,
        null,
        null,
        null,
        k
      ), v._vnode = p;
    }, R);
  }, O = {
    p: C,
    um: Ke,
    m: Xe,
    r: ft,
    mt: ke,
    mc: j,
    pc: ve,
    pbc: x,
    n: L,
    o: e
  };
  return {
    render: A,
    hydrate: void 0,
    createApp: Jd(A)
  };
}
function co({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function $s({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function mf(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function Ci(e, t, s = !1) {
  const n = e.children, r = t.children;
  if (ge(n) && ge(r))
    for (let o = 0; o < n.length; o++) {
      const i = n[o];
      let a = r[o];
      a.shapeFlag & 1 && !a.dynamicChildren && ((a.patchFlag <= 0 || a.patchFlag === 32) && (a = r[o] = ss(r[o]), a.el = i.el), !s && a.patchFlag !== -2 && Ci(i, a)), a.type === Zr && (a.patchFlag === -1 && (a = r[o] = ss(a)), a.el = i.el), a.type === Tt && !a.el && (a.el = i.el);
    }
}
function pf(e) {
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
function kc(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : kc(t);
}
function ra(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
function Wo(e) {
  if (e.placeholder)
    return e.placeholder;
  const t = e.component;
  return t ? Wo(t.subTree) : null;
}
const Sc = (e) => e.__isSuspense;
function hf(e, t) {
  t && t.pendingBranch ? ge(e) ? t.effects.push(...e) : t.effects.push(e) : yd(e);
}
const Ce = /* @__PURE__ */ Symbol.for("v-fgt"), Zr = /* @__PURE__ */ Symbol.for("v-txt"), Tt = /* @__PURE__ */ Symbol.for("v-cmt"), uo = /* @__PURE__ */ Symbol.for("v-stc"), as = [];
let Rt = null;
function D(e = !1) {
  as.push(Rt = e ? null : []);
}
function Ri() {
  as.pop(), Rt = as[as.length - 1] || null;
}
let Dn = 1;
function kr(e, t = !1) {
  Dn += e, e < 0 && Rt && t && (Rt.hasOnce = !0);
}
function Cc(e) {
  return e.dynamicChildren = Dn > 0 ? Rt || Ds : null, Ri(), Dn > 0 && Rt && Rt.push(e), e;
}
function J(e, t, s, n, r, o) {
  return Cc(
    m(
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
function Be(e, t, s, n, r) {
  return Cc(
    z(
      e,
      t,
      s,
      n,
      r,
      !0
    )
  );
}
function tn(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function hn(e, t) {
  return e.type === t.type && e.key === t.key;
}
const Rc = ({ key: e }) => e ?? null, pr = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? et(e) || /* @__PURE__ */ ot(e) || Ae(e) ? { i: mt, r: e, k: t, f: !!s } : e : null);
function m(e, t = null, s = null, n = 0, r = null, o = e === Ce ? 0 : 1, i = !1, a = !1) {
  const l = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && Rc(t),
    ref: t && pr(t),
    scopeId: ec,
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
    ctx: mt
  };
  return a ? (Sr(l, s), o & 128 && e.normalize(l)) : s && (l.shapeFlag |= et(s) ? 8 : 16), Dn > 0 && // avoid a block node from tracking itself
  !i && // has current parent block
  Rt && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (l.patchFlag > 0 || o & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  l.patchFlag !== 32 && Rt.push(l), l;
}
const z = gf;
function gf(e, t = null, s = null, n = 0, r = null, o = !1) {
  if ((!e || e === ic) && (e = Tt), tn(e)) {
    const a = sn(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && Sr(a, s), Dn > 0 && !o && Rt && (a.shapeFlag & 6 ? Rt[Rt.indexOf(e)] = a : Rt.push(a)), a.patchFlag = -2, a;
  }
  if (Af(e) && (e = e.__vccOpts), t) {
    t = vf(t);
    let { class: a, style: l } = t;
    a && !et(a) && (t.class = xt(a)), Ge(l) && (/* @__PURE__ */ Fr(l) && !ge(l) && (l = pt({}, l)), t.style = li(l));
  }
  const i = et(e) ? 1 : Sc(e) ? 128 : Gr(e) ? 64 : Ge(e) ? 4 : Ae(e) ? 2 : 0;
  return m(
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
function vf(e) {
  return e ? /* @__PURE__ */ Fr(e) || vc(e) ? pt({}, e) : e : null;
}
function sn(e, t, s = !1, n = !1) {
  const { props: r, ref: o, patchFlag: i, children: a, transition: l } = e, c = t ? yf(r || {}, t) : r, u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: c,
    key: c && Rc(c),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && o ? ge(o) ? o.concat(pr(t)) : [o, pr(t)] : pr(t)
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
    patchFlag: t && e.type !== Ce ? i === -1 ? 16 : i | 16 : i,
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
    ssContent: e.ssContent && sn(e.ssContent),
    ssFallback: e.ssFallback && sn(e.ssFallback),
    placeholder: e.placeholder,
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce,
    cacheIndex: e.cacheIndex
  };
  return l && n && wr(
    u,
    l.clone(u)
  ), u;
}
function I(e = " ", t = 0) {
  return z(Zr, null, e, t);
}
function be(e = "", t = !1) {
  return t ? (D(), Be(Tt, null, e)) : z(Tt, null, e);
}
function Ft(e) {
  return e == null || typeof e == "boolean" ? z(Tt) : ge(e) ? z(
    Ce,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : tn(e) ? ss(e) : z(Zr, null, String(e));
}
function ss(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : sn(e);
}
function Sr(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (ge(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const r = t.default;
      r && (r._c && (r._d = !1), Sr(e, r()), r._c && (r._d = !0));
      return;
    } else {
      s = 32;
      const r = t._;
      !r && !vc(t) ? t._ctx = mt : r === 3 && mt && (mt.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else if (Ae(t)) {
    if (n & 65) {
      Sr(e, { default: t });
      return;
    }
    t = { default: t, _ctx: mt }, s = 32;
  } else
    t = String(t), n & 64 ? (s = 16, t = [I(t)]) : s = 8;
  e.children = t, e.shapeFlag |= s;
}
function yf(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const r in n)
      if (r === "class")
        t.class !== n.class && (t.class = xt([t.class, n.class]));
      else if (r === "style")
        t.style = li([t.style, n.style]);
      else if (Nr(r)) {
        const o = t[r], i = n[r];
        i && o !== i && !(ge(o) && o.includes(i)) ? t[r] = o ? [].concat(o, i) : i : i == null && o == null && // mergeProps({ 'onUpdate:modelValue': undefined }) should not retain
        // the model listener.
        !Mr(r) && (t[r] = i);
      } else r !== "" && (t[r] = n[r]);
  }
  return t;
}
function jt(e, t, s, n = null) {
  Mt(e, t, 7, [
    s,
    n
  ]);
}
const bf = dc();
let Ac = 0;
function wf() {
  return Ac;
}
function _f(e, t, s) {
  const n = e.type, r = (t ? t.appContext : e.appContext) || bf, o = {
    uid: Ac++,
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
    scope: new El(
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
    propsOptions: bc(n, r),
    emitsOptions: fc(n, r),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: qe,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: qe,
    data: qe,
    props: qe,
    attrs: qe,
    slots: qe,
    refs: qe,
    setupState: qe,
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
  return o.ctx = { _: o }, o.root = t ? t.root : o, o.emit = Yd.bind(null, o), e.ce && e.ce(o), o;
}
let gt = null;
const Kr = () => gt || mt;
let Cr, jn;
{
  const e = Lr(), t = (s, n) => {
    let r;
    return (r = e[s]) || (r = e[s] = []), r.push(n), (o) => {
      r.length > 1 ? r.forEach((i) => i(o)) : r[0](o);
    };
  };
  Cr = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => gt = s
  ), jn = t(
    "__VUE_SSR_SETTERS__",
    (s) => Vn = s
  );
}
const Kn = (e) => {
  const t = gt;
  return Cr(e), e.scope.on(), () => {
    e.scope.off(), Cr(t);
  };
}, oa = () => {
  gt && gt.scope.off(), Cr(null);
};
function Ec(e) {
  return e.vnode.shapeFlag & 4;
}
let Vn = !1;
function xf(e, t = !1, s = !1) {
  t && jn(t);
  const { props: n, children: r } = e.vnode, o = Ec(e);
  rf(e, n, o, t), cf(e, r, s || t);
  const i = o ? kf(e, t) : void 0;
  return t && jn(!1), i;
}
function kf(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Wd);
  const { setup: n } = s;
  if (n) {
    Zt();
    const r = e.setupContext = n.length > 1 ? Cf(e) : null, o = Kn(e), i = Zn(
      n,
      e,
      0,
      [
        e.props,
        r
      ]
    ), a = _l(i);
    if (Kt(), o(), (a || e.sp) && !Xs(e) && rc(e), a) {
      if (i.then(oa, oa), t)
        return i.then((l) => {
          jn(!0);
          try {
            ia(e, l, t);
          } finally {
            jn(!1);
          }
        }).catch((l) => {
          Wr(l, e, 0);
        });
      e.asyncDep = i;
    } else
      ia(e, i);
  } else
    Ic(e);
}
function ia(e, t, s) {
  Ae(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : Ge(t) && (e.setupState = Zl(t)), Ic(e);
}
function Ic(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || Gt);
  {
    const r = Kn(e);
    Zt();
    try {
      Bd(e);
    } finally {
      Kt(), r();
    }
  }
}
const Sf = {
  get(e, t) {
    return ht(e, "get", ""), e[t];
  }
};
function Cf(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, Sf),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Jr(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(Zl(vi(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in Tn)
        return Tn[s](e);
    },
    has(t, s) {
      return s in t || s in Tn;
    }
  })) : e.proxy;
}
function Rf(e, t = !0) {
  return Ae(e) ? e.displayName || e.name : e.name || t && e.__name;
}
function Af(e) {
  return Ae(e) && "__vccOpts" in e;
}
const Ve = (e, t) => /* @__PURE__ */ md(e, t, Vn);
function Ln(e, t, s) {
  try {
    kr(-1);
    const n = arguments.length;
    return n === 2 ? Ge(t) && !ge(t) ? tn(t) ? z(e, null, [t]) : z(e, t) : z(e, null, t) : (n > 3 ? s = Array.prototype.slice.call(arguments, 2) : n === 3 && tn(s) && (s = [s]), z(e, t, s));
  } finally {
    kr(1);
  }
}
const Ef = "3.5.44";
/**
* @vue/runtime-dom v3.5.44
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let Bo;
const aa = typeof window < "u" && window.trustedTypes;
if (aa)
  try {
    Bo = /* @__PURE__ */ aa.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const Oc = Bo ? (e) => Bo.createHTML(e) : (e) => e, If = "http://www.w3.org/2000/svg", Of = "http://www.w3.org/1998/Math/MathML", ts = typeof document < "u" ? document : null, la = ts && /* @__PURE__ */ ts.createElement("template"), Tf = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const r = t === "svg" ? ts.createElementNS(If, e) : t === "mathml" ? ts.createElementNS(Of, e) : s ? ts.createElement(e, { is: s }) : ts.createElement(e);
    return e === "select" && n && n.multiple != null && r.setAttribute("multiple", n.multiple), r;
  },
  createText: (e) => ts.createTextNode(e),
  createComment: (e) => ts.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => ts.querySelector(e),
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
      la.innerHTML = Oc(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const a = la.content;
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
}, $f = /* @__PURE__ */ Symbol("_vtc");
function Pf(e, t, s) {
  const n = e[$f];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const ca = /* @__PURE__ */ Symbol("_vod"), Nf = /* @__PURE__ */ Symbol("_vsh"), Mf = /* @__PURE__ */ Symbol(""), zf = /(?:^|;)\s*display\s*:/;
function Df(e, t, s) {
  const n = e.style, r = et(s);
  let o = !1;
  if (s && !r) {
    if (t)
      if (et(t))
        for (const i of t.split(";")) {
          const a = i.slice(0, i.indexOf(":")).trim();
          s[a] == null && kn(n, a, "");
        }
      else
        for (const i in t)
          s[i] == null && kn(n, i, "");
    for (const i in s) {
      i === "display" && (o = !0);
      const a = s[i];
      a != null ? Vf(
        e,
        i,
        !et(t) && t ? t[i] : void 0,
        a
      ) || kn(n, i, a) : kn(n, i, "");
    }
  } else if (r) {
    if (t !== s) {
      const i = n[Mf];
      i && (s += ";" + i), n.cssText = s, o = zf.test(s);
    }
  } else t && e.removeAttribute("style");
  ca in e && ((!r || t !== s) && (e[ca] = o ? n.display : ""), e[Nf] && (n.display = "none"));
}
const sr = /\s*!important$/;
function kn(e, t, s) {
  if (ge(s))
    s.forEach((n) => kn(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    sr.test(s) ? e.setProperty(t, s.replace(sr, ""), "important") : e.setProperty(t, s);
  else {
    const n = jf(e, t);
    sr.test(s) ? e.setProperty(
      Es(n),
      s.replace(sr, ""),
      "important"
    ) : e[n] = s;
  }
}
const ua = ["Webkit", "Moz", "ms"], fo = {};
function jf(e, t) {
  const s = fo[t];
  if (s)
    return s;
  let n = _t(t);
  if (n !== "filter" && n in e)
    return fo[t] = n;
  n = jr(n);
  for (let r = 0; r < ua.length; r++) {
    const o = ua[r] + n;
    if (o in e)
      return fo[t] = o;
  }
  return t;
}
function Vf(e, t, s, n) {
  return e.tagName === "TEXTAREA" && (t === "width" || t === "height") && et(n) && s === n;
}
const da = "http://www.w3.org/1999/xlink";
function fa(e, t, s, n, r, o = Uu(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(da, t.slice(6, t.length)) : e.setAttributeNS(da, t, s) : s == null || o && !Cl(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    o ? "" : Et(s) ? String(s) : s
  );
}
function ma(e, t, s, n, r) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? Oc(s) : s);
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
    a === "boolean" ? s = Cl(s) : s == null && a === "string" ? (s = "", i = !0) : a === "number" && (s = 0, i = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  i && e.removeAttribute(r || t);
}
function _s(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function Lf(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const pa = /* @__PURE__ */ Symbol("_vei");
function Uf(e, t, s, n, r = null) {
  const o = e[pa] || (e[pa] = {}), i = o[t];
  if (n && i)
    i.value = n;
  else {
    const [a, l] = Bf(t);
    if (n) {
      const c = o[t] = qf(
        n,
        r
      );
      _s(e, a, c, l);
    } else i && (Lf(e, a, i, l), o[t] = void 0);
  }
}
const Ff = /(Once|Passive|Capture)$/, Wf = /^on:?(?:Once|Passive|Capture)$/;
function Bf(e) {
  let t, s;
  for (; (s = e.match(Ff)) && !Wf.test(e); )
    t || (t = {}), e = e.slice(0, e.length - s[1].length), t[s[1].toLowerCase()] = !0;
  return [e[2] === ":" ? e.slice(3) : Es(e.slice(2)), t];
}
let mo = 0;
const Gf = /* @__PURE__ */ Promise.resolve(), Hf = () => mo || (Gf.then(() => mo = 0), mo = Date.now());
function qf(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    const r = s.value;
    if (ge(r)) {
      const o = n.stopImmediatePropagation;
      n.stopImmediatePropagation = () => {
        o.call(n), n._stopped = !0;
      };
      const i = r.slice(), a = [n];
      for (let l = 0; l < i.length && !n._stopped; l++) {
        const c = i[l];
        c && Mt(
          c,
          t,
          5,
          a
        );
      }
    } else
      Mt(
        r,
        t,
        5,
        [n]
      );
  };
  return s.value = e, s.attached = Hf(), s;
}
const ha = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, Zf = (e, t, s, n, r, o) => {
  const i = r === "svg";
  t === "class" ? Pf(e, n, i) : t === "style" ? Df(e, s, n) : Nr(t) ? Mr(t) || Uf(e, t, s, n, o) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : Kf(e, t, n, i)) ? (ma(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && fa(e, t, n, i, o, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && // #12408 check if it's declared prop or it's async custom element
  (Jf(e, t) || // @ts-expect-error _def is private
  e._def.__asyncLoader && (/[A-Z]/.test(t) || !et(n))) ? ma(e, _t(t), n, o, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), fa(e, t, n, i));
};
function Kf(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && ha(t) && Ae(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "autocorrect" || t === "sandbox" && e.tagName === "IFRAME" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const r = e.tagName;
    if (r === "IMG" || r === "VIDEO" || r === "CANVAS" || r === "SOURCE")
      return !1;
  }
  return ha(t) && et(s) ? !1 : t in e;
}
function Jf(e, t) {
  const s = (
    // @ts-expect-error _def is private
    e._def.props
  );
  if (!s)
    return !1;
  const n = _t(t);
  return Array.isArray(s) ? s.some((r) => _t(r) === n) : Object.keys(s).some((r) => _t(r) === n);
}
const nn = (e) => {
  const t = e.props["onUpdate:modelValue"] || !1;
  return ge(t) ? (s) => fr(t, s) : t;
};
function Qf(e) {
  e.target.composing = !0;
}
function ga(e) {
  const t = e.target;
  t.composing && (t.composing = !1, t.dispatchEvent(new Event("input")));
}
const Bt = /* @__PURE__ */ Symbol("_assign"), nr = /* @__PURE__ */ Symbol("_initialValue");
function po(e, t, s) {
  return t && (e = e.trim()), s && (e = Vr(e)), e;
}
const rt = {
  created(e, { modifiers: { lazy: t, trim: s, number: n } }, r) {
    e.parentNode && (e.type === "text" ? e[nr] = e.defaultValue.replace(/[\r\n]/g, "") : e.type === "textarea" && (e[nr] = e.defaultValue.replace(/\r\n?/g, `
`))), e[Bt] = nn(r);
    const o = n || r.props && r.props.type === "number";
    _s(e, t ? "change" : "input", (i) => {
      i.target.composing || e[Bt](po(e.value, s, o));
    }), (s || o) && _s(e, "change", () => {
      e.value = po(e.value, s, o);
    }), t || (_s(e, "compositionstart", Qf), _s(e, "compositionend", ga), _s(e, "change", ga));
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(e, { value: t, modifiers: { trim: s, number: n } }) {
    const r = t ?? "", o = e[nr];
    delete e[nr], o !== void 0 && (e.type === "text" || e.type === "textarea") && e.value !== o ? e[Bt](po(e.value, s, n)) : e.value = r;
  },
  beforeUpdate(e, { value: t, oldValue: s, modifiers: { lazy: n, trim: r, number: o } }, i) {
    if (e[Bt] = nn(i), e.composing) return;
    const a = (o || e.type === "number") && !/^0\d/.test(e.value) ? Vr(e.value) : e.value, l = t ?? "";
    if (a === l)
      return;
    const c = e.getRootNode();
    (c instanceof Document || c instanceof ShadowRoot) && c.activeElement === e && e.type !== "range" && (n && t === s || r && e.value.trim() === l) || (e.value = l);
  }
}, en = {
  // #4096 array checkboxes need to be deep traversed
  deep: !0,
  created(e, t, s) {
    e[Bt] = nn(s), _s(e, "change", () => {
      const n = e._modelValue, r = Un(e), o = e.checked, i = e[Bt];
      if (ge(n)) {
        const a = ci(n, r), l = a !== -1;
        if (o && !l)
          i(n.concat(r));
        else if (!o && l) {
          const c = [...n];
          c.splice(a, 1), i(c);
        }
      } else if (ls(n)) {
        const a = new Set(n);
        o ? a.add(r) : a.delete(r), i(a);
      } else
        i(Tc(e, o));
    });
  },
  // set initial checked on mount to wait for true-value/false-value
  mounted: va,
  beforeUpdate(e, t, s) {
    e[Bt] = nn(s), va(e, t, s);
  }
};
function va(e, { value: t, oldValue: s }, n) {
  e._modelValue = t;
  let r;
  if (ge(t))
    r = ci(t, n.props.value) > -1;
  else if (ls(t))
    r = t.has(n.props.value);
  else {
    if (t === s) return;
    r = cs(t, Tc(e, !0));
  }
  e.checked !== r && (e.checked = r);
}
const os = {
  // <select multiple> value need to be deep traversed
  deep: !0,
  created(e, { value: t, modifiers: { number: s } }, n) {
    e._modelValue = t, _s(e, "change", () => {
      const r = Array.prototype.filter.call(e.options, (l) => l.selected).map(
        (l) => s ? Vr(Un(l)) : Un(l)
      ), o = e.multiple, i = o ? ls(e._modelValue) ? new Set(r) : r : r[0], a = e._pendingValue = [
        o,
        o ? ge(i) ? r.slice() : r : i
      ];
      try {
        e[Bt](i);
      } finally {
        Br(() => {
          e._pendingValue === a && (e._pendingValue = void 0);
        });
      }
    }), e[Bt] = nn(n);
  },
  // set value in mounted & updated because <select> relies on its children
  // <option>s.
  mounted(e, { value: t }) {
    ya(e, t);
  },
  beforeUpdate(e, { value: t }, s) {
    e._modelValue = t, e[Bt] = nn(s);
  },
  updated(e, { value: t }) {
    const s = e._pendingValue;
    e._pendingValue = void 0, (!s || s[0] !== e.multiple || !Yf(t, s[1], s[0])) && ya(e, t);
  }
};
function Yf(e, t, s) {
  if (!s || ge(e)) return cs(e, t);
  if (ls(e)) {
    if (e.size !== t.length) return !1;
    for (const n of t)
      if (!e.has(n)) return !1;
    return !0;
  }
  return !1;
}
function ya(e, t) {
  const s = e.multiple, n = ge(t);
  if (!(s && !n && !ls(t))) {
    for (let r = 0, o = e.options.length; r < o; r++) {
      const i = e.options[r], a = Un(i);
      if (s)
        if (n) {
          const l = typeof a;
          l === "string" || l === "number" ? i.selected = t.some((c) => String(c) === String(a)) : i.selected = ci(t, a) > -1;
        } else
          i.selected = t.has(a);
      else if (cs(Un(i), t)) {
        e.selectedIndex !== r && (e.selectedIndex = r);
        return;
      }
    }
    !s && e.selectedIndex !== -1 && (e.selectedIndex = -1);
  }
}
function Un(e) {
  return "_value" in e ? e._value : e.value;
}
function Tc(e, t) {
  const s = t ? "_trueValue" : "_falseValue";
  return s in e ? e[s] : t;
}
const Xf = ["ctrl", "shift", "alt", "meta"], em = {
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
  exact: (e, t) => Xf.some((s) => e[`${s}Key`] && !t.includes(s))
}, Ai = (e, t) => {
  if (!e) return e;
  const s = e._withMods || (e._withMods = {}), n = t.join(".");
  return s[n] || (s[n] = ((r, ...o) => {
    for (let i = 0; i < t.length; i++) {
      const a = em[t[i]];
      if (a && a(r, t)) return;
    }
    return e(r, ...o);
  }));
}, tm = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
}, rn = (e, t) => {
  const s = e._withKeys || (e._withKeys = {}), n = t.join(".");
  return s[n] || (s[n] = ((r) => {
    if (!("key" in r))
      return;
    const o = Es(r.key);
    if (t.some(
      (i) => i === o || tm[i] === o
    ))
      return e(r);
  }));
}, sm = /* @__PURE__ */ pt({ patchProp: Zf }, Tf);
let ba;
function nm() {
  return ba || (ba = df(sm));
}
const rm = ((...e) => {
  const t = nm().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const r = im(n);
    if (!r) return;
    const o = t._component;
    !Ae(o) && !o.render && !o.template && (o.template = r.innerHTML), r.nodeType === 1 && (r.textContent = "");
    const i = s(r, !1, om(r));
    return r instanceof Element && (r.removeAttribute("v-cloak"), r.setAttribute("data-v-app", "")), i;
  }, t;
});
function om(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function im(e) {
  return et(e) ? document.querySelector(e) : e;
}
/*!
 * pinia v3.0.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
let $c;
const Qr = (e) => $c = e, Pc = (
  /* istanbul ignore next */
  Symbol()
);
function Go(e) {
  return e && typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" && typeof e.toJSON != "function";
}
var $n;
(function(e) {
  e.direct = "direct", e.patchObject = "patch object", e.patchFunction = "patch function";
})($n || ($n = {}));
function am() {
  const e = Il(!0), t = e.run(() => /* @__PURE__ */ E({}));
  let s = [], n = [];
  const r = vi({
    install(o) {
      Qr(r), r._a = o, o.provide(Pc, r), o.config.globalProperties.$pinia = r, n.forEach((i) => s.push(i)), n = [];
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
const Nc = () => {
};
function wa(e, t, s, n = Nc) {
  e.add(t);
  const r = () => {
    e.delete(t) && n();
  };
  return !s && ui() && Ol(r), r;
}
function Hs(e, ...t) {
  e.forEach((s) => {
    s(...t);
  });
}
const lm = (e) => e(), _a = Symbol(), ho = Symbol();
function Ho(e, t) {
  e instanceof Map && t instanceof Map ? t.forEach((s, n) => e.set(n, s)) : e instanceof Set && t instanceof Set && t.forEach(e.add, e);
  for (const s in t) {
    if (!t.hasOwnProperty(s))
      continue;
    const n = t[s], r = e[s];
    Go(r) && Go(n) && e.hasOwnProperty(s) && !/* @__PURE__ */ ot(n) && !/* @__PURE__ */ Ht(n) ? e[s] = Ho(r, n) : e[s] = n;
  }
  return e;
}
const cm = (
  /* istanbul ignore next */
  Symbol()
);
function um(e) {
  return !Go(e) || !Object.prototype.hasOwnProperty.call(e, cm);
}
const { assign: gs } = Object;
function dm(e) {
  return !!(/* @__PURE__ */ ot(e) && e.effect);
}
function fm(e, t, s, n) {
  const { state: r, actions: o, getters: i } = t, a = s.state.value[e];
  let l;
  function c() {
    a || (s.state.value[e] = r ? r() : {});
    const u = /* @__PURE__ */ cd(s.state.value[e]);
    return gs(u, o, Object.keys(i || {}).reduce((f, h) => (f[h] = vi(Ve(() => {
      Qr(s);
      const d = s._s.get(e);
      return i[h].call(d, d);
    })), f), {}));
  }
  return l = Mc(e, c, t, s, n, !0), l;
}
function Mc(e, t, s = {}, n, r, o) {
  let i;
  const a = gs({ actions: {} }, s), l = { deep: !0 };
  let c, u, f = /* @__PURE__ */ new Set(), h = /* @__PURE__ */ new Set(), d;
  const y = n.state.value[e];
  !o && !y && (n.state.value[e] = {});
  let C;
  function U(j) {
    let H;
    c = u = !1, typeof j == "function" ? (j(n.state.value[e]), H = {
      type: $n.patchFunction,
      storeId: e,
      events: d
    }) : (Ho(n.state.value[e], j), H = {
      type: $n.patchObject,
      payload: j,
      storeId: e,
      events: d
    });
    const x = C = Symbol();
    Br().then(() => {
      C === x && (c = !0);
    }), u = !0, Hs(f, H, n.state.value[e]);
  }
  const Q = o ? function() {
    const { state: H } = s, x = H ? H() : {};
    this.$patch((G) => {
      gs(G, x);
    });
  } : (
    /* istanbul ignore next */
    Nc
  );
  function B() {
    i.stop(), f.clear(), h.clear(), n._s.delete(e);
  }
  const Y = (j, H = "") => {
    if (_a in j)
      return j[ho] = H, j;
    const x = function() {
      Qr(n);
      const G = Array.from(arguments), S = /* @__PURE__ */ new Set(), X = /* @__PURE__ */ new Set();
      function ke($) {
        S.add($);
      }
      function xe($) {
        X.add($);
      }
      Hs(h, {
        args: G,
        name: x[ho],
        store: ae,
        after: ke,
        onError: xe
      });
      let b;
      try {
        b = j.apply(this && this.$id === e ? this : ae, G);
      } catch ($) {
        throw Hs(X, $), $;
      }
      return b instanceof Promise ? b.then(($) => (Hs(S, $), $)).catch(($) => (Hs(X, $), Promise.reject($))) : (Hs(S, b), b);
    };
    return x[_a] = !0, x[ho] = H, x;
  }, q = {
    _p: n,
    // _s: scope,
    $id: e,
    $onAction: wa.bind(null, h),
    $patch: U,
    $reset: Q,
    $subscribe(j, H = {}) {
      const x = wa(f, j, H.detached, () => G()), G = i.run(() => ks(() => n.state.value[e], (S) => {
        (H.flush === "sync" ? u : c) && j({
          storeId: e,
          type: $n.direct,
          events: d
        }, S);
      }, gs({}, l, H)));
      return x;
    },
    $dispose: B
  }, ae = /* @__PURE__ */ qn(q);
  n._s.set(e, ae);
  const re = (n._a && n._a.runWithContext || lm)(() => n._e.run(() => (i = Il()).run(() => t({ action: Y }))));
  for (const j in re) {
    const H = re[j];
    if (/* @__PURE__ */ ot(H) && !dm(H) || /* @__PURE__ */ Ht(H))
      o || (y && um(H) && (/* @__PURE__ */ ot(H) ? H.value = y[j] : Ho(H, y[j])), n.state.value[e][j] = H);
    else if (typeof H == "function") {
      const x = Y(H, j);
      re[j] = x, a.actions[j] = H;
    }
  }
  return gs(ae, re), gs(/* @__PURE__ */ De(ae), re), Object.defineProperty(ae, "$state", {
    get: () => n.state.value[e],
    set: (j) => {
      U((H) => {
        gs(H, j);
      });
    }
  }), n._p.forEach((j) => {
    gs(ae, i.run(() => j({
      store: ae,
      app: n._a,
      pinia: n,
      options: a
    })));
  }), y && o && s.hydrate && s.hydrate(ae.$state, y), c = !0, u = !0, ae;
}
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function mn(e, t, s) {
  let n;
  const r = typeof t == "function";
  n = r ? s : t;
  function o(i, a) {
    const l = bi();
    return i = // in test mode, ignore the argument provided as we can always retrieve a
    // pinia instance with getActivePinia()
    i || (l ? Ct(Pc, null) : null), i && Qr(i), i = $c, i._s.has(e) || (r ? Mc(e, t, n, i) : fm(e, n, i)), i._s.get(e);
  }
  return o.$id = e, o;
}
/*!
 * vue-router v4.6.4
 * (c) 2025 Eduardo San Martin Morote
 * @license MIT
 */
const Ks = typeof document < "u";
function zc(e) {
  return typeof e == "object" || "displayName" in e || "props" in e || "__vccOpts" in e;
}
function mm(e) {
  return e.__esModule || e[Symbol.toStringTag] === "Module" || e.default && zc(e.default);
}
const Qe = Object.assign;
function go(e, t) {
  const s = {};
  for (const n in t) {
    const r = t[n];
    s[n] = zt(r) ? r.map(e) : e(r);
  }
  return s;
}
const Pn = () => {
}, zt = Array.isArray;
function xa(e, t) {
  const s = {};
  for (const n in e) s[n] = n in t ? t[n] : e[n];
  return s;
}
const Dc = /#/g, pm = /&/g, hm = /\//g, gm = /=/g, vm = /\?/g, jc = /\+/g, ym = /%5B/g, bm = /%5D/g, Vc = /%5E/g, wm = /%60/g, Lc = /%7B/g, _m = /%7C/g, Uc = /%7D/g, xm = /%20/g;
function Ei(e) {
  return e == null ? "" : encodeURI("" + e).replace(_m, "|").replace(ym, "[").replace(bm, "]");
}
function km(e) {
  return Ei(e).replace(Lc, "{").replace(Uc, "}").replace(Vc, "^");
}
function qo(e) {
  return Ei(e).replace(jc, "%2B").replace(xm, "+").replace(Dc, "%23").replace(pm, "%26").replace(wm, "`").replace(Lc, "{").replace(Uc, "}").replace(Vc, "^");
}
function Sm(e) {
  return qo(e).replace(gm, "%3D");
}
function Cm(e) {
  return Ei(e).replace(Dc, "%23").replace(vm, "%3F");
}
function Rm(e) {
  return Cm(e).replace(hm, "%2F");
}
function Fn(e) {
  if (e == null) return null;
  try {
    return decodeURIComponent("" + e);
  } catch {
  }
  return "" + e;
}
const Am = /\/$/, Em = (e) => e.replace(Am, "");
function vo(e, t, s = "/") {
  let n, r = {}, o = "", i = "";
  const a = t.indexOf("#");
  let l = t.indexOf("?");
  return l = a >= 0 && l > a ? -1 : l, l >= 0 && (n = t.slice(0, l), o = t.slice(l, a > 0 ? a : t.length), r = e(o.slice(1))), a >= 0 && (n = n || t.slice(0, a), i = t.slice(a, t.length)), n = $m(n ?? t, s), {
    fullPath: n + o + i,
    path: n,
    query: r,
    hash: Fn(i)
  };
}
function Im(e, t) {
  const s = t.query ? e(t.query) : "";
  return t.path + (s && "?") + s + (t.hash || "");
}
function Om(e, t, s) {
  const n = t.matched.length - 1, r = s.matched.length - 1;
  return n > -1 && n === r && on(t.matched[n], s.matched[r]) && Fc(t.params, s.params) && e(t.query) === e(s.query) && t.hash === s.hash;
}
function on(e, t) {
  return (e.aliasOf || e) === (t.aliasOf || t);
}
function Fc(e, t) {
  if (Object.keys(e).length !== Object.keys(t).length) return !1;
  for (var s in e) if (!Tm(e[s], t[s])) return !1;
  return !0;
}
function Tm(e, t) {
  return zt(e) ? ka(e, t) : zt(t) ? ka(t, e) : e?.valueOf() === t?.valueOf();
}
function ka(e, t) {
  return zt(t) ? e.length === t.length && e.every((s, n) => s === t[n]) : e.length === 1 && e[0] === t;
}
function $m(e, t) {
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
const ms = {
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
let Zo = /* @__PURE__ */ (function(e) {
  return e.pop = "pop", e.push = "push", e;
})({}), Sa = /* @__PURE__ */ (function(e) {
  return e.back = "back", e.forward = "forward", e.unknown = "", e;
})({});
const yo = "";
function Pm(e) {
  if (!e) if (Ks) {
    const t = document.querySelector("base");
    e = t && t.getAttribute("href") || "/", e = e.replace(/^\w+:\/\/[^\/]+/, "");
  } else e = "/";
  return e[0] !== "/" && e[0] !== "#" && (e = "/" + e), Em(e);
}
const Nm = /^[^#]+#/;
function Mm(e, t) {
  return e.replace(Nm, "#") + t;
}
function zm(e, t) {
  const s = document.documentElement.getBoundingClientRect(), n = e.getBoundingClientRect();
  return {
    behavior: t.behavior,
    left: n.left - s.left - (t.left || 0),
    top: n.top - s.top - (t.top || 0)
  };
}
const Dm = () => ({
  left: window.scrollX,
  top: window.scrollY
});
function jm(e) {
  let t;
  if ("el" in e) {
    const s = e.el, n = typeof s == "string" && s.startsWith("#"), r = typeof s == "string" ? n ? document.getElementById(s.slice(1)) : document.querySelector(s) : s;
    if (!r)
      return;
    t = zm(r, e);
  } else t = e;
  "scrollBehavior" in document.documentElement.style ? window.scrollTo(t) : window.scrollTo(t.left != null ? t.left : window.scrollX, t.top != null ? t.top : window.scrollY);
}
function Ca(e, t) {
  return (history.state ? history.state.position - t : -1) + e;
}
const Ko = /* @__PURE__ */ new Map();
function Vm(e, t) {
  Ko.set(e, t);
}
function Lm(e) {
  const t = Ko.get(e);
  return Ko.delete(e), t;
}
function Um(e) {
  return typeof e == "string" || e && typeof e == "object";
}
function Wc(e) {
  return typeof e == "string" || typeof e == "symbol";
}
let nt = /* @__PURE__ */ (function(e) {
  return e[e.MATCHER_NOT_FOUND = 1] = "MATCHER_NOT_FOUND", e[e.NAVIGATION_GUARD_REDIRECT = 2] = "NAVIGATION_GUARD_REDIRECT", e[e.NAVIGATION_ABORTED = 4] = "NAVIGATION_ABORTED", e[e.NAVIGATION_CANCELLED = 8] = "NAVIGATION_CANCELLED", e[e.NAVIGATION_DUPLICATED = 16] = "NAVIGATION_DUPLICATED", e;
})({});
const Bc = Symbol("");
nt.MATCHER_NOT_FOUND + "", nt.NAVIGATION_GUARD_REDIRECT + "", nt.NAVIGATION_ABORTED + "", nt.NAVIGATION_CANCELLED + "", nt.NAVIGATION_DUPLICATED + "";
function an(e, t) {
  return Qe(/* @__PURE__ */ new Error(), {
    type: e,
    [Bc]: !0
  }, t);
}
function Xt(e, t) {
  return e instanceof Error && Bc in e && (t == null || !!(e.type & t));
}
const Fm = [
  "params",
  "query",
  "hash"
];
function Wm(e) {
  if (typeof e == "string") return e;
  if (e.path != null) return e.path;
  const t = {};
  for (const s of Fm) s in e && (t[s] = e[s]);
  return JSON.stringify(t, null, 2);
}
function Bm(e) {
  const t = {};
  if (e === "" || e === "?") return t;
  const s = (e[0] === "?" ? e.slice(1) : e).split("&");
  for (let n = 0; n < s.length; ++n) {
    const r = s[n].replace(jc, " "), o = r.indexOf("="), i = Fn(o < 0 ? r : r.slice(0, o)), a = o < 0 ? null : Fn(r.slice(o + 1));
    if (i in t) {
      let l = t[i];
      zt(l) || (l = t[i] = [l]), l.push(a);
    } else t[i] = a;
  }
  return t;
}
function Ra(e) {
  let t = "";
  for (let s in e) {
    const n = e[s];
    if (s = Sm(s), n == null) {
      n !== void 0 && (t += (t.length ? "&" : "") + s);
      continue;
    }
    (zt(n) ? n.map((r) => r && qo(r)) : [n && qo(n)]).forEach((r) => {
      r !== void 0 && (t += (t.length ? "&" : "") + s, r != null && (t += "=" + r));
    });
  }
  return t;
}
function Gm(e) {
  const t = {};
  for (const s in e) {
    const n = e[s];
    n !== void 0 && (t[s] = zt(n) ? n.map((r) => r == null ? null : "" + r) : n == null ? n : "" + n);
  }
  return t;
}
const Hm = Symbol(""), Aa = Symbol(""), Yr = Symbol(""), Ii = Symbol(""), Jo = Symbol("");
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
function bs(e, t, s, n, r, o = (i) => i()) {
  const i = n && (n.enterCallbacks[r] = n.enterCallbacks[r] || []);
  return () => new Promise((a, l) => {
    const c = (h) => {
      h === !1 ? l(an(nt.NAVIGATION_ABORTED, {
        from: s,
        to: t
      })) : h instanceof Error ? l(h) : Um(h) ? l(an(nt.NAVIGATION_GUARD_REDIRECT, {
        from: t,
        to: h
      })) : (i && n.enterCallbacks[r] === i && typeof h == "function" && i.push(h), a());
    }, u = o(() => e.call(n && n.instances[r], t, s, c));
    let f = Promise.resolve(u);
    e.length < 3 && (f = f.then(c)), f.catch((h) => l(h));
  });
}
function bo(e, t, s, n, r = (o) => o()) {
  const o = [];
  for (const i of e)
    for (const a in i.components) {
      let l = i.components[a];
      if (!(t !== "beforeRouteEnter" && !i.instances[a]))
        if (zc(l)) {
          const c = (l.__vccOpts || l)[t];
          c && o.push(bs(c, s, n, i, a, r));
        } else {
          let c = l();
          o.push(() => c.then((u) => {
            if (!u) throw new Error(`Couldn't resolve component "${a}" at "${i.path}"`);
            const f = mm(u) ? u.default : u;
            i.mods[a] = u, i.components[a] = f;
            const h = (f.__vccOpts || f)[t];
            return h && bs(h, s, n, i, a, r)();
          }));
        }
    }
  return o;
}
function qm(e, t) {
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
function Zm(e = "") {
  let t = [], s = [[yo, {}]], n = 0;
  e = Pm(e);
  function r(a, l = {}) {
    n++, n !== s.length && s.splice(n), s.push([a, l]);
  }
  function o(a, l, { direction: c, delta: u }) {
    const f = {
      direction: c,
      delta: u,
      type: Zo.pop
    };
    for (const h of t) h(a, l, f);
  }
  const i = {
    location: yo,
    state: {},
    base: e,
    createHref: Mm.bind(null, e),
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
      t = [], s = [[yo, {}]], n = 0;
    },
    go(a, l = !0) {
      const c = this.location, u = a < 0 ? Sa.back : Sa.forward;
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
let js = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.Group = 2] = "Group", e;
})({});
var ct = /* @__PURE__ */ (function(e) {
  return e[e.Static = 0] = "Static", e[e.Param = 1] = "Param", e[e.ParamRegExp = 2] = "ParamRegExp", e[e.ParamRegExpEnd = 3] = "ParamRegExpEnd", e[e.EscapeNext = 4] = "EscapeNext", e;
})(ct || {});
const Km = {
  type: js.Static,
  value: ""
}, Jm = /[a-zA-Z0-9_]/;
function Qm(e) {
  if (!e) return [[]];
  if (e === "/") return [[Km]];
  if (!e.startsWith("/")) throw new Error(`Invalid path "${e}"`);
  function t(d) {
    throw new Error(`ERR (${s})/"${c}": ${d}`);
  }
  let s = ct.Static, n = s;
  const r = [];
  let o;
  function i() {
    o && r.push(o), o = [];
  }
  let a = 0, l, c = "", u = "";
  function f() {
    c && (s === ct.Static ? o.push({
      type: js.Static,
      value: c
    }) : s === ct.Param || s === ct.ParamRegExp || s === ct.ParamRegExpEnd ? (o.length > 1 && (l === "*" || l === "+") && t(`A repeatable param (${c}) must be alone in its segment. eg: '/:ids+.`), o.push({
      type: js.Param,
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
    if (l = e[a++], l === "\\" && s !== ct.ParamRegExp) {
      n = s, s = ct.EscapeNext;
      continue;
    }
    switch (s) {
      case ct.Static:
        l === "/" ? (c && f(), i()) : l === ":" ? (f(), s = ct.Param) : h();
        break;
      case ct.EscapeNext:
        h(), s = n;
        break;
      case ct.Param:
        l === "(" ? s = ct.ParamRegExp : Jm.test(l) ? h() : (f(), s = ct.Static, l !== "*" && l !== "?" && l !== "+" && a--);
        break;
      case ct.ParamRegExp:
        l === ")" ? u[u.length - 1] == "\\" ? u = u.slice(0, -1) + l : s = ct.ParamRegExpEnd : u += l;
        break;
      case ct.ParamRegExpEnd:
        f(), s = ct.Static, l !== "*" && l !== "?" && l !== "+" && a--, u = "";
        break;
      default:
        t("Unknown state");
        break;
    }
  }
  return s === ct.ParamRegExp && t(`Unfinished custom RegExp for param "${c}"`), f(), i(), r;
}
const Ea = "[^/]+?", Ym = {
  sensitive: !1,
  strict: !1,
  start: !0,
  end: !0
};
var bt = /* @__PURE__ */ (function(e) {
  return e[e._multiplier = 10] = "_multiplier", e[e.Root = 90] = "Root", e[e.Segment = 40] = "Segment", e[e.SubSegment = 30] = "SubSegment", e[e.Static = 40] = "Static", e[e.Dynamic = 20] = "Dynamic", e[e.BonusCustomRegExp = 10] = "BonusCustomRegExp", e[e.BonusWildcard = -50] = "BonusWildcard", e[e.BonusRepeatable = -20] = "BonusRepeatable", e[e.BonusOptional = -8] = "BonusOptional", e[e.BonusStrict = 0.7000000000000001] = "BonusStrict", e[e.BonusCaseSensitive = 0.25] = "BonusCaseSensitive", e;
})(bt || {});
const Xm = /[.+*?^${}()[\]/\\]/g;
function ep(e, t) {
  const s = Qe({}, Ym, t), n = [];
  let r = s.start ? "^" : "";
  const o = [];
  for (const c of e) {
    const u = c.length ? [] : [bt.Root];
    s.strict && !c.length && (r += "/");
    for (let f = 0; f < c.length; f++) {
      const h = c[f];
      let d = bt.Segment + (s.sensitive ? bt.BonusCaseSensitive : 0);
      if (h.type === js.Static)
        f || (r += "/"), r += h.value.replace(Xm, "\\$&"), d += bt.Static;
      else if (h.type === js.Param) {
        const { value: y, repeatable: C, optional: U, regexp: Q } = h;
        o.push({
          name: y,
          repeatable: C,
          optional: U
        });
        const B = Q || Ea;
        if (B !== Ea) {
          d += bt.BonusCustomRegExp;
          try {
            `${B}`;
          } catch (q) {
            throw new Error(`Invalid custom RegExp for param "${y}" (${B}): ` + q.message);
          }
        }
        let Y = C ? `((?:${B})(?:/(?:${B}))*)` : `(${B})`;
        f || (Y = U && c.length < 2 ? `(?:/${Y})` : "/" + Y), U && (Y += "?"), r += Y, d += bt.Dynamic, U && (d += bt.BonusOptional), C && (d += bt.BonusRepeatable), B === ".*" && (d += bt.BonusWildcard);
      }
      u.push(d);
    }
    n.push(u);
  }
  if (s.strict && s.end) {
    const c = n.length - 1;
    n[c][n[c].length - 1] += bt.BonusStrict;
  }
  s.strict || (r += "/?"), s.end ? r += "$" : s.strict && !r.endsWith("/") && (r += "(?:/|$)");
  const i = new RegExp(r, s.sensitive ? "" : "i");
  function a(c) {
    const u = c.match(i), f = {};
    if (!u) return null;
    for (let h = 1; h < u.length; h++) {
      const d = u[h] || "", y = o[h - 1];
      f[y.name] = d && y.repeatable ? d.split("/") : d;
    }
    return f;
  }
  function l(c) {
    let u = "", f = !1;
    for (const h of e) {
      (!f || !u.endsWith("/")) && (u += "/"), f = !1;
      for (const d of h) if (d.type === js.Static) u += d.value;
      else if (d.type === js.Param) {
        const { value: y, repeatable: C, optional: U } = d, Q = y in c ? c[y] : "";
        if (zt(Q) && !C) throw new Error(`Provided param "${y}" is an array but it is not repeatable (* or + modifiers)`);
        const B = zt(Q) ? Q.join("/") : Q;
        if (!B) if (U)
          h.length < 2 && (u.endsWith("/") ? u = u.slice(0, -1) : f = !0);
        else throw new Error(`Missing required param "${y}"`);
        u += B;
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
function tp(e, t) {
  let s = 0;
  for (; s < e.length && s < t.length; ) {
    const n = t[s] - e[s];
    if (n) return n;
    s++;
  }
  return e.length < t.length ? e.length === 1 && e[0] === bt.Static + bt.Segment ? -1 : 1 : e.length > t.length ? t.length === 1 && t[0] === bt.Static + bt.Segment ? 1 : -1 : 0;
}
function Gc(e, t) {
  let s = 0;
  const n = e.score, r = t.score;
  for (; s < n.length && s < r.length; ) {
    const o = tp(n[s], r[s]);
    if (o) return o;
    s++;
  }
  if (Math.abs(r.length - n.length) === 1) {
    if (Ia(n)) return 1;
    if (Ia(r)) return -1;
  }
  return r.length - n.length;
}
function Ia(e) {
  const t = e[e.length - 1];
  return e.length > 0 && t[t.length - 1] < 0;
}
const sp = {
  strict: !1,
  end: !0,
  sensitive: !1
};
function np(e, t, s) {
  const n = ep(Qm(e.path), s), r = Qe(n, {
    record: e,
    parent: t,
    children: [],
    alias: []
  });
  return t && !r.record.aliasOf == !t.record.aliasOf && t.children.push(r), r;
}
function rp(e, t) {
  const s = [], n = /* @__PURE__ */ new Map();
  t = xa(sp, t);
  function r(f) {
    return n.get(f);
  }
  function o(f, h, d) {
    const y = !d, C = Ta(f);
    C.aliasOf = d && d.record;
    const U = xa(t, f), Q = [C];
    if ("alias" in f) {
      const q = typeof f.alias == "string" ? [f.alias] : f.alias;
      for (const ae of q) Q.push(Ta(Qe({}, C, {
        components: d ? d.record.components : C.components,
        path: ae,
        aliasOf: d ? d.record : C
      })));
    }
    let B, Y;
    for (const q of Q) {
      const { path: ae } = q;
      if (h && ae[0] !== "/") {
        const ye = h.record.path, re = ye[ye.length - 1] === "/" ? "" : "/";
        q.path = h.record.path + (ae && re + ae);
      }
      if (B = np(q, h, U), d ? d.alias.push(B) : (Y = Y || B, Y !== B && Y.alias.push(B), y && f.name && !$a(B) && i(f.name)), Hc(B) && l(B), C.children) {
        const ye = C.children;
        for (let re = 0; re < ye.length; re++) o(ye[re], B, d && d.children[re]);
      }
      d = d || B;
    }
    return Y ? () => {
      i(Y);
    } : Pn;
  }
  function i(f) {
    if (Wc(f)) {
      const h = n.get(f);
      h && (n.delete(f), s.splice(s.indexOf(h), 1), h.children.forEach(i), h.alias.forEach(i));
    } else {
      const h = s.indexOf(f);
      h > -1 && (s.splice(h, 1), f.record.name && n.delete(f.record.name), f.children.forEach(i), f.alias.forEach(i));
    }
  }
  function a() {
    return s;
  }
  function l(f) {
    const h = ap(f, s);
    s.splice(h, 0, f), f.record.name && !$a(f) && n.set(f.record.name, f);
  }
  function c(f, h) {
    let d, y = {}, C, U;
    if ("name" in f && f.name) {
      if (d = n.get(f.name), !d) throw an(nt.MATCHER_NOT_FOUND, { location: f });
      U = d.record.name, y = Qe(Oa(h.params, d.keys.filter((Y) => !Y.optional).concat(d.parent ? d.parent.keys.filter((Y) => Y.optional) : []).map((Y) => Y.name)), f.params && Oa(f.params, d.keys.map((Y) => Y.name))), C = d.stringify(y);
    } else if (f.path != null)
      C = f.path, d = s.find((Y) => Y.re.test(C)), d && (y = d.parse(C), U = d.record.name);
    else {
      if (d = h.name ? n.get(h.name) : s.find((Y) => Y.re.test(h.path)), !d) throw an(nt.MATCHER_NOT_FOUND, {
        location: f,
        currentLocation: h
      });
      U = d.record.name, y = Qe({}, h.params, f.params), C = d.stringify(y);
    }
    const Q = [];
    let B = d;
    for (; B; )
      Q.unshift(B.record), B = B.parent;
    return {
      name: U,
      path: C,
      params: y,
      matched: Q,
      meta: ip(Q)
    };
  }
  e.forEach((f) => o(f));
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
function Oa(e, t) {
  const s = {};
  for (const n of t) n in e && (s[n] = e[n]);
  return s;
}
function Ta(e) {
  const t = {
    path: e.path,
    redirect: e.redirect,
    name: e.name,
    meta: e.meta || {},
    aliasOf: e.aliasOf,
    beforeEnter: e.beforeEnter,
    props: op(e),
    children: e.children || [],
    instances: {},
    leaveGuards: /* @__PURE__ */ new Set(),
    updateGuards: /* @__PURE__ */ new Set(),
    enterCallbacks: {},
    components: "components" in e ? e.components || null : e.component && { default: e.component }
  };
  return Object.defineProperty(t, "mods", { value: {} }), t;
}
function op(e) {
  const t = {}, s = e.props || !1;
  if ("component" in e) t.default = s;
  else for (const n in e.components) t[n] = typeof s == "object" ? s[n] : s;
  return t;
}
function $a(e) {
  for (; e; ) {
    if (e.record.aliasOf) return !0;
    e = e.parent;
  }
  return !1;
}
function ip(e) {
  return e.reduce((t, s) => Qe(t, s.meta), {});
}
function ap(e, t) {
  let s = 0, n = t.length;
  for (; s !== n; ) {
    const o = s + n >> 1;
    Gc(e, t[o]) < 0 ? n = o : s = o + 1;
  }
  const r = lp(e);
  return r && (n = t.lastIndexOf(r, n - 1)), n;
}
function lp(e) {
  let t = e;
  for (; t = t.parent; ) if (Hc(t) && Gc(e, t) === 0) return t;
}
function Hc({ record: e }) {
  return !!(e.name || e.components && Object.keys(e.components).length || e.redirect);
}
function Pa(e) {
  const t = Ct(Yr), s = Ct(Ii), n = Ve(() => {
    const l = g(e.to);
    return t.resolve(l);
  }), r = Ve(() => {
    const { matched: l } = n.value, { length: c } = l, u = l[c - 1], f = s.matched;
    if (!u || !f.length) return -1;
    const h = f.findIndex(on.bind(null, u));
    if (h > -1) return h;
    const d = Na(l[c - 2]);
    return c > 1 && Na(u) === d && f[f.length - 1].path !== d ? f.findIndex(on.bind(null, l[c - 2])) : h;
  }), o = Ve(() => r.value > -1 && fp(s.params, n.value.params)), i = Ve(() => r.value > -1 && r.value === s.matched.length - 1 && Fc(s.params, n.value.params));
  function a(l = {}) {
    if (dp(l)) {
      const c = t[g(e.replace) ? "replace" : "push"](g(e.to)).catch(Pn);
      return e.viewTransition && typeof document < "u" && "startViewTransition" in document && document.startViewTransition(() => c), c;
    }
    return Promise.resolve();
  }
  return {
    route: n,
    href: Ve(() => n.value.href),
    isActive: o,
    isExactActive: i,
    navigate: a
  };
}
function cp(e) {
  return e.length === 1 ? e[0] : e;
}
const up = /* @__PURE__ */ St({
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
  useLink: Pa,
  setup(e, { slots: t }) {
    const s = /* @__PURE__ */ qn(Pa(e)), { options: n } = Ct(Yr), r = Ve(() => ({
      [Ma(e.activeClass, n.linkActiveClass, "router-link-active")]: s.isActive,
      [Ma(e.exactActiveClass, n.linkExactActiveClass, "router-link-exact-active")]: s.isExactActive
    }));
    return () => {
      const o = t.default && cp(t.default(s));
      return e.custom ? o : Ln("a", {
        "aria-current": s.isExactActive ? e.ariaCurrentValue : null,
        href: s.href,
        onClick: s.navigate,
        class: r.value
      }, o);
    };
  }
}), qc = up;
function dp(e) {
  if (!(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) && !e.defaultPrevented && !(e.button !== void 0 && e.button !== 0)) {
    if (e.currentTarget && e.currentTarget.getAttribute) {
      const t = e.currentTarget.getAttribute("target");
      if (/\b_blank\b/i.test(t)) return;
    }
    return e.preventDefault && e.preventDefault(), !0;
  }
}
function fp(e, t) {
  for (const s in t) {
    const n = t[s], r = e[s];
    if (typeof n == "string") {
      if (n !== r) return !1;
    } else if (!zt(r) || r.length !== n.length || n.some((o, i) => o.valueOf() !== r[i].valueOf())) return !1;
  }
  return !0;
}
function Na(e) {
  return e ? e.aliasOf ? e.aliasOf.path : e.path : "";
}
const Ma = (e, t, s) => e ?? t ?? s, mp = /* @__PURE__ */ St({
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
    const n = Ct(Jo), r = Ve(() => e.route || n.value), o = Ct(Aa, 0), i = Ve(() => {
      let c = g(o);
      const { matched: u } = r.value;
      let f;
      for (; (f = u[c]) && !f.components; ) c++;
      return c;
    }), a = Ve(() => r.value.matched[i.value]);
    mr(Aa, Ve(() => i.value + 1)), mr(Hm, a), mr(Jo, r);
    const l = /* @__PURE__ */ E();
    return ks(() => [
      l.value,
      a.value,
      e.name
    ], ([c, u, f], [h, d, y]) => {
      u && (u.instances[f] = c, d && d !== u && c && c === h && (u.leaveGuards.size || (u.leaveGuards = d.leaveGuards), u.updateGuards.size || (u.updateGuards = d.updateGuards))), c && u && (!d || !on(u, d) || !h) && (u.enterCallbacks[f] || []).forEach((C) => C(c));
    }, { flush: "post" }), () => {
      const c = r.value, u = e.name, f = a.value, h = f && f.components[u];
      if (!h) return za(s.default, {
        Component: h,
        route: c
      });
      const d = f.props[u], y = d ? d === !0 ? c.params : typeof d == "function" ? d(c) : d : null, U = Ln(h, Qe({}, y, t, {
        onVnodeUnmounted: (Q) => {
          Q.component.isUnmounted && (f.instances[u] = null);
        },
        ref: l
      }));
      return za(s.default, {
        Component: U,
        route: c
      }) || U;
    };
  }
});
function za(e, t) {
  if (!e) return null;
  const s = e(t);
  return s.length === 1 ? s[0] : s;
}
const Zc = mp;
function pp(e) {
  const t = rp(e.routes, e), s = e.parseQuery || Bm, n = e.stringifyQuery || Ra, r = e.history, o = gn(), i = gn(), a = gn(), l = /* @__PURE__ */ In(ms);
  let c = ms;
  Ks && e.scrollBehavior && "scrollRestoration" in history && (history.scrollRestoration = "manual");
  const u = go.bind(null, (L) => "" + L), f = go.bind(null, Rm), h = go.bind(null, Fn);
  function d(L, A) {
    let O, ie;
    return Wc(L) ? (O = t.getRecordMatcher(L), ie = A) : ie = L, t.addRoute(ie, O);
  }
  function y(L) {
    const A = t.getRecordMatcher(L);
    A && t.removeRoute(A);
  }
  function C() {
    return t.getRoutes().map((L) => L.record);
  }
  function U(L) {
    return !!t.getRecordMatcher(L);
  }
  function Q(L, A) {
    if (A = Qe({}, A || l.value), typeof L == "string") {
      const R = vo(s, L, A.path), P = t.resolve({ path: R.path }, A), W = r.createHref(R.fullPath);
      return Qe(R, P, {
        params: h(P.params),
        hash: Fn(R.hash),
        redirectedFrom: void 0,
        href: W
      });
    }
    let O;
    if (L.path != null)
      O = Qe({}, L, { path: vo(s, L.path, A.path).path });
    else {
      const R = Qe({}, L.params);
      for (const P in R) R[P] == null && delete R[P];
      O = Qe({}, L, { params: f(R) }), A.params = f(A.params);
    }
    const ie = t.resolve(O, A), p = L.hash || "";
    ie.params = u(h(ie.params));
    const v = Im(n, Qe({}, L, {
      hash: km(p),
      path: ie.path
    })), k = r.createHref(v);
    return Qe({
      fullPath: v,
      hash: p,
      query: n === Ra ? Gm(L.query) : L.query || {}
    }, ie, {
      redirectedFrom: void 0,
      href: k
    });
  }
  function B(L) {
    return typeof L == "string" ? vo(s, L, l.value.path) : Qe({}, L);
  }
  function Y(L, A) {
    if (c !== L) return an(nt.NAVIGATION_CANCELLED, {
      from: A,
      to: L
    });
  }
  function q(L) {
    return re(L);
  }
  function ae(L) {
    return q(Qe(B(L), { replace: !0 }));
  }
  function ye(L, A) {
    const O = L.matched[L.matched.length - 1];
    if (O && O.redirect) {
      const { redirect: ie } = O;
      let p = typeof ie == "function" ? ie(L, A) : ie;
      return typeof p == "string" && (p = p.includes("?") || p.includes("#") ? p = B(p) : { path: p }, p.params = {}), Qe({
        query: L.query,
        hash: L.hash,
        params: p.path != null ? {} : L.params
      }, p);
    }
  }
  function re(L, A) {
    const O = c = Q(L), ie = l.value, p = L.state, v = L.force, k = L.replace === !0, R = ye(O, ie);
    if (R) return re(Qe(B(R), {
      state: typeof R == "object" ? Qe({}, p, R.state) : p,
      force: v,
      replace: k
    }), A || O);
    const P = O;
    P.redirectedFrom = A;
    let W;
    return !v && Om(n, ie, O) && (W = an(nt.NAVIGATION_DUPLICATED, {
      to: P,
      from: ie
    }), Xe(ie, ie, !0, !1)), (W ? Promise.resolve(W) : x(P, ie)).catch((_) => Xt(_) ? Xt(_, nt.NAVIGATION_GUARD_REDIRECT) ? _ : oe(_) : ve(_, P, ie)).then((_) => {
      if (_) {
        if (Xt(_, nt.NAVIGATION_GUARD_REDIRECT))
          return re(Qe({ replace: k }, B(_.to), {
            state: typeof _.to == "object" ? Qe({}, p, _.to.state) : p,
            force: v
          }), A || P);
      } else _ = S(P, ie, !0, k, p);
      return G(P, ie, _), _;
    });
  }
  function j(L, A) {
    const O = Y(L, A);
    return O ? Promise.reject(O) : Promise.resolve();
  }
  function H(L) {
    const A = at.values().next().value;
    return A && typeof A.runWithContext == "function" ? A.runWithContext(L) : L();
  }
  function x(L, A) {
    let O;
    const [ie, p, v] = qm(L, A);
    O = bo(ie.reverse(), "beforeRouteLeave", L, A);
    for (const R of ie) R.leaveGuards.forEach((P) => {
      O.push(bs(P, L, A));
    });
    const k = j.bind(null, L, A);
    return O.push(k), Ne(O).then(() => {
      O = [];
      for (const R of o.list()) O.push(bs(R, L, A));
      return O.push(k), Ne(O);
    }).then(() => {
      O = bo(p, "beforeRouteUpdate", L, A);
      for (const R of p) R.updateGuards.forEach((P) => {
        O.push(bs(P, L, A));
      });
      return O.push(k), Ne(O);
    }).then(() => {
      O = [];
      for (const R of v) if (R.beforeEnter) if (zt(R.beforeEnter)) for (const P of R.beforeEnter) O.push(bs(P, L, A));
      else O.push(bs(R.beforeEnter, L, A));
      return O.push(k), Ne(O);
    }).then(() => (L.matched.forEach((R) => R.enterCallbacks = {}), O = bo(v, "beforeRouteEnter", L, A, H), O.push(k), Ne(O))).then(() => {
      O = [];
      for (const R of i.list()) O.push(bs(R, L, A));
      return O.push(k), Ne(O);
    }).catch((R) => Xt(R, nt.NAVIGATION_CANCELLED) ? R : Promise.reject(R));
  }
  function G(L, A, O) {
    a.list().forEach((ie) => H(() => ie(L, A, O)));
  }
  function S(L, A, O, ie, p) {
    const v = Y(L, A);
    if (v) return v;
    const k = A === ms, R = Ks ? history.state : {};
    O && (ie || k ? r.replace(L.fullPath, Qe({ scroll: k && R && R.scroll }, p)) : r.push(L.fullPath, p)), l.value = L, Xe(L, A, O, k), oe();
  }
  let X;
  function ke() {
    X || (X = r.listen((L, A, O) => {
      if (!ze.listening) return;
      const ie = Q(L), p = ye(ie, ze.currentRoute.value);
      if (p) {
        re(Qe(p, {
          replace: !0,
          force: !0
        }), ie).catch(Pn);
        return;
      }
      c = ie;
      const v = l.value;
      Ks && Vm(Ca(v.fullPath, O.delta), Dm()), x(ie, v).catch((k) => Xt(k, nt.NAVIGATION_ABORTED | nt.NAVIGATION_CANCELLED) ? k : Xt(k, nt.NAVIGATION_GUARD_REDIRECT) ? (re(Qe(B(k.to), { force: !0 }), ie).then((R) => {
        Xt(R, nt.NAVIGATION_ABORTED | nt.NAVIGATION_DUPLICATED) && !O.delta && O.type === Zo.pop && r.go(-1, !1);
      }).catch(Pn), Promise.reject()) : (O.delta && r.go(-O.delta, !1), ve(k, ie, v))).then((k) => {
        k = k || S(ie, v, !1), k && (O.delta && !Xt(k, nt.NAVIGATION_CANCELLED) ? r.go(-O.delta, !1) : O.type === Zo.pop && Xt(k, nt.NAVIGATION_ABORTED | nt.NAVIGATION_DUPLICATED) && r.go(-1, !1)), G(ie, v, k);
      }).catch(Pn);
    }));
  }
  let xe = gn(), b = gn(), $;
  function ve(L, A, O) {
    oe(L);
    const ie = b.list();
    return ie.length ? ie.forEach((p) => p(L, A, O)) : console.error(L), Promise.reject(L);
  }
  function Fe() {
    return $ && l.value !== ms ? Promise.resolve() : new Promise((L, A) => {
      xe.add([L, A]);
    });
  }
  function oe(L) {
    return $ || ($ = !L, ke(), xe.list().forEach(([A, O]) => L ? O(L) : A()), xe.reset()), L;
  }
  function Xe(L, A, O, ie) {
    const { scrollBehavior: p } = e;
    if (!Ks || !p) return Promise.resolve();
    const v = !O && Lm(Ca(L.fullPath, 0)) || (ie || !O) && history.state && history.state.scroll || null;
    return Br().then(() => p(L, A, v)).then((k) => k && jm(k)).catch((k) => ve(k, L, A));
  }
  const Ke = (L) => r.go(L);
  let ft;
  const at = /* @__PURE__ */ new Set(), ze = {
    currentRoute: l,
    listening: !0,
    addRoute: d,
    removeRoute: y,
    clearRoutes: t.clearRoutes,
    hasRoute: U,
    getRoutes: C,
    resolve: Q,
    options: e,
    push: q,
    replace: ae,
    go: Ke,
    back: () => Ke(-1),
    forward: () => Ke(1),
    beforeEach: o.add,
    beforeResolve: i.add,
    afterEach: a.add,
    onError: b.add,
    isReady: Fe,
    install(L) {
      L.component("RouterLink", qc), L.component("RouterView", Zc), L.config.globalProperties.$router = ze, Object.defineProperty(L.config.globalProperties, "$route", {
        enumerable: !0,
        get: () => g(l)
      }), Ks && !ft && l.value === ms && (ft = !0, q(r.location).catch((ie) => {
      }));
      const A = {};
      for (const ie in ms) Object.defineProperty(A, ie, {
        get: () => l.value[ie],
        enumerable: !0
      });
      L.provide(Yr, ze), L.provide(Ii, /* @__PURE__ */ Hl(A)), L.provide(Jo, l);
      const O = L.unmount;
      at.add(L), L.unmount = function() {
        at.delete(L), at.size < 1 && (c = ms, X && X(), X = null, l.value = ms, ft = !1, $ = !1), O();
      };
    }
  };
  function Ne(L) {
    return L.reduce((A, O) => A.then(() => H(O)), Promise.resolve());
  }
  return ze;
}
function hp() {
  return Ct(Yr);
}
function Kc(e) {
  return Ct(Ii);
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ps = {
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
const Da = (...e) => e.filter((t, s, n) => !!t && t.trim() !== "" && n.indexOf(t) === s).join(" ").trim();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function wo(e) {
  return e != null;
}
function gp(e, t = {}) {
  const s = t.attributeNames ?? {}, n = (h) => s[h] ?? h, r = e.size ?? e.width ?? Ps.width, o = e.size ?? e.height ?? Ps.height, i = e.aliases?.filter((h) => typeof h == "string" && h.trim() !== "").map((h) => `lucide-${h}`) ?? [], a = [...e.name ? [`lucide-${e.name}`] : [], ...i], l = t.className?.split(" ").filter(Boolean) ?? [], c = t.includeDefaultClasses === !1 ? Da(...l) : Da("lucide", ...a, ...l), u = t.absoluteStrokeWidth ? Number(t.strokeWidth ?? Ps["stroke-width"]) * Number(e.size ?? e.width ?? Ps.width) / Number(t.size ?? t.width ?? Ps.width) : t.strokeWidth ?? Ps["stroke-width"];
  return [
    "svg",
    {
      ...Object.entries(Ps).reduce((h, [d, y]) => (h[n(d)] = y, h), {}),
      ..."color" in t && t.color && {
        [n("stroke")]: t.color
      },
      ..."size" in t && wo(t.size) && {
        [n("width")]: t.size,
        [n("height")]: t.size
      },
      ..."width" in t && wo(t.width) && {
        [n("width")]: t.width
      },
      ..."height" in t && wo(t.height) && {
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
      const [d, y, C] = h, U = t.nonScalingStroke ? { [n("vector-effect")]: "non-scaling-stroke", ...y } : y;
      return C ? [d, U, C] : [d, U];
    })
  ];
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const vp = (e) => {
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
const rr = (e) => e === "";
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const yp = (e) => e?.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const bp = /* @__PURE__ */ Symbol("lucide-icons");
function wp() {
  return Ct(bp, {});
}
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const _p = ({
  name: e,
  iconNode: t,
  "icon-node": s,
  icon: n = {
    name: e && yp(e),
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
  width: f = u,
  height: h = u,
  color: d,
  ...y
}, { slots: C }) => {
  const {
    size: U,
    color: Q,
    strokeWidth: B = 2,
    absoluteStrokeWidth: Y = !1,
    nonScalingStroke: q = !1,
    class: ae = ""
  } = wp(), ye = rr(r) || rr(o) || r === !0 || o === !0 || Y === !0, re = rr(i) || rr(a) || i === !0 || a === !0 || q === !0;
  delete y.class;
  const j = C.default?.(), [, H, x = []] = gp(n, {
    color: d ?? Q,
    width: f ?? u ?? U,
    height: h ?? u ?? U,
    strokeWidth: l ?? c ?? B,
    absoluteStrokeWidth: ye,
    nonScalingStroke: re,
    className: ae,
    hasA11yProp: j != null && j.length > 0 || vp(y),
    attributes: y
  });
  return Ln("svg", H, [
    ...x.map(([G, S]) => Ln(G, S)),
    ...j ?? []
  ]);
};
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
function Dt(e, t = []) {
  const s = typeof e == "string" ? {
    name: e,
    node: t
  } : e;
  return (n, { slots: r }) => Ln(
    _p,
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
const xp = {
  name: "database",
  size: 24,
  node: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]
}, kp = Dt(xp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Sp = {
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
}, Jc = Dt(Sp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Cp = {
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
}, Qo = Dt(Cp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Rp = {
  name: "monitor-smartphone",
  size: 24,
  node: [
    ["path", { d: "M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8", key: "10dyio" }],
    ["path", { d: "M10 19v-3.96 3.15", key: "1irgej" }],
    ["path", { d: "M7 19h5", key: "qswx4l" }],
    ["rect", { width: "6", height: "10", x: "16", y: "12", rx: "2", key: "1egngj" }]
  ]
}, Ap = Dt(Rp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Ep = {
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
}, Ip = Dt(Ep);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Op = {
  name: "refresh-cw",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]
}, Xr = Dt(Op);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Tp = {
  name: "rotate-ccw-clock",
  size: 24,
  node: [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ],
  aliases: ["history"]
}, Qc = Dt(Tp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const $p = {
  name: "search",
  size: 24,
  node: [
    ["path", { d: "m21 21-4.34-4.34", key: "14j7rj" }],
    ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }]
  ]
}, Pp = Dt($p);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Np = {
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
}, Yc = Dt(Np);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Mp = {
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
}, Xc = Dt(Mp);
/**
 * @license @lucide/vue v1.57.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const zp = {
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
}, Dp = Dt(zp);
function jp(e) {
  return ui() ? (Ol(e), !0) : !1;
}
const _o = /* @__PURE__ */ new WeakMap(), Vp = /* @__NO_SIDE_EFFECTS__ */ (...e) => {
  var t;
  const s = e[0], n = (t = Kr()) == null ? void 0 : t.proxy;
  if (n == null && !bi())
    throw new Error("injectLocal must be called in setup");
  return n && _o.has(n) && s in _o.get(n) ? _o.get(n)[s] : Ct(...e);
}, Lp = typeof window < "u" && typeof document < "u";
typeof WorkerGlobalScope < "u" && globalThis instanceof WorkerGlobalScope;
const Up = Object.prototype.toString, Fp = (e) => Up.call(e) === "[object Object]";
function ja(e) {
  return e.endsWith("rem") ? Number.parseFloat(e) * 16 : Number.parseFloat(e);
}
function xo(e) {
  return Array.isArray(e) ? e : [e];
}
function Wp(e, t, s) {
  return ks(
    e,
    t,
    {
      ...s,
      immediate: !0
    }
  );
}
const eu = Lp ? window : void 0;
function Bp(e) {
  var t;
  const s = Ys(e);
  return (t = s?.$el) != null ? t : s;
}
function Gp(...e) {
  const t = [], s = () => {
    t.forEach((a) => a()), t.length = 0;
  }, n = (a, l, c, u) => (a.addEventListener(l, c, u), () => a.removeEventListener(l, c, u)), r = Ve(() => {
    const a = xo(Ys(e[0])).filter((l) => l != null);
    return a.every((l) => typeof l != "string") ? a : void 0;
  }), o = Wp(
    () => {
      var a, l;
      return [
        (l = (a = r.value) == null ? void 0 : a.map((c) => Bp(c))) != null ? l : [eu].filter((c) => c != null),
        xo(Ys(r.value ? e[1] : e[0])),
        xo(g(r.value ? e[2] : e[1])),
        // @ts-expect-error - TypeScript gets the correct types, but somehow still complains
        Ys(r.value ? e[3] : e[2])
      ];
    },
    ([a, l, c, u]) => {
      if (s(), !a?.length || !l?.length || !c?.length)
        return;
      const f = Fp(u) ? { ...u } : u;
      t.push(
        ...a.flatMap(
          (h) => l.flatMap(
            (d) => c.map((y) => n(h, d, y, f))
          )
        )
      );
    },
    { flush: "post" }
  ), i = () => {
    o(), s();
  };
  return jp(s), i;
}
// @__NO_SIDE_EFFECTS__
function Hp() {
  const e = /* @__PURE__ */ In(!1), t = Kr();
  return t && fs(() => {
    e.value = !0;
  }, t), e;
}
// @__NO_SIDE_EFFECTS__
function qp(e) {
  const t = /* @__PURE__ */ Hp();
  return Ve(() => (t.value, !!e()));
}
const Zp = Symbol("vueuse-ssr-width");
// @__NO_SIDE_EFFECTS__
function Kp() {
  const e = bi() ? /* @__PURE__ */ Vp(Zp, null) : null;
  return typeof e == "number" ? e : void 0;
}
function Jp(e, t = {}) {
  const { window: s = eu, ssrWidth: n = /* @__PURE__ */ Kp() } = t, r = /* @__PURE__ */ qp(() => s && "matchMedia" in s && typeof s.matchMedia == "function"), o = /* @__PURE__ */ In(typeof n == "number"), i = /* @__PURE__ */ In(), a = /* @__PURE__ */ In(!1), l = (c) => {
    a.value = c.matches;
  };
  return xd(() => {
    if (o.value) {
      o.value = !r.value;
      const c = Ys(e).split(",");
      a.value = c.some((u) => {
        const f = u.includes("not all"), h = u.match(/\(\s*min-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/), d = u.match(/\(\s*max-width:\s*(-?\d+(?:\.\d*)?[a-z]+\s*)\)/);
        let y = !!(h || d);
        return h && y && (y = n >= ja(h[1])), d && y && (y = n <= ja(d[1])), f ? !y : y;
      });
      return;
    }
    r.value && (i.value = s.matchMedia(Ys(e)), a.value = i.value.matches);
  }), Gp(i, "change", l, { passive: !0 }), Ve(() => a.value);
}
const tu = "comfymodal", Oi = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings"
], Qp = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings"
};
function Rs(e) {
  return typeof e == "string" && Oi.indexOf(e) !== -1;
}
function or(e) {
  try {
    return decodeURIComponent(e);
  } catch {
    return null;
  }
}
function su(e) {
  const t = { matched: !1, page: "", focus: null };
  if (typeof e != "string") return t;
  const s = e.charAt(0) === "#" ? e.slice(1) : e;
  if (s === "") return t;
  const n = s.split("&"), r = n[0], o = r.indexOf("=");
  if (o === -1 || or(r.slice(0, o)) !== tu) return t;
  const i = or(r.slice(o + 1));
  if (!Rs(i)) return t;
  let a = null;
  for (let l = 1; l < n.length; l++) {
    const c = n[l], u = c.indexOf("=");
    if (u === -1 || or(c.slice(0, u)) !== "focus") continue;
    const f = or(c.slice(u + 1));
    a = f === null || f === "" ? null : f;
    break;
  }
  return { matched: !0, page: i, focus: a };
}
function nu(e) {
  if (!Rs(e?.page)) return "";
  const t = typeof e.focus == "string" && e.focus !== "" ? e.focus : null;
  return "#" + tu + "=" + e.page + (t ? "&focus=" + encodeURIComponent(t) : "");
}
function Va(e, t) {
  if (!t || !Rs(t.page)) return "none";
  if (!e || !Rs(e.page)) return "replace";
  if (t.page !== e.page) return "push";
  const s = e.focus || null, n = t.focus || null;
  return s === n ? "none" : "replace";
}
function Yp(e, t) {
  if (e && Rs(e.page))
    return {
      page: e.page,
      focus: typeof e.focus == "string" && e.focus !== "" ? e.focus : null
    };
  const s = su(t);
  return s.matched && Rs(s.page) ? { page: s.page, focus: s.focus } : { page: "playground", focus: null };
}
const Xp = /* @__PURE__ */ new Set([
  "completed",
  "failed",
  "canceled"
]);
function ko(e) {
  return Xp.has(e);
}
let La = 0;
function eh() {
  return La += 1, typeof crypto < "u" && typeof crypto.randomUUID == "function" ? `op_${crypto.randomUUID()}` : `op_${Date.now().toString(36)}_${La}`;
}
const It = /* @__PURE__ */ mn("studio-operations", () => {
  const e = /* @__PURE__ */ E(/* @__PURE__ */ new Map()), t = Ve(() => [...e.value.values()]), s = Ve(
    () => t.value.filter((h) => h.status === "pending" || h.status === "running")
  );
  function n(h) {
    return e.value.get(h);
  }
  function r(h) {
    const d = Date.now(), y = eh(), C = h.status === "pending" ? "pending" : "running";
    return e.value.set(y, {
      id: y,
      kind: h.kind,
      label: h.label,
      status: C,
      progress: h.progress,
      message: h.message,
      startedAt: d,
      finishedAt: void 0,
      workspaceId: h.workspaceId
    }), y;
  }
  function o(h, d) {
    const y = e.value.get(h);
    if (!y) return;
    const { status: C, ...U } = d, Q = { ...y, ...U };
    !ko(y.status) && C !== void 0 && !ko(C) && (Q.status = C), e.value.set(h, Q);
  }
  function i(h, d, y) {
    const C = e.value.get(h);
    !C || ko(C.status) || e.value.set(h, {
      ...C,
      status: d,
      message: y === void 0 ? C.message : y,
      finishedAt: Date.now()
    });
  }
  function a(h, d) {
    i(h, "completed", d);
  }
  function l(h, d) {
    i(h, "failed", d);
  }
  function c(h, d) {
    i(h, "canceled", d);
  }
  function u(h) {
    e.value.delete(h);
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
    finish: a,
    fail: l,
    cancel: c,
    remove: u,
    clear: f
  };
});
var je;
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
})(je || (je = {}));
var Ua;
(function(e) {
  e.mergeShapes = (t, s) => ({
    ...t,
    ...s
    // second overwrites first
  });
})(Ua || (Ua = {}));
const me = je.arrayToEnum([
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
]), ws = (e) => {
  switch (typeof e) {
    case "undefined":
      return me.undefined;
    case "string":
      return me.string;
    case "number":
      return Number.isNaN(e) ? me.nan : me.number;
    case "boolean":
      return me.boolean;
    case "function":
      return me.function;
    case "bigint":
      return me.bigint;
    case "symbol":
      return me.symbol;
    case "object":
      return Array.isArray(e) ? me.array : e === null ? me.null : e.then && typeof e.then == "function" && e.catch && typeof e.catch == "function" ? me.promise : typeof Map < "u" && e instanceof Map ? me.map : typeof Set < "u" && e instanceof Set ? me.set : typeof Date < "u" && e instanceof Date ? me.date : me.object;
    default:
      return me.unknown;
  }
}, te = je.arrayToEnum([
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
class us extends Error {
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
    if (!(t instanceof us))
      throw new Error(`Not a ZodError: ${t}`);
  }
  toString() {
    return this.message;
  }
  get message() {
    return JSON.stringify(this.issues, je.jsonStringifyReplacer, 2);
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
us.create = (e) => new us(e);
const Yo = (e, t) => {
  let s;
  switch (e.code) {
    case te.invalid_type:
      e.received === me.undefined ? s = "Required" : s = `Expected ${e.expected}, received ${e.received}`;
      break;
    case te.invalid_literal:
      s = `Invalid literal value, expected ${JSON.stringify(e.expected, je.jsonStringifyReplacer)}`;
      break;
    case te.unrecognized_keys:
      s = `Unrecognized key(s) in object: ${je.joinValues(e.keys, ", ")}`;
      break;
    case te.invalid_union:
      s = "Invalid input";
      break;
    case te.invalid_union_discriminator:
      s = `Invalid discriminator value. Expected ${je.joinValues(e.options)}`;
      break;
    case te.invalid_enum_value:
      s = `Invalid enum value. Expected ${je.joinValues(e.options)}, received '${e.received}'`;
      break;
    case te.invalid_arguments:
      s = "Invalid function arguments";
      break;
    case te.invalid_return_type:
      s = "Invalid function return type";
      break;
    case te.invalid_date:
      s = "Invalid date";
      break;
    case te.invalid_string:
      typeof e.validation == "object" ? "includes" in e.validation ? (s = `Invalid input: must include "${e.validation.includes}"`, typeof e.validation.position == "number" && (s = `${s} at one or more positions greater than or equal to ${e.validation.position}`)) : "startsWith" in e.validation ? s = `Invalid input: must start with "${e.validation.startsWith}"` : "endsWith" in e.validation ? s = `Invalid input: must end with "${e.validation.endsWith}"` : je.assertNever(e.validation) : e.validation !== "regex" ? s = `Invalid ${e.validation}` : s = "Invalid";
      break;
    case te.too_small:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "more than"} ${e.minimum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at least" : "over"} ${e.minimum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "bigint" ? s = `Number must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${e.minimum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly equal to " : e.inclusive ? "greater than or equal to " : "greater than "}${new Date(Number(e.minimum))}` : s = "Invalid input";
      break;
    case te.too_big:
      e.type === "array" ? s = `Array must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "less than"} ${e.maximum} element(s)` : e.type === "string" ? s = `String must contain ${e.exact ? "exactly" : e.inclusive ? "at most" : "under"} ${e.maximum} character(s)` : e.type === "number" ? s = `Number must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "bigint" ? s = `BigInt must be ${e.exact ? "exactly" : e.inclusive ? "less than or equal to" : "less than"} ${e.maximum}` : e.type === "date" ? s = `Date must be ${e.exact ? "exactly" : e.inclusive ? "smaller than or equal to" : "smaller than"} ${new Date(Number(e.maximum))}` : s = "Invalid input";
      break;
    case te.custom:
      s = "Invalid input";
      break;
    case te.invalid_intersection_types:
      s = "Intersection results could not be merged";
      break;
    case te.not_multiple_of:
      s = `Number must be a multiple of ${e.multipleOf}`;
      break;
    case te.not_finite:
      s = "Number must be finite";
      break;
    default:
      s = t.defaultError, je.assertNever(e);
  }
  return { message: s };
};
let th = Yo;
function sh() {
  return th;
}
const nh = (e) => {
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
function le(e, t) {
  const s = sh(), n = nh({
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
      s === Yo ? void 0 : Yo
      // then global default map
    ].filter((r) => !!r)
  });
  e.common.issues.push(n);
}
class kt {
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
        return Re;
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
    return kt.mergeObjectSync(t, n);
  }
  static mergeObjectSync(t, s) {
    const n = {};
    for (const r of s) {
      const { key: o, value: i } = r;
      if (o.status === "aborted" || i.status === "aborted")
        return Re;
      o.status === "dirty" && t.dirty(), i.status === "dirty" && t.dirty(), o.value !== "__proto__" && (typeof i.value < "u" || r.alwaysSet) && (n[o.value] = i.value);
    }
    return { status: t.value, value: n };
  }
}
const Re = Object.freeze({
  status: "aborted"
}), Sn = (e) => ({ status: "dirty", value: e }), $t = (e) => ({ status: "valid", value: e }), Fa = (e) => e.status === "aborted", Wa = (e) => e.status === "dirty", ln = (e) => e.status === "valid", Rr = (e) => typeof Promise < "u" && e instanceof Promise;
var pe;
(function(e) {
  e.errToObj = (t) => typeof t == "string" ? { message: t } : t || {}, e.toString = (t) => typeof t == "string" ? t : t?.message;
})(pe || (pe = {}));
class Qt {
  constructor(t, s, n, r) {
    this._cachedPath = [], this.parent = t, this.data = s, this._path = n, this._key = r;
  }
  get path() {
    return this._cachedPath.length || (Array.isArray(this._key) ? this._cachedPath.push(...this._path, ...this._key) : this._cachedPath.push(...this._path, this._key)), this._cachedPath;
  }
}
const Ba = (e, t) => {
  if (ln(t))
    return { success: !0, data: t.value };
  if (!e.common.issues.length)
    throw new Error("Validation failed but no issues detected.");
  return {
    success: !1,
    get error() {
      if (this._error)
        return this._error;
      const s = new us(e.common.issues);
      return this._error = s, this._error;
    }
  };
};
function Ie(e) {
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
class Me {
  get description() {
    return this._def.description;
  }
  _getType(t) {
    return ws(t.data);
  }
  _getOrReturnCtx(t, s) {
    return s || {
      common: t.parent.common,
      data: t.data,
      parsedType: ws(t.data),
      schemaErrorMap: this._def.errorMap,
      path: t.path,
      parent: t.parent
    };
  }
  _processInputParams(t) {
    return {
      status: new kt(),
      ctx: {
        common: t.parent.common,
        data: t.data,
        parsedType: ws(t.data),
        schemaErrorMap: this._def.errorMap,
        path: t.path,
        parent: t.parent
      }
    };
  }
  _parseSync(t) {
    const s = this._parse(t);
    if (Rr(s))
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
      parsedType: ws(t)
    }, r = this._parseSync({ data: t, path: n.path, parent: n });
    return Ba(n, r);
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
      parsedType: ws(t)
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
      parsedType: ws(t)
    }, r = this._parse({ data: t, path: n.path, parent: n }), o = await (Rr(r) ? r : Promise.resolve(r));
    return Ba(n, o);
  }
  refine(t, s) {
    const n = (r) => typeof s == "string" || typeof s > "u" ? { message: s } : typeof s == "function" ? s(r) : s;
    return this._refinement((r, o) => {
      const i = t(r), a = () => o.addIssue({
        code: te.custom,
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
      typeName: Se.ZodEffects,
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
    return Ss.create(this, this._def);
  }
  nullable() {
    return fn.create(this, this._def);
  }
  nullish() {
    return this.nullable().optional();
  }
  array() {
    return qt.create(this);
  }
  promise() {
    return Tr.create(this, this._def);
  }
  or(t) {
    return Er.create([this, t], this._def);
  }
  and(t) {
    return Ir.create(this, t, this._def);
  }
  transform(t) {
    return new dn({
      ...Ie(this._def),
      schema: this,
      typeName: Se.ZodEffects,
      effect: { type: "transform", transform: t }
    });
  }
  default(t) {
    const s = typeof t == "function" ? t : () => t;
    return new ti({
      ...Ie(this._def),
      innerType: this,
      defaultValue: s,
      typeName: Se.ZodDefault
    });
  }
  brand() {
    return new Rh({
      typeName: Se.ZodBranded,
      type: this,
      ...Ie(this._def)
    });
  }
  catch(t) {
    const s = typeof t == "function" ? t : () => t;
    return new si({
      ...Ie(this._def),
      innerType: this,
      catchValue: s,
      typeName: Se.ZodCatch
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
    return Ti.create(this, t);
  }
  readonly() {
    return ni.create(this);
  }
  isOptional() {
    return this.safeParse(void 0).success;
  }
  isNullable() {
    return this.safeParse(null).success;
  }
}
const rh = /^c[^\s-]{8,}$/i, oh = /^[0-9a-z]+$/, ih = /^[0-9A-HJKMNP-TV-Z]{26}$/i, ah = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i, lh = /^[a-z0-9_-]{21}$/i, ch = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/, uh = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/, dh = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i, fh = "^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$";
let So;
const mh = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/, ph = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/, hh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/, gh = /^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/, vh = /^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/, yh = /^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/, ru = "((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))", bh = new RegExp(`^${ru}$`);
function ou(e) {
  let t = "[0-5]\\d";
  e.precision ? t = `${t}\\.\\d{${e.precision}}` : e.precision == null && (t = `${t}(\\.\\d+)?`);
  const s = e.precision ? "+" : "?";
  return `([01]\\d|2[0-3]):[0-5]\\d(:${t})${s}`;
}
function wh(e) {
  return new RegExp(`^${ou(e)}$`);
}
function _h(e) {
  let t = `${ru}T${ou(e)}`;
  const s = [];
  return s.push(e.local ? "Z?" : "Z"), e.offset && s.push("([+-]\\d{2}:?\\d{2})"), t = `${t}(${s.join("|")})`, new RegExp(`^${t}$`);
}
function xh(e, t) {
  return !!((t === "v4" || !t) && mh.test(e) || (t === "v6" || !t) && hh.test(e));
}
function kh(e, t) {
  if (!ch.test(e))
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
function Sh(e, t) {
  return !!((t === "v4" || !t) && ph.test(e) || (t === "v6" || !t) && gh.test(e));
}
class is extends Me {
  _parse(t) {
    if (this._def.coerce && (t.data = String(t.data)), this._getType(t) !== me.string) {
      const o = this._getOrReturnCtx(t);
      return le(o, {
        code: te.invalid_type,
        expected: me.string,
        received: o.parsedType
      }), Re;
    }
    const n = new kt();
    let r;
    for (const o of this._def.checks)
      if (o.kind === "min")
        t.data.length < o.value && (r = this._getOrReturnCtx(t, r), le(r, {
          code: te.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "max")
        t.data.length > o.value && (r = this._getOrReturnCtx(t, r), le(r, {
          code: te.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !1,
          message: o.message
        }), n.dirty());
      else if (o.kind === "length") {
        const i = t.data.length > o.value, a = t.data.length < o.value;
        (i || a) && (r = this._getOrReturnCtx(t, r), i ? le(r, {
          code: te.too_big,
          maximum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }) : a && le(r, {
          code: te.too_small,
          minimum: o.value,
          type: "string",
          inclusive: !0,
          exact: !0,
          message: o.message
        }), n.dirty());
      } else if (o.kind === "email")
        dh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "email",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "emoji")
        So || (So = new RegExp(fh, "u")), So.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "emoji",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "uuid")
        ah.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "uuid",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "nanoid")
        lh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "nanoid",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid")
        rh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "cuid",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "cuid2")
        oh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "cuid2",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "ulid")
        ih.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
          validation: "ulid",
          code: te.invalid_string,
          message: o.message
        }), n.dirty());
      else if (o.kind === "url")
        try {
          new URL(t.data);
        } catch {
          r = this._getOrReturnCtx(t, r), le(r, {
            validation: "url",
            code: te.invalid_string,
            message: o.message
          }), n.dirty();
        }
      else o.kind === "regex" ? (o.regex.lastIndex = 0, o.regex.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "regex",
        code: te.invalid_string,
        message: o.message
      }), n.dirty())) : o.kind === "trim" ? t.data = t.data.trim() : o.kind === "includes" ? t.data.includes(o.value, o.position) || (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.invalid_string,
        validation: { includes: o.value, position: o.position },
        message: o.message
      }), n.dirty()) : o.kind === "toLowerCase" ? t.data = t.data.toLowerCase() : o.kind === "toUpperCase" ? t.data = t.data.toUpperCase() : o.kind === "startsWith" ? t.data.startsWith(o.value) || (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.invalid_string,
        validation: { startsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "endsWith" ? t.data.endsWith(o.value) || (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.invalid_string,
        validation: { endsWith: o.value },
        message: o.message
      }), n.dirty()) : o.kind === "datetime" ? _h(o).test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.invalid_string,
        validation: "datetime",
        message: o.message
      }), n.dirty()) : o.kind === "date" ? bh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.invalid_string,
        validation: "date",
        message: o.message
      }), n.dirty()) : o.kind === "time" ? wh(o).test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.invalid_string,
        validation: "time",
        message: o.message
      }), n.dirty()) : o.kind === "duration" ? uh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "duration",
        code: te.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "ip" ? xh(t.data, o.version) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "ip",
        code: te.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "jwt" ? kh(t.data, o.alg) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "jwt",
        code: te.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "cidr" ? Sh(t.data, o.version) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "cidr",
        code: te.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64" ? vh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "base64",
        code: te.invalid_string,
        message: o.message
      }), n.dirty()) : o.kind === "base64url" ? yh.test(t.data) || (r = this._getOrReturnCtx(t, r), le(r, {
        validation: "base64url",
        code: te.invalid_string,
        message: o.message
      }), n.dirty()) : je.assertNever(o);
    return { status: n.value, value: t.data };
  }
  _regex(t, s, n) {
    return this.refinement((r) => t.test(r), {
      validation: s,
      code: te.invalid_string,
      ...pe.errToObj(n)
    });
  }
  _addCheck(t) {
    return new is({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  email(t) {
    return this._addCheck({ kind: "email", ...pe.errToObj(t) });
  }
  url(t) {
    return this._addCheck({ kind: "url", ...pe.errToObj(t) });
  }
  emoji(t) {
    return this._addCheck({ kind: "emoji", ...pe.errToObj(t) });
  }
  uuid(t) {
    return this._addCheck({ kind: "uuid", ...pe.errToObj(t) });
  }
  nanoid(t) {
    return this._addCheck({ kind: "nanoid", ...pe.errToObj(t) });
  }
  cuid(t) {
    return this._addCheck({ kind: "cuid", ...pe.errToObj(t) });
  }
  cuid2(t) {
    return this._addCheck({ kind: "cuid2", ...pe.errToObj(t) });
  }
  ulid(t) {
    return this._addCheck({ kind: "ulid", ...pe.errToObj(t) });
  }
  base64(t) {
    return this._addCheck({ kind: "base64", ...pe.errToObj(t) });
  }
  base64url(t) {
    return this._addCheck({
      kind: "base64url",
      ...pe.errToObj(t)
    });
  }
  jwt(t) {
    return this._addCheck({ kind: "jwt", ...pe.errToObj(t) });
  }
  ip(t) {
    return this._addCheck({ kind: "ip", ...pe.errToObj(t) });
  }
  cidr(t) {
    return this._addCheck({ kind: "cidr", ...pe.errToObj(t) });
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
      ...pe.errToObj(t?.message)
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
      ...pe.errToObj(t?.message)
    });
  }
  duration(t) {
    return this._addCheck({ kind: "duration", ...pe.errToObj(t) });
  }
  regex(t, s) {
    return this._addCheck({
      kind: "regex",
      regex: t,
      ...pe.errToObj(s)
    });
  }
  includes(t, s) {
    return this._addCheck({
      kind: "includes",
      value: t,
      position: s?.position,
      ...pe.errToObj(s?.message)
    });
  }
  startsWith(t, s) {
    return this._addCheck({
      kind: "startsWith",
      value: t,
      ...pe.errToObj(s)
    });
  }
  endsWith(t, s) {
    return this._addCheck({
      kind: "endsWith",
      value: t,
      ...pe.errToObj(s)
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t,
      ...pe.errToObj(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t,
      ...pe.errToObj(s)
    });
  }
  length(t, s) {
    return this._addCheck({
      kind: "length",
      value: t,
      ...pe.errToObj(s)
    });
  }
  /**
   * Equivalent to `.min(1)`
   */
  nonempty(t) {
    return this.min(1, pe.errToObj(t));
  }
  trim() {
    return new is({
      ...this._def,
      checks: [...this._def.checks, { kind: "trim" }]
    });
  }
  toLowerCase() {
    return new is({
      ...this._def,
      checks: [...this._def.checks, { kind: "toLowerCase" }]
    });
  }
  toUpperCase() {
    return new is({
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
is.create = (e) => new is({
  checks: [],
  typeName: Se.ZodString,
  coerce: e?.coerce ?? !1,
  ...Ie(e)
});
function Ch(e, t) {
  const s = (e.toString().split(".")[1] || "").length, n = (t.toString().split(".")[1] || "").length, r = s > n ? s : n, o = Number.parseInt(e.toFixed(r).replace(".", "")), i = Number.parseInt(t.toFixed(r).replace(".", ""));
  return o % i / 10 ** r;
}
class cn extends Me {
  constructor() {
    super(...arguments), this.min = this.gte, this.max = this.lte, this.step = this.multipleOf;
  }
  _parse(t) {
    if (this._def.coerce && (t.data = Number(t.data)), this._getType(t) !== me.number) {
      const o = this._getOrReturnCtx(t);
      return le(o, {
        code: te.invalid_type,
        expected: me.number,
        received: o.parsedType
      }), Re;
    }
    let n;
    const r = new kt();
    for (const o of this._def.checks)
      o.kind === "int" ? je.isInteger(t.data) || (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.invalid_type,
        expected: "integer",
        received: "float",
        message: o.message
      }), r.dirty()) : o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.too_small,
        minimum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.too_big,
        maximum: o.value,
        type: "number",
        inclusive: o.inclusive,
        exact: !1,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? Ch(t.data, o.value) !== 0 && (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : o.kind === "finite" ? Number.isFinite(t.data) || (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.not_finite,
        message: o.message
      }), r.dirty()) : je.assertNever(o);
    return { status: r.value, value: t.data };
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, pe.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, pe.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, pe.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, pe.toString(s));
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
          message: pe.toString(r)
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
      message: pe.toString(t)
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !1,
      message: pe.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !1,
      message: pe.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: 0,
      inclusive: !0,
      message: pe.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: 0,
      inclusive: !0,
      message: pe.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: pe.toString(s)
    });
  }
  finite(t) {
    return this._addCheck({
      kind: "finite",
      message: pe.toString(t)
    });
  }
  safe(t) {
    return this._addCheck({
      kind: "min",
      inclusive: !0,
      value: Number.MIN_SAFE_INTEGER,
      message: pe.toString(t)
    })._addCheck({
      kind: "max",
      inclusive: !0,
      value: Number.MAX_SAFE_INTEGER,
      message: pe.toString(t)
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
    return !!this._def.checks.find((t) => t.kind === "int" || t.kind === "multipleOf" && je.isInteger(t.value));
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
  typeName: Se.ZodNumber,
  coerce: e?.coerce || !1,
  ...Ie(e)
});
class Wn extends Me {
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
    if (this._getType(t) !== me.bigint)
      return this._getInvalidInput(t);
    let n;
    const r = new kt();
    for (const o of this._def.checks)
      o.kind === "min" ? (o.inclusive ? t.data < o.value : t.data <= o.value) && (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.too_small,
        type: "bigint",
        minimum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "max" ? (o.inclusive ? t.data > o.value : t.data >= o.value) && (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.too_big,
        type: "bigint",
        maximum: o.value,
        inclusive: o.inclusive,
        message: o.message
      }), r.dirty()) : o.kind === "multipleOf" ? t.data % o.value !== BigInt(0) && (n = this._getOrReturnCtx(t, n), le(n, {
        code: te.not_multiple_of,
        multipleOf: o.value,
        message: o.message
      }), r.dirty()) : je.assertNever(o);
    return { status: r.value, value: t.data };
  }
  _getInvalidInput(t) {
    const s = this._getOrReturnCtx(t);
    return le(s, {
      code: te.invalid_type,
      expected: me.bigint,
      received: s.parsedType
    }), Re;
  }
  gte(t, s) {
    return this.setLimit("min", t, !0, pe.toString(s));
  }
  gt(t, s) {
    return this.setLimit("min", t, !1, pe.toString(s));
  }
  lte(t, s) {
    return this.setLimit("max", t, !0, pe.toString(s));
  }
  lt(t, s) {
    return this.setLimit("max", t, !1, pe.toString(s));
  }
  setLimit(t, s, n, r) {
    return new Wn({
      ...this._def,
      checks: [
        ...this._def.checks,
        {
          kind: t,
          value: s,
          inclusive: n,
          message: pe.toString(r)
        }
      ]
    });
  }
  _addCheck(t) {
    return new Wn({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  positive(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !1,
      message: pe.toString(t)
    });
  }
  negative(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !1,
      message: pe.toString(t)
    });
  }
  nonpositive(t) {
    return this._addCheck({
      kind: "max",
      value: BigInt(0),
      inclusive: !0,
      message: pe.toString(t)
    });
  }
  nonnegative(t) {
    return this._addCheck({
      kind: "min",
      value: BigInt(0),
      inclusive: !0,
      message: pe.toString(t)
    });
  }
  multipleOf(t, s) {
    return this._addCheck({
      kind: "multipleOf",
      value: t,
      message: pe.toString(s)
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
Wn.create = (e) => new Wn({
  checks: [],
  typeName: Se.ZodBigInt,
  coerce: e?.coerce ?? !1,
  ...Ie(e)
});
class Xo extends Me {
  _parse(t) {
    if (this._def.coerce && (t.data = !!t.data), this._getType(t) !== me.boolean) {
      const n = this._getOrReturnCtx(t);
      return le(n, {
        code: te.invalid_type,
        expected: me.boolean,
        received: n.parsedType
      }), Re;
    }
    return $t(t.data);
  }
}
Xo.create = (e) => new Xo({
  typeName: Se.ZodBoolean,
  coerce: e?.coerce || !1,
  ...Ie(e)
});
class Ar extends Me {
  _parse(t) {
    if (this._def.coerce && (t.data = new Date(t.data)), this._getType(t) !== me.date) {
      const o = this._getOrReturnCtx(t);
      return le(o, {
        code: te.invalid_type,
        expected: me.date,
        received: o.parsedType
      }), Re;
    }
    if (Number.isNaN(t.data.getTime())) {
      const o = this._getOrReturnCtx(t);
      return le(o, {
        code: te.invalid_date
      }), Re;
    }
    const n = new kt();
    let r;
    for (const o of this._def.checks)
      o.kind === "min" ? t.data.getTime() < o.value && (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.too_small,
        message: o.message,
        inclusive: !0,
        exact: !1,
        minimum: o.value,
        type: "date"
      }), n.dirty()) : o.kind === "max" ? t.data.getTime() > o.value && (r = this._getOrReturnCtx(t, r), le(r, {
        code: te.too_big,
        message: o.message,
        inclusive: !0,
        exact: !1,
        maximum: o.value,
        type: "date"
      }), n.dirty()) : je.assertNever(o);
    return {
      status: n.value,
      value: new Date(t.data.getTime())
    };
  }
  _addCheck(t) {
    return new Ar({
      ...this._def,
      checks: [...this._def.checks, t]
    });
  }
  min(t, s) {
    return this._addCheck({
      kind: "min",
      value: t.getTime(),
      message: pe.toString(s)
    });
  }
  max(t, s) {
    return this._addCheck({
      kind: "max",
      value: t.getTime(),
      message: pe.toString(s)
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
Ar.create = (e) => new Ar({
  checks: [],
  coerce: e?.coerce || !1,
  typeName: Se.ZodDate,
  ...Ie(e)
});
class Ga extends Me {
  _parse(t) {
    if (this._getType(t) !== me.symbol) {
      const n = this._getOrReturnCtx(t);
      return le(n, {
        code: te.invalid_type,
        expected: me.symbol,
        received: n.parsedType
      }), Re;
    }
    return $t(t.data);
  }
}
Ga.create = (e) => new Ga({
  typeName: Se.ZodSymbol,
  ...Ie(e)
});
class Ha extends Me {
  _parse(t) {
    if (this._getType(t) !== me.undefined) {
      const n = this._getOrReturnCtx(t);
      return le(n, {
        code: te.invalid_type,
        expected: me.undefined,
        received: n.parsedType
      }), Re;
    }
    return $t(t.data);
  }
}
Ha.create = (e) => new Ha({
  typeName: Se.ZodUndefined,
  ...Ie(e)
});
class qa extends Me {
  _parse(t) {
    if (this._getType(t) !== me.null) {
      const n = this._getOrReturnCtx(t);
      return le(n, {
        code: te.invalid_type,
        expected: me.null,
        received: n.parsedType
      }), Re;
    }
    return $t(t.data);
  }
}
qa.create = (e) => new qa({
  typeName: Se.ZodNull,
  ...Ie(e)
});
class Za extends Me {
  constructor() {
    super(...arguments), this._any = !0;
  }
  _parse(t) {
    return $t(t.data);
  }
}
Za.create = (e) => new Za({
  typeName: Se.ZodAny,
  ...Ie(e)
});
class Ka extends Me {
  constructor() {
    super(...arguments), this._unknown = !0;
  }
  _parse(t) {
    return $t(t.data);
  }
}
Ka.create = (e) => new Ka({
  typeName: Se.ZodUnknown,
  ...Ie(e)
});
class As extends Me {
  _parse(t) {
    const s = this._getOrReturnCtx(t);
    return le(s, {
      code: te.invalid_type,
      expected: me.never,
      received: s.parsedType
    }), Re;
  }
}
As.create = (e) => new As({
  typeName: Se.ZodNever,
  ...Ie(e)
});
class Ja extends Me {
  _parse(t) {
    if (this._getType(t) !== me.undefined) {
      const n = this._getOrReturnCtx(t);
      return le(n, {
        code: te.invalid_type,
        expected: me.void,
        received: n.parsedType
      }), Re;
    }
    return $t(t.data);
  }
}
Ja.create = (e) => new Ja({
  typeName: Se.ZodVoid,
  ...Ie(e)
});
class qt extends Me {
  _parse(t) {
    const { ctx: s, status: n } = this._processInputParams(t), r = this._def;
    if (s.parsedType !== me.array)
      return le(s, {
        code: te.invalid_type,
        expected: me.array,
        received: s.parsedType
      }), Re;
    if (r.exactLength !== null) {
      const i = s.data.length > r.exactLength.value, a = s.data.length < r.exactLength.value;
      (i || a) && (le(s, {
        code: i ? te.too_big : te.too_small,
        minimum: a ? r.exactLength.value : void 0,
        maximum: i ? r.exactLength.value : void 0,
        type: "array",
        inclusive: !0,
        exact: !0,
        message: r.exactLength.message
      }), n.dirty());
    }
    if (r.minLength !== null && s.data.length < r.minLength.value && (le(s, {
      code: te.too_small,
      minimum: r.minLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.minLength.message
    }), n.dirty()), r.maxLength !== null && s.data.length > r.maxLength.value && (le(s, {
      code: te.too_big,
      maximum: r.maxLength.value,
      type: "array",
      inclusive: !0,
      exact: !1,
      message: r.maxLength.message
    }), n.dirty()), s.common.async)
      return Promise.all([...s.data].map((i, a) => r.type._parseAsync(new Qt(s, i, s.path, a)))).then((i) => kt.mergeArray(n, i));
    const o = [...s.data].map((i, a) => r.type._parseSync(new Qt(s, i, s.path, a)));
    return kt.mergeArray(n, o);
  }
  get element() {
    return this._def.type;
  }
  min(t, s) {
    return new qt({
      ...this._def,
      minLength: { value: t, message: pe.toString(s) }
    });
  }
  max(t, s) {
    return new qt({
      ...this._def,
      maxLength: { value: t, message: pe.toString(s) }
    });
  }
  length(t, s) {
    return new qt({
      ...this._def,
      exactLength: { value: t, message: pe.toString(s) }
    });
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
qt.create = (e, t) => new qt({
  type: e,
  minLength: null,
  maxLength: null,
  exactLength: null,
  typeName: Se.ZodArray,
  ...Ie(t)
});
function Js(e) {
  if (e instanceof it) {
    const t = {};
    for (const s in e.shape) {
      const n = e.shape[s];
      t[s] = Ss.create(Js(n));
    }
    return new it({
      ...e._def,
      shape: () => t
    });
  } else return e instanceof qt ? new qt({
    ...e._def,
    type: Js(e.element)
  }) : e instanceof Ss ? Ss.create(Js(e.unwrap())) : e instanceof fn ? fn.create(Js(e.unwrap())) : e instanceof Us ? Us.create(e.items.map((t) => Js(t))) : e;
}
class it extends Me {
  constructor() {
    super(...arguments), this._cached = null, this.nonstrict = this.passthrough, this.augment = this.extend;
  }
  _getCached() {
    if (this._cached !== null)
      return this._cached;
    const t = this._def.shape(), s = je.objectKeys(t);
    return this._cached = { shape: t, keys: s }, this._cached;
  }
  _parse(t) {
    if (this._getType(t) !== me.object) {
      const c = this._getOrReturnCtx(t);
      return le(c, {
        code: te.invalid_type,
        expected: me.object,
        received: c.parsedType
      }), Re;
    }
    const { status: n, ctx: r } = this._processInputParams(t), { shape: o, keys: i } = this._getCached(), a = [];
    if (!(this._def.catchall instanceof As && this._def.unknownKeys === "strip"))
      for (const c in r.data)
        i.includes(c) || a.push(c);
    const l = [];
    for (const c of i) {
      const u = o[c], f = r.data[c];
      l.push({
        key: { status: "valid", value: c },
        value: u._parse(new Qt(r, f, r.path, c)),
        alwaysSet: c in r.data
      });
    }
    if (this._def.catchall instanceof As) {
      const c = this._def.unknownKeys;
      if (c === "passthrough")
        for (const u of a)
          l.push({
            key: { status: "valid", value: u },
            value: { status: "valid", value: r.data[u] }
          });
      else if (c === "strict")
        a.length > 0 && (le(r, {
          code: te.unrecognized_keys,
          keys: a
        }), n.dirty());
      else if (c !== "strip") throw new Error("Internal ZodObject error: invalid unknownKeys value.");
    } else {
      const c = this._def.catchall;
      for (const u of a) {
        const f = r.data[u];
        l.push({
          key: { status: "valid", value: u },
          value: c._parse(
            new Qt(r, f, r.path, u)
            //, ctx.child(key), value, getParsedType(value)
          ),
          alwaysSet: u in r.data
        });
      }
    }
    return r.common.async ? Promise.resolve().then(async () => {
      const c = [];
      for (const u of l) {
        const f = await u.key, h = await u.value;
        c.push({
          key: f,
          value: h,
          alwaysSet: u.alwaysSet
        });
      }
      return c;
    }).then((c) => kt.mergeObjectSync(n, c)) : kt.mergeObjectSync(n, l);
  }
  get shape() {
    return this._def.shape();
  }
  strict(t) {
    return pe.errToObj, new it({
      ...this._def,
      unknownKeys: "strict",
      ...t !== void 0 ? {
        errorMap: (s, n) => {
          const r = this._def.errorMap?.(s, n).message ?? n.defaultError;
          return s.code === "unrecognized_keys" ? {
            message: pe.errToObj(t).message ?? r
          } : {
            message: r
          };
        }
      } : {}
    });
  }
  strip() {
    return new it({
      ...this._def,
      unknownKeys: "strip"
    });
  }
  passthrough() {
    return new it({
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
    return new it({
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
    return new it({
      unknownKeys: t._def.unknownKeys,
      catchall: t._def.catchall,
      shape: () => ({
        ...this._def.shape(),
        ...t._def.shape()
      }),
      typeName: Se.ZodObject
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
    return new it({
      ...this._def,
      catchall: t
    });
  }
  pick(t) {
    const s = {};
    for (const n of je.objectKeys(t))
      t[n] && this.shape[n] && (s[n] = this.shape[n]);
    return new it({
      ...this._def,
      shape: () => s
    });
  }
  omit(t) {
    const s = {};
    for (const n of je.objectKeys(this.shape))
      t[n] || (s[n] = this.shape[n]);
    return new it({
      ...this._def,
      shape: () => s
    });
  }
  /**
   * @deprecated
   */
  deepPartial() {
    return Js(this);
  }
  partial(t) {
    const s = {};
    for (const n of je.objectKeys(this.shape)) {
      const r = this.shape[n];
      t && !t[n] ? s[n] = r : s[n] = r.optional();
    }
    return new it({
      ...this._def,
      shape: () => s
    });
  }
  required(t) {
    const s = {};
    for (const n of je.objectKeys(this.shape))
      if (t && !t[n])
        s[n] = this.shape[n];
      else {
        let o = this.shape[n];
        for (; o instanceof Ss; )
          o = o._def.innerType;
        s[n] = o;
      }
    return new it({
      ...this._def,
      shape: () => s
    });
  }
  keyof() {
    return iu(je.objectKeys(this.shape));
  }
}
it.create = (e, t) => new it({
  shape: () => e,
  unknownKeys: "strip",
  catchall: As.create(),
  typeName: Se.ZodObject,
  ...Ie(t)
});
it.strictCreate = (e, t) => new it({
  shape: () => e,
  unknownKeys: "strict",
  catchall: As.create(),
  typeName: Se.ZodObject,
  ...Ie(t)
});
it.lazycreate = (e, t) => new it({
  shape: e,
  unknownKeys: "strip",
  catchall: As.create(),
  typeName: Se.ZodObject,
  ...Ie(t)
});
class Er extends Me {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t), n = this._def.options;
    function r(o) {
      for (const a of o)
        if (a.result.status === "valid")
          return a.result;
      for (const a of o)
        if (a.result.status === "dirty")
          return s.common.issues.push(...a.ctx.common.issues), a.result;
      const i = o.map((a) => new us(a.ctx.common.issues));
      return le(s, {
        code: te.invalid_union,
        unionErrors: i
      }), Re;
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
      const a = i.map((l) => new us(l));
      return le(s, {
        code: te.invalid_union,
        unionErrors: a
      }), Re;
    }
  }
  get options() {
    return this._def.options;
  }
}
Er.create = (e, t) => new Er({
  options: e,
  typeName: Se.ZodUnion,
  ...Ie(t)
});
function ei(e, t) {
  const s = ws(e), n = ws(t);
  if (e === t)
    return { valid: !0, data: e };
  if (s === me.object && n === me.object) {
    const r = je.objectKeys(t), o = je.objectKeys(e).filter((a) => r.indexOf(a) !== -1), i = { ...e, ...t };
    for (const a of o) {
      const l = ei(e[a], t[a]);
      if (!l.valid)
        return { valid: !1 };
      i[a] = l.data;
    }
    return { valid: !0, data: i };
  } else if (s === me.array && n === me.array) {
    if (e.length !== t.length)
      return { valid: !1 };
    const r = [];
    for (let o = 0; o < e.length; o++) {
      const i = e[o], a = t[o], l = ei(i, a);
      if (!l.valid)
        return { valid: !1 };
      r.push(l.data);
    }
    return { valid: !0, data: r };
  } else return s === me.date && n === me.date && +e == +t ? { valid: !0, data: e } : { valid: !1 };
}
class Ir extends Me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = (o, i) => {
      if (Fa(o) || Fa(i))
        return Re;
      const a = ei(o.value, i.value);
      return a.valid ? ((Wa(o) || Wa(i)) && s.dirty(), { status: s.value, value: a.data }) : (le(n, {
        code: te.invalid_intersection_types
      }), Re);
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
Ir.create = (e, t, s) => new Ir({
  left: e,
  right: t,
  typeName: Se.ZodIntersection,
  ...Ie(s)
});
class Us extends Me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== me.array)
      return le(n, {
        code: te.invalid_type,
        expected: me.array,
        received: n.parsedType
      }), Re;
    if (n.data.length < this._def.items.length)
      return le(n, {
        code: te.too_small,
        minimum: this._def.items.length,
        inclusive: !0,
        exact: !1,
        type: "array"
      }), Re;
    !this._def.rest && n.data.length > this._def.items.length && (le(n, {
      code: te.too_big,
      maximum: this._def.items.length,
      inclusive: !0,
      exact: !1,
      type: "array"
    }), s.dirty());
    const o = [...n.data].map((i, a) => {
      const l = this._def.items[a] || this._def.rest;
      return l ? l._parse(new Qt(n, i, n.path, a)) : null;
    }).filter((i) => !!i);
    return n.common.async ? Promise.all(o).then((i) => kt.mergeArray(s, i)) : kt.mergeArray(s, o);
  }
  get items() {
    return this._def.items;
  }
  rest(t) {
    return new Us({
      ...this._def,
      rest: t
    });
  }
}
Us.create = (e, t) => {
  if (!Array.isArray(e))
    throw new Error("You must pass an array of schemas to z.tuple([ ... ])");
  return new Us({
    items: e,
    typeName: Se.ZodTuple,
    rest: null,
    ...Ie(t)
  });
};
class Or extends Me {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== me.object)
      return le(n, {
        code: te.invalid_type,
        expected: me.object,
        received: n.parsedType
      }), Re;
    const r = [], o = this._def.keyType, i = this._def.valueType;
    for (const a in n.data)
      r.push({
        key: o._parse(new Qt(n, a, n.path, a)),
        value: i._parse(new Qt(n, n.data[a], n.path, a)),
        alwaysSet: a in n.data
      });
    return n.common.async ? kt.mergeObjectAsync(s, r) : kt.mergeObjectSync(s, r);
  }
  get element() {
    return this._def.valueType;
  }
  static create(t, s, n) {
    return s instanceof Me ? new Or({
      keyType: t,
      valueType: s,
      typeName: Se.ZodRecord,
      ...Ie(n)
    }) : new Or({
      keyType: is.create(),
      valueType: t,
      typeName: Se.ZodRecord,
      ...Ie(s)
    });
  }
}
class Qa extends Me {
  get keySchema() {
    return this._def.keyType;
  }
  get valueSchema() {
    return this._def.valueType;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== me.map)
      return le(n, {
        code: te.invalid_type,
        expected: me.map,
        received: n.parsedType
      }), Re;
    const r = this._def.keyType, o = this._def.valueType, i = [...n.data.entries()].map(([a, l], c) => ({
      key: r._parse(new Qt(n, a, n.path, [c, "key"])),
      value: o._parse(new Qt(n, l, n.path, [c, "value"]))
    }));
    if (n.common.async) {
      const a = /* @__PURE__ */ new Map();
      return Promise.resolve().then(async () => {
        for (const l of i) {
          const c = await l.key, u = await l.value;
          if (c.status === "aborted" || u.status === "aborted")
            return Re;
          (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
        }
        return { status: s.value, value: a };
      });
    } else {
      const a = /* @__PURE__ */ new Map();
      for (const l of i) {
        const c = l.key, u = l.value;
        if (c.status === "aborted" || u.status === "aborted")
          return Re;
        (c.status === "dirty" || u.status === "dirty") && s.dirty(), a.set(c.value, u.value);
      }
      return { status: s.value, value: a };
    }
  }
}
Qa.create = (e, t, s) => new Qa({
  valueType: t,
  keyType: e,
  typeName: Se.ZodMap,
  ...Ie(s)
});
class Bn extends Me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.parsedType !== me.set)
      return le(n, {
        code: te.invalid_type,
        expected: me.set,
        received: n.parsedType
      }), Re;
    const r = this._def;
    r.minSize !== null && n.data.size < r.minSize.value && (le(n, {
      code: te.too_small,
      minimum: r.minSize.value,
      type: "set",
      inclusive: !0,
      exact: !1,
      message: r.minSize.message
    }), s.dirty()), r.maxSize !== null && n.data.size > r.maxSize.value && (le(n, {
      code: te.too_big,
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
          return Re;
        u.status === "dirty" && s.dirty(), c.add(u.value);
      }
      return { status: s.value, value: c };
    }
    const a = [...n.data.values()].map((l, c) => o._parse(new Qt(n, l, n.path, c)));
    return n.common.async ? Promise.all(a).then((l) => i(l)) : i(a);
  }
  min(t, s) {
    return new Bn({
      ...this._def,
      minSize: { value: t, message: pe.toString(s) }
    });
  }
  max(t, s) {
    return new Bn({
      ...this._def,
      maxSize: { value: t, message: pe.toString(s) }
    });
  }
  size(t, s) {
    return this.min(t, s).max(t, s);
  }
  nonempty(t) {
    return this.min(1, t);
  }
}
Bn.create = (e, t) => new Bn({
  valueType: e,
  minSize: null,
  maxSize: null,
  typeName: Se.ZodSet,
  ...Ie(t)
});
class Ya extends Me {
  get schema() {
    return this._def.getter();
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    return this._def.getter()._parse({ data: s.data, path: s.path, parent: s });
  }
}
Ya.create = (e, t) => new Ya({
  getter: e,
  typeName: Se.ZodLazy,
  ...Ie(t)
});
class Xa extends Me {
  _parse(t) {
    if (t.data !== this._def.value) {
      const s = this._getOrReturnCtx(t);
      return le(s, {
        received: s.data,
        code: te.invalid_literal,
        expected: this._def.value
      }), Re;
    }
    return { status: "valid", value: t.data };
  }
  get value() {
    return this._def.value;
  }
}
Xa.create = (e, t) => new Xa({
  value: e,
  typeName: Se.ZodLiteral,
  ...Ie(t)
});
function iu(e, t) {
  return new un({
    values: e,
    typeName: Se.ZodEnum,
    ...Ie(t)
  });
}
class un extends Me {
  _parse(t) {
    if (typeof t.data != "string") {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return le(s, {
        expected: je.joinValues(n),
        received: s.parsedType,
        code: te.invalid_type
      }), Re;
    }
    if (this._cache || (this._cache = new Set(this._def.values)), !this._cache.has(t.data)) {
      const s = this._getOrReturnCtx(t), n = this._def.values;
      return le(s, {
        received: s.data,
        code: te.invalid_enum_value,
        options: n
      }), Re;
    }
    return $t(t.data);
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
un.create = iu;
class el extends Me {
  _parse(t) {
    const s = je.getValidEnumValues(this._def.values), n = this._getOrReturnCtx(t);
    if (n.parsedType !== me.string && n.parsedType !== me.number) {
      const r = je.objectValues(s);
      return le(n, {
        expected: je.joinValues(r),
        received: n.parsedType,
        code: te.invalid_type
      }), Re;
    }
    if (this._cache || (this._cache = new Set(je.getValidEnumValues(this._def.values))), !this._cache.has(t.data)) {
      const r = je.objectValues(s);
      return le(n, {
        received: n.data,
        code: te.invalid_enum_value,
        options: r
      }), Re;
    }
    return $t(t.data);
  }
  get enum() {
    return this._def.values;
  }
}
el.create = (e, t) => new el({
  values: e,
  typeName: Se.ZodNativeEnum,
  ...Ie(t)
});
class Tr extends Me {
  unwrap() {
    return this._def.type;
  }
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    if (s.parsedType !== me.promise && s.common.async === !1)
      return le(s, {
        code: te.invalid_type,
        expected: me.promise,
        received: s.parsedType
      }), Re;
    const n = s.parsedType === me.promise ? s.data : Promise.resolve(s.data);
    return $t(n.then((r) => this._def.type.parseAsync(r, {
      path: s.path,
      errorMap: s.common.contextualErrorMap
    })));
  }
}
Tr.create = (e, t) => new Tr({
  type: e,
  typeName: Se.ZodPromise,
  ...Ie(t)
});
class dn extends Me {
  innerType() {
    return this._def.schema;
  }
  sourceType() {
    return this._def.schema._def.typeName === Se.ZodEffects ? this._def.schema.sourceType() : this._def.schema;
  }
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t), r = this._def.effect || null, o = {
      addIssue: (i) => {
        le(n, i), i.fatal ? s.abort() : s.dirty();
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
            return Re;
          const l = await this._def.schema._parseAsync({
            data: a,
            path: n.path,
            parent: n
          });
          return l.status === "aborted" ? Re : l.status === "dirty" || s.value === "dirty" ? Sn(l.value) : l;
        });
      {
        if (s.value === "aborted")
          return Re;
        const a = this._def.schema._parseSync({
          data: i,
          path: n.path,
          parent: n
        });
        return a.status === "aborted" ? Re : a.status === "dirty" || s.value === "dirty" ? Sn(a.value) : a;
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
        return a.status === "aborted" ? Re : (a.status === "dirty" && s.dirty(), i(a.value), { status: s.value, value: a.value });
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((a) => a.status === "aborted" ? Re : (a.status === "dirty" && s.dirty(), i(a.value).then(() => ({ status: s.value, value: a.value }))));
    }
    if (r.type === "transform")
      if (n.common.async === !1) {
        const i = this._def.schema._parseSync({
          data: n.data,
          path: n.path,
          parent: n
        });
        if (!ln(i))
          return Re;
        const a = r.transform(i.value, o);
        if (a instanceof Promise)
          throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");
        return { status: s.value, value: a };
      } else
        return this._def.schema._parseAsync({ data: n.data, path: n.path, parent: n }).then((i) => ln(i) ? Promise.resolve(r.transform(i.value, o)).then((a) => ({
          status: s.value,
          value: a
        })) : Re);
    je.assertNever(r);
  }
}
dn.create = (e, t, s) => new dn({
  schema: e,
  typeName: Se.ZodEffects,
  effect: t,
  ...Ie(s)
});
dn.createWithPreprocess = (e, t, s) => new dn({
  schema: t,
  effect: { type: "preprocess", transform: e },
  typeName: Se.ZodEffects,
  ...Ie(s)
});
class Ss extends Me {
  _parse(t) {
    return this._getType(t) === me.undefined ? $t(void 0) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
Ss.create = (e, t) => new Ss({
  innerType: e,
  typeName: Se.ZodOptional,
  ...Ie(t)
});
class fn extends Me {
  _parse(t) {
    return this._getType(t) === me.null ? $t(null) : this._def.innerType._parse(t);
  }
  unwrap() {
    return this._def.innerType;
  }
}
fn.create = (e, t) => new fn({
  innerType: e,
  typeName: Se.ZodNullable,
  ...Ie(t)
});
class ti extends Me {
  _parse(t) {
    const { ctx: s } = this._processInputParams(t);
    let n = s.data;
    return s.parsedType === me.undefined && (n = this._def.defaultValue()), this._def.innerType._parse({
      data: n,
      path: s.path,
      parent: s
    });
  }
  removeDefault() {
    return this._def.innerType;
  }
}
ti.create = (e, t) => new ti({
  innerType: e,
  typeName: Se.ZodDefault,
  defaultValue: typeof t.default == "function" ? t.default : () => t.default,
  ...Ie(t)
});
class si extends Me {
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
    return Rr(r) ? r.then((o) => ({
      status: "valid",
      value: o.status === "valid" ? o.value : this._def.catchValue({
        get error() {
          return new us(n.common.issues);
        },
        input: n.data
      })
    })) : {
      status: "valid",
      value: r.status === "valid" ? r.value : this._def.catchValue({
        get error() {
          return new us(n.common.issues);
        },
        input: n.data
      })
    };
  }
  removeCatch() {
    return this._def.innerType;
  }
}
si.create = (e, t) => new si({
  innerType: e,
  typeName: Se.ZodCatch,
  catchValue: typeof t.catch == "function" ? t.catch : () => t.catch,
  ...Ie(t)
});
class tl extends Me {
  _parse(t) {
    if (this._getType(t) !== me.nan) {
      const n = this._getOrReturnCtx(t);
      return le(n, {
        code: te.invalid_type,
        expected: me.nan,
        received: n.parsedType
      }), Re;
    }
    return { status: "valid", value: t.data };
  }
}
tl.create = (e) => new tl({
  typeName: Se.ZodNaN,
  ...Ie(e)
});
class Rh extends Me {
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
class Ti extends Me {
  _parse(t) {
    const { status: s, ctx: n } = this._processInputParams(t);
    if (n.common.async)
      return (async () => {
        const o = await this._def.in._parseAsync({
          data: n.data,
          path: n.path,
          parent: n
        });
        return o.status === "aborted" ? Re : o.status === "dirty" ? (s.dirty(), Sn(o.value)) : this._def.out._parseAsync({
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
      return r.status === "aborted" ? Re : r.status === "dirty" ? (s.dirty(), {
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
    return new Ti({
      in: t,
      out: s,
      typeName: Se.ZodPipeline
    });
  }
}
class ni extends Me {
  _parse(t) {
    const s = this._def.innerType._parse(t), n = (r) => (ln(r) && (r.value = Object.freeze(r.value)), r);
    return Rr(s) ? s.then((r) => n(r)) : n(s);
  }
  unwrap() {
    return this._def.innerType;
  }
}
ni.create = (e, t) => new ni({
  innerType: e,
  typeName: Se.ZodReadonly,
  ...Ie(t)
});
var Se;
(function(e) {
  e.ZodString = "ZodString", e.ZodNumber = "ZodNumber", e.ZodNaN = "ZodNaN", e.ZodBigInt = "ZodBigInt", e.ZodBoolean = "ZodBoolean", e.ZodDate = "ZodDate", e.ZodSymbol = "ZodSymbol", e.ZodUndefined = "ZodUndefined", e.ZodNull = "ZodNull", e.ZodAny = "ZodAny", e.ZodUnknown = "ZodUnknown", e.ZodNever = "ZodNever", e.ZodVoid = "ZodVoid", e.ZodArray = "ZodArray", e.ZodObject = "ZodObject", e.ZodUnion = "ZodUnion", e.ZodDiscriminatedUnion = "ZodDiscriminatedUnion", e.ZodIntersection = "ZodIntersection", e.ZodTuple = "ZodTuple", e.ZodRecord = "ZodRecord", e.ZodMap = "ZodMap", e.ZodSet = "ZodSet", e.ZodFunction = "ZodFunction", e.ZodLazy = "ZodLazy", e.ZodLiteral = "ZodLiteral", e.ZodEnum = "ZodEnum", e.ZodEffects = "ZodEffects", e.ZodNativeEnum = "ZodNativeEnum", e.ZodOptional = "ZodOptional", e.ZodNullable = "ZodNullable", e.ZodDefault = "ZodDefault", e.ZodCatch = "ZodCatch", e.ZodPromise = "ZodPromise", e.ZodBranded = "ZodBranded", e.ZodPipeline = "ZodPipeline", e.ZodReadonly = "ZodReadonly";
})(Se || (Se = {}));
const dt = is.create, Co = cn.create, ir = Xo.create;
As.create;
const au = qt.create, $i = it.create;
Er.create;
Ir.create;
Us.create;
const Ah = Or.create, ri = un.create;
Tr.create;
Ss.create;
fn.create;
const Eh = "comfymodal.studio.vue.";
function Ih() {
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
function Oh() {
  try {
    if (typeof localStorage < "u") {
      const e = "__comfymodal_probe__";
      return localStorage.setItem(e, "1"), localStorage.removeItem(e), localStorage;
    }
  } catch {
  }
  return Ih();
}
function Qs(e, t, s, n) {
  const r = Eh + e, o = Oh();
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
const Th = "/comfymodal";
class $h extends Error {
  status;
  payload;
  constructor(t, s, n) {
    super(s), this.name = "StudioHttpError", this.status = t, this.payload = n;
  }
}
function Ph(e, t) {
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
function Nh(e, t) {
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
  } = t, { signal: l, cleanup: c } = Nh(o, i);
  try {
    if (l && l.aborted) throw l.reason;
    const u = await s(Th + e, {
      method: n,
      headers: {
        "Content-Type": "application/json",
        ...a
      },
      body: r === void 0 ? void 0 : JSON.stringify(r),
      signal: l
    }), f = await u.text();
    let h = null;
    if (f !== "")
      try {
        h = JSON.parse(f);
      } catch {
        h = f;
      }
    if (!u.ok)
      throw new $h(
        u.status,
        Ph(h, `Request failed with status ${u.status}`),
        h
      );
    return h;
  } finally {
    c();
  }
}
const Mh = $i({ value: dt(), label: dt() }).passthrough(), zh = $i({
  gpu: dt().default(""),
  default_gpu: dt().default(""),
  available_gpus: au(Mh).default([]),
  persisted_gpu: dt().default(""),
  output_format: dt().default("original"),
  quality: Co().default(75),
  webp_lossless_compression: dt().default("balanced"),
  auto_save_local: ir().default(!1),
  save_folder: dt().default(""),
  save_metadata_sidecar: ir().default(!0),
  preview_default: ri(["off", "on"]).default("off"),
  preview_codec: dt().default("webp"),
  preview_quality: Co().default(70),
  data_saver_default: ri(["off", "on"]).default("off"),
  data_saver_codec: dt().default("webp"),
  data_saver_quality: Co().default(70),
  execution_mode: dt().default("v2"),
  execution_mode_source: dt().default(""),
  execution_mode_locked: ir().default(!1),
  engine_migration_notice: dt().nullable().default(null),
  skip_plan_validation: ir().default(!1),
  golden_gpu_order: Ah(dt()).default({})
}).passthrough(), Dh = $i({ status: dt().optional(), level: dt().default("off"), effective: dt().default("off") }).passthrough();
async function ar() {
  return zh.parse(await se("/config"));
}
async function jh(e) {
  return se("/config", { method: "POST", body: e });
}
async function sl() {
  return Dh.parse(await se("/profile/level"));
}
async function Vh(e) {
  return se("/profile/level", { method: "POST", body: { level: e } });
}
async function Lh() {
  return se("/studio/golden/profiles");
}
async function Uh(e, t) {
  return se("/studio/golden/gpu-order", { method: "POST", body: { profile: e, order: t } });
}
async function Fh(e) {
  return se("/studio/golden/deploy", { method: "POST", body: { profile: e } });
}
async function nl(e) {
  return se(`/studio/golden/deploy?profile=${encodeURIComponent(e)}`);
}
const vn = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar"
};
function rl(e) {
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
const lu = "comfymodal-studio";
function eo(e) {
  if (typeof BroadcastChannel > "u") return () => {
  };
  const t = new BroadcastChannel(lu), s = (n) => {
    const r = n.data?.kind;
    (r === "settings" || r === "workspace" || r === "history" || r === "workflows") && e(r);
  };
  return t.addEventListener("message", s), () => {
    t.removeEventListener("message", s), t.close();
  };
}
function He(e) {
  if (typeof BroadcastChannel > "u") return;
  const t = new BroadcastChannel(lu);
  t.postMessage({ kind: e, at: Date.now() }), t.close();
}
function Gn() {
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
      const f = () => {
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
function Wh(e) {
  if (e && e.aborted)
    throw new DOMException("Polling aborted", "AbortError");
}
function Bh(e, t) {
  return t && t.aborted ? Promise.reject(new DOMException("Polling aborted", "AbortError")) : t ? new Promise((s, n) => {
    const r = setTimeout(() => {
      t.removeEventListener("abort", o), s();
    }, e), o = () => {
      clearTimeout(r), n(new DOMException("Polling aborted", "AbortError"));
    };
    t.addEventListener("abort", o, { once: !0 });
  }) : new Promise((s) => setTimeout(s, e));
}
async function Cn(e) {
  const { intervalMs: t, signal: s, run: n, done: r, onAttempt: o } = e;
  let i = 0;
  for (; ; ) {
    Wh(s), i += 1, o && o(i);
    const a = await n(s, i);
    if (r(a)) return a;
    await Bh(t, s);
  }
}
const Gh = ri(["comfortable", "compact"]), Ro = Qs(
  "shell.density",
  "comfortable",
  Gh
), Hh = [
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
], cu = [
  "generation",
  "outputs",
  "accounts",
  "interface",
  "advanced"
];
function qh(e) {
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
const uu = /* @__PURE__ */ mn("studio-settings", () => {
  const e = /* @__PURE__ */ E("generation"), t = /* @__PURE__ */ E(Ro.read()), s = /* @__PURE__ */ E(null), n = /* @__PURE__ */ E("off"), r = /* @__PURE__ */ E("off"), o = /* @__PURE__ */ E(!1), i = /* @__PURE__ */ E(!1), a = /* @__PURE__ */ E(null), l = /* @__PURE__ */ E(!1), c = /* @__PURE__ */ E([]), u = /* @__PURE__ */ E(null), f = /* @__PURE__ */ E(null), h = /* @__PURE__ */ E(!1);
  let d = !1, y = null;
  const C = Qs("golden.profile", "", dt()), U = Qs(
    "golden.favorites",
    [],
    au(dt())
  ), Q = Qs("history.columns", "6"), B = Qs("inventory.interval", "300"), Y = /* @__PURE__ */ E(C.read()), q = /* @__PURE__ */ E(U.read()), ae = /* @__PURE__ */ E(Q.read()), ye = /* @__PURE__ */ E(B.read()), re = Ve(() => s.value?.gpu ?? ""), j = Ve(() => {
    const A = s.value?.golden_gpu_order;
    return A && typeof A == "object" ? A : {};
  });
  async function H() {
    o.value = !0, a.value = null;
    try {
      const [A, O] = await Promise.all([ar(), sl()]);
      s.value = A, n.value = O.level, r.value = O.effective || O.level, rl(A), l.value = !0;
    } catch (A) {
      throw a.value = A instanceof Error ? A.message : "Could not load Settings", A;
    } finally {
      o.value = !1, d && (d = !1, H());
    }
  }
  async function x(A) {
    i.value = !0, a.value = null;
    try {
      await jh(A);
      const O = await ar();
      s.value = O, rl(O), He("settings");
    } catch (O) {
      try {
        s.value = await ar();
      } catch {
      }
      throw a.value = O instanceof Error ? O.message : "Could not save Settings", O;
    } finally {
      i.value = !1;
    }
  }
  async function G(A) {
    const O = n.value;
    n.value = A, yn("comfymodal_heavy_tracing", A);
    try {
      await Vh(A);
      const ie = await sl();
      r.value = ie.effective || ie.level, He("settings");
    } catch (ie) {
      throw n.value = O, yn("comfymodal_heavy_tracing", O), ie;
    }
  }
  async function S(A) {
    const O = qh("comfymodal_skip_plan_validation");
    yn("comfymodal_skip_plan_validation", A ? "1" : "0");
    try {
      await x({ skip_plan_validation: A });
    } catch (ie) {
      if (O === null)
        try {
          localStorage.removeItem("comfymodal_skip_plan_validation");
        } catch {
        }
      else
        yn("comfymodal_skip_plan_validation", O);
      throw ie;
    }
  }
  async function X() {
    u.value = null;
    try {
      const A = await Lh();
      if (!A || A.status !== "ok" || !Array.isArray(A.profiles))
        throw new Error(
          A && A.message || "invalid catalog response"
        );
      const O = new Set(
        A.profiles.filter((v) => v && typeof v.name == "string").map((v) => v.name)
      );
      c.value = A.profiles.filter((v) => v && O.has(v.name));
      const ie = s.value?.golden_profile, p = typeof ie == "string" ? ie : "";
      if (O.has(p))
        Y.value = p;
      else if (!O.has(Y.value)) {
        const v = typeof A.defaultProfile == "string" && O.has(A.defaultProfile) ? A.defaultProfile : "";
        Y.value = v;
      }
      C.write(Y.value), Y.value && (f.value = await nl(
        Y.value
      ));
    } catch (A) {
      throw u.value = A instanceof Error ? A.message : "Could not load Golden profiles", A;
    }
  }
  function ke(A) {
    Y.value = A, C.write(A);
  }
  function xe(A) {
    const O = q.value.includes(A) ? q.value.filter((ie) => ie !== A) : [...q.value, A];
    q.value = O, U.write(O);
  }
  async function b(A, O) {
    await Uh(A, O);
    const ie = await ar();
    s.value = ie, He("settings");
  }
  async function $(A) {
    const O = It(), ie = O.start({ kind: "deploy", label: `Deploy Golden ${A}` });
    h.value = !0;
    try {
      await Fh(A), await Cn({
        intervalMs: 2e3,
        run: async () => {
          const p = await nl(A), v = String(p?.state ?? "unknown");
          return O.patch(ie, { message: `Golden deploy: ${v}` }), p;
        },
        done: (p) => p?.state === "done" || p?.state === "failed"
      }).then((p) => {
        if (p?.state === "failed")
          throw new Error(String(p.output || p.message || "Golden deploy failed"));
        f.value = p;
      }), O.finish(ie, "Golden deploy finished"), await X();
    } catch (p) {
      throw O.fail(
        ie,
        p instanceof Error ? p.message : "Golden deploy failed"
      ), p;
    } finally {
      h.value = !1;
    }
    return ie;
  }
  function ve(A) {
    ae.value = A, Q.write(A);
  }
  function Fe(A) {
    ye.value = A, B.write(A);
  }
  async function oe(A) {
    if (A === "generation") {
      bn(["comfymodal_gpu", "comfymodal_preview_default", "comfymodal_preview_codec", "comfymodal_preview_quality", "comfymodal_data_saver_default", "comfymodal_data_saver_codec", "comfymodal_data_saver_quality"]);
      const O = s.value?.default_gpu || "rtx-pro-6000";
      await x({ gpu: O, golden_profile: null }), ke("");
    } else A === "outputs" ? (bn(["comfymodal_output_format", "comfymodal_quality", "comfymodal_webp_lossless_compression", "comfymodal_auto_save_local", "comfymodal_save_folder", "comfymodal_save_metadata_sidecar"]), await x({
      output_format: "original",
      quality: 75,
      webp_lossless_compression: "balanced",
      auto_save_local: !1,
      save_metadata_sidecar: !0
    })) : A === "interface" ? (bn(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1", "comfymodal_remote_inventory_refresh_interval_s", "comfymodal-studio-history-columns"]), ve("6"), Fe("300")) : A === "advanced" && (bn(["comfymodal_heavy_tracing", "comfymodal_skip_plan_validation"]), await G("off").catch(() => {
    }), await x({ skip_plan_validation: !1 }).catch(() => {
    }));
    He("settings");
  }
  async function Xe() {
    bn(Hh), ke(""), q.value = [], U.write([]), ve("6"), Fe("300");
    const A = s.value?.default_gpu || "rtx-pro-6000";
    await x({ gpu: A, golden_profile: null }).catch(() => {
    }), await G("off").catch(() => {
    }), await x({ skip_plan_validation: !1 }).catch(() => {
    }), await H().catch(() => {
    });
  }
  async function Ke() {
    y || (y = eo((A) => {
      if (A === "settings") {
        if (o.value) {
          d = !0;
          return;
        }
        H();
      }
    })), l.value || await H(), yn("comfymodal_heavy_tracing", n.value);
  }
  function ft(A) {
    cu.includes(A) && (e.value = A);
  }
  function at(A) {
    t.value = A, Ro.write(A);
  }
  function ze() {
    e.value = "generation", t.value = "comfortable", Ro.write("comfortable");
  }
  const Ne = Gn();
  async function L(A) {
    const O = await Ne.run(A);
    return O.stale ? null : O.value;
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
    goldenDeployState: f,
    goldenDeploying: h,
    selectedGoldenProfile: Y,
    favoriteGoldenProfiles: q,
    columnsPreference: ae,
    refreshIntervalPreference: ye,
    gpu: re,
    goldenGpuOrder: j,
    outputPreferences: Ve(() => s.value ? {
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
    load: H,
    initialize: Ke,
    save: x,
    setProfile: G,
    setSkipPlanValidation: S,
    loadGolden: X,
    selectGoldenProfile: ke,
    toggleGoldenFavorite: xe,
    setGoldenGpuOrder: b,
    deployGoldenProfile: $,
    setHistoryColumns: ve,
    setInventoryInterval: Fe,
    resetSection: oe,
    resetAll: Xe,
    loadSubresource: L,
    setSection: ft,
    setDensity: at,
    reset: ze
  };
});
function Ao(e) {
  const t = e.active_workspace_id ?? null, s = (e.workspaces ?? []).map((n) => {
    const r = String(n.id ?? "");
    return { id: r, label: String(n.label ?? r), isActive: r !== "" && r === t, lastDeployStatus: String(n.last_deploy_status ?? "idle"), lastUsedAt: typeof n.last_used_at == "string" ? n.last_used_at : null };
  });
  return { activeId: t, rows: s };
}
function du(e) {
  if (!e || typeof e != "object") return { state: "unknown", message: "", details: "", hasLog: !1, available: !1 };
  const t = e;
  return { state: String(t.state ?? "unknown"), message: String(t.message ?? ""), details: String(t.details ?? ""), hasLog: !!t.has_log, available: !0, ...t };
}
function Zh(e) {
  return e === "ready" || e === "deployed_unwarmed";
}
async function Kh() {
  return se("/workspaces");
}
async function Jh(e) {
  return se("/workspaces/active", { method: "POST", body: { workspace_id: e } });
}
async function ol() {
  return du(await se("/deploy/status"));
}
async function Qh() {
  return se("/deploy", { method: "POST" });
}
async function Yh() {
  return se("/deploy/log");
}
async function Xh(e) {
  const t = `?max_age=${encodeURIComponent(String(e))}`;
  return se(`/studio/inventory/refresh${t}`);
}
async function eg(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.type && t.set("type", e.type), e.state && t.set("state", e.state);
  const s = t.toString() ? `?${t}` : "";
  return se(`/studio/models${s}`);
}
async function tg(e = !1) {
  return se("/studio/models/rescan", { method: "POST", body: { force_rehash: e } });
}
async function sg() {
  return se("/studio/custom-nodes");
}
async function ng() {
  return se("/studio/custom-nodes/refresh", { method: "POST" });
}
async function rg(e) {
  return se("/workspaces", { method: "POST", body: e });
}
async function og(e) {
  return se("/workspaces/swap", { method: "POST", body: e });
}
async function ig(e) {
  return se(`/workspaces/swap/${encodeURIComponent(e)}`);
}
function ag(e, t) {
  return { workspace_id: e, confirm: !0, selected_keys: t.slice() };
}
function il(e) {
  const t = String(e && e.phase || "");
  if (t === "downloading_models") {
    const s = String(e && e.download_message || ""), n = Number(e && e.download_completed || 0), r = Number(e && e.download_total || 0) + Number(e && e.download_skipped || 0);
    return s || `Preparing downloads… ${n}/${r}`;
  }
  return t === "syncing_custom_nodes" ? String(e && e.sync_message || "Syncing custom nodes to Modal…") : t === "deploying" ? String(e && e.deploy_message || "Deploying workspace…") : t ? `Phase: ${t.replace(/_/g, " ")}` : "";
}
async function lg() {
  return se("/studio/custom-nodes/sync-status");
}
async function cg() {
  return se("/studio/custom-nodes/sync", { method: "POST" });
}
async function ug() {
  return se("/studio/custom-nodes/sync/rebuild-dependencies", { method: "POST" });
}
async function dg(e) {
  return se(`/studio/custom-nodes/sync/status/${encodeURIComponent(e)}`);
}
async function fg(e) {
  return se("/model/install", { method: "POST", body: e });
}
async function mg(e) {
  return se(`/download/status/${encodeURIComponent(e || "")}`);
}
async function pg(e) {
  return se("/studio/models/install-request", { method: "POST", body: e });
}
async function hg(e) {
  return se("/studio/custom-nodes/install-request", { method: "POST", body: e });
}
async function gg() {
  return se("/manifest/repair/scan", { method: "POST" });
}
async function vg(e) {
  return se("/manifest/repair/apply", { method: "POST", body: { updates: e } });
}
async function yg(e, t) {
  return se("/manifest/repair/delete-placeholder", { method: "POST", body: { folder: e, filename: t } });
}
async function bg() {
  return se("/auth/status");
}
async function al(e) {
  return se(e === "civitai" ? "/civitai-token" : "/hf-token");
}
async function wg(e, t) {
  return se(e === "civitai" ? "/civitai-token" : "/hf-token", { method: "POST", body: { token: t } });
}
function ll(e) {
  return !!(e && typeof e == "object" && typeof e.token == "string" && e.token !== "");
}
async function _g() {
  return se("/health?mode=deploy");
}
const Pi = /* @__PURE__ */ mn("studio-infrastructure", () => {
  const e = /* @__PURE__ */ E("unknown"), t = /* @__PURE__ */ E(null), s = /* @__PURE__ */ E(null), n = /* @__PURE__ */ E([]), r = /* @__PURE__ */ E(null), o = /* @__PURE__ */ E(du(null)), i = /* @__PURE__ */ E(null), a = /* @__PURE__ */ E([]), l = /* @__PURE__ */ E([]), c = /* @__PURE__ */ E([]), u = /* @__PURE__ */ E(null), f = /* @__PURE__ */ E(!1), h = /* @__PURE__ */ E(null), d = /* @__PURE__ */ E(!1), y = /* @__PURE__ */ E(null), C = /* @__PURE__ */ E(null), U = /* @__PURE__ */ E(!1), Q = /* @__PURE__ */ E(null), B = /* @__PURE__ */ E(!1), Y = /* @__PURE__ */ E(!1), q = /* @__PURE__ */ E(null), ae = /* @__PURE__ */ E(null), ye = /* @__PURE__ */ E(null), re = Gn(), j = /* @__PURE__ */ E(null), H = /* @__PURE__ */ E(null), x = /* @__PURE__ */ E(null);
  let G = !1, S = null;
  const X = Ve(() => n.value.find((w) => w.isActive) ?? null);
  function ke(w, M) {
    e.value = w, t.value = M ?? null;
  }
  function xe(w) {
    s.value = w;
  }
  function b() {
    e.value = "unknown", t.value = null, s.value = null;
  }
  function $(w) {
    y.value = w;
  }
  async function ve() {
    const w = Ao(await Kh());
    n.value = w.rows, r.value = w.activeId;
  }
  async function Fe() {
    o.value = await ol(), e.value = o.value.state, t.value = o.value.message || null;
  }
  async function oe() {
    const w = await re.run(async (ce) => {
      const [Ee, we] = await Promise.all([eg(), sg()]);
      return ce.aborted ? null : { modelResult: Ee, nodeResult: we };
    });
    if (w.stale || !w.value) return;
    const M = w.value.modelResult.models;
    a.value = (Array.isArray(M) ? M : []).filter(
      (ce) => !!ce && typeof ce == "object"
    );
    const Z = w.value.nodeResult.custom_nodes;
    c.value = (Array.isArray(Z) ? Z : []).filter(
      (ce) => !!ce && typeof ce == "object"
    );
  }
  async function Xe() {
    f.value = !0, h.value = null;
    try {
      await Promise.all([ve(), Fe(), oe()]), s.value = "server inventory loaded";
    } catch (w) {
      throw h.value = w instanceof Error ? w.message : "Could not load infrastructure", w;
    } finally {
      f.value = !1, G && (G = !1, Xe());
    }
  }
  async function Ke() {
    S || (S = eo((w) => {
      if (w === "workspace") {
        if (f.value) {
          G = !0;
          return;
        }
        Xe();
      }
    })), n.value.length || await Xe();
  }
  async function ft(w) {
    d.value = !0;
    try {
      const M = await rg(w), Z = Ao(M);
      n.value = Z.rows, r.value = Z.activeId, He("workspace");
    } finally {
      d.value = !1;
    }
  }
  async function at(w) {
    if (H.value || x.value)
      throw new Error("Cannot change workspace while an operation is active");
    d.value = !0;
    const M = n.value;
    try {
      const Z = await Jh(w);
      if (!Z || Z.status !== "ok")
        throw new Error(String(Z?.message || "Activation failed"));
      const ce = Ao(Z);
      n.value = ce.rows, r.value = ce.activeId, $(`Active workspace is now ${ce.rows.find((Ee) => Ee.isActive)?.label || w}.`), await Fe(), He("workspace");
    } catch (Z) {
      throw n.value = M, Z;
    } finally {
      d.value = !1;
    }
  }
  async function ze(w, M) {
    const Z = It();
    if (H.value || x.value)
      throw new Error("Another operation is already active");
    d.value = !0, U.value = !1, C.value = null;
    const ce = r.value ?? void 0, Ee = Z.start({
      kind: "workspace-swap",
      label: "Swap workspace",
      workspaceId: ce
    });
    x.value = Ee;
    const we = new AbortController(), We = window.setTimeout(() => we.abort(), 1800 * 1e3);
    try {
      const Oe = await og({ workspace_id: w, ...M || {} }), st = String(Oe.status || "");
      if (st === "busy") throw new Error(String(Oe.message || "Deploy already running — try again later."));
      if (st === "error") throw new Error(String(Oe.message || "Workspace swap failed."));
      if (st === "confirm_required") {
        U.value = !0, Z.patch(Ee, { status: "pending", message: "Confirmation required" });
        return;
      }
      if (st === "repair_required")
        throw Z.fail(Ee, String(Oe.message || "manifest repair required")), await k(), new Error(String(Oe.message || "manifest repair required"));
      if (st === "review_required") {
        const Os = (Array.isArray(Oe.to_install) ? Oe.to_install : []).map((Ws) => {
          const Bs = Ws;
          return {
            key: `${String(Bs.save_path || Bs.folder || "")}/${String(Bs.filename || "")}`,
            filename: String(Bs.filename || ""),
            folder: String(Bs.folder || Bs.save_path || "")
          };
        });
        C.value = {
          workspaceLabel: String(Oe.workspace_label || w),
          toInstall: Os,
          installCount: Number(Oe.install_count || Os.length),
          presentCount: Number(Oe.present_count || 0),
          removeCount: Array.isArray(Oe.to_remove) ? Oe.to_remove.length : 0
        }, Z.patch(Ee, { status: "pending", message: "Review required" });
        return;
      }
      if (st === "started" && Oe.swap_id) {
        await O(String(Oe.swap_id), Ee, we.signal, ce);
        return;
      }
      throw new Error(String(Oe.message || "Unexpected swap response."));
    } catch (Oe) {
      if (U.value || C.value) throw Oe;
      const st = Oe instanceof Error ? Oe.message : "Workspace swap failed";
      throw Z.fail(Ee, st), $(st), Oe;
    } finally {
      window.clearTimeout(We), !U.value && !C.value && (x.value = null), d.value = !1;
    }
  }
  async function Ne(w) {
    U.value = !1, x.value = null, await ze(w, { confirm_prompt_interrupt: !0 });
  }
  async function L(w, M) {
    const Z = x.value;
    C.value = null, x.value = null, Z && It().cancel(Z, "Superseded by review confirmation"), await ze(w, ag(w, M));
  }
  async function A() {
    const w = x.value;
    U.value = !1, C.value = null, x.value = null, d.value = !1, w && It().cancel(w, "Swap cancelled."), $("Swap cancelled.");
  }
  async function O(w, M, Z, ce) {
    const Ee = It();
    try {
      await Cn({
        intervalMs: 1e3,
        signal: Z,
        run: async () => {
          const we = await ig(w);
          return Ee.patch(M, { message: il(we) || "Working…" }), $(il(we) || "Working…"), we;
        },
        done: (we) => String(we.status || "") !== "running"
      }).then((we) => {
        const We = String(we.status || "");
        if (We === "ok") {
          const Oe = String(we.workspace_label || "workspace");
          Ee.finish(M, `Swap done — ${Oe}. Deploy started.`), $(`Done — ${Oe}. Deploy started.`);
        } else throw We === "repair_required" ? (Ee.fail(M, String(we.message || "manifest repair required")), k(), new Error(String(we.message || "manifest repair required"))) : We === "not_found" ? new Error("Swap status unavailable.") : new Error(
          String(we.message || we.error || we.deploy_message || "Workspace swap failed")
        );
      }), ce && r.value, await ve(), await Fe(), He("workspace");
    } catch (we) {
      if (!U.value && !C.value) {
        const We = we instanceof Error ? we.message : "Workspace swap failed";
        try {
          Ee.fail(M, We);
        } catch {
        }
        $(We);
      }
      throw we;
    } finally {
      x.value = null;
    }
  }
  async function ie() {
    const w = It();
    if (H.value) return H.value;
    if (x.value) throw new Error("Cannot deploy while a swap is active");
    const M = r.value ?? void 0, Z = w.start({
      kind: "deploy",
      label: "Deploy workspace",
      workspaceId: M
    });
    H.value = Z;
    const ce = new AbortController();
    j.value = ce;
    const Ee = window.setTimeout(() => ce.abort(new DOMException("Deployment polling timed out", "TimeoutError")), 600 * 1e3);
    try {
      await Qh(), w.patch(Z, { status: "running", message: "Deployment started" });
      const we = await Cn({
        intervalMs: 3e3,
        signal: ce.signal,
        run: async () => {
          const We = await ol();
          return o.value = We, e.value = We.state, t.value = We.message || null, w.patch(Z, { message: We.message || `Deployment: ${We.state}` }), We;
        },
        done: (We) => We.state === "ready" || We.state === "deployed_unwarmed" || We.state !== "deploying" && We.state !== "starting" && We.state !== "unknown"
      });
      if (!Zh(we.state)) throw new Error(we.message || `Deployment ended in ${we.state}`);
      if (M && r.value !== M) throw new Error("Deployment target workspace changed");
      w.finish(Z, we.message || "Deployment completed");
    } catch (we) {
      const We = we instanceof Error ? we.message : "Deployment failed";
      throw w.fail(Z, We), we;
    } finally {
      window.clearTimeout(Ee), j.value = null, H.value = null;
    }
    return Z;
  }
  async function p() {
    const [w, M, Z] = await Promise.all([
      bg().catch(() => null),
      al("hf").catch(() => null),
      al("civitai").catch(() => null)
    ]);
    Q.value = !!(w && w.connected === !0), B.value = ll(M), Y.value = ll(Z);
  }
  async function v(w, M) {
    const Z = await wg(w, M);
    if (!Z || Z.status !== "ok")
      throw new Error(String(Z?.message || Z?.error || "Save failed."));
    return await p(), M ? "Saved." : "Cleared.";
  }
  async function k() {
    ae.value = null;
    const w = await gg();
    q.value = w;
  }
  async function R(w) {
    ae.value = null;
    const M = await vg(w);
    ae.value = String(M.message || "Repairs applied."), q.value = M;
  }
  async function P(w, M) {
    await yg(w, M), await k();
  }
  async function W() {
    u.value = await lg();
  }
  async function _() {
    const w = It(), M = w.start({ kind: "node-sync", label: "Push custom-node plugins" });
    try {
      await cg(), w.finish(M, "Plugins pushed"), await W(), He("workspace");
    } catch (Z) {
      throw w.fail(M, Z instanceof Error ? Z.message : "Push failed"), Z;
    }
  }
  async function T() {
    const w = It(), M = w.start({ kind: "node-sync", label: "Rebuild custom-node dependencies" });
    try {
      const Z = await ug(), ce = String(Z.sync_id || Z.syncId || "");
      ce && await Cn({
        intervalMs: 3e3,
        run: async () => {
          const Ee = await dg(ce);
          return w.patch(M, { message: String(Ee.message || "Rebuilding…") }), Ee;
        },
        done: (Ee) => String(Ee.status || "") !== "running"
      }), w.finish(M, "Dependencies rebuilt"), await W(), He("workspace");
    } catch (Z) {
      throw w.fail(M, Z instanceof Error ? Z.message : "Rebuild failed"), Z;
    }
  }
  async function N(w) {
    const M = It(), Z = M.start({ kind: "model-download", label: `Download ${String(w.filename || w.url || "model")}` });
    try {
      const ce = await fg(w), Ee = String(ce.download_id || ce.downloadId || "");
      if (!Ee) {
        M.finish(Z, "Install request accepted"), await oe();
        return;
      }
      await Cn({
        intervalMs: 2e3,
        run: async () => {
          const we = await mg(Ee);
          return M.patch(Z, {
            progress: typeof we.progress == "number" ? we.progress : void 0,
            message: String(we.message || "Downloading…")
          }), we;
        },
        done: (we) => String(we.status || "") !== "running"
      }).then((we) => {
        if (String(we.status || "") === "error")
          throw new Error(String(we.message || "Download failed"));
      }), M.finish(Z, "Download complete"), await oe(), He("workspace");
    } catch (ce) {
      throw M.fail(Z, ce instanceof Error ? ce.message : "Download failed"), ce;
    }
  }
  async function V(w) {
    await pg(w), await oe();
  }
  async function fe(w) {
    await hg(w), await oe();
  }
  async function ne() {
    await Xh(0), await oe(), s.value = "inventory refreshed", He("workspace");
  }
  async function he(w = !0) {
    const M = await tg(w);
    a.value = Array.isArray(M.models) ? M.models.filter((Z) => !!Z && typeof Z == "object") : a.value, await oe();
  }
  async function _e() {
    const w = await ng();
    c.value = Array.isArray(w.custom_nodes) ? w.custom_nodes.filter((M) => !!M && typeof M == "object") : c.value, await oe();
  }
  async function $e() {
    i.value = await Yh();
  }
  async function Le() {
    ye.value = await _g();
  }
  return {
    deployState: e,
    deployMessage: t,
    syncSummary: s,
    workspaces: n,
    activeWorkspaceId: r,
    activeWorkspace: X,
    deployStatus: o,
    deployLog: i,
    models: a,
    modelTypes: l,
    customNodes: c,
    customNodeSync: u,
    loading: f,
    error: h,
    busy: d,
    progress: y,
    swapReview: C,
    swapConfirmRequired: U,
    authConnected: Q,
    hfConfigured: B,
    civitaiConfigured: Y,
    repairIssues: q,
    repairMessage: ae,
    health: ye,
    deploymentOperationId: H,
    swapOperationId: x,
    setDeploy: ke,
    setSyncSummary: xe,
    reset: b,
    load: Xe,
    initialize: Ke,
    loadWorkspaces: ve,
    loadDeployment: Fe,
    loadInventory: oe,
    saveWorkspace: ft,
    selectWorkspace: at,
    startSwap: ze,
    confirmSwapInterrupt: Ne,
    confirmSwapReview: L,
    cancelSwapDialog: A,
    deploy: ie,
    loadCredentials: p,
    saveCredential: v,
    scanRepair: k,
    applyRepair: R,
    deletePlaceholder: P,
    loadSyncStatus: W,
    pushPlugins: _,
    rebuildDependencies: T,
    installModel: N,
    installModelRequest: V,
    installCustomNode: fe,
    refreshRemoteInventoryNow: ne,
    rescanModelsNow: he,
    refreshCustomNodesNow: _e,
    loadLog: $e,
    loadHealth: Le
  };
});
function fu(e) {
  var t, s, n = "";
  if (typeof e == "string" || typeof e == "number") n += e;
  else if (typeof e == "object") if (Array.isArray(e)) {
    var r = e.length;
    for (t = 0; t < r; t++) e[t] && (s = fu(e[t])) && (n && (n += " "), n += s);
  } else for (s in e) e[s] && (n && (n += " "), n += s);
  return n;
}
function mu() {
  for (var e, t, s = 0, n = "", r = arguments.length; s < r; s++) (e = arguments[s]) && (t = fu(e)) && (n && (n += " "), n += t);
  return n;
}
const xg = (e, t) => {
  const s = new Array(e.length + t.length);
  for (let n = 0; n < e.length; n++)
    s[n] = e[n];
  for (let n = 0; n < t.length; n++)
    s[e.length + n] = t[n];
  return s;
}, kg = (e, t) => ({
  classGroupId: e,
  validator: t
}), pu = (e = /* @__PURE__ */ new Map(), t = null, s) => ({
  nextPart: e,
  validators: t,
  classGroupId: s
}), $r = "-", cl = [], Sg = "arbitrary..", Cg = (e) => {
  const t = Ag(e), {
    conflictingClassGroups: s,
    conflictingClassGroupModifiers: n
  } = e;
  return {
    getClassGroupId: (i) => {
      if (i.startsWith("[") && i.endsWith("]"))
        return Rg(i);
      const a = i.split($r), l = a[0] === "" && a.length > 1 ? 1 : 0;
      return hu(a, l, t);
    },
    getConflictingClassGroupIds: (i, a) => {
      if (a) {
        const l = n[i], c = s[i];
        return l ? c ? xg(c, l) : l : c || cl;
      }
      return s[i] || cl;
    }
  };
}, hu = (e, t, s) => {
  if (e.length - t === 0)
    return s.classGroupId;
  const r = e[t], o = s.nextPart.get(r);
  if (o) {
    const c = hu(e, t + 1, o);
    if (c) return c;
  }
  const i = s.validators;
  if (i === null)
    return;
  const a = t === 0 ? e.join($r) : e.slice(t).join($r), l = i.length;
  for (let c = 0; c < l; c++) {
    const u = i[c];
    if (u.validator(a))
      return u.classGroupId;
  }
}, Rg = (e) => e.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
  const t = e.slice(1, -1), s = t.indexOf(":"), n = t.slice(0, s);
  return n ? Sg + n : void 0;
})(), Ag = (e) => {
  const {
    theme: t,
    classGroups: s
  } = e;
  return Eg(s, t);
}, Eg = (e, t) => {
  const s = pu();
  for (const n in e) {
    const r = e[n];
    Ni(r, s, n, t);
  }
  return s;
}, Ni = (e, t, s, n) => {
  const r = e.length;
  for (let o = 0; o < r; o++) {
    const i = e[o];
    Ig(i, t, s, n);
  }
}, Ig = (e, t, s, n) => {
  if (typeof e == "string") {
    Og(e, t, s);
    return;
  }
  if (typeof e == "function") {
    Tg(e, t, s, n);
    return;
  }
  $g(e, t, s, n);
}, Og = (e, t, s) => {
  const n = e === "" ? t : gu(t, e);
  n.classGroupId = s;
}, Tg = (e, t, s, n) => {
  if (Pg(e)) {
    Ni(e(n), t, s, n);
    return;
  }
  t.validators === null && (t.validators = []), t.validators.push(kg(s, e));
}, $g = (e, t, s, n) => {
  const r = Object.entries(e), o = r.length;
  for (let i = 0; i < o; i++) {
    const [a, l] = r[i];
    Ni(l, gu(t, a), s, n);
  }
}, gu = (e, t) => {
  let s = e;
  const n = t.split($r), r = n.length;
  for (let o = 0; o < r; o++) {
    const i = n[o];
    let a = s.nextPart.get(i);
    a || (a = pu(), s.nextPart.set(i, a)), s = a;
  }
  return s;
}, Pg = (e) => "isThemeGetter" in e && e.isThemeGetter === !0, Ng = (e) => {
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
}, oi = "!", ul = ":", Mg = [], dl = (e, t, s, n, r) => ({
  modifiers: e,
  hasImportantModifier: t,
  baseClassName: s,
  maybePostfixModifierPosition: n,
  isExternal: r
}), zg = (e) => {
  const {
    prefix: t,
    experimentalParseClassName: s
  } = e;
  let n = (r) => {
    const o = [];
    let i = 0, a = 0, l = 0, c;
    const u = r.length;
    for (let C = 0; C < u; C++) {
      const U = r[C];
      if (i === 0 && a === 0) {
        if (U === ul) {
          o.push(r.slice(l, C)), l = C + 1;
          continue;
        }
        if (U === "/") {
          c = C;
          continue;
        }
      }
      U === "[" ? i++ : U === "]" ? i-- : U === "(" ? a++ : U === ")" && a--;
    }
    const f = o.length === 0 ? r : r.slice(l);
    let h = f, d = !1;
    f.endsWith(oi) ? (h = f.slice(0, -1), d = !0) : (
      /**
       * In Tailwind CSS v3 the important modifier was at the start of the base class name. This is still supported for legacy reasons.
       * @see https://github.com/dcastil/tailwind-merge/issues/513#issuecomment-2614029864
       */
      f.startsWith(oi) && (h = f.slice(1), d = !0)
    );
    const y = c && c > l ? c - l : void 0;
    return dl(o, d, h, y);
  };
  if (t) {
    const r = t + ul, o = n;
    n = (i) => i.startsWith(r) ? o(i.slice(r.length)) : dl(Mg, !1, i, void 0, !0);
  }
  if (s) {
    const r = n;
    n = (o) => s({
      className: o,
      parseClassName: r
    });
  }
  return n;
}, Dg = (e) => {
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
}, jg = (e) => ({
  cache: Ng(e.cacheSize),
  parseClassName: zg(e),
  sortModifiers: Dg(e),
  postfixLookupClassGroupIds: Vg(e),
  ...Cg(e)
}), Vg = (e) => {
  const t = /* @__PURE__ */ Object.create(null), s = e.postfixLookupClassGroups;
  if (s)
    for (let n = 0; n < s.length; n++)
      t[s[n]] = !0;
  return t;
}, Lg = /\s+/, Ug = (e, t) => {
  const {
    parseClassName: s,
    getClassGroupId: n,
    getConflictingClassGroupIds: r,
    sortModifiers: o,
    postfixLookupClassGroupIds: i
  } = t, a = [], l = e.trim().split(Lg);
  let c = "";
  for (let u = l.length - 1; u >= 0; u -= 1) {
    const f = l[u], {
      isExternal: h,
      modifiers: d,
      hasImportantModifier: y,
      baseClassName: C,
      maybePostfixModifierPosition: U
    } = s(f);
    if (h) {
      c = f + (c.length > 0 ? " " + c : c);
      continue;
    }
    let Q = !!U, B;
    if (Q) {
      const re = C.substring(0, U);
      B = n(re);
      const j = B && i[B] ? n(C) : void 0;
      j && j !== B && (B = j, Q = !1);
    } else
      B = n(C);
    if (!B) {
      if (!Q) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      if (B = n(C), !B) {
        c = f + (c.length > 0 ? " " + c : c);
        continue;
      }
      Q = !1;
    }
    const Y = d.length === 0 ? "" : d.length === 1 ? d[0] : o(d).join(":"), q = y ? Y + oi : Y, ae = q + B;
    if (a.indexOf(ae) > -1)
      continue;
    a.push(ae);
    const ye = r(B, Q);
    for (let re = 0; re < ye.length; ++re) {
      const j = ye[re];
      a.push(q + j);
    }
    c = f + (c.length > 0 ? " " + c : c);
  }
  return c;
}, Fg = (...e) => {
  let t = 0, s, n, r = "";
  for (; t < e.length; )
    (s = e[t++]) && (n = vu(s)) && (r && (r += " "), r += n);
  return r;
}, vu = (e) => {
  if (typeof e == "string")
    return e;
  let t, s = "";
  for (let n = 0; n < e.length; n++)
    e[n] && (t = vu(e[n])) && (s && (s += " "), s += t);
  return s;
}, Wg = (e, ...t) => {
  let s, n, r, o;
  const i = (l) => {
    const c = t.reduce((u, f) => f(u), e());
    return s = jg(c), n = s.cache.get, r = s.cache.set, o = a, a(l);
  }, a = (l) => {
    const c = n(l);
    if (c)
      return c;
    const u = Ug(l, s);
    return r(l, u), u;
  };
  return o = i, (...l) => o(Fg(...l));
}, Bg = [], lt = (e) => {
  const t = (s) => s[e] || Bg;
  return t.isThemeGetter = !0, t.themeKey = e, t;
}, yu = /^\[(?:(\w[\w-]*):)?(.+)\]$/i, bu = /^\((?:(\w[\w-]*):)?(.+)\)$/i, Gg = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/, Hg = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/, qg = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/, Zg = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix|color|light-dark)\(.+\)$/, Kg = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/, Jg = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/, ps = (e) => Gg.test(e), Te = (e) => !!e && !Number.isNaN(Number(e)), Vt = (e) => !!e && Number.isInteger(Number(e)), Eo = (e) => e.endsWith("%") && Te(e.slice(0, -1)), es = (e) => Hg.test(e), wu = () => !0, Qg = (e) => (
  // `colorFunctionRegex` check is necessary because color functions can have percentages in them which which would be incorrectly classified as lengths.
  // For example, `hsl(0 0% 0%)` would be classified as a length without this check.
  // I could also use lookbehind assertion in `lengthUnitRegex` but that isn't supported widely enough.
  qg.test(e) && !Zg.test(e)
), Mi = () => !1, Yg = (e) => Kg.test(e), Xg = (e) => Jg.test(e), ev = (e) => !ue(e) && !de(e), tv = (e) => e.startsWith("@container") && (e[10] === "/" && e[11] !== void 0 || e[11] === "s" && e[16] !== void 0 && e.startsWith("-size/", 10) || e[11] === "n" && e[18] !== void 0 && e.startsWith("-normal/", 10)), sv = (e) => Is(e, ku, Mi), ue = (e) => yu.test(e), Ns = (e) => Is(e, Su, Qg), fl = (e) => Is(e, uv, Te), nv = (e) => Is(e, Ru, wu), rv = (e) => Is(e, Cu, Mi), ml = (e) => Is(e, _u, Mi), ov = (e) => Is(e, xu, Xg), lr = (e) => Is(e, Au, Yg), de = (e) => bu.test(e), wn = (e) => Fs(e, Su), iv = (e) => Fs(e, Cu), pl = (e) => Fs(e, _u), av = (e) => Fs(e, ku), lv = (e) => Fs(e, xu), cr = (e) => Fs(e, Au, !0), cv = (e) => Fs(e, Ru, !0), Is = (e, t, s) => {
  const n = yu.exec(e);
  return n ? n[1] ? t(n[1]) : s(n[2]) : !1;
}, Fs = (e, t, s = !1) => {
  const n = bu.exec(e);
  return n ? n[1] ? t(n[1]) : s : !1;
}, _u = (e) => e === "position" || e === "percentage", xu = (e) => e === "image" || e === "url", ku = (e) => e === "length" || e === "size" || e === "bg-size", Su = (e) => e === "length", uv = (e) => e === "number", Cu = (e) => e === "family-name", Ru = (e) => e === "number" || e === "weight", Au = (e) => e === "shadow", dv = () => {
  const e = lt("color"), t = lt("font"), s = lt("text"), n = lt("font-weight"), r = lt("tracking"), o = lt("leading"), i = lt("breakpoint"), a = lt("container"), l = lt("spacing"), c = lt("radius"), u = lt("shadow"), f = lt("inset-shadow"), h = lt("text-shadow"), d = lt("drop-shadow"), y = lt("blur"), C = lt("perspective"), U = lt("aspect"), Q = lt("ease"), B = lt("animate"), Y = () => ["auto", "avoid", "all", "avoid-page", "page", "left", "right", "column"], q = () => [
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
  ], ae = () => [...q(), de, ue], ye = () => ["auto", "hidden", "clip", "visible", "scroll"], re = () => ["auto", "contain", "none"], j = () => [de, ue, l], H = () => [ps, "full", "auto", ...j()], x = () => [Vt, "none", "subgrid", de, ue], G = () => ["auto", {
    span: ["full", Vt, de, ue]
  }, Vt, de, ue], S = () => [Vt, "auto", de, ue], X = () => ["auto", "min", "max", "fr", de, ue], ke = () => ["start", "end", "center", "between", "around", "evenly", "stretch", "baseline", "center-safe", "end-safe"], xe = () => ["start", "end", "center", "stretch", "center-safe", "end-safe"], b = () => ["auto", ...j()], $ = () => [ps, "auto", "full", "dvw", "dvh", "lvw", "lvh", "svw", "svh", "min", "max", "fit", ...j()], ve = () => [a, ps, "screen", "full", "dvw", "lvw", "svw", "min", "max", "fit", ...j()], Fe = () => [ps, "screen", "full", "lh", "dvh", "lvh", "svh", "min", "max", "fit", ...j()], oe = () => [e, de, ue], Xe = () => [...q(), pl, ml, {
    position: [de, ue]
  }], Ke = () => ["no-repeat", {
    repeat: ["", "x", "y", "space", "round"]
  }], ft = () => ["auto", "cover", "contain", av, sv, {
    size: [de, ue]
  }], at = () => [Eo, wn, Ns], ze = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    "full",
    c,
    de,
    ue
  ], Ne = () => ["", Te, wn, Ns], L = () => ["solid", "dashed", "dotted", "double"], A = () => ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"], O = () => [Te, Eo, pl, ml], ie = () => [
    // Deprecated since Tailwind CSS v4.0.0
    "",
    "none",
    y,
    de,
    ue
  ], p = () => ["none", Te, de, ue], v = () => ["none", Te, de, ue], k = () => [Te, de, ue], R = () => [ps, "full", ...j()];
  return {
    cacheSize: 500,
    theme: {
      animate: ["spin", "ping", "pulse", "bounce"],
      aspect: ["video"],
      blur: [es],
      breakpoint: [es],
      color: [wu],
      container: [es],
      "drop-shadow": [es],
      ease: ["in", "out", "in-out"],
      font: [ev],
      "font-weight": ["thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black"],
      "inset-shadow": [es],
      leading: ["none", "tight", "snug", "normal", "relaxed", "loose"],
      perspective: ["dramatic", "near", "normal", "midrange", "distant", "none"],
      radius: [es],
      shadow: [es],
      spacing: ["px", Te],
      text: [es],
      "text-shadow": [es],
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
        aspect: ["auto", "square", ps, ue, de, U]
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
        "@container": ["", "normal", "size", de, ue]
      }],
      /**
       * Container Name
       * @see https://tailwindcss.com/docs/responsive-design#named-containers
       */
      "container-named": [tv],
      /**
       * Columns
       * @see https://tailwindcss.com/docs/columns
       */
      columns: [{
        columns: [Te, "auto", ue, de, a]
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
        object: ae()
      }],
      /**
       * Overflow
       * @see https://tailwindcss.com/docs/overflow
       */
      overflow: [{
        overflow: ye()
      }],
      /**
       * Overflow X
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-x": [{
        "overflow-x": ye()
      }],
      /**
       * Overflow Y
       * @see https://tailwindcss.com/docs/overflow
       */
      "overflow-y": [{
        "overflow-y": ye()
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
        z: [Vt, "auto", de, ue]
      }],
      // ------------------------
      // --- Flexbox and Grid ---
      // ------------------------
      /**
       * Flex Basis
       * @see https://tailwindcss.com/docs/flex-basis
       */
      basis: [{
        basis: [ps, "full", "auto", a, ...j()]
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
        flex: [Te, ps, "auto", "initial", "none", ue]
      }],
      /**
       * Flex Grow
       * @see https://tailwindcss.com/docs/flex-grow
       */
      grow: [{
        grow: ["", Te, de, ue]
      }],
      /**
       * Flex Shrink
       * @see https://tailwindcss.com/docs/flex-shrink
       */
      shrink: [{
        shrink: ["", Te, de, ue]
      }],
      /**
       * Order
       * @see https://tailwindcss.com/docs/order
       */
      order: [{
        order: [Vt, "first", "last", "none", de, ue]
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
        col: G()
      }],
      /**
       * Grid Column Start
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-start": [{
        "col-start": S()
      }],
      /**
       * Grid Column End
       * @see https://tailwindcss.com/docs/grid-column
       */
      "col-end": [{
        "col-end": S()
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
        row: G()
      }],
      /**
       * Grid Row Start
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-start": [{
        "row-start": S()
      }],
      /**
       * Grid Row End
       * @see https://tailwindcss.com/docs/grid-row
       */
      "row-end": [{
        "row-end": S()
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
        "auto-cols": X()
      }],
      /**
       * Grid Auto Rows
       * @see https://tailwindcss.com/docs/grid-auto-rows
       */
      "auto-rows": [{
        "auto-rows": X()
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
        justify: [...ke(), "normal"]
      }],
      /**
       * Justify Items
       * @see https://tailwindcss.com/docs/justify-items
       */
      "justify-items": [{
        "justify-items": [...xe(), "normal"]
      }],
      /**
       * Justify Self
       * @see https://tailwindcss.com/docs/justify-self
       */
      "justify-self": [{
        "justify-self": ["auto", ...xe()]
      }],
      /**
       * Align Content
       * @see https://tailwindcss.com/docs/align-content
       */
      "align-content": [{
        content: ["normal", ...ke()]
      }],
      /**
       * Align Items
       * @see https://tailwindcss.com/docs/align-items
       */
      "align-items": [{
        items: [...xe(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Align Self
       * @see https://tailwindcss.com/docs/align-self
       */
      "align-self": [{
        self: ["auto", ...xe(), {
          baseline: ["", "last"]
        }]
      }],
      /**
       * Place Content
       * @see https://tailwindcss.com/docs/place-content
       */
      "place-content": [{
        "place-content": ke()
      }],
      /**
       * Place Items
       * @see https://tailwindcss.com/docs/place-items
       */
      "place-items": [{
        "place-items": [...xe(), "baseline"]
      }],
      /**
       * Place Self
       * @see https://tailwindcss.com/docs/place-self
       */
      "place-self": [{
        "place-self": ["auto", ...xe()]
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
        m: b()
      }],
      /**
       * Margin Inline
       * @see https://tailwindcss.com/docs/margin
       */
      mx: [{
        mx: b()
      }],
      /**
       * Margin Block
       * @see https://tailwindcss.com/docs/margin
       */
      my: [{
        my: b()
      }],
      /**
       * Margin Inline Start
       * @see https://tailwindcss.com/docs/margin
       */
      ms: [{
        ms: b()
      }],
      /**
       * Margin Inline End
       * @see https://tailwindcss.com/docs/margin
       */
      me: [{
        me: b()
      }],
      /**
       * Margin Block Start
       * @see https://tailwindcss.com/docs/margin
       */
      mbs: [{
        mbs: b()
      }],
      /**
       * Margin Block End
       * @see https://tailwindcss.com/docs/margin
       */
      mbe: [{
        mbe: b()
      }],
      /**
       * Margin Top
       * @see https://tailwindcss.com/docs/margin
       */
      mt: [{
        mt: b()
      }],
      /**
       * Margin Right
       * @see https://tailwindcss.com/docs/margin
       */
      mr: [{
        mr: b()
      }],
      /**
       * Margin Bottom
       * @see https://tailwindcss.com/docs/margin
       */
      mb: [{
        mb: b()
      }],
      /**
       * Margin Left
       * @see https://tailwindcss.com/docs/margin
       */
      ml: [{
        ml: b()
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
        size: $()
      }],
      /**
       * Inline Size
       * @see https://tailwindcss.com/docs/inline-size
       */
      "inline-size": [{
        inline: ["auto", ...ve()]
      }],
      /**
       * Min-Inline Size
       * @see https://tailwindcss.com/docs/min-inline-size
       */
      "min-inline-size": [{
        "min-inline": ["auto", ...ve()]
      }],
      /**
       * Max-Inline Size
       * @see https://tailwindcss.com/docs/max-inline-size
       */
      "max-inline-size": [{
        "max-inline": ["none", ...ve()]
      }],
      /**
       * Block Size
       * @see https://tailwindcss.com/docs/block-size
       */
      "block-size": [{
        block: ["auto", ...Fe()]
      }],
      /**
       * Min-Block Size
       * @see https://tailwindcss.com/docs/min-block-size
       */
      "min-block-size": [{
        "min-block": ["auto", ...Fe()]
      }],
      /**
       * Max-Block Size
       * @see https://tailwindcss.com/docs/max-block-size
       */
      "max-block-size": [{
        "max-block": ["none", ...Fe()]
      }],
      /**
       * Width
       * @see https://tailwindcss.com/docs/width
       */
      w: [{
        w: [a, "screen", ...$()]
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
          ...$()
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
          ...$()
        ]
      }],
      /**
       * Height
       * @see https://tailwindcss.com/docs/height
       */
      h: [{
        h: ["screen", "lh", ...$()]
      }],
      /**
       * Min-Height
       * @see https://tailwindcss.com/docs/min-height
       */
      "min-h": [{
        "min-h": ["screen", "lh", "none", ...$()]
      }],
      /**
       * Max-Height
       * @see https://tailwindcss.com/docs/max-height
       */
      "max-h": [{
        "max-h": ["screen", "lh", "none", ...$()]
      }],
      // ------------------
      // --- Typography ---
      // ------------------
      /**
       * Font Size
       * @see https://tailwindcss.com/docs/font-size
       */
      "font-size": [{
        text: ["base", s, wn, Ns]
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
        font: [n, cv, nv]
      }],
      /**
       * Font Stretch
       * @see https://tailwindcss.com/docs/font-stretch
       */
      "font-stretch": [{
        "font-stretch": ["ultra-condensed", "extra-condensed", "condensed", "semi-condensed", "normal", "semi-expanded", "expanded", "extra-expanded", "ultra-expanded", Eo, ue]
      }],
      /**
       * Font Family
       * @see https://tailwindcss.com/docs/font-family
       */
      "font-family": [{
        font: [iv, rv, t]
      }],
      /**
       * Font Feature Settings
       * @see https://tailwindcss.com/docs/font-feature-settings
       */
      "font-features": [{
        "font-features": [ue]
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
        tracking: [r, de, ue]
      }],
      /**
       * Line Clamp
       * @see https://tailwindcss.com/docs/line-clamp
       */
      "line-clamp": [{
        "line-clamp": [Te, "none", de, fl]
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
          ...j()
        ]
      }],
      /**
       * List Style Image
       * @see https://tailwindcss.com/docs/list-style-image
       */
      "list-image": [{
        "list-image": ["none", de, ue]
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
        list: ["disc", "decimal", "none", de, ue]
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
        decoration: [...L(), "wavy"]
      }],
      /**
       * Text Decoration Thickness
       * @see https://tailwindcss.com/docs/text-decoration-thickness
       */
      "text-decoration-thickness": [{
        decoration: [Te, "from-font", "auto", de, Ns]
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
        "underline-offset": [Te, "auto", de, ue]
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
        tab: [Vt, de, ue]
      }],
      /**
       * Vertical Alignment
       * @see https://tailwindcss.com/docs/vertical-align
       */
      "vertical-align": [{
        align: ["baseline", "top", "middle", "bottom", "text-top", "text-bottom", "sub", "super", de, ue]
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
        content: ["none", de, ue]
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
        bg: Ke()
      }],
      /**
       * Background Size
       * @see https://tailwindcss.com/docs/background-size
       */
      "bg-size": [{
        bg: ft()
      }],
      /**
       * Background Image
       * @see https://tailwindcss.com/docs/background-image
       */
      "bg-image": [{
        bg: ["none", {
          linear: [{
            to: ["t", "tr", "r", "br", "b", "bl", "l", "tl"]
          }, Vt, de, ue],
          radial: ["", de, ue],
          conic: ["", Vt, de, ue]
        }, lv, ov]
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
        border: Ne()
      }],
      /**
       * Border Width Inline
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-x": [{
        "border-x": Ne()
      }],
      /**
       * Border Width Block
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-y": [{
        "border-y": Ne()
      }],
      /**
       * Border Width Inline Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-s": [{
        "border-s": Ne()
      }],
      /**
       * Border Width Inline End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-e": [{
        "border-e": Ne()
      }],
      /**
       * Border Width Block Start
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-bs": [{
        "border-bs": Ne()
      }],
      /**
       * Border Width Block End
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-be": [{
        "border-be": Ne()
      }],
      /**
       * Border Width Top
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-t": [{
        "border-t": Ne()
      }],
      /**
       * Border Width Right
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-r": [{
        "border-r": Ne()
      }],
      /**
       * Border Width Bottom
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-b": [{
        "border-b": Ne()
      }],
      /**
       * Border Width Left
       * @see https://tailwindcss.com/docs/border-width
       */
      "border-w-l": [{
        "border-l": Ne()
      }],
      /**
       * Divide Width X
       * @see https://tailwindcss.com/docs/border-width#between-children
       */
      "divide-x": [{
        "divide-x": Ne()
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
        "divide-y": Ne()
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
        border: [...L(), "hidden", "none"]
      }],
      /**
       * Divide Style
       * @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
       */
      "divide-style": [{
        divide: [...L(), "hidden", "none"]
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
        outline: [...L(), "none", "hidden"]
      }],
      /**
       * Outline Offset
       * @see https://tailwindcss.com/docs/outline-offset
       */
      "outline-offset": [{
        "outline-offset": [Te, de, ue]
      }],
      /**
       * Outline Width
       * @see https://tailwindcss.com/docs/outline-width
       */
      "outline-w": [{
        outline: ["", Te, wn, Ns]
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
          cr,
          lr
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
        "inset-shadow": ["none", f, cr, lr]
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
        ring: Ne()
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
        "ring-offset": [Te, Ns]
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
        "inset-ring": Ne()
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
        "text-shadow": ["none", h, cr, lr]
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
        opacity: [Te, de, ue]
      }],
      /**
       * Mix Blend Mode
       * @see https://tailwindcss.com/docs/mix-blend-mode
       */
      "mix-blend": [{
        "mix-blend": [...A(), "plus-darker", "plus-lighter"]
      }],
      /**
       * Background Blend Mode
       * @see https://tailwindcss.com/docs/background-blend-mode
       */
      "bg-blend": [{
        "bg-blend": A()
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
        "mask-linear": [Te]
      }],
      "mask-image-linear-from-pos": [{
        "mask-linear-from": O()
      }],
      "mask-image-linear-to-pos": [{
        "mask-linear-to": O()
      }],
      "mask-image-linear-from-color": [{
        "mask-linear-from": oe()
      }],
      "mask-image-linear-to-color": [{
        "mask-linear-to": oe()
      }],
      "mask-image-t-from-pos": [{
        "mask-t-from": O()
      }],
      "mask-image-t-to-pos": [{
        "mask-t-to": O()
      }],
      "mask-image-t-from-color": [{
        "mask-t-from": oe()
      }],
      "mask-image-t-to-color": [{
        "mask-t-to": oe()
      }],
      "mask-image-r-from-pos": [{
        "mask-r-from": O()
      }],
      "mask-image-r-to-pos": [{
        "mask-r-to": O()
      }],
      "mask-image-r-from-color": [{
        "mask-r-from": oe()
      }],
      "mask-image-r-to-color": [{
        "mask-r-to": oe()
      }],
      "mask-image-b-from-pos": [{
        "mask-b-from": O()
      }],
      "mask-image-b-to-pos": [{
        "mask-b-to": O()
      }],
      "mask-image-b-from-color": [{
        "mask-b-from": oe()
      }],
      "mask-image-b-to-color": [{
        "mask-b-to": oe()
      }],
      "mask-image-l-from-pos": [{
        "mask-l-from": O()
      }],
      "mask-image-l-to-pos": [{
        "mask-l-to": O()
      }],
      "mask-image-l-from-color": [{
        "mask-l-from": oe()
      }],
      "mask-image-l-to-color": [{
        "mask-l-to": oe()
      }],
      "mask-image-x-from-pos": [{
        "mask-x-from": O()
      }],
      "mask-image-x-to-pos": [{
        "mask-x-to": O()
      }],
      "mask-image-x-from-color": [{
        "mask-x-from": oe()
      }],
      "mask-image-x-to-color": [{
        "mask-x-to": oe()
      }],
      "mask-image-y-from-pos": [{
        "mask-y-from": O()
      }],
      "mask-image-y-to-pos": [{
        "mask-y-to": O()
      }],
      "mask-image-y-from-color": [{
        "mask-y-from": oe()
      }],
      "mask-image-y-to-color": [{
        "mask-y-to": oe()
      }],
      "mask-image-radial": [{
        "mask-radial": [de, ue]
      }],
      "mask-image-radial-from-pos": [{
        "mask-radial-from": O()
      }],
      "mask-image-radial-to-pos": [{
        "mask-radial-to": O()
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
        "mask-radial-at": q()
      }],
      "mask-image-conic-pos": [{
        "mask-conic": [Te]
      }],
      "mask-image-conic-from-pos": [{
        "mask-conic-from": O()
      }],
      "mask-image-conic-to-pos": [{
        "mask-conic-to": O()
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
        mask: Xe()
      }],
      /**
       * Mask Repeat
       * @see https://tailwindcss.com/docs/mask-repeat
       */
      "mask-repeat": [{
        mask: Ke()
      }],
      /**
       * Mask Size
       * @see https://tailwindcss.com/docs/mask-size
       */
      "mask-size": [{
        mask: ft()
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
        mask: ["none", de, ue]
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
          de,
          ue
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
        brightness: [Te, de, ue]
      }],
      /**
       * Contrast
       * @see https://tailwindcss.com/docs/contrast
       */
      contrast: [{
        contrast: [Te, de, ue]
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
          d,
          cr,
          lr
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
        grayscale: ["", Te, de, ue]
      }],
      /**
       * Hue Rotate
       * @see https://tailwindcss.com/docs/hue-rotate
       */
      "hue-rotate": [{
        "hue-rotate": [Te, de, ue]
      }],
      /**
       * Invert
       * @see https://tailwindcss.com/docs/invert
       */
      invert: [{
        invert: ["", Te, de, ue]
      }],
      /**
       * Saturate
       * @see https://tailwindcss.com/docs/saturate
       */
      saturate: [{
        saturate: [Te, de, ue]
      }],
      /**
       * Sepia
       * @see https://tailwindcss.com/docs/sepia
       */
      sepia: [{
        sepia: ["", Te, de, ue]
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
          de,
          ue
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
        "backdrop-brightness": [Te, de, ue]
      }],
      /**
       * Backdrop Contrast
       * @see https://tailwindcss.com/docs/backdrop-contrast
       */
      "backdrop-contrast": [{
        "backdrop-contrast": [Te, de, ue]
      }],
      /**
       * Backdrop Grayscale
       * @see https://tailwindcss.com/docs/backdrop-grayscale
       */
      "backdrop-grayscale": [{
        "backdrop-grayscale": ["", Te, de, ue]
      }],
      /**
       * Backdrop Hue Rotate
       * @see https://tailwindcss.com/docs/backdrop-hue-rotate
       */
      "backdrop-hue-rotate": [{
        "backdrop-hue-rotate": [Te, de, ue]
      }],
      /**
       * Backdrop Invert
       * @see https://tailwindcss.com/docs/backdrop-invert
       */
      "backdrop-invert": [{
        "backdrop-invert": ["", Te, de, ue]
      }],
      /**
       * Backdrop Opacity
       * @see https://tailwindcss.com/docs/backdrop-opacity
       */
      "backdrop-opacity": [{
        "backdrop-opacity": [Te, de, ue]
      }],
      /**
       * Backdrop Saturate
       * @see https://tailwindcss.com/docs/backdrop-saturate
       */
      "backdrop-saturate": [{
        "backdrop-saturate": [Te, de, ue]
      }],
      /**
       * Backdrop Sepia
       * @see https://tailwindcss.com/docs/backdrop-sepia
       */
      "backdrop-sepia": [{
        "backdrop-sepia": ["", Te, de, ue]
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
        transition: ["", "all", "colors", "opacity", "shadow", "transform", "none", de, ue]
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
        duration: [Te, "initial", de, ue]
      }],
      /**
       * Transition Timing Function
       * @see https://tailwindcss.com/docs/transition-timing-function
       */
      ease: [{
        ease: ["linear", "initial", Q, de, ue]
      }],
      /**
       * Transition Delay
       * @see https://tailwindcss.com/docs/transition-delay
       */
      delay: [{
        delay: [Te, de, ue]
      }],
      /**
       * Animation
       * @see https://tailwindcss.com/docs/animation
       */
      animate: [{
        animate: ["none", B, de, ue]
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
        perspective: [C, de, ue]
      }],
      /**
       * Perspective Origin
       * @see https://tailwindcss.com/docs/perspective-origin
       */
      "perspective-origin": [{
        "perspective-origin": ae()
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
        transform: [de, ue, "", "none", "gpu", "cpu"]
      }],
      /**
       * Transform Origin
       * @see https://tailwindcss.com/docs/transform-origin
       */
      "transform-origin": [{
        origin: ae()
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
        translate: R()
      }],
      /**
       * Translate X
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-x": [{
        "translate-x": R()
      }],
      /**
       * Translate Y
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-y": [{
        "translate-y": R()
      }],
      /**
       * Translate Z
       * @see https://tailwindcss.com/docs/translate
       */
      "translate-z": [{
        "translate-z": R()
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
        zoom: [Vt, de, ue]
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
        cursor: ["auto", "default", "pointer", "wait", "text", "move", "help", "not-allowed", "none", "context-menu", "progress", "cell", "crosshair", "vertical-text", "alias", "copy", "no-drop", "grab", "grabbing", "all-scroll", "col-resize", "row-resize", "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize", "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize", "zoom-in", "zoom-out", de, ue]
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
        "will-change": ["auto", "scroll", "contents", "transform", de, ue]
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
        stroke: [Te, wn, Ns, fl]
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
}, fv = /* @__PURE__ */ Wg(dv);
function zi(...e) {
  return fv(mu(e));
}
const mv = {
  "data-testid": "vue-studio-root",
  class: "cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
}, pv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3" }, hv = {
  "aria-label": "Studio pages",
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1"
}, gv = { class: "cmst:flex-1" }, vv = {
  class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90",
  "data-testid": "vue-status-strip"
}, yv = { "data-testid": "vue-status-route" }, bv = { "data-testid": "vue-status-ops" }, wv = { "data-testid": "vue-status-density" }, _v = { class: "cmst:flex cmst:items-center cmst:gap-1" }, xv = /* @__PURE__ */ St({
  __name: "StudioApp",
  setup(e) {
    const t = Kc(), s = It(), n = uu(), r = Pi();
    fs(() => {
      n.initialize(), r.initialize();
    });
    const o = Jp("(min-width: 768px)"), i = {
      playground: Jc,
      history: Qc,
      workflows: Qo,
      backend: Yc,
      settings: Xc
    }, a = Ve(() => String(t.name ?? "playground"));
    function l(c) {
      const u = a.value === c;
      return zi(
        "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
        u ? "cmst:bg-cmst-secondary cmst:text-cmst-fg" : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg"
      );
    }
    return (c, u) => (D(), J("div", mv, [
      m("header", pv, [
        u[0] || (u[0] = m("span", { class: "cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight" }, [
          I(" Modal Studio "),
          m("span", { class: "cmst:font-normal cmst:opacity-70" }, "· Vue proof shell")
        ], -1)),
        m("nav", hv, [
          (D(!0), J(Ce, null, tt(g(Oi), (f) => (D(), Be(g(qc), {
            key: f,
            to: { name: f },
            class: xt(l(f)),
            "data-testid": `vue-nav-${f}`
          }, {
            default: F(() => [
              (D(), Be(Ud(i[f]), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              })),
              I(" " + K(g(Qp)[f]), 1)
            ]),
            _: 2
          }, 1032, ["to", "class", "data-testid"]))), 128))
        ])
      ]),
      m("main", gv, [
        z(g(Zc))
      ]),
      m("footer", vv, [
        m("span", null, [
          u[1] || (u[1] = I("route: ", -1)),
          m("strong", yv, K(a.value), 1)
        ]),
        m("span", null, [
          u[2] || (u[2] = I(" operations: ", -1)),
          m("strong", bv, K(g(s).active.length) + " active", 1),
          I(" / " + K(g(s).all.length) + " total ", 1)
        ]),
        m("span", null, [
          u[3] || (u[3] = I(" density: ", -1)),
          m("strong", wv, K(g(n).density), 1)
        ]),
        m("span", _v, [
          z(g(Ap), {
            class: "cmst:size-3.5",
            "aria-hidden": "true"
          }),
          u[4] || (u[4] = I(" viewport: ", -1)),
          m("strong", null, K(g(o) ? "wide" : "narrow"), 1),
          u[5] || (u[5] = I(" (VueUse media query) ", -1))
        ])
      ])
    ]));
  }
}), kv = "/", Eu = { page: "playground", focus: null };
function ur(e) {
  const t = e.focus ? `?focus=${encodeURIComponent(e.focus)}` : "";
  return `/${e.page}${t}`;
}
function Io(e) {
  const [t, s] = e.split("?"), n = t.replace(/^\//, ""), r = Rs(n) ? n : Eu.page;
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
function Oo(e) {
  const t = su(e.location.hash);
  return !t.matched || !Rs(t.page) ? null : { page: t.page, focus: t.focus };
}
function To(e, t, s) {
  const n = nu(t);
  if (!n) return;
  const r = e.location.pathname + e.location.search + n;
  s === "push" ? e.history.pushState({}, "", r) : e.history.replaceState({}, "", r);
}
function Sv(e, t) {
  let s = Yp(t, e.location.hash), n = ur(s), r = {};
  const o = n, i = /* @__PURE__ */ new Set();
  let a = !1;
  const l = () => {
    const u = n;
    s = Oo(e) ?? { ...Eu }, n = ur(s), i.forEach((h) => h(n, u));
  }, c = (u, f) => u === null && f === o;
  return {
    get base() {
      return kv;
    },
    get location() {
      return n;
    },
    get state() {
      return r;
    },
    createHref: (u) => {
      const f = nu(Io(u));
      return f === "" ? "#" + u : f;
    },
    replace: (u, f) => {
      const h = Oo(e), d = Io(u), y = ur(d);
      s = d, f !== void 0 && (r = f), n = y, !c(h, y) && Va(h, d) !== "none" && To(e, d, "replace");
    },
    push: (u, f) => {
      const h = Oo(e), d = Io(u), y = ur(d);
      if (s = d, f !== void 0 && (r = f), n = y, c(h, y)) return;
      const C = Va(h, d);
      C === "push" ? To(e, d, "push") : C === "replace" && To(e, d, "replace");
    },
    go: (u) => {
      e.history.go(u);
    },
    listen: (u) => {
      const f = (h, d) => {
        u(h, d, { type: "pop", direction: "unknown", delta: 0 });
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
const hl = (e) => typeof e == "boolean" ? `${e}` : e === 0 ? "0" : e, gl = mu, Cv = (e, t) => (s) => {
  var n;
  if (t?.variants == null) return gl(e, s?.class, s?.className);
  const { variants: r, defaultVariants: o } = t, i = Object.keys(r).map((c) => {
    const u = s?.[c], f = o?.[c];
    if (u === null) return null;
    const h = hl(u) || hl(f);
    return r[c][h];
  }), a = s && Object.entries(s).reduce((c, u) => {
    let [f, h] = u;
    return h === void 0 || (c[f] = h), c;
  }, {}), l = t == null || (n = t.compoundVariants) === null || n === void 0 ? void 0 : n.reduce((c, u) => {
    let { class: f, className: h, ...d } = u;
    return Object.entries(d).every((y) => {
      let [C, U] = y;
      return Array.isArray(U) ? U.includes({
        ...o,
        ...a
      }[C]) : {
        ...o,
        ...a
      }[C] === U;
    }) ? [
      ...c,
      f,
      h
    ] : c;
  }, []);
  return gl(e, i, l, s?.class, s?.className);
}, Rv = Cv(
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
), Av = ["type", "disabled"], ee = /* @__PURE__ */ St({
  __name: "StudioButton",
  props: {
    variant: { default: "default" },
    size: { default: "default" },
    type: { default: "button" },
    disabled: { type: Boolean, default: !1 }
  },
  setup(e) {
    return (t, s) => (D(), J("button", {
      type: e.type,
      disabled: e.disabled,
      class: xt(g(Rv)({ variant: e.variant, size: e.size }))
    }, [
      ac(t.$slots, "default")
    ], 10, Av));
  }
}), Ze = /* @__PURE__ */ St({
  __name: "StudioCard",
  setup(e) {
    return (t, s) => (D(), J("div", {
      class: xt(
        g(zi)(
          "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm"
        )
      )
    }, [
      ac(t.$slots, "default")
    ], 2));
  }
});
function Jn(e) {
  return zi(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    e
  );
}
const Ev = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Iv = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Ov = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Tv = { class: "cmst:flex cmst:gap-2" }, $v = {
  key: 0,
  class: "cmst:mt-2 cmst:text-sm",
  "data-testid": "vue-backend-progress"
}, Pv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, Nv = ["data-testid", "onClick"], Mv = { class: "cmst:block cmst:text-xs cmst:opacity-70" }, zv = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Dv = {
  key: 0,
  class: "cmst:mt-3 cmst:max-w-md cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3",
  "data-testid": "vue-workspace-form"
}, jv = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Vv = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Lv = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Uv = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-red-300",
  role: "alert"
}, Fv = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, Wv = {
  key: 1,
  class: "cmst:mt-3 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3",
  "data-testid": "vue-swap-confirm"
}, Bv = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, Gv = {
  key: 2,
  class: "cmst:mt-3 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3",
  "data-testid": "vue-swap-review"
}, Hv = { class: "cmst:text-sm" }, qv = ["value"], Zv = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, Kv = { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, Jv = { "data-testid": "vue-auth-status" }, Qv = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Yv = { class: "cmst:text-sm" }, Xv = { "data-testid": "vue-cred-hf-state" }, ey = { class: "cmst:mt-1 cmst:flex cmst:gap-2" }, ty = { class: "cmst:text-sm" }, sy = { "data-testid": "vue-cred-civitai-state" }, ny = { class: "cmst:mt-1 cmst:flex cmst:gap-2" }, ry = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs"
}, oy = { class: "cmst:flex cmst:items-center cmst:justify-between" }, iy = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, ay = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs"
}, ly = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, cy = { class: "cmst:mt-1 cmst:text-sm" }, uy = { "data-testid": "vue-deploy-state" }, dy = {
  key: 0,
  class: "cmst:text-sm cmst:opacity-80"
}, fy = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, my = {
  key: 0,
  class: "cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, py = { class: "cmst:flex cmst:items-center cmst:justify-between" }, hy = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs"
}, gy = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, vy = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2" }, yy = { class: "cmst:text-sm cmst:font-semibold" }, by = { class: "cmst:flex cmst:gap-2" }, wy = {
  class: "cmst:mt-3 cmst:flex cmst:max-h-64 cmst:flex-col cmst:gap-1 cmst:overflow-auto cmst:text-sm",
  "data-testid": "vue-models-list"
}, _y = { class: "cmst:opacity-60" }, xy = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, ky = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Sy = { class: "cmst:text-sm cmst:font-semibold" }, Cy = {
  class: "cmst:mt-3 cmst:flex cmst:max-h-64 cmst:flex-col cmst:gap-1 cmst:overflow-auto cmst:text-sm",
  "data-testid": "vue-nodes-list"
}, Ry = /* @__PURE__ */ St({
  __name: "BackendView",
  setup(e) {
    const t = Pi(), s = /* @__PURE__ */ E("workspaces"), n = /* @__PURE__ */ E(""), r = /* @__PURE__ */ E(!1), o = /* @__PURE__ */ E(""), i = /* @__PURE__ */ E(""), a = /* @__PURE__ */ E(""), l = /* @__PURE__ */ E(""), c = /* @__PURE__ */ E(""), u = /* @__PURE__ */ E([]), f = /* @__PURE__ */ E(""), h = /* @__PURE__ */ E(""), d = /* @__PURE__ */ E(""), y = /* @__PURE__ */ E(""), C = /* @__PURE__ */ E(""), U = /* @__PURE__ */ E("diffusion_models"), Q = /* @__PURE__ */ E(!1);
    fs(async () => {
      await t.initialize().catch(() => {
      }), await Promise.all([
        t.loadCredentials().catch(() => {
        }),
        t.loadSyncStatus().catch(() => {
        })
      ]);
    });
    async function B() {
      n.value && await t.selectWorkspace(n.value).catch(() => {
      });
    }
    function Y() {
      c.value = "", o.value = "", i.value = "", a.value = "", l.value = "", r.value = !0;
    }
    function q() {
      const G = t.workspaces.find((S) => S.id === n.value);
      G && (c.value = G.id, o.value = G.label, i.value = "", a.value = "", l.value = "", r.value = !0);
    }
    async function ae() {
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
      } catch (G) {
        l.value = G instanceof Error ? G.message : "Save failed.";
      }
    }
    async function ye() {
      n.value && await t.startSwap(n.value).catch(() => {
      });
    }
    async function re() {
      await t.confirmSwapReview(n.value, u.value).catch(() => {
      });
    }
    async function j() {
      await t.deploy().catch(() => {
      });
    }
    async function H(G) {
      d.value = "";
      try {
        const S = await t.saveCredential(G, G === "hf" ? f.value : h.value);
        d.value = S, f.value = "", h.value = "";
      } catch (S) {
        d.value = S instanceof Error ? S.message : "Save failed.";
      }
    }
    async function x() {
      C.value.trim() && (await t.installModel({ url: C.value.trim(), folder: U.value }).catch(() => {
      }), C.value = "");
    }
    return (G, S) => (D(), J("section", {
      class: xt(g(Jn)()),
      "data-testid": "vue-page-backend"
    }, [
      g(t).error ? (D(), J("div", Ev, K(g(t).error), 1)) : be("", !0),
      z(Ze, { class: "cmst:p-4" }, {
        default: F(() => [
          m("div", Iv, [
            m("div", null, [
              m("h2", Ov, [
                z(g(Yc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                S[26] || (S[26] = I(" Manage Modal ", -1))
              ]),
              S[27] || (S[27] = m("p", { class: "cmst:text-sm cmst:opacity-80" }, [
                I("Route key remains "),
                m("code", null, "backend"),
                I(". Server truth only.")
              ], -1))
            ]),
            m("div", Tv, [
              (D(), J(Ce, null, tt(["workspaces", "deployment", "models", "nodes"], (X) => z(ee, {
                key: X,
                variant: s.value === X ? "default" : "outline",
                size: "sm",
                "data-testid": `vue-backend-tab-${X}`,
                onClick: (ke) => s.value = X
              }, {
                default: F(() => [
                  I(K(X), 1)
                ]),
                _: 2
              }, 1032, ["variant", "data-testid", "onClick"])), 64)),
              z(ee, {
                variant: "outline",
                size: "icon",
                "aria-label": "Reload infrastructure",
                disabled: g(t).loading,
                onClick: S[0] || (S[0] = (X) => g(t).load())
              }, {
                default: F(() => [
                  z(g(Xr), {
                    class: xt(["cmst:size-4", g(t).loading ? "cmst:animate-spin" : ""]),
                    "aria-hidden": "true"
                  }, null, 8, ["class"])
                ]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          g(t).progress ? (D(), J("p", $v, K(g(t).progress), 1)) : be("", !0)
        ]),
        _: 1
      }),
      s.value === "workspaces" ? (D(), J(Ce, { key: 1 }, [
        z(Ze, { class: "cmst:p-4" }, {
          default: F(() => [
            S[42] || (S[42] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Workspaces", -1)),
            m("div", Pv, [
              (D(!0), J(Ce, null, tt(g(t).workspaces, (X) => (D(), J("button", {
                key: X.id,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-workspace-${X.id}`,
                onClick: (ke) => n.value = X.id
              }, [
                m("strong", null, K(X.label), 1),
                m("span", Mv, K(X.isActive ? "Active workspace" : `Idle · last deploy: ${X.lastDeployStatus}`), 1)
              ], 8, Nv))), 128))
            ]),
            m("div", zv, [
              z(ee, {
                size: "sm",
                variant: "secondary",
                disabled: !n.value || g(t).busy,
                "data-testid": "vue-workspace-activate",
                onClick: B
              }, {
                default: F(() => [...S[28] || (S[28] = [
                  I("Set Active", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              z(ee, {
                size: "sm",
                variant: "outline",
                disabled: g(t).busy,
                onClick: Y
              }, {
                default: F(() => [...S[29] || (S[29] = [
                  I("+ Add Workspace", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              z(ee, {
                size: "sm",
                variant: "outline",
                disabled: !n.value || g(t).busy,
                onClick: q
              }, {
                default: F(() => [...S[30] || (S[30] = [
                  I("Edit Workspace", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              z(ee, {
                size: "sm",
                disabled: !n.value || g(t).busy,
                "data-testid": "vue-workspace-swap",
                onClick: ye
              }, {
                default: F(() => [...S[31] || (S[31] = [
                  I("Swap Workspace", -1)
                ])]),
                _: 1
              }, 8, ["disabled"])
            ]),
            r.value ? (D(), J("div", Dv, [
              m("label", jv, [
                S[32] || (S[32] = I("Label", -1)),
                Pe(m("input", {
                  "onUpdate:modelValue": S[1] || (S[1] = (X) => o.value = X),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2"
                }, null, 512), [
                  [rt, o.value]
                ])
              ]),
              m("label", Vv, [
                S[33] || (S[33] = I("Token ID", -1)),
                Pe(m("input", {
                  "onUpdate:modelValue": S[2] || (S[2] = (X) => i.value = X),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  placeholder: "ak-…"
                }, null, 512), [
                  [rt, i.value]
                ])
              ]),
              m("label", Lv, [
                S[34] || (S[34] = I("Token Secret", -1)),
                Pe(m("input", {
                  "onUpdate:modelValue": S[3] || (S[3] = (X) => a.value = X),
                  type: "password",
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  placeholder: "as-…"
                }, null, 512), [
                  [rt, a.value]
                ])
              ]),
              l.value ? (D(), J("p", Uv, K(l.value), 1)) : be("", !0),
              m("div", Fv, [
                z(ee, {
                  size: "sm",
                  "data-testid": "vue-workspace-save",
                  onClick: ae
                }, {
                  default: F(() => [...S[35] || (S[35] = [
                    I("Save Workspace", -1)
                  ])]),
                  _: 1
                }),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: S[4] || (S[4] = (X) => r.value = !1)
                }, {
                  default: F(() => [...S[36] || (S[36] = [
                    I("Cancel", -1)
                  ])]),
                  _: 1
                })
              ])
            ])) : be("", !0),
            g(t).swapConfirmRequired ? (D(), J("div", Wv, [
              S[39] || (S[39] = m("p", { class: "cmst:text-sm" }, "A prompt is still running. Switch workspaces anyway?", -1)),
              m("div", Bv, [
                z(ee, {
                  size: "sm",
                  "data-testid": "vue-swap-confirm-yes",
                  onClick: S[5] || (S[5] = (X) => g(t).confirmSwapInterrupt(n.value))
                }, {
                  default: F(() => [...S[37] || (S[37] = [
                    I("Interrupt and Switch", -1)
                  ])]),
                  _: 1
                }),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: S[6] || (S[6] = (X) => g(t).cancelSwapDialog())
                }, {
                  default: F(() => [...S[38] || (S[38] = [
                    I("Cancel", -1)
                  ])]),
                  _: 1
                })
              ])
            ])) : be("", !0),
            g(t).swapReview ? (D(), J("div", Gv, [
              m("p", Hv, "Select models to download to " + K(g(t).swapReview.workspaceLabel) + ":", 1),
              (D(!0), J(Ce, null, tt(g(t).swapReview.toInstall, (X) => (D(), J("label", {
                key: X.key,
                class: "cmst:mt-1 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm"
              }, [
                Pe(m("input", {
                  "onUpdate:modelValue": S[7] || (S[7] = (ke) => u.value = ke),
                  type: "checkbox",
                  value: X.key
                }, null, 8, qv), [
                  [en, u.value]
                ]),
                I(" " + K(X.filename) + " (" + K(X.folder) + ") ", 1)
              ]))), 128)),
              m("div", Zv, [
                z(ee, {
                  size: "sm",
                  "data-testid": "vue-swap-review-go",
                  onClick: re
                }, {
                  default: F(() => [...S[40] || (S[40] = [
                    I("Start Swap", -1)
                  ])]),
                  _: 1
                }),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: S[8] || (S[8] = (X) => g(t).cancelSwapDialog())
                }, {
                  default: F(() => [...S[41] || (S[41] = [
                    I("Cancel", -1)
                  ])]),
                  _: 1
                })
              ])
            ])) : be("", !0)
          ]),
          _: 1
        }),
        z(Ze, { class: "cmst:p-4" }, {
          default: F(() => [
            S[48] || (S[48] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Accounts & Tokens", -1)),
            m("p", Kv, [
              S[43] || (S[43] = I(" Modal connection: ", -1)),
              m("strong", Jv, K(g(t).authConnected === null ? "unknown" : g(t).authConnected ? "connected" : "not configured"), 1)
            ]),
            m("div", Qv, [
              m("div", null, [
                m("p", Yv, [
                  S[44] || (S[44] = I("HuggingFace: ", -1)),
                  m("strong", Xv, K(g(t).hfConfigured ? "configured" : "not configured"), 1)
                ]),
                m("div", ey, [
                  Pe(m("input", {
                    "onUpdate:modelValue": S[9] || (S[9] = (X) => f.value = X),
                    type: "password",
                    placeholder: "hf_...",
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                    "data-testid": "vue-cred-hf-input"
                  }, null, 512), [
                    [rt, f.value]
                  ]),
                  z(ee, {
                    size: "sm",
                    "data-testid": "vue-cred-hf-save",
                    onClick: S[10] || (S[10] = (X) => H("hf"))
                  }, {
                    default: F(() => [...S[45] || (S[45] = [
                      I("Save", -1)
                    ])]),
                    _: 1
                  })
                ])
              ]),
              m("div", null, [
                m("p", ty, [
                  S[46] || (S[46] = I("Civitai: ", -1)),
                  m("strong", sy, K(g(t).civitaiConfigured ? "configured" : "not configured"), 1)
                ]),
                m("div", ny, [
                  Pe(m("input", {
                    "onUpdate:modelValue": S[11] || (S[11] = (X) => h.value = X),
                    type: "password",
                    placeholder: "Civitai API Key",
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                    "data-testid": "vue-cred-civitai-input"
                  }, null, 512), [
                    [rt, h.value]
                  ]),
                  z(ee, {
                    size: "sm",
                    "data-testid": "vue-cred-civitai-save",
                    onClick: S[12] || (S[12] = (X) => H("civitai"))
                  }, {
                    default: F(() => [...S[47] || (S[47] = [
                      I("Save", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ]),
            d.value ? (D(), J("p", ry, K(d.value), 1)) : be("", !0)
          ]),
          _: 1
        }),
        z(Ze, { class: "cmst:p-4" }, {
          default: F(() => [
            m("div", oy, [
              S[50] || (S[50] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Manifest repair", -1)),
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-repair-scan",
                onClick: S[13] || (S[13] = (X) => g(t).scanRepair())
              }, {
                default: F(() => [...S[49] || (S[49] = [
                  I("Scan issues", -1)
                ])]),
                _: 1
              })
            ]),
            g(t).repairIssues ? (D(), J("pre", iy, K(JSON.stringify(g(t).repairIssues, null, 2)), 1)) : be("", !0),
            g(t).repairMessage ? (D(), J("p", ay, K(g(t).repairMessage), 1)) : be("", !0)
          ]),
          _: 1
        })
      ], 64)) : be("", !0),
      s.value === "deployment" ? (D(), J(Ce, { key: 2 }, [
        z(Ze, { class: "cmst:p-4" }, {
          default: F(() => [
            m("div", ly, [
              m("div", null, [
                S[52] || (S[52] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Deployment readiness", -1)),
                m("p", cy, [
                  S[51] || (S[51] = I("State: ", -1)),
                  m("strong", uy, K(g(t).deployStatus.state), 1)
                ]),
                g(t).deployMessage ? (D(), J("p", dy, K(g(t).deployMessage), 1)) : be("", !0)
              ]),
              m("div", fy, [
                z(ee, {
                  size: "sm",
                  disabled: g(t).loading || !!g(t).deploymentOperationId,
                  "data-testid": "vue-deploy",
                  onClick: j
                }, {
                  default: F(() => [...S[53] || (S[53] = [
                    I("Deploy", -1)
                  ])]),
                  _: 1
                }, 8, ["disabled"]),
                z(ee, {
                  size: "sm",
                  variant: "outline",
                  "data-testid": "vue-deploy-refresh",
                  onClick: S[14] || (S[14] = (X) => g(t).loadDeployment())
                }, {
                  default: F(() => [...S[54] || (S[54] = [
                    I("Refresh Status", -1)
                  ])]),
                  _: 1
                }),
                z(ee, {
                  size: "sm",
                  variant: "outline",
                  onClick: S[15] || (S[15] = (X) => Q.value = !Q.value)
                }, {
                  default: F(() => [
                    I(K(Q.value ? "Hide" : "Show") + " Log", 1)
                  ]),
                  _: 1
                })
              ])
            ]),
            Q.value ? (D(), J("pre", my, K(g(t).deployLog ?? "Loading…"), 1)) : be("", !0),
            Q.value && !g(t).deployLog ? (D(), Be(ee, {
              key: 1,
              class: "cmst:mt-2",
              size: "sm",
              variant: "ghost",
              onClick: S[16] || (S[16] = (X) => g(t).loadLog())
            }, {
              default: F(() => [...S[55] || (S[55] = [
                I("Load deployment log", -1)
              ])]),
              _: 1
            })) : be("", !0)
          ]),
          _: 1
        }),
        z(Ze, { class: "cmst:p-4" }, {
          default: F(() => [
            m("div", py, [
              S[57] || (S[57] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Custom-node sync", -1)),
              z(ee, {
                size: "sm",
                variant: "outline",
                onClick: S[17] || (S[17] = (X) => g(t).loadSyncStatus())
              }, {
                default: F(() => [...S[56] || (S[56] = [
                  I("Refresh status", -1)
                ])]),
                _: 1
              })
            ]),
            g(t).customNodeSync ? (D(), J("pre", hy, K(JSON.stringify(g(t).customNodeSync, null, 2)), 1)) : be("", !0),
            m("div", gy, [
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-node-push",
                onClick: S[18] || (S[18] = (X) => g(t).pushPlugins())
              }, {
                default: F(() => [...S[58] || (S[58] = [
                  I("Push plugins (FAST)", -1)
                ])]),
                _: 1
              }),
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-node-rebuild",
                onClick: S[19] || (S[19] = (X) => g(t).rebuildDependencies())
              }, {
                default: F(() => [...S[59] || (S[59] = [
                  I("Rebuild dependencies (SLOW)", -1)
                ])]),
                _: 1
              })
            ])
          ]),
          _: 1
        })
      ], 64)) : be("", !0),
      s.value === "models" ? (D(), Be(Ze, {
        key: 3,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          m("div", vy, [
            m("h3", yy, "Models (" + K(g(t).models.length) + ")", 1),
            m("div", by, [
              Pe(m("input", {
                "onUpdate:modelValue": S[20] || (S[20] = (X) => y.value = X),
                class: "cmst:h-9 cmst:w-48 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                placeholder: "Search models",
                onKeyup: S[21] || (S[21] = rn((X) => g(t).loadInventory(), ["enter"]))
              }, null, 544), [
                [rt, y.value]
              ]),
              z(ee, {
                size: "sm",
                variant: "outline",
                onClick: S[22] || (S[22] = (X) => g(t).rescanModelsNow(!0))
              }, {
                default: F(() => [...S[60] || (S[60] = [
                  I("Rescan", -1)
                ])]),
                _: 1
              })
            ])
          ]),
          m("ul", wy, [
            (D(!0), J(Ce, null, tt(g(t).models, (X, ke) => (D(), J("li", {
              key: ke,
              class: "cmst:rounded cmst:bg-cmst-bg cmst:px-2 cmst:py-1 cmst:text-xs"
            }, [
              I(K(String(X.filename || X.name || X.id || `model ${ke}`)) + " ", 1),
              m("span", _y, " · " + K(String(X.folder || X.type || "")), 1)
            ]))), 128))
          ]),
          m("div", xy, [
            Pe(m("input", {
              "onUpdate:modelValue": S[23] || (S[23] = (X) => C.value = X),
              class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              placeholder: "Paste a direct model link",
              "data-testid": "vue-model-url"
            }, null, 512), [
              [rt, C.value]
            ]),
            Pe(m("select", {
              "onUpdate:modelValue": S[24] || (S[24] = (X) => U.value = X),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
            }, [...S[61] || (S[61] = [
              m("option", { value: "diffusion_models" }, "diffusion_models", -1),
              m("option", { value: "vae" }, "vae", -1),
              m("option", { value: "clip" }, "clip", -1),
              m("option", { value: "loras" }, "loras", -1),
              m("option", { value: "upscale_models" }, "upscale_models", -1)
            ])], 512), [
              [os, U.value]
            ]),
            z(ee, {
              size: "sm",
              "data-testid": "vue-model-install",
              onClick: x
            }, {
              default: F(() => [...S[62] || (S[62] = [
                I("Install", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        _: 1
      })) : be("", !0),
      s.value === "nodes" ? (D(), Be(Ze, {
        key: 4,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          m("div", ky, [
            m("h3", Sy, "Custom nodes (" + K(g(t).customNodes.length) + ")", 1),
            z(ee, {
              size: "sm",
              variant: "outline",
              onClick: S[25] || (S[25] = (X) => g(t).refreshCustomNodesNow())
            }, {
              default: F(() => [...S[63] || (S[63] = [
                I("Refresh registry", -1)
              ])]),
              _: 1
            })
          ]),
          m("ul", Cy, [
            (D(!0), J(Ce, null, tt(g(t).customNodes, (X, ke) => (D(), J("li", {
              key: ke,
              class: "cmst:rounded cmst:bg-cmst-bg cmst:px-2 cmst:py-1 cmst:text-xs"
            }, K(String(X.title || X.id || X.name || `node ${ke}`)), 1))), 128))
          ])
        ]),
        _: 1
      })) : be("", !0)
    ], 2));
  }
});
function Iu(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return t.item ?? t.generation ?? t.experiment ?? e;
}
function Ye(e, ...t) {
  for (const s of t) if (typeof e[s] == "string") return e[s];
  return "";
}
function Ay(e, t) {
  const s = e && typeof e == "object" ? e : {}, n = Ye(s, "asset_id", "assetId"), r = () => `/comfymodal/history-v2/assets/${encodeURIComponent(n)}`;
  return {
    index: typeof s.index == "number" ? s.index : t,
    outputId: Ye(s, "output_id", "outputId"),
    assetId: n,
    logicalKey: Ye(s, "logical_key", "logicalKey"),
    thumbUrl: Ye(s, "thumb_url", "thumbnail_url") || r(),
    previewUrl: Ye(s, "preview_url", "data_saver_url") || r(),
    dataSaverUrl: Ye(s, "data_saver_url", "preview_url") || r(),
    originalUrl: Ye(s, "original_url") || r(),
    originalAvailable: s.original_available !== !1,
    width: typeof s.width == "number" ? s.width : null,
    height: typeof s.height == "number" ? s.height : null,
    filename: Ye(s, "filename", "name"),
    exportState: Ye(s, "export_state", "exportState") || "not_exported"
  };
}
function Ey(e, t) {
  const s = e && typeof e == "object" ? e : {};
  return {
    index: t,
    status: Ye(s, "status", "outcome") || "unknown",
    error: Ye(s, "error", "message") || null,
    ...s
  };
}
function Di(e) {
  return e.dataSaverUrl || e.thumbUrl || e.originalUrl;
}
function Ou(e) {
  return e.originalAvailable && e.originalUrl ? e.originalUrl : e.dataSaverUrl || e.originalUrl || e.thumbUrl;
}
function Tu(e) {
  return e.originalUrl || e.dataSaverUrl || e.thumbUrl;
}
function Iy(e, t) {
  const s = e.featured_output_index;
  if (typeof s == "number" && t[s]) return s;
  const n = e.featured_output;
  if (n && typeof n == "object") {
    const r = n.index;
    if (typeof r == "number" && t[r]) return r;
  }
  return 0;
}
function Pr(e) {
  const t = e && typeof e == "object" ? e : {}, n = (Array.isArray(t.outputs) ? t.outputs : []).map((c, u) => Ay(c, u)), r = Iy(t, n), o = Array.isArray(t.cells) ? t.cells : [], i = Array.isArray(t.cover) ? t.cover : [], a = Array.isArray(t.attempts) ? t.attempts : [], l = Array.isArray(t.errors) ? t.errors : [];
  return {
    id: Ye(t, "id", "generation_id", "experiment_id", "run_id"),
    kind: t.kind === "experiment" || t.experiment_id ? "experiment" : "generation",
    status: Ye(t, "status", "outcome") || "unknown",
    workflow: Ye(t, "workflow", "workflow_name"),
    workflowVersion: Ye(t, "workflow_version", "workflowVersion", "version_id"),
    preset: Ye(t, "preset", "preset_name"),
    prompt: Ye(t, "prompt", "positive_prompt"),
    startedAt: Ye(t, "started_at", "created_at") || null,
    completedAt: Ye(t, "completed_at", "finished_at") || null,
    durationMs: typeof t.duration_ms == "number" ? t.duration_ms : null,
    favorite: t.favorite === !0,
    note: Ye(t, "note"),
    outputs: n,
    featuredOutput: n[r] ?? n[0] ?? null,
    featuredOutputIndex: r,
    originalAvailable: t.original_available !== !1,
    replayCapable: t.replay_capable !== !1,
    replayReason: Ye(t, "replay_reason", "replayReason"),
    attempts: a.map((c, u) => Ey(c, u)),
    errors: l.filter((c) => !!c && typeof c == "object").map((c) => ({ code: Ye(c, "code") || "error", message: Ye(c, "message") || "Unknown error" })),
    params: t.params && typeof t.params == "object" ? t.params : {},
    timing: t.timing && typeof t.timing == "object" ? t.timing : {},
    cells: o.map((c) => Pr(c)),
    cover: i.map((c) => c ? Pr(c) : null),
    axisLabels: {
      x: Ye(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "x"),
      y: Ye(t.axis_labels && typeof t.axis_labels == "object" ? t.axis_labels : {}, "y")
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
async function Oy(e = {}) {
  const t = new URLSearchParams(), s = { limit: 24, ...e };
  s.sort !== void 0 && (s.order = s.sort, delete s.sort), s.favorite_only !== void 0 && (s.favorite = s.favorite_only, delete s.favorite_only);
  for (const [n, r] of Object.entries(s))
    r !== void 0 && String(r) !== "" && t.set(n, String(r));
  return se(`/history-v2/feed?${t}`);
}
async function Ty(e) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}`).then(Iu);
}
async function $y(e) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}`).then(Iu);
}
async function Py(e, t) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function Ny(e, t) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/favorite`, { method: "PATCH", body: { favorite: t } });
}
async function My(e, t) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function zy(e, t) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/note`, { method: "PATCH", body: { note: t } });
}
async function Dy(e, t) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/featured`, { method: "PATCH", body: { output_index: t } });
}
async function jy(e, t = {}) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/original`, { method: "POST", body: t });
}
async function Vy(e) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/original/retry`, { method: "POST" });
}
async function Ly(e) {
  return se(`/history-v2/generations/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function Uy(e) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/resume`, { method: "POST" });
}
async function Fy(e) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/cancel`, { method: "POST" });
}
async function Wy(e, t) {
  return se(`/history-v2/experiments/${encodeURIComponent(e)}/cells/${encodeURIComponent(t)}/retry`, { method: "POST" });
}
async function By(e, t) {
  return se("/history-v2/bulk-delete", { method: "POST", body: { generation_ids: e, experiment_ids: t } });
}
async function Gy(e) {
  return se(`/history-v2/assets/${encodeURIComponent(e)}/export`, { method: "POST" });
}
async function Hy(e) {
  return se(`/history-v2/assets/${encodeURIComponent(e)}/open`, { method: "POST" });
}
async function qy(e) {
  return se(`/history-v2/assets/${encodeURIComponent(e)}/reveal`, { method: "POST" });
}
function Zy(e) {
  const t = e.split(";")[0].trim().toLowerCase();
  return t === "image/png" ? "png" : t === "image/jpeg" ? "jpg" : t === "image/webp" ? "webp" : t === "image/gif" ? "gif" : t === "image/bmp" ? "bmp" : "png";
}
function Ky(e, t, s) {
  return `${[e.workflow || "generation", e.id, `output-${t.index}`].map((r) => r.replace(/[^a-zA-Z0-9-_]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48)).filter(Boolean).join("-") || "history-output"}.${s}`;
}
async function Jy(e, t, s = "original") {
  const n = s === "original" ? t.originalUrl : s === "dataSaver" ? t.dataSaverUrl : t.thumbUrl, r = await fetch(n);
  if (!r.ok) throw new Error(`Download failed with status ${r.status}`);
  const o = await r.blob(), i = Ky(e, t, Zy(o.type)), a = URL.createObjectURL(o);
  try {
    const l = document.createElement("a");
    l.href = a, l.download = i, document.body.appendChild(l), l.click(), l.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(a), 1e3);
  }
}
async function Qy(e) {
  const t = e.kind === "experiment" ? "experiments" : "generations";
  return se(`/history-v2/${t}/${encodeURIComponent(e.id)}`, { method: "DELETE" });
}
const qs = Qs("history.view.v2", { query: "", sort: "newest", favoriteOnly: !1, kind: "mixed", status: "" }), Qn = /* @__PURE__ */ mn("studio-history", () => {
  const e = /* @__PURE__ */ E([]), t = /* @__PURE__ */ E(null), s = /* @__PURE__ */ E(null), n = /* @__PURE__ */ E(qs.read().query), r = /* @__PURE__ */ E(qs.read().sort), o = /* @__PURE__ */ E(qs.read().favoriteOnly), i = /* @__PURE__ */ E(qs.read().kind), a = /* @__PURE__ */ E(qs.read().status), l = /* @__PURE__ */ E(null), c = /* @__PURE__ */ E(!1), u = /* @__PURE__ */ E(!1), f = /* @__PURE__ */ E(null), h = /* @__PURE__ */ E(null), d = /* @__PURE__ */ E(null), y = /* @__PURE__ */ E(null), C = /* @__PURE__ */ E(/* @__PURE__ */ new Set()), U = /* @__PURE__ */ E(!1), Q = /* @__PURE__ */ E(null), B = Gn(), Y = Gn();
  let q = !1, ae = null;
  const ye = Ve(() => e.value.find((_) => _.id === t.value) ?? null), re = Ve(() => e.value.find((_) => _.id === s.value) ?? ye.value), j = Ve(() => ({
    a: e.value.find((_) => _.id === d.value) ?? null,
    b: e.value.find((_) => _.id === y.value) ?? null
  })), H = Ve(() => [...C.value]);
  function x() {
    qs.write({ query: n.value, sort: r.value, favoriteOnly: o.value, kind: i.value, status: a.value });
  }
  function G(_) {
    s.value = _, _ && (t.value = _);
  }
  function S(_) {
    n.value = _, x();
  }
  function X(_) {
    r.value = _, x();
  }
  function ke(_) {
    o.value = _, x();
  }
  function xe(_) {
    i.value = _, x();
  }
  function b(_) {
    a.value = _, x();
  }
  function $(_) {
    const T = e.value.findIndex((N) => N.id === _.id && N.kind === _.kind);
    T >= 0 ? e.value[T] = _ : e.value.unshift(_);
  }
  function ve(_, T) {
    e.value = e.value.filter((N) => !(N.id === T && N.kind === _)), t.value === T && (t.value = null), s.value === T && (s.value = null), d.value === T && (d.value = null), y.value === T && (y.value = null), C.value.delete(`${_}:${T}`);
  }
  async function Fe(_ = !1) {
    u.value = !0, f.value = null;
    try {
      const T = await B.run(async (fe) => {
        const ne = await Oy({
          search: n.value,
          order: r.value,
          favorite: o.value ? !0 : void 0,
          kind: i.value === "mixed" ? void 0 : i.value,
          status: a.value || void 0,
          cursor: _ ? l.value ?? void 0 : void 0
        });
        return fe.aborted ? null : ne;
      });
      if (T.stale || !T.value) return;
      const N = T.value, V = (N.items ?? N.records ?? []).map(Pr);
      e.value = _ ? e.value.concat(V) : V, l.value = N.next_cursor ?? null, c.value = N.has_more === !0 || !!l.value;
    } catch (T) {
      throw f.value = T instanceof Error ? T.message : "Could not load History V2", T;
    } finally {
      u.value = !1, q && (q = !1, Fe());
    }
  }
  async function oe(_, T = "generation") {
    h.value = null;
    try {
      const N = await Y.run(async (V) => {
        const fe = T === "experiment" ? await $y(_) : await Ty(_);
        return V.aborted ? null : fe;
      });
      if (N.stale || !N.value) return;
      $(Pr(N.value)), t.value = _;
    } catch (N) {
      throw h.value = N instanceof Error ? N.message : "Could not load History detail", N;
    }
  }
  async function Xe(_) {
    if (G(_), !_) return;
    const T = e.value.find((N) => N.id === _);
    await oe(_, T?.kind ?? "generation");
  }
  async function Ke(_, T) {
    const N = _.favorite;
    _.favorite = T;
    try {
      _.kind === "experiment" ? await Ny(_.id, T) : await Py(_.id, T), He("history");
    } catch (V) {
      throw _.favorite = N, V;
    }
  }
  async function ft(_, T) {
    const N = _.note;
    _.note = T;
    try {
      _.kind === "experiment" ? await zy(_.id, T) : await My(_.id, T), He("history");
    } catch (V) {
      throw _.note = N, V;
    }
  }
  async function at(_, T) {
    await Dy(_.id, T), await oe(_.id, _.kind), He("history");
  }
  async function ze(_) {
    await Qy(_), ve(_.kind, _.id), He("history");
  }
  function Ne(_) {
    const T = `${_.kind}:${_.id}`, N = new Set(C.value);
    N.has(T) ? N.delete(T) : N.add(T), C.value = N;
  }
  function L() {
    C.value = /* @__PURE__ */ new Set();
  }
  async function A() {
    const _ = [], T = [];
    for (const N of C.value) {
      const V = N.indexOf(":"), fe = N.slice(0, V), ne = N.slice(V + 1);
      fe === "experiment" ? T.push(ne) : _.push(ne);
    }
    if (!(!_.length && !T.length)) {
      await By(_, T);
      for (const N of _) ve("generation", N);
      for (const N of T) ve("experiment", N);
      L(), He("history");
    }
  }
  async function O(_, T) {
    let N;
    return T === "original" ? N = await jy(_.id) : T === "retry" ? N = await Vy(_.id) : N = await Ly(_.id), Q.value = `${T} accepted for ${_.id}`, He("history"), N;
  }
  async function ie(_, T, N) {
    let V;
    return T === "resume" ? V = await Uy(_.id) : N ? V = await Wy(_.id, N) : V = await Fy(_.id), await oe(_.id, "experiment"), He("history"), V;
  }
  async function p(_) {
    const T = await Gy(_.assetId);
    return _.exportState = "exported", T;
  }
  function v(_, T) {
    _ === "a" ? d.value = T : y.value = T;
  }
  function k() {
    const _ = d.value;
    d.value = y.value, y.value = _;
  }
  function R() {
    d.value = null, y.value = null;
  }
  async function P() {
    ae || (ae = eo((_) => {
      if (_ === "history") {
        if (u.value) {
          q = !0;
          return;
        }
        Fe();
      }
    })), e.value.length || await Fe();
  }
  function W() {
    e.value = [], t.value = null, s.value = null, l.value = null, d.value = null, y.value = null, C.value = /* @__PURE__ */ new Set();
  }
  return {
    records: e,
    selected: ye,
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
    error: f,
    detailError: h,
    compareA: d,
    compareB: y,
    compareRecords: j,
    selection: H,
    viewerOpen: U,
    actionMessage: Q,
    setFocus: G,
    setQuery: S,
    setSort: X,
    setFavoriteOnly: ke,
    setKindFilter: xe,
    setStatusFilter: b,
    loadFeed: Fe,
    loadDetail: oe,
    applyRouteFocus: Xe,
    setFavorite: Ke,
    setNote: ft,
    setFeatured: at,
    remove: ze,
    toggleSelection: Ne,
    clearSelection: L,
    removeSelected: A,
    runReplayAction: O,
    runExperimentAction: ie,
    exportAsset: p,
    openHistoryAsset: Hy,
    revealHistoryAsset: qy,
    downloadHistoryAsset: Jy,
    selectCompare: v,
    swapCompare: k,
    clearCompare: R,
    selectFeedAsset: Di,
    selectDetailAsset: Ou,
    selectCompareAsset: Tu,
    initialize: P,
    clear: W
  };
}), Yy = ["aria-label", "data-testid"], Xy = ["src", "alt"], eb = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:p-3 cmst:text-sm" }, tb = { class: "cmst:min-w-0" }, sb = { class: "cmst:block cmst:truncate" }, nb = { class: "cmst:block cmst:truncate cmst:text-xs cmst:opacity-70" }, rb = ["aria-pressed", "aria-label", "data-testid"], ob = /* @__PURE__ */ St({
  __name: "ImageCard",
  props: {
    record: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t, n = Qn();
    async function r(o, i) {
      i.stopPropagation(), await n.setFavorite(o, !o.favorite).catch(() => {
      });
    }
    return (o, i) => (D(), Be(Ze, { class: "cmst:overflow-hidden" }, {
      default: F(() => [
        m("button", {
          type: "button",
          class: "cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:p-0 cmst:text-left",
          "aria-label": `Open ${e.record.workflow || e.record.id}`,
          "data-testid": `vue-history-card-${e.record.id}`,
          onClick: i[0] || (i[0] = (a) => s("select", e.record)),
          onKeydown: i[1] || (i[1] = rn((a) => s("select", e.record), ["enter"]))
        }, [
          e.record.featuredOutput ? (D(), J("img", {
            key: 0,
            src: g(Di)(e.record.featuredOutput),
            alt: e.record.workflow || e.record.id,
            class: "cmst:block cmst:aspect-square cmst:w-full cmst:object-cover",
            loading: "lazy"
          }, null, 8, Xy)) : be("", !0)
        ], 40, Yy),
        m("div", eb, [
          m("div", tb, [
            m("strong", sb, K(e.record.workflow || e.record.id), 1),
            m("span", nb, K(e.record.status) + " · " + K(e.record.kind), 1)
          ]),
          m("button", {
            type: "button",
            class: "cmst:shrink-0 cmst:rounded cmst:px-2 cmst:py-1 cmst:text-base",
            "aria-pressed": e.record.favorite ? "true" : "false",
            "aria-label": e.record.favorite ? `Remove ${e.record.id} from favorites` : `Add ${e.record.id} to favorites`,
            "data-testid": `vue-history-favorite-${e.record.id}`,
            onClick: i[2] || (i[2] = (a) => r(e.record, a))
          }, K(e.record.favorite ? "★" : "☆"), 9, rb)
        ])
      ]),
      _: 1
    }));
  }
}), ib = {
  class: "cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2 cmst:lg:grid-cols-3",
  "data-testid": "vue-history-grid"
}, ab = /* @__PURE__ */ St({
  __name: "ImageGrid",
  props: {
    records: {}
  },
  emits: ["select"],
  setup(e, { emit: t }) {
    const s = t;
    return (n, r) => (D(), J("div", ib, [
      (D(!0), J(Ce, null, tt(e.records, (o) => (D(), Be(ob, {
        key: `${o.kind}:${o.id}`,
        record: o,
        onSelect: r[0] || (r[0] = (i) => s("select", i))
      }, null, 8, ["record"]))), 128))
    ]));
  }
}), lb = ["aria-label", "onKeydown"], cb = { class: "cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4" }, ub = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, db = { class: "cmst:text-lg cmst:font-semibold" }, fb = { class: "cmst:text-xs cmst:opacity-70" }, mb = {
  key: 0,
  class: "cmst:mt-2 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, pb = {
  key: 1,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70",
  role: "status"
}, hb = ["src", "alt", "data-testid"], gb = {
  key: 3,
  class: "cmst:mt-4 cmst:text-sm cmst:opacity-70"
}, vb = {
  key: 4,
  class: "cmst:mt-3 cmst:text-sm cmst:text-red-300"
}, yb = { class: "cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, bb = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, wb = { class: "cmst:mt-2 cmst:flex cmst:items-center cmst:gap-2" }, _b = { class: "cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-xs" }, xb = ["data-testid"], kb = {
  key: 0,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, Sb = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, Cb = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:opacity-70"
}, Rb = { class: "cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1" }, Ab = {
  key: 1,
  class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm"
}, Eb = { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, Ib = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, Ob = ["data-testid"], Tb = { class: "cmst:mt-4 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, $b = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, Pb = { key: 0 }, Nb = {
  key: 1,
  class: "cmst:flex cmst:items-center cmst:gap-2"
}, Mb = { class: "cmst:text-xs" }, zb = /* @__PURE__ */ St({
  __name: "StudioViewer",
  props: {
    record: {}
  },
  emits: ["close"],
  setup(e, { emit: t }) {
    const s = e, n = t, r = Qn(), o = /* @__PURE__ */ E(s.record?.note ?? ""), i = /* @__PURE__ */ E(!1), a = /* @__PURE__ */ E(null), l = /* @__PURE__ */ E(null), c = /* @__PURE__ */ E(null);
    fs(() => {
      c.value = document.activeElement, o.value = s.record?.note ?? "", l.value?.focus();
    }), xi(() => {
      c.value?.focus?.();
    });
    async function u(h, d) {
      a.value = h;
      try {
        await d();
      } catch {
      } finally {
        a.value = null;
      }
    }
    function f() {
      n("close");
    }
    return (h, d) => e.record ? (D(), J("div", {
      key: 0,
      class: "cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6",
      "data-state": "open",
      "data-testid": "vue-history-viewer",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": `${e.record.kind} detail`,
      tabindex: "-1",
      onKeydown: rn(Ai(f, ["stop"]), ["esc"])
    }, [
      m("div", cb, [
        m("div", ub, [
          m("div", null, [
            m("h2", db, K(e.record.workflow || e.record.id), 1),
            m("p", fb, K(e.record.status) + " · " + K(e.record.kind) + " · " + K(e.record.id), 1)
          ]),
          z(ee, {
            ref_key: "closeBtn",
            ref: l,
            variant: "outline",
            size: "sm",
            "data-testid": "vue-viewer-close",
            onClick: f
          }, {
            default: F(() => [...d[13] || (d[13] = [
              I("Close", -1)
            ])]),
            _: 1
          }, 512)
        ]),
        g(r).detailError ? (D(), J("div", mb, K(g(r).detailError), 1)) : be("", !0),
        g(r).actionMessage ? (D(), J("p", pb, K(g(r).actionMessage), 1)) : be("", !0),
        e.record.featuredOutput ? (D(), J("img", {
          key: 2,
          src: g(Ou)(e.record.featuredOutput),
          alt: e.record.workflow || e.record.id,
          class: "cmst:mx-auto cmst:mt-4 cmst:max-h-[50vh] cmst:max-w-full cmst:object-contain",
          "data-testid": `vue-viewer-image-${e.record.id}`
        }, null, 8, hb)) : (D(), J("p", gb, "No projected image asset.")),
        e.record.errors.length ? (D(), J("div", vb, [
          (D(!0), J(Ce, null, tt(e.record.errors, (y, C) => (D(), J("p", { key: C }, K(y.code) + ": " + K(y.message), 1))), 128))
        ])) : be("", !0),
        m("div", yb, [
          m("div", bb, [
            d[16] || (d[16] = m("h3", { class: "cmst:font-semibold" }, "Annotations", -1)),
            m("div", wb, [
              z(ee, {
                size: "sm",
                variant: "outline",
                "aria-pressed": e.record.favorite ? "true" : "false",
                "data-testid": `vue-viewer-favorite-${e.record.id}`,
                onClick: d[0] || (d[0] = (y) => u("favorite", () => g(r).setFavorite(e.record, !e.record.favorite)))
              }, {
                default: F(() => [
                  I(K(e.record.favorite ? "★ Favorited" : "☆ Favorite"), 1)
                ]),
                _: 1
              }, 8, ["aria-pressed", "data-testid"])
            ]),
            m("label", _b, [
              d[14] || (d[14] = I(" Note ", -1)),
              Pe(m("textarea", {
                "onUpdate:modelValue": d[1] || (d[1] = (y) => o.value = y),
                rows: "2",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-sm",
                "data-testid": `vue-viewer-note-${e.record.id}`
              }, null, 8, xb), [
                [rt, o.value]
              ])
            ]),
            z(ee, {
              class: "cmst:mt-2",
              size: "sm",
              variant: "secondary",
              "data-testid": `vue-viewer-note-save-${e.record.id}`,
              onClick: d[2] || (d[2] = (y) => u("note", () => g(r).setNote(e.record, o.value)))
            }, {
              default: F(() => [...d[15] || (d[15] = [
                I("Save note", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          e.record.kind === "generation" ? (D(), J("div", kb, [
            d[25] || (d[25] = m("h3", { class: "cmst:font-semibold" }, "Replay", -1)),
            m("div", Sb, [
              z(ee, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || a.value !== null,
                "data-testid": `vue-viewer-original-${e.record.id}`,
                onClick: d[3] || (d[3] = (y) => u("original", () => g(r).runReplayAction(e.record, "original")))
              }, {
                default: F(() => [...d[17] || (d[17] = [
                  I("Generate Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              z(ee, {
                size: "sm",
                variant: "outline",
                disabled: !e.record.replayCapable || a.value !== null,
                "data-testid": `vue-viewer-retry-${e.record.id}`,
                onClick: d[4] || (d[4] = (y) => u("retry", () => g(r).runReplayAction(e.record, "retry")))
              }, {
                default: F(() => [...d[18] || (d[18] = [
                  I("Retry Original", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"]),
              z(ee, {
                size: "sm",
                variant: "outline",
                disabled: a.value !== null,
                "data-testid": `vue-viewer-resume-${e.record.id}`,
                onClick: d[5] || (d[5] = (y) => u("resume", () => g(r).runReplayAction(e.record, "resume")))
              }, {
                default: F(() => [...d[19] || (d[19] = [
                  I("Resume", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "data-testid"])
            ]),
            e.record.replayCapable ? be("", !0) : (D(), J("p", Cb, K(e.record.replayReason || "Not replay-capable."), 1)),
            d[26] || (d[26] = m("h3", { class: "cmst:mt-3 cmst:font-semibold" }, "Outputs", -1)),
            (D(!0), J(Ce, null, tt(e.record.outputs, (y) => (D(), J("div", {
              key: y.index,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs"
            }, [
              m("p", null, K(y.filename || `output ${y.index}`) + " · " + K(y.exportState), 1),
              m("div", Rb, [
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-download-${y.assetId}`,
                  onClick: (C) => u(`download-${y.index}`, () => g(r).downloadHistoryAsset(e.record, y, "original"))
                }, {
                  default: F(() => [...d[20] || (d[20] = [
                    I("Download", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-export-${y.assetId}`,
                  onClick: (C) => u(`export-${y.index}`, () => g(r).exportAsset(y))
                }, {
                  default: F(() => [...d[21] || (d[21] = [
                    I("Export", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"]),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (C) => u(`open-${y.index}`, () => g(r).openHistoryAsset(y.assetId))
                }, {
                  default: F(() => [...d[22] || (d[22] = [
                    I("Open", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  onClick: (C) => u(`reveal-${y.index}`, () => g(r).revealHistoryAsset(y.assetId))
                }, {
                  default: F(() => [...d[23] || (d[23] = [
                    I("Reveal", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"]),
                z(ee, {
                  size: "sm",
                  variant: "ghost",
                  "data-testid": `vue-featured-${y.index}`,
                  onClick: (C) => u("featured", () => g(r).setFeatured(e.record, y.index))
                }, {
                  default: F(() => [...d[24] || (d[24] = [
                    I("Feature", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid", "onClick"])
              ])
            ]))), 128))
          ])) : (D(), J("div", Ab, [
            d[30] || (d[30] = m("h3", { class: "cmst:font-semibold" }, "Experiment", -1)),
            m("p", Eb, "Cells: " + K(e.record.counts.cells) + " · Results: " + K(e.record.counts.results) + " · Failed: " + K(e.record.counts.failed), 1),
            m("div", Ib, [
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-resume-${e.record.id}`,
                onClick: d[6] || (d[6] = (y) => u("exp-resume", () => g(r).runExperimentAction(e.record, "resume")))
              }, {
                default: F(() => [...d[27] || (d[27] = [
                  I("Resume", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"]),
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": `vue-experiment-cancel-${e.record.id}`,
                onClick: d[7] || (d[7] = (y) => u("exp-cancel", () => g(r).runExperimentAction(e.record, "cancel")))
              }, {
                default: F(() => [...d[28] || (d[28] = [
                  I("Cancel", -1)
                ])]),
                _: 1
              }, 8, ["data-testid"])
            ]),
            (D(!0), J(Ce, null, tt(e.record.cells, (y) => (D(), J("div", {
              key: y.id,
              class: "cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs",
              "data-testid": `vue-cell-${y.id}`
            }, [
              m("p", null, K(y.id) + " · " + K(y.status), 1),
              y.status === "failed" ? (D(), Be(ee, {
                key: 0,
                class: "cmst:mt-1",
                size: "sm",
                variant: "ghost",
                "data-testid": `vue-cell-retry-${y.id}`,
                onClick: (C) => u(`cell-${y.id}`, () => g(r).runExperimentAction(e.record, "cancel", y.id))
              }, {
                default: F(() => [...d[29] || (d[29] = [
                  I("Retry cell", -1)
                ])]),
                _: 1
              }, 8, ["data-testid", "onClick"])) : be("", !0)
            ], 8, Ob))), 128))
          ]))
        ]),
        m("div", Tb, [
          m("div", $b, [
            z(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-a-${e.record.id}`,
              onClick: d[8] || (d[8] = (y) => g(r).selectCompare("a", e.record.id))
            }, {
              default: F(() => [...d[31] || (d[31] = [
                I("Compare A", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            z(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-compare-set-b-${e.record.id}`,
              onClick: d[9] || (d[9] = (y) => g(r).selectCompare("b", e.record.id))
            }, {
              default: F(() => [...d[32] || (d[32] = [
                I("Compare B", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]),
          i.value ? (D(), J("div", Nb, [
            m("span", Mb, "Delete this " + K(e.record.kind) + "?", 1),
            z(ee, {
              size: "sm",
              "data-testid": `vue-delete-confirm-${e.record.id}`,
              onClick: d[11] || (d[11] = (y) => u("delete", () => g(r).remove(e.record).then(f)))
            }, {
              default: F(() => [...d[34] || (d[34] = [
                I("Confirm delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"]),
            z(ee, {
              size: "sm",
              variant: "ghost",
              onClick: d[12] || (d[12] = (y) => i.value = !1)
            }, {
              default: F(() => [...d[35] || (d[35] = [
                I("Cancel", -1)
              ])]),
              _: 1
            })
          ])) : (D(), J("div", Pb, [
            z(ee, {
              size: "sm",
              variant: "outline",
              "data-testid": `vue-delete-${e.record.id}`,
              onClick: d[10] || (d[10] = (y) => i.value = !0)
            }, {
              default: F(() => [...d[33] || (d[33] = [
                I("Delete", -1)
              ])]),
              _: 1
            }, 8, ["data-testid"])
          ]))
        ])
      ])
    ], 40, lb)) : be("", !0);
  }
});
function Db() {
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
const jb = { class: "cmst:flex cmst:items-center cmst:justify-between cmst:gap-2" }, Vb = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70",
  "data-testid": "vue-picker-empty"
}, Lb = {
  key: 1,
  class: "cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:sm:grid-cols-3"
}, Ub = ["data-testid", "aria-label", "onClick"], Fb = ["src", "alt"], Wb = { class: "cmst:mt-1 cmst:block cmst:truncate cmst:text-xs" }, Bb = { class: "cmst:mt-3 cmst:flex cmst:justify-center" }, Gb = /* @__PURE__ */ St({
  __name: "HistoryPicker",
  emits: ["select", "cancel"],
  setup(e, { emit: t }) {
    const s = Qn(), n = /* @__PURE__ */ E(""), r = /* @__PURE__ */ E(null);
    fs(async () => {
      r.value = Db(), await s.initialize();
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
    return (c, u) => (D(), Be(Ad, {
      to: r.value ?? void 0
    }, [
      m("div", {
        class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
        "data-state": "open",
        "data-testid": "vue-history-picker",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": "Pick a History generation",
        tabindex: "-1",
        onKeydown: u[4] || (u[4] = rn(Ai((f) => o("cancel"), ["stop"]), ["esc"]))
      }, [
        z(Ze, { class: "cmst:w-[min(48rem,94vw)] cmst:max-h-[86vh] cmst:overflow-auto cmst:p-4" }, {
          default: F(() => [
            m("div", jb, [
              u[6] || (u[6] = m("h2", { class: "cmst:text-base cmst:font-semibold" }, "Pick from History", -1)),
              z(ee, {
                variant: "ghost",
                size: "sm",
                "data-testid": "vue-picker-cancel",
                onClick: u[0] || (u[0] = (f) => o("cancel"))
              }, {
                default: F(() => [...u[5] || (u[5] = [
                  I("Cancel", -1)
                ])]),
                _: 1
              })
            ]),
            Pe(m("input", {
              "onUpdate:modelValue": u[1] || (u[1] = (f) => n.value = f),
              class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              placeholder: "Search generations",
              "aria-label": "Search generations",
              onInput: u[2] || (u[2] = (f) => a(f.target.value))
            }, null, 544), [
              [rt, n.value]
            ]),
            g(s).records.length ? (D(), J("div", Lb, [
              (D(!0), J(Ce, null, tt(g(s).records, (f) => (D(), J("button", {
                key: `${f.kind}:${f.id}`,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-picker-option-${f.id}`,
                "aria-label": `Select ${f.workflow || f.id}`,
                onClick: (h) => l(f)
              }, [
                f.featuredOutput ? (D(), J("img", {
                  key: 0,
                  src: g(Di)(f.featuredOutput),
                  alt: f.workflow || f.id,
                  class: "cmst:aspect-square cmst:w-full cmst:object-cover cmst:rounded",
                  loading: "lazy"
                }, null, 8, Fb)) : be("", !0),
                m("span", Wb, K(f.workflow || f.id), 1)
              ], 8, Ub))), 128))
            ])) : (D(), J("div", Vb, "No generations match.")),
            m("div", Bb, [
              g(s).hasMore ? (D(), Be(ee, {
                key: 0,
                variant: "outline",
                size: "sm",
                onClick: u[3] || (u[3] = (f) => g(s).loadFeed(!0))
              }, {
                default: F(() => [...u[7] || (u[7] = [
                  I("Load more", -1)
                ])]),
                _: 1
              })) : be("", !0)
            ])
          ]),
          _: 1
        })
      ], 32)
    ], 8, ["to"]));
  }
}), Hb = { class: "cmst:flex cmst:items-center cmst:justify-between" }, qb = { class: "cmst:flex cmst:gap-2" }, Zb = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-3" }, Kb = ["src", "alt", "data-testid"], Jb = {
  key: 1,
  class: "cmst:text-xs cmst:opacity-60"
}, Qb = /* @__PURE__ */ St({
  __name: "CompareViewer",
  setup(e) {
    const t = Qn(), s = Ve(() => t.compareRecords);
    function n(r, o) {
      const a = t.records.find((l) => l.id === r)?.featuredOutput;
      return a ? o === "original" ? Tu(a) : a.dataSaverUrl || a.thumbUrl : null;
    }
    return (r, o) => s.value.a || s.value.b ? (D(), Be(Ze, {
      key: 0,
      class: "cmst:p-4",
      "data-testid": "vue-compare"
    }, {
      default: F(() => [
        m("div", Hb, [
          o[4] || (o[4] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Compare (transient — never persisted)", -1)),
          m("div", qb, [
            z(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-swap",
              onClick: o[0] || (o[0] = (i) => g(t).swapCompare())
            }, {
              default: F(() => [...o[2] || (o[2] = [
                I("Switch A/B", -1)
              ])]),
              _: 1
            }),
            z(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-compare-clear",
              onClick: o[1] || (o[1] = (i) => g(t).clearCompare())
            }, {
              default: F(() => [...o[3] || (o[3] = [
                I("Clear", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        m("div", Zb, [
          (D(), J(Ce, null, tt(["a", "b"], (i) => m("figure", { key: i }, [
            n(i === "a" ? g(t).compareA : g(t).compareB, "original") ? (D(), J("img", {
              key: 0,
              src: n(i === "a" ? g(t).compareA : g(t).compareB, "original"),
              alt: `Compare ${i.toUpperCase()}`,
              class: "cmst:w-full cmst:rounded cmst:object-contain",
              "data-testid": `vue-compare-${i}`
            }, null, 8, Kb)) : (D(), J("figcaption", Jb, "Slot " + K(i.toUpperCase()) + " empty or deleted.", 1))
          ])), 64))
        ])
      ]),
      _: 1
    })) : be("", !0);
  }
}), Yb = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Xb = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, ew = { class: "cmst:flex cmst:gap-2" }, tw = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, sw = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, nw = ["value"], rw = ["value"], ow = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, iw = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, aw = { class: "cmst:flex cmst:items-center cmst:justify-between" }, lw = { class: "cmst:text-xs cmst:opacity-70" }, cw = { class: "cmst:flex cmst:gap-2" }, uw = { class: "cmst:flex cmst:justify-center" }, dw = { class: "cmst:flex cmst:flex-wrap cmst:gap-2" }, fw = /* @__PURE__ */ St({
  __name: "HistoryView",
  setup(e) {
    const t = Qn(), s = Kc(), n = hp(), r = /* @__PURE__ */ E(t.query), o = /* @__PURE__ */ E(!1);
    function i() {
      const h = s.query.focus;
      return typeof h == "string" && h !== "" ? h : null;
    }
    fs(async () => {
      await t.initialize(), await t.applyRouteFocus(i());
    }), ks(
      () => s.query.focus,
      (h) => {
        t.applyRouteFocus(typeof h == "string" ? h : null);
      }
    );
    let a;
    ks(r, (h) => {
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
    function u(h, d) {
      d.stopPropagation(), t.toggleSelection(h);
    }
    function f(h) {
      o.value = !1, l(h);
    }
    return (h, d) => (D(), J("section", {
      class: xt(g(Jn)()),
      "data-testid": "vue-page-history"
    }, [
      z(Ze, { class: "cmst:p-4" }, {
        default: F(() => [
          m("div", Yb, [
            m("div", null, [
              m("h2", Xb, [
                z(g(Qc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                d[15] || (d[15] = I("History V2", -1))
              ]),
              d[16] || (d[16] = m("p", { class: "cmst:text-sm cmst:opacity-80" }, "Server cursor stays authoritative; stale reads never commit.", -1))
            ]),
            m("div", ew, [
              z(ee, {
                variant: "outline",
                size: "sm",
                "data-testid": "vue-history-picker-open",
                onClick: d[0] || (d[0] = (y) => o.value = !0)
              }, {
                default: F(() => [...d[17] || (d[17] = [
                  I("Pick generation", -1)
                ])]),
                _: 1
              }),
              z(ee, {
                variant: "outline",
                size: "icon",
                "aria-label": "Refresh history",
                disabled: g(t).loading,
                onClick: d[1] || (d[1] = (y) => g(t).loadFeed())
              }, {
                default: F(() => [
                  z(g(Xr), {
                    class: xt(["cmst:size-4", g(t).loading ? "cmst:animate-spin" : ""])
                  }, null, 8, ["class"])
                ]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          m("div", tw, [
            m("label", sw, [
              z(g(Pp), {
                class: "cmst:size-4",
                "aria-hidden": "true"
              }),
              Pe(m("input", {
                "onUpdate:modelValue": d[2] || (d[2] = (y) => r.value = y),
                class: "cmst:h-9 cmst:w-56 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search history",
                "aria-label": "Search history",
                "data-testid": "vue-history-search"
              }, null, 512), [
                [rt, r.value]
              ])
            ]),
            m("select", {
              value: g(t).kindFilter,
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              "aria-label": "Record kind",
              onChange: d[3] || (d[3] = (y) => {
                g(t).setKindFilter(y.target.value), g(t).loadFeed();
              })
            }, [...d[18] || (d[18] = [
              m("option", { value: "mixed" }, "All kinds", -1),
              m("option", { value: "generation" }, "Generations", -1),
              m("option", { value: "experiment" }, "Experiments", -1)
            ])], 40, nw),
            m("select", {
              value: g(t).statusFilter,
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              "aria-label": "Status filter",
              onChange: d[4] || (d[4] = (y) => {
                g(t).setStatusFilter(y.target.value), g(t).loadFeed();
              })
            }, [...d[19] || (d[19] = [
              m("option", { value: "" }, "All statuses", -1),
              m("option", { value: "completed" }, "Completed", -1),
              m("option", { value: "failed" }, "Failed", -1),
              m("option", { value: "running" }, "Running", -1),
              m("option", { value: "canceled" }, "Canceled", -1)
            ])], 40, rw),
            Pe(m("select", {
              "onUpdate:modelValue": d[5] || (d[5] = (y) => g(t).sort = y),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
              "aria-label": "Sort order",
              onChange: d[6] || (d[6] = (y) => {
                g(t).setSort(g(t).sort), g(t).loadFeed();
              })
            }, [...d[20] || (d[20] = [
              m("option", { value: "newest" }, "Newest", -1),
              m("option", { value: "oldest" }, "Oldest", -1),
              m("option", { value: "fastest" }, "Fastest", -1),
              m("option", { value: "slowest" }, "Slowest", -1)
            ])], 544), [
              [os, g(t).sort]
            ]),
            m("label", ow, [
              Pe(m("input", {
                "onUpdate:modelValue": d[7] || (d[7] = (y) => g(t).favoriteOnly = y),
                type: "checkbox",
                onChange: d[8] || (d[8] = (y) => {
                  g(t).setFavoriteOnly(g(t).favoriteOnly), g(t).loadFeed();
                })
              }, null, 544), [
                [en, g(t).favoriteOnly]
              ]),
              d[21] || (d[21] = I(" Favorites", -1))
            ])
          ])
        ]),
        _: 1
      }),
      g(t).error ? (D(), J("div", iw, [
        I(K(g(t).error) + " ", 1),
        z(ee, {
          class: "cmst:ml-2",
          size: "sm",
          variant: "outline",
          onClick: d[9] || (d[9] = (y) => g(t).loadFeed())
        }, {
          default: F(() => [...d[22] || (d[22] = [
            I("Retry", -1)
          ])]),
          _: 1
        })
      ])) : be("", !0),
      g(t).loading && !g(t).records.length ? (D(), Be(Ze, {
        key: 1,
        class: "cmst:p-6 cmst:text-sm"
      }, {
        default: F(() => [...d[23] || (d[23] = [
          I("Loading History V2…", -1)
        ])]),
        _: 1
      })) : g(t).records.length ? (D(), J(Ce, { key: 3 }, [
        m("div", aw, [
          m("p", lw, K(g(t).records.length) + " records · " + K(g(t).selection.length) + " selected", 1),
          m("div", cw, [
            g(t).selection.length ? (D(), Be(ee, {
              key: 0,
              size: "sm",
              variant: "outline",
              "data-testid": "vue-history-bulk-delete",
              onClick: d[11] || (d[11] = (y) => g(t).removeSelected())
            }, {
              default: F(() => [
                I("Delete selected (" + K(g(t).selection.length) + ")", 1)
              ]),
              _: 1
            })) : be("", !0),
            g(t).selection.length ? (D(), Be(ee, {
              key: 1,
              size: "sm",
              variant: "ghost",
              onClick: d[12] || (d[12] = (y) => g(t).clearSelection())
            }, {
              default: F(() => [...d[26] || (d[26] = [
                I("Clear selection", -1)
              ])]),
              _: 1
            })) : be("", !0)
          ])
        ]),
        z(ab, {
          records: g(t).records,
          onSelect: l
        }, null, 8, ["records"]),
        m("div", uw, [
          g(t).hasMore ? (D(), Be(ee, {
            key: 0,
            variant: "outline",
            onClick: d[13] || (d[13] = (y) => g(t).loadFeed(!0))
          }, {
            default: F(() => [...d[27] || (d[27] = [
              I("Load more", -1)
            ])]),
            _: 1
          })) : be("", !0)
        ]),
        m("div", dw, [
          (D(!0), J(Ce, null, tt(g(t).records.slice(0, 6), (y) => (D(), Be(ee, {
            key: `bulk-${y.kind}-${y.id}`,
            size: "sm",
            variant: g(t).selection.includes(`${y.kind}:${y.id}`) ? "default" : "ghost",
            "data-testid": `vue-history-select-${y.id}`,
            onClick: (C) => u(y, C)
          }, {
            default: F(() => [
              I(K(g(t).selection.includes(`${y.kind}:${y.id}`) ? "✓" : "+") + " " + K(y.id.slice(0, 12)), 1)
            ]),
            _: 2
          }, 1032, ["variant", "data-testid", "onClick"]))), 128))
        ])
      ], 64)) : (D(), Be(Ze, {
        key: 2,
        class: "cmst:p-6 cmst:text-sm cmst:opacity-75",
        "data-testid": "vue-history-empty"
      }, {
        default: F(() => [
          d[25] || (d[25] = I(" No History V2 records match this query. ", -1)),
          z(ee, {
            class: "cmst:ml-2",
            size: "sm",
            variant: "outline",
            onClick: d[10] || (d[10] = (y) => {
              g(t).setQuery(""), r.value = "", g(t).setStatusFilter(""), g(t).setKindFilter("mixed"), g(t).loadFeed();
            })
          }, {
            default: F(() => [...d[24] || (d[24] = [
              I("Clear filters", -1)
            ])]),
            _: 1
          })
        ]),
        _: 1
      })),
      z(Qb),
      g(t).viewerOpen ? (D(), Be(zb, {
        key: 4,
        record: g(t).selected,
        onClose: c
      }, null, 8, ["record"])) : be("", !0),
      o.value ? (D(), Be(Gb, {
        key: 5,
        onSelect: f,
        onCancel: d[14] || (d[14] = (y) => o.value = !1)
      })) : be("", !0)
    ], 2));
  }
}), mw = /* @__PURE__ */ mn("studio-playground", () => {
  const e = /* @__PURE__ */ E("txt2img"), t = /* @__PURE__ */ E(!1);
  function s(r) {
    e.value = r;
  }
  function n(r) {
    t.value = r;
  }
  return { featureId: e, experimentMode: t, setFeature: s, setExperimentMode: n };
}), pw = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, hw = { class: "cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3" }, gw = ["checked"], vw = { class: "cmst:text-sm cmst:opacity-80" }, yw = { class: "cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3" }, bw = {
  key: 0,
  class: "cmst:text-sm",
  "data-testid": "vue-op-progress"
}, ww = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, _w = { key: 0 }, xw = /* @__PURE__ */ St({
  __name: "PlaygroundView",
  setup(e) {
    const t = mw(), s = It(), n = /* @__PURE__ */ E(null), r = Ve(() => n.value ? s.get(n.value)?.progress ?? null : null);
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
    return (i, a) => (D(), J("section", {
      class: xt(g(Jn)()),
      "data-testid": "vue-page-playground"
    }, [
      z(Ze, { class: "cmst:p-4" }, {
        default: F(() => [
          m("h2", pw, [
            z(g(Jc), {
              class: "cmst:size-5",
              "aria-hidden": "true"
            }),
            a[1] || (a[1] = I(" Playground (Phase-1 proof) ", -1))
          ]),
          a[3] || (a[3] = m("p", { class: "cmst:text-sm cmst:opacity-80" }, " Product functionality is intentionally not ported yet. This view proves store ownership and the operation registry. ", -1)),
          m("label", hw, [
            m("input", {
              type: "checkbox",
              checked: g(t).experimentMode,
              onChange: a[0] || (a[0] = (l) => g(t).setExperimentMode(l.target.checked))
            }, null, 40, gw),
            a[2] || (a[2] = I(" Experiment mode (playground store) ", -1))
          ])
        ]),
        _: 1
      }),
      z(Ze, { class: "cmst:p-4" }, {
        default: F(() => [
          a[5] || (a[5] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "operationStore demo", -1)),
          m("p", vw, " A synthetic local operation publishes presentation state into the shared registry. Active operations: " + K(g(s).active.length) + ". ", 1),
          m("div", yw, [
            z(ee, {
              variant: "default",
              size: "sm",
              disabled: n.value !== null,
              onClick: o
            }, {
              default: F(() => [
                z(g(Ip), { "aria-hidden": "true" }),
                a[4] || (a[4] = I(" Run synthetic operation ", -1))
              ]),
              _: 1
            }, 8, ["disabled"]),
            r.value !== null ? (D(), J("span", bw, K(Math.round((r.value ?? 0) * 100)) + "% ", 1)) : be("", !0)
          ]),
          m("ul", ww, [
            (D(!0), J(Ce, null, tt(g(s).all.slice(-5), (l) => (D(), J("li", {
              key: l.id,
              "data-testid": "vue-op-row"
            }, [
              m("strong", null, K(l.label), 1),
              I(" — " + K(l.status), 1),
              l.message ? (D(), J("span", _w, " — " + K(l.message), 1)) : be("", !0)
            ]))), 128))
          ])
        ]),
        _: 1
      })
    ], 2));
  }
}), kw = {
  key: 0,
  class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300",
  role: "alert"
}, Sw = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, Cw = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Rw = {
  "aria-label": "Settings sections",
  class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-1"
}, Aw = ["aria-current", "data-testid", "onClick"], Ew = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Iw = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Ow = ["value"], Tw = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, $w = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Pw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Nw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Mw = ["value"], zw = ["value"], Dw = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70"
}, jw = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Vw = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2" }, Lw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Uw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Fw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Ww = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Bw = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-4 cmst:text-sm" }, Gw = { class: "cmst:flex cmst:items-center cmst:gap-2" }, Hw = { class: "cmst:flex cmst:items-center cmst:gap-2" }, qw = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, Zw = ["aria-pressed", "data-testid", "onClick"], Kw = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:opacity-70"
}, Jw = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Qw = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, Yw = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, Xw = ["value"], e_ = ["value"], t_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, s_ = ["value"], n_ = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, r_ = ["value"], o_ = { class: "cmst:flex cmst:items-center cmst:justify-between" }, i_ = { class: "cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, a_ = { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, l_ = {
  key: 0,
  "data-testid": "vue-settings-restart-banner"
}, c_ = { class: "cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm" }, u_ = { class: "cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" }, d_ = /* @__PURE__ */ St({
  __name: "SettingsView",
  setup(e) {
    const t = uu(), s = /* @__PURE__ */ E(75), n = /* @__PURE__ */ E(""), r = /* @__PURE__ */ E("original"), o = /* @__PURE__ */ E("balanced"), i = /* @__PURE__ */ E(!1), a = /* @__PURE__ */ E(!0), l = /* @__PURE__ */ E("off"), c = /* @__PURE__ */ E(70), u = /* @__PURE__ */ E("off"), f = /* @__PURE__ */ E(""), h = /* @__PURE__ */ E(!1), d = /* @__PURE__ */ E(!1), y = Ve(() => t.config), C = Ve(() => y.value?.available_gpus ?? []);
    function U() {
      const H = y.value;
      H && (s.value = H.quality, n.value = H.save_folder, r.value = H.output_format, o.value = H.webp_lossless_compression, i.value = H.auto_save_local, a.value = H.save_metadata_sidecar, l.value = H.data_saver_default, c.value = H.data_saver_quality, u.value = t.profileLevel, f.value = H.gpu, h.value = H.skip_plan_validation);
    }
    fs(async () => {
      await t.initialize().catch(() => {
      }), await t.loadGolden().catch(() => {
      }), U();
    });
    async function Q() {
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
      }), U();
    }
    async function B() {
      await t.save({ gpu: f.value }).catch(() => {
      }), U();
    }
    async function Y() {
      await t.save({
        data_saver_default: l.value,
        data_saver_quality: Number(c.value)
      }).catch(() => {
      }), U();
    }
    async function q() {
      await t.setSkipPlanValidation(h.value).catch(() => {
      }), U();
    }
    async function ae() {
      await t.setProfile(u.value).catch(() => {
      }), U();
    }
    async function ye(H) {
      await t.resetSection(H), U();
    }
    async function re() {
      if (!d.value) {
        d.value = !0;
        return;
      }
      d.value = !1, await t.resetAll(), U();
    }
    function j(H) {
      return "cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:border cmst:border-solid " + (t.activeSection === H ? "cmst:bg-cmst-secondary cmst:text-cmst-fg cmst:border-cmst-border" : "cmst:bg-transparent cmst:text-cmst-muted cmst:border-transparent cmst:hover:bg-cmst-secondary");
    }
    return (H, x) => (D(), J("section", {
      class: xt(g(Jn)()),
      "data-testid": "vue-page-settings"
    }, [
      g(t).error ? (D(), J("div", kw, K(g(t).error), 1)) : be("", !0),
      z(Ze, { class: "cmst:p-4" }, {
        default: F(() => [
          m("div", Sw, [
            m("div", null, [
              m("h2", Cw, [
                z(g(Xc), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                x[20] || (x[20] = I(" Settings ", -1))
              ]),
              x[21] || (x[21] = m("p", { class: "cmst:text-sm cmst:opacity-80" }, "Server-backed authority. Failed saves revert to server truth.", -1))
            ]),
            z(ee, {
              variant: "outline",
              size: "icon",
              "aria-label": "Reload settings",
              disabled: g(t).loading,
              onClick: x[0] || (x[0] = (G) => g(t).load().then(U).catch(() => {
              }))
            }, {
              default: F(() => [
                z(g(Xr), {
                  class: xt(["cmst:size-4", g(t).loading ? "cmst:animate-spin" : ""]),
                  "aria-hidden": "true"
                }, null, 8, ["class"])
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          m("nav", Rw, [
            (D(!0), J(Ce, null, tt(g(cu), (G) => (D(), J("button", {
              key: G,
              type: "button",
              class: xt(j(G)),
              "aria-current": g(t).activeSection === G ? "true" : void 0,
              "data-testid": `vue-settings-tab-${G}`,
              onClick: (S) => g(t).setSection(G)
            }, K(G), 11, Aw))), 128))
          ])
        ]),
        _: 1
      }),
      g(t).activeSection === "generation" ? (D(), Be(Ze, {
        key: 1,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          m("div", Ew, [
            x[23] || (x[23] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Generation", -1)),
            z(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-settings-reset-generation",
              onClick: x[1] || (x[1] = (G) => ye("generation"))
            }, {
              default: F(() => [...x[22] || (x[22] = [
                I("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          m("label", Iw, [
            x[24] || (x[24] = I(" GPU ", -1)),
            Pe(m("select", {
              "onUpdate:modelValue": x[2] || (x[2] = (G) => f.value = G),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              "data-testid": "vue-settings-gpu",
              onChange: B
            }, [
              (D(!0), J(Ce, null, tt(C.value, (G) => (D(), J("option", {
                key: G.value,
                value: G.value
              }, K(G.label), 9, Ow))), 128))
            ], 544), [
              [os, f.value]
            ])
          ]),
          m("div", Tw, [
            m("label", $w, [
              x[26] || (x[26] = I(" Data Saver default ", -1)),
              Pe(m("select", {
                "onUpdate:modelValue": x[3] || (x[3] = (G) => l.value = G),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: Y
              }, [...x[25] || (x[25] = [
                m("option", { value: "off" }, "Off", -1),
                m("option", { value: "on" }, "On", -1)
              ])], 544), [
                [os, l.value]
              ])
            ]),
            m("label", Pw, [
              x[27] || (x[27] = I(" Data Saver quality ", -1)),
              Pe(m("input", {
                "onUpdate:modelValue": x[4] || (x[4] = (G) => c.value = G),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: Y
              }, null, 544), [
                [
                  rt,
                  c.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            m("div", Nw, [
              x[29] || (x[29] = I(" Golden profile ", -1)),
              m("select", {
                value: g(t).selectedGoldenProfile,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-settings-golden-profile",
                onChange: x[5] || (x[5] = (G) => g(t).selectGoldenProfile(G.target.value))
              }, [
                x[28] || (x[28] = m("option", { value: "" }, "None", -1)),
                (D(!0), J(Ce, null, tt(g(t).goldenProfiles, (G) => (D(), J("option", {
                  key: G.name,
                  value: G.name
                }, K(G.name), 9, zw))), 128))
              ], 40, Mw)
            ])
          ]),
          y.value?.engine_migration_notice ? (D(), J("p", Dw, K(y.value.engine_migration_notice), 1)) : be("", !0)
        ]),
        _: 1
      })) : be("", !0),
      g(t).activeSection === "outputs" ? (D(), Be(Ze, {
        key: 2,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          m("div", jw, [
            x[31] || (x[31] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Outputs", -1)),
            z(ee, {
              variant: "ghost",
              size: "sm",
              "data-testid": "vue-settings-reset-outputs",
              onClick: x[6] || (x[6] = (G) => ye("outputs"))
            }, {
              default: F(() => [...x[30] || (x[30] = [
                I("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          m("div", Vw, [
            m("label", Lw, [
              x[33] || (x[33] = I(" Output format ", -1)),
              Pe(m("select", {
                "onUpdate:modelValue": x[7] || (x[7] = (G) => r.value = G),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, [...x[32] || (x[32] = [
                m("option", { value: "original" }, "Original", -1),
                m("option", { value: "png" }, "PNG", -1),
                m("option", { value: "jpeg" }, "JPEG", -1),
                m("option", { value: "webp" }, "WebP", -1)
              ])], 512), [
                [os, r.value]
              ])
            ]),
            m("label", Uw, [
              x[34] || (x[34] = I(" Quality ", -1)),
              Pe(m("input", {
                "onUpdate:modelValue": x[8] || (x[8] = (G) => s.value = G),
                type: "number",
                min: "1",
                max: "100",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [
                  rt,
                  s.value,
                  void 0,
                  { number: !0 }
                ]
              ])
            ]),
            m("label", Fw, [
              x[36] || (x[36] = I(" WebP lossless compression ", -1)),
              Pe(m("select", {
                "onUpdate:modelValue": x[9] || (x[9] = (G) => o.value = G),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, [...x[35] || (x[35] = [
                m("option", { value: "balanced" }, "Balanced", -1),
                m("option", { value: "fast" }, "Fast", -1),
                m("option", { value: "best" }, "Best", -1)
              ])], 512), [
                [os, o.value]
              ])
            ]),
            m("label", Ww, [
              x[37] || (x[37] = I(" Save folder ", -1)),
              Pe(m("input", {
                "onUpdate:modelValue": x[10] || (x[10] = (G) => n.value = G),
                type: "text",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
              }, null, 512), [
                [rt, n.value]
              ])
            ])
          ]),
          m("div", Bw, [
            m("label", Gw, [
              Pe(m("input", {
                "onUpdate:modelValue": x[11] || (x[11] = (G) => i.value = G),
                type: "checkbox"
              }, null, 512), [
                [en, i.value]
              ]),
              x[38] || (x[38] = I(" Auto-save local ", -1))
            ]),
            m("label", Hw, [
              Pe(m("input", {
                "onUpdate:modelValue": x[12] || (x[12] = (G) => a.value = G),
                type: "checkbox"
              }, null, 512), [
                [en, a.value]
              ]),
              x[39] || (x[39] = I(" Save metadata sidecar ", -1))
            ]),
            z(ee, {
              size: "sm",
              disabled: g(t).saving,
              "data-testid": "vue-settings-save-output",
              onClick: Q
            }, {
              default: F(() => [
                I(K(g(t).saving ? "Saving…" : "Save outputs"), 1)
              ]),
              _: 1
            }, 8, ["disabled"])
          ])
        ]),
        _: 1
      })) : be("", !0),
      g(t).activeSection === "accounts" ? (D(), Be(Ze, {
        key: 3,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          x[40] || (x[40] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Accounts & Tokens", -1)),
          x[41] || (x[41] = m("p", { class: "cmst:mt-1 cmst:text-sm cmst:opacity-80" }, "Credential status lives in Manage Modal. Golden favorites are a browser-only preference here.", -1)),
          m("div", qw, [
            (D(!0), J(Ce, null, tt(g(t).goldenProfiles, (G) => (D(), J("button", {
              key: G.name,
              type: "button",
              class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:px-3 cmst:py-1 cmst:text-sm",
              "aria-pressed": g(t).favoriteGoldenProfiles.includes(G.name) ? "true" : "false",
              "data-testid": `vue-golden-favorite-${G.name}`,
              onClick: (S) => g(t).toggleGoldenFavorite(G.name)
            }, K(g(t).favoriteGoldenProfiles.includes(G.name) ? "★" : "☆") + " " + K(G.name), 9, Zw))), 128))
          ]),
          g(t).goldenProfiles.length ? be("", !0) : (D(), J("p", Kw, "Golden catalog not loaded yet."))
        ]),
        _: 1
      })) : be("", !0),
      g(t).activeSection === "interface" ? (D(), Be(Ze, {
        key: 4,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          m("div", Jw, [
            x[43] || (x[43] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Interface", -1)),
            z(ee, {
              variant: "ghost",
              size: "sm",
              onClick: x[13] || (x[13] = (G) => ye("interface"))
            }, {
              default: F(() => [...x[42] || (x[42] = [
                I("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          m("div", Qw, [
            m("label", Yw, [
              x[44] || (x[44] = I(" History grid columns ", -1)),
              m("select", {
                value: g(t).columnsPreference,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: x[14] || (x[14] = (G) => g(t).setHistoryColumns(G.target.value))
              }, [
                (D(), J(Ce, null, tt([2, 3, 4, 5, 6, 7, 8], (G) => m("option", {
                  key: G,
                  value: String(G)
                }, K(G), 9, e_)), 64))
              ], 40, Xw)
            ]),
            m("label", t_, [
              x[46] || (x[46] = I(" Remote inventory refresh ", -1)),
              m("select", {
                value: g(t).refreshIntervalPreference,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                onChange: x[15] || (x[15] = (G) => g(t).setInventoryInterval(G.target.value))
              }, [...x[45] || (x[45] = [
                m("option", { value: "0" }, "Off", -1),
                m("option", { value: "60" }, "1 minute", -1),
                m("option", { value: "300" }, "5 minutes", -1),
                m("option", { value: "900" }, "15 minutes", -1),
                m("option", { value: "1800" }, "30 minutes", -1)
              ])], 40, s_)
            ]),
            m("label", n_, [
              x[48] || (x[48] = I(" Shell density ", -1)),
              m("select", {
                value: g(t).density,
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                "data-testid": "vue-density-toggle",
                onChange: x[16] || (x[16] = (G) => g(t).setDensity(G.target.value))
              }, [...x[47] || (x[47] = [
                m("option", { value: "comfortable" }, "Comfortable", -1),
                m("option", { value: "compact" }, "Compact", -1)
              ])], 40, r_)
            ])
          ])
        ]),
        _: 1
      })) : be("", !0),
      g(t).activeSection === "advanced" ? (D(), Be(Ze, {
        key: 5,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          m("div", o_, [
            x[50] || (x[50] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Advanced", -1)),
            z(ee, {
              variant: "ghost",
              size: "sm",
              onClick: x[17] || (x[17] = (G) => ye("advanced"))
            }, {
              default: F(() => [...x[49] || (x[49] = [
                I("Reset section", -1)
              ])]),
              _: 1
            })
          ]),
          m("label", i_, [
            x[52] || (x[52] = I(" Heavy tracing ", -1)),
            Pe(m("select", {
              "onUpdate:modelValue": x[18] || (x[18] = (G) => u.value = G),
              class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
              onChange: ae
            }, [...x[51] || (x[51] = [
              m("option", { value: "off" }, "Off", -1),
              m("option", { value: "summary" }, "Summary", -1),
              m("option", { value: "detailed" }, "Detailed", -1),
              m("option", { value: "trace" }, "Trace", -1),
              m("option", { value: "trace_verbose" }, "Verbose trace", -1)
            ])], 544), [
              [os, u.value]
            ])
          ]),
          m("p", a_, [
            x[53] || (x[53] = I(" Requires ComfyUI restart. ", -1)),
            g(t).profileLevel !== g(t).effectiveProfileLevel ? (D(), J("span", l_, " Restart pending: selected " + K(g(t).profileLevel) + ", effective " + K(g(t).effectiveProfileLevel) + ". ", 1)) : be("", !0)
          ]),
          m("label", c_, [
            Pe(m("input", {
              "onUpdate:modelValue": x[19] || (x[19] = (G) => h.value = G),
              type: "checkbox",
              "data-testid": "vue-settings-skip-validation",
              onChange: q
            }, null, 544), [
              [en, h.value]
            ]),
            x[54] || (x[54] = I(" Skip plan validation (temporary triage only) ", -1))
          ]),
          m("div", u_, [
            z(ee, {
              variant: "outline",
              size: "sm",
              "data-testid": "vue-settings-reset-all",
              onClick: re
            }, {
              default: F(() => [
                I(K(d.value ? "Confirm reset all settings" : "Reset all settings"), 1)
              ]),
              _: 1
            }),
            x[55] || (x[55] = m("p", { class: "cmst:mt-1 cmst:text-xs cmst:opacity-70" }, "Resets only Settings-owned keys. Credentials and user data are not affected.", -1))
          ])
        ]),
        _: 1
      })) : be("", !0)
    ], 2));
  }
});
function ji(e) {
  if (!e || typeof e != "object") return e;
  const t = e;
  return Object.prototype.hasOwnProperty.call(t, "workflow") ? t.workflow : Object.prototype.hasOwnProperty.call(t, "version") ? t.version : Object.prototype.hasOwnProperty.call(t, "mapping") ? t.mapping : e;
}
async function f_(e = {}) {
  const t = new URLSearchParams();
  e.search && t.set("search", e.search), e.tag && t.set("tag", e.tag), e.folder && t.set("folder", e.folder), e.favorite && t.set("favorite", "1");
  const s = t.toString() ? `?${t}` : "";
  return se(`/studio/workflows${s}`);
}
async function m_(e) {
  return se(`/studio/workflows/${encodeURIComponent(e)}`).then((t) => ({ ...t, workflow: ji(t) }));
}
async function p_(e) {
  return se(`/studio/workflows/${encodeURIComponent(e)}/versions`);
}
async function h_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}`).then((t) => ji(t));
}
async function g_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`).then((t) => ji(t));
}
async function v_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/candidates`);
}
async function y_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/dependencies`);
}
async function b_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`);
}
async function vl(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/portability`);
}
async function w_() {
  return se("/studio/workflows/folders");
}
async function __() {
  return se("/studio/workflows/tags");
}
async function yl(e, t) {
  return se(`/studio/workflows/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function x_(e) {
  return se("/studio/workflows", { method: "POST", body: e });
}
async function k_(e) {
  return se("/studio/workflows/import", { method: "POST", body: e });
}
async function S_(e) {
  return se(`/studio/workflows/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function C_(e) {
  return se("/studio/workflows/folders", { method: "POST", body: { path: e } });
}
async function R_(e, t) {
  return se(`/studio/workflows/${encodeURIComponent(e)}/versions`, { method: "POST", body: t });
}
async function A_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/state`);
}
async function E_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping`, { method: "POST", body: t });
}
async function I_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/mapping/revision`, { method: "POST", body: t });
}
async function O_(e, t) {
  return se(`/studio/workflows/${encodeURIComponent(e)}/dependencies/nonessential`, { method: "POST", body: { keys: t } });
}
async function T_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/compatibility`, { method: "PATCH", body: t });
}
async function $_(e, t) {
  return se(`/studio/method-compat?workflow_id=${encodeURIComponent(e)}&version_id=${encodeURIComponent(t)}`);
}
async function P_(e) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`);
}
async function N_(e, t) {
  return se(`/studio/workflows/versions/${encodeURIComponent(e)}/presets`, { method: "POST", body: t });
}
async function M_(e, t) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "PATCH", body: t });
}
async function z_(e) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}`, { method: "DELETE" });
}
async function D_(e, t = {}) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}/duplicate`, { method: "POST", body: t });
}
async function j_(e, t) {
  return se(`/studio/workflows/presets/${encodeURIComponent(e)}/copy-to-version`, { method: "POST", body: { workflow_version_id: t } });
}
async function V_(e, t) {
  return se(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`);
}
async function L_(e) {
  return se("/studio/guidance-mappings", { method: "POST", body: { mapping: e } });
}
async function U_(e, t) {
  return se(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(e)}&mode=${encodeURIComponent(t)}`, { method: "DELETE" });
}
async function F_(e) {
  const t = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(e)}/export`);
  if (!t.ok) return { ok: !1, message: `Export failed with status ${t.status}` };
  const s = await t.blob(), n = t.headers.get("Content-Disposition") || "", r = /filename="?([^";]+)"?/.exec(n);
  return { ok: !0, blob: s, filename: r ? r[1].trim() : "manifest.json" };
}
async function bl(e, t = !0) {
  return se(`/studio/workflows/import-manifest?dry_run=${t ? "1" : "0"}`, { method: "POST", body: e });
}
function W_(e) {
  const t = String(e || "t2i").toLowerCase();
  return t === "txt2img" ? "t2i" : t;
}
const vs = ["feature-type", "required-bindings", "exposed-controls", "details"];
function hr(e) {
  return {
    v: 1,
    workflowId: e.workflowId || "",
    versionId: e.versionId || "",
    step: e.step && vs.includes(e.step) ? e.step : "feature-type",
    featureType: e.featureType || "t2i",
    bindings: e.bindings || {},
    outputBinding: e.outputBinding || null,
    controls: Array.isArray(e.controls) ? e.controls.slice(0, 64) : [],
    details: e.details || {}
  };
}
function B_(e, t, s) {
  if (!e || e.length > 12e3) return null;
  try {
    const n = JSON.parse(e);
    return n.v !== 1 || n.workflowId !== t || n.versionId !== s ? null : hr(n);
  } catch {
    return null;
  }
}
const dr = "comfymodal.studio.wizard.draft.v1", G_ = /* @__PURE__ */ mn("studio-workflows", () => {
  const e = /* @__PURE__ */ E([]), t = /* @__PURE__ */ E(null), s = /* @__PURE__ */ E(null), n = /* @__PURE__ */ E([]), r = /* @__PURE__ */ E(null), o = /* @__PURE__ */ E(null), i = /* @__PURE__ */ E(null), a = /* @__PURE__ */ E(null), l = /* @__PURE__ */ E(null), c = /* @__PURE__ */ E(null), u = /* @__PURE__ */ E([]), f = /* @__PURE__ */ E(null), h = /* @__PURE__ */ E(null), d = /* @__PURE__ */ E(""), y = /* @__PURE__ */ E(""), C = /* @__PURE__ */ E(!1), U = /* @__PURE__ */ E(""), Q = /* @__PURE__ */ E(!1), B = /* @__PURE__ */ E(null), Y = /* @__PURE__ */ E(!1), q = /* @__PURE__ */ E(null), ae = /* @__PURE__ */ E(!1), ye = /* @__PURE__ */ E(null), re = /* @__PURE__ */ E(null), j = /* @__PURE__ */ E(null), H = /* @__PURE__ */ E(null), x = Gn();
  let G = null;
  function S(w) {
    t.value = w;
  }
  function X() {
    t.value = null, s.value = null, n.value = [], r.value = null;
  }
  async function ke() {
    Q.value = !0, B.value = null;
    try {
      const [w, M, Z] = await Promise.all([
        f_({ search: U.value, tag: d.value || void 0, folder: y.value || void 0, favorite: C.value || void 0 }),
        w_().catch(() => null),
        __().catch(() => null)
      ]);
      e.value = w.workflows ?? [], f.value = M, h.value = Z;
    } catch (w) {
      throw B.value = w instanceof Error ? w.message : "Could not load workflows", w;
    } finally {
      Q.value = !1;
    }
  }
  async function xe() {
    G || (G = eo((w) => {
      w === "workflows" && !Q.value && ke();
    })), e.value.length || await ke();
  }
  async function b(w) {
    t.value = w;
    const M = await x.run(async (Ee) => {
      const [we, We] = await Promise.all([m_(w), p_(w)]);
      return Ee.aborted ? null : { workflowResponse: we, versionsResponse: We };
    });
    if (M.stale || !M.value) return;
    s.value = M.value.workflowResponse.workflow ?? null, n.value = M.value.versionsResponse.versions ?? [];
    const Z = s.value?.latest_version_id, ce = n.value.find((Ee) => Ee.workflow_version_id === Z) ?? n.value.at(-1) ?? null;
    ce && await $(ce.workflow_version_id);
  }
  async function $(w) {
    const M = await x.run(async (ce) => {
      const [Ee, we, We, Oe, st, Os, Ws] = await Promise.all([
        h_(w),
        g_(w),
        y_(w),
        b_(w),
        vl(w),
        P_(w),
        A_(w)
      ]);
      return ce.aborted ? null : { versionResponse: Ee, mappingResponse: we, dependencyResponse: We, compatibilityResponse: Oe, portabilityResponse: st, presetsResponse: Os, stateResponse: Ws };
    });
    if (M.stale || !M.value) return;
    r.value = M.value.versionResponse, o.value = M.value.mappingResponse, i.value = null, a.value = M.value.dependencyResponse, l.value = M.value.compatibilityResponse, c.value = M.value.portabilityResponse, re.value = M.value.stateResponse;
    const Z = M.value.presetsResponse;
    u.value = Z.presets ?? [], s.value && w && (j.value = await $_(s.value.workflow_id, w).catch(() => null));
  }
  async function ve() {
    r.value && (i.value = await v_(r.value.workflow_version_id));
  }
  function Fe() {
    const w = s.value?.workflow_id ?? "", M = r.value?.workflow_version_id ?? "";
    try {
      q.value = B_(sessionStorage.getItem(dr), w, M) ?? hr({ workflowId: w, versionId: M, featureType: W_(s.value?.workflow_type) });
    } catch {
      q.value = hr({ workflowId: w, versionId: M });
    }
    Y.value = !0;
  }
  function oe(w) {
    if (q.value) {
      q.value = hr({ ...q.value, ...w });
      try {
        sessionStorage.setItem(dr, JSON.stringify(q.value));
      } catch {
      }
    }
  }
  function Xe(w) {
    oe({ step: w });
  }
  function Ke() {
    Y.value = !1, q.value = null;
    try {
      sessionStorage.removeItem(dr);
    } catch {
    }
  }
  async function ft(w) {
    t.value && (await yl(t.value, w), await ke(), await b(t.value), He("workflows"));
  }
  async function at(w, M) {
    await yl(w, { favorite: M }), await ke(), He("workflows");
  }
  async function ze(w) {
    await x_(w), await ke(), He("workflows");
  }
  async function Ne(w) {
    const M = It(), Z = M.start({ kind: "workflow-import", label: "Import workflow" });
    try {
      await k_(w), M.finish(Z, "Workflow imported"), await ke(), He("workflows");
    } catch (ce) {
      throw M.fail(Z, ce instanceof Error ? ce.message : "Import failed"), ce;
    }
  }
  async function L() {
    t.value && (await S_(t.value), X(), await ke(), He("workflows"));
  }
  async function A(w) {
    await C_(w), await ke();
  }
  async function O(w) {
    t.value && (await R_(t.value, w), await b(t.value), He("workflows"));
  }
  async function ie(w) {
    const M = r.value?.workflow_version_id;
    if (!M) throw new Error("No version selected");
    const Z = o.value;
    !!Z && typeof Z.mapping_id == "string" ? await I_(M, w) : await E_(M, w), await $(M), He("workflows");
  }
  async function p(w) {
    t.value && (await O_(t.value, w), r.value && await $(r.value.workflow_version_id));
  }
  async function v(w) {
    r.value && (await T_(r.value.workflow_version_id, w), await $(r.value.workflow_version_id));
  }
  async function k() {
    r.value && (c.value = await vl(r.value.workflow_version_id));
  }
  async function R() {
    if (!r.value) return;
    const w = await F_(r.value.workflow_version_id);
    if (!w.ok || !w.blob) throw new Error(w.message || "Export failed");
    const M = URL.createObjectURL(w.blob);
    try {
      const Z = document.createElement("a");
      Z.href = M, Z.download = w.filename || "manifest.json", document.body.appendChild(Z), Z.click(), Z.remove();
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(M), 1e3);
    }
  }
  async function P(w) {
    const M = await bl(w, !0);
    return H.value = M, M;
  }
  async function W(w) {
    await bl(w, !1), H.value = null, await ke(), He("workflows");
  }
  function _(w) {
    const M = {};
    for (const [Z, ce] of Object.entries(w))
      ce instanceof Blob || typeof ce == "string" && (ce.startsWith("blob:") || ce.startsWith("data:image/")) || Z === "sourceImage" || Z === "referenceImages" || Z === "mask" || Z === "sketch" || Z === "generatedImages" || Z === "compareImages" || (M[Z] = ce);
    return M;
  }
  async function T(w) {
    r.value && (await N_(r.value.workflow_version_id, {
      ...w,
      studio_state: _(w.studio_state)
    }), await $(r.value.workflow_version_id));
  }
  async function N(w, M) {
    const Z = M.studio_state && typeof M.studio_state == "object" ? { ...M, studio_state: _(M.studio_state) } : M;
    await M_(w, Z), r.value && await $(r.value.workflow_version_id);
  }
  async function V(w) {
    await z_(w), r.value && await $(r.value.workflow_version_id);
  }
  async function fe(w, M) {
    await D_(w, M ? { name: M } : {}), r.value && await $(r.value.workflow_version_id);
  }
  async function ne(w, M) {
    await j_(w, M), He("workflows");
  }
  async function he(w, M) {
    return V_(w, M);
  }
  async function _e(w) {
    await L_(w);
  }
  async function $e(w, M) {
    await U_(w, M);
  }
  async function Le() {
    const w = q.value;
    if (!w) throw new Error("No wizard draft");
    const M = w.bindings || {};
    if (!Object.values(M).filter(
      (ce) => ce && typeof ce == "object" && ce.confirmed === !0
    ).length) throw new Error("Confirm at least one graph binding first");
    if (!w.outputBinding) throw new Error("Capture the output binding first");
    ae.value = !0, ye.value = null;
    try {
      await ie({
        feature_type: w.featureType,
        bindings: w.bindings,
        output_binding: w.outputBinding,
        controls: w.controls,
        details: w.details
      });
      try {
        sessionStorage.removeItem(dr);
      } catch {
      }
      q.value = null, Y.value = !1;
    } catch (ce) {
      throw ye.value = ce instanceof Error ? ce.message : "Mapping save failed", ce;
    } finally {
      ae.value = !1;
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
    folders: f,
    tags: h,
    tagFilter: d,
    folderFilter: y,
    favoritesOnly: C,
    versionState: re,
    methodCompat: j,
    manifestPreview: H,
    query: U,
    loading: Q,
    error: B,
    wizardOpen: Y,
    wizardDraft: q,
    wizardSaving: ae,
    wizardError: ye,
    select: S,
    clear: X,
    loadList: ke,
    initialize: xe,
    selectWorkflow: b,
    selectVersion: $,
    loadMappingCandidates: ve,
    openWizard: Fe,
    updateWizard: oe,
    setWizardStep: Xe,
    closeWizard: Ke,
    updateMetadata: ft,
    toggleFavorite: at,
    createNewWorkflow: ze,
    importNewWorkflow: Ne,
    deleteSelectedWorkflow: L,
    createFolder: A,
    captureVersion: O,
    saveMapping: ie,
    markNonessential: p,
    saveCompatibility: v,
    recheckPortability: k,
    exportManifest: R,
    previewManifestImport: P,
    commitManifestImport: W,
    sanitizePresetState: _,
    createPreset: T,
    savePreset: N,
    removePreset: V,
    duplicateCurrentPreset: fe,
    copyPresetForward: ne,
    loadGuidance: he,
    saveGuidance: _e,
    removeGuidance: $e,
    saveWizardMapping: Le
  };
}), H_ = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, q_ = { class: "cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2" }, Z_ = { class: "cmst:flex cmst:gap-2" }, K_ = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" }, J_ = { class: "cmst:flex cmst:items-center cmst:gap-1 cmst:text-sm" }, Q_ = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, Y_ = ["data-testid", "onClick"], X_ = { class: "cmst:block cmst:text-xs cmst:opacity-70" }, ex = {
  key: 0,
  class: "cmst:mt-3 cmst:text-sm cmst:opacity-70"
}, tx = { class: "cmst:mt-3" }, sx = {
  key: 0,
  class: "cmst:mt-1 cmst:text-xs cmst:text-red-300",
  role: "alert"
}, nx = { class: "cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3" }, rx = { class: "cmst:text-base cmst:font-semibold" }, ox = { class: "cmst:text-xs cmst:opacity-70" }, ix = { class: "cmst:flex cmst:gap-2" }, ax = { class: "cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2" }, lx = ["value"], cx = ["value"], ux = { class: "cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2" }, dx = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, fx = { class: "cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm" }, mx = { class: "cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3" }, px = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, hx = { class: "cmst:mt-2" }, gx = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:text-xs"
}, vx = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, yx = {
  key: 0,
  class: "cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:text-xs"
}, bx = { class: "cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm" }, wx = { class: "cmst:mt-2 cmst:flex cmst:gap-1" }, _x = { class: "cmst:mt-4" }, xx = { class: "cmst:mt-2 cmst:flex cmst:gap-2" }, kx = { class: "cmst:mt-2 cmst:text-sm" }, Sx = { class: "cmst:mt-4" }, Cx = { class: "cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2" }, Rx = { class: "cmst:mt-3 cmst:text-sm" }, Ax = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, Ex = ["onKeydown"], Ix = { class: "cmst:flex cmst:items-center cmst:justify-between" }, Ox = { class: "cmst:text-xs cmst:opacity-70" }, Tx = { class: "cmst:mt-5 cmst:rounded-md cmst:bg-cmst-bg cmst:p-4" }, $x = ["value"], Px = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, Nx = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs"
}, Mx = { class: "cmst:mt-3 cmst:flex cmst:gap-2" }, zx = { class: "cmst:mt-2 cmst:text-sm" }, Dx = { class: "cmst:mt-3" }, jx = { class: "cmst:mt-2 cmst:max-h-40 cmst:overflow-auto cmst:text-xs" }, Vx = {
  key: 0,
  class: "cmst:mt-2 cmst:text-xs cmst:text-red-300",
  role: "alert"
}, Lx = { class: "cmst:mt-4 cmst:flex cmst:justify-between" }, Ux = /* @__PURE__ */ St({
  __name: "WorkflowsView",
  setup(e) {
    const t = G_(), s = Pi(), n = /* @__PURE__ */ E(""), r = /* @__PURE__ */ E("workflows"), o = /* @__PURE__ */ E(""), i = /* @__PURE__ */ E(""), a = /* @__PURE__ */ E(""), l = /* @__PURE__ */ E(""), c = /* @__PURE__ */ E(""), u = /* @__PURE__ */ E(""), f = /* @__PURE__ */ E(""), h = /* @__PURE__ */ E(""), d = /* @__PURE__ */ E(""), y = /* @__PURE__ */ E("txt2img"), C = /* @__PURE__ */ E(""), U = Ve(() => Math.max(0, vs.indexOf(t.wizardDraft?.step ?? "feature-type"))), Q = Ve(() => vs[U.value]);
    fs(async () => {
      await Promise.all([t.initialize(), s.initialize()]);
    });
    async function B() {
      t.query = n.value, await t.loadList();
    }
    async function Y(xe) {
      await t.selectWorkflow(xe);
      const b = t.selectedWorkflow;
      l.value = String(b?.name ?? ""), c.value = String(b?.folder ?? "");
    }
    function q() {
      t.openWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!0);
    }
    function ae() {
      window.__comfymodalCancelStudioGraphBinding?.(), t.closeWizard(), window.__comfymodalSetGraphInteractionEnabled?.(!1);
    }
    async function ye() {
      if (!o.value.trim()) return;
      const xe = o.value.trim();
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = "Click a node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "prompt",
          label: "prompt",
          allowOutput: !1,
          onCapture: (b) => {
            t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { ...b, confirmed: !0 } } }), a.value = `Confirmed ${String(b.nodeTitle ?? b.nodeId ?? "graph target")}`;
          },
          onCancel: (b) => {
            a.value = b;
          }
        });
        return;
      }
      t.updateWizard({ bindings: { ...t.wizardDraft?.bindings ?? {}, prompt: { target: xe, confirmed: !0 } } }), a.value = `Confirmed graph target ${xe}`;
    }
    async function re() {
      if (window.__comfymodalBeginStudioGraphBinding) {
        a.value = "Click the output node in the ComfyUI graph…", await window.__comfymodalBeginStudioGraphBinding({
          bindingKey: "output",
          label: "output",
          allowOutput: !0,
          onCapture: (xe) => {
            t.updateWizard({ outputBinding: { ...xe, confirmed: !0 } }), a.value = `Output bound to ${String(xe.nodeTitle ?? xe.nodeId ?? "graph target")}`;
          },
          onCancel: (xe) => {
            a.value = xe;
          }
        });
        return;
      }
      t.updateWizard({ outputBinding: { target: "SaveImage.images", confirmed: !0 } }), a.value = "Output binding recorded";
    }
    async function j() {
      a.value = "";
      try {
        await t.saveWizardMapping(), a.value = "Mapping saved";
      } catch (xe) {
        a.value = xe instanceof Error ? xe.message : "Save failed";
      }
    }
    function H() {
      const xe = vs[Math.min(vs.length - 1, U.value + 1)];
      t.setWizardStep(xe);
    }
    function x() {
      const xe = vs[Math.max(0, U.value - 1)];
      t.setWizardStep(xe);
    }
    function G() {
      if (!i.value.trim()) return;
      const xe = [...t.wizardDraft?.controls ?? [], { label: i.value.trim(), enabled: !0 }];
      t.updateWizard({ controls: xe }), i.value = "";
    }
    async function S() {
      f.value = "";
      try {
        const xe = JSON.parse(u.value);
        await t.importNewWorkflow(xe), u.value = "";
      } catch (xe) {
        f.value = xe instanceof Error ? xe.message : "Import failed";
      }
    }
    async function X() {
      await t.updateMetadata({ name: l.value, folder: c.value }).catch(() => {
      });
    }
    async function ke() {
      try {
        await t.saveMapping(JSON.parse(C.value || "{}"));
      } catch {
      }
    }
    return (xe, b) => (D(), J("section", {
      class: xt(g(Jn)()),
      "data-testid": "vue-page-workflows"
    }, [
      z(Ze, { class: "cmst:p-4" }, {
        default: F(() => [
          m("div", H_, [
            m("div", null, [
              m("h2", q_, [
                z(g(Qo), {
                  class: "cmst:size-5",
                  "aria-hidden": "true"
                }),
                b[29] || (b[29] = I("Workflows & Models", -1))
              ]),
              b[30] || (b[30] = m("p", { class: "cmst:text-sm cmst:opacity-80" }, "Workflow/version state and shared infrastructure inventory remain separate authorities.", -1))
            ]),
            m("div", Z_, [
              z(ee, {
                variant: r.value === "workflows" ? "default" : "outline",
                size: "sm",
                onClick: b[0] || (b[0] = ($) => r.value = "workflows")
              }, {
                default: F(() => [
                  z(g(Qo), { class: "cmst:size-4" }),
                  b[31] || (b[31] = I("Workflows", -1))
                ]),
                _: 1
              }, 8, ["variant"]),
              z(ee, {
                variant: r.value === "models" ? "default" : "outline",
                size: "sm",
                onClick: b[1] || (b[1] = ($) => r.value = "models")
              }, {
                default: F(() => [
                  z(g(kp), { class: "cmst:size-4" }),
                  b[32] || (b[32] = I("Models / Nodes", -1))
                ]),
                _: 1
              }, 8, ["variant"])
            ])
          ])
        ]),
        _: 1
      }),
      r.value === "workflows" ? (D(), J(Ce, { key: 0 }, [
        z(Ze, { class: "cmst:p-4" }, {
          default: F(() => [
            m("div", K_, [
              Pe(m("input", {
                "onUpdate:modelValue": b[2] || (b[2] = ($) => n.value = $),
                class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2",
                placeholder: "Search workflows",
                "aria-label": "Search workflows",
                onKeyup: rn(B, ["enter"])
              }, null, 544), [
                [rt, n.value]
              ]),
              Pe(m("select", {
                "onUpdate:modelValue": b[3] || (b[3] = ($) => g(t).tagFilter = $),
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                "aria-label": "Filter by tag",
                onChange: b[4] || (b[4] = ($) => g(t).loadList())
              }, [...b[33] || (b[33] = [
                m("option", { value: "" }, "All tags", -1)
              ])], 544), [
                [os, g(t).tagFilter]
              ]),
              m("label", J_, [
                Pe(m("input", {
                  "onUpdate:modelValue": b[5] || (b[5] = ($) => g(t).favoritesOnly = $),
                  type: "checkbox",
                  onChange: b[6] || (b[6] = ($) => g(t).loadList())
                }, null, 544), [
                  [en, g(t).favoritesOnly]
                ]),
                b[34] || (b[34] = I(" Favorites", -1))
              ]),
              z(ee, {
                size: "sm",
                variant: "secondary",
                onClick: B
              }, {
                default: F(() => [...b[35] || (b[35] = [
                  I("Search", -1)
                ])]),
                _: 1
              }),
              z(ee, {
                size: "sm",
                variant: "outline",
                onClick: b[7] || (b[7] = ($) => g(t).loadList())
              }, {
                default: F(() => [
                  z(g(Xr), { class: "cmst:size-4" })
                ]),
                _: 1
              })
            ]),
            m("div", Q_, [
              (D(!0), J(Ce, null, tt(g(t).workflows, ($) => (D(), J("button", {
                key: $.workflow_id,
                type: "button",
                class: "cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary",
                "data-testid": `vue-workflow-${$.workflow_id}`,
                onClick: (ve) => Y($.workflow_id)
              }, [
                m("strong", null, K($.name || $.workflow_id), 1),
                m("span", X_, K($.folder || "No folder") + " · " + K($.latest_version_id || "No version"), 1)
              ], 8, Y_))), 128))
            ]),
            g(t).workflows.length ? be("", !0) : (D(), J("p", ex, "No workflows returned by the server.")),
            m("div", tx, [
              b[37] || (b[37] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Import workflow", -1)),
              Pe(m("textarea", {
                "onUpdate:modelValue": b[8] || (b[8] = ($) => u.value = $),
                rows: "3",
                class: "cmst:mt-1 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-xs",
                placeholder: '{"name": "...", "static_graph": {...}}',
                "data-testid": "vue-workflow-import-input"
              }, null, 512), [
                [rt, u.value]
              ]),
              f.value ? (D(), J("p", sx, K(f.value), 1)) : be("", !0),
              z(ee, {
                class: "cmst:mt-2",
                size: "sm",
                "data-testid": "vue-workflow-import",
                onClick: S
              }, {
                default: F(() => [...b[36] || (b[36] = [
                  I("Import", -1)
                ])]),
                _: 1
              })
            ])
          ]),
          _: 1
        }),
        g(t).selectedWorkflow ? (D(), Be(Ze, {
          key: 0,
          class: "cmst:p-4"
        }, {
          default: F(() => [
            m("div", nx, [
              m("div", null, [
                m("h3", rx, K(g(t).selectedWorkflow.name), 1),
                m("p", ox, "Version " + K(g(t).selectedVersion?.version ?? g(t).selectedVersion?.workflow_version_id), 1)
              ]),
              m("div", ix, [
                z(ee, {
                  size: "sm",
                  variant: "outline",
                  "data-testid": `vue-workflow-favorite-${g(t).selectedWorkflow.workflow_id}`,
                  onClick: b[9] || (b[9] = ($) => g(t).toggleFavorite(g(t).selectedWorkflow.workflow_id, !g(t).selectedWorkflow.favorite))
                }, {
                  default: F(() => [...b[38] || (b[38] = [
                    I("★", -1)
                  ])]),
                  _: 1
                }, 8, ["data-testid"]),
                z(ee, {
                  size: "sm",
                  onClick: q
                }, {
                  default: F(() => [
                    z(g(Dp), { class: "cmst:size-4" }),
                    b[39] || (b[39] = I("Setup wizard", -1))
                  ]),
                  _: 1
                })
              ])
            ]),
            m("div", ax, [
              m("select", {
                value: g(t).selectedVersion?.workflow_version_id ?? "",
                class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                "aria-label": "Select version",
                "data-testid": "vue-version-select",
                onChange: b[10] || (b[10] = ($) => g(t).selectVersion($.target.value))
              }, [
                (D(!0), J(Ce, null, tt(g(t).versions, ($) => (D(), J("option", {
                  key: $.workflow_version_id,
                  value: $.workflow_version_id
                }, "v" + K($.version ?? $.workflow_version_id), 9, cx))), 128))
              ], 40, lx),
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-version-capture",
                onClick: b[11] || (b[11] = ($) => g(t).captureVersion({}))
              }, {
                default: F(() => [...b[40] || (b[40] = [
                  I("Capture version", -1)
                ])]),
                _: 1
              }),
              z(ee, {
                size: "sm",
                variant: "outline",
                "data-testid": "vue-workflow-delete",
                onClick: b[12] || (b[12] = ($) => g(t).deleteSelectedWorkflow())
              }, {
                default: F(() => [...b[41] || (b[41] = [
                  I("Delete workflow", -1)
                ])]),
                _: 1
              })
            ]),
            m("div", ux, [
              m("label", dx, [
                b[42] || (b[42] = I("Name", -1)),
                Pe(m("input", {
                  "onUpdate:modelValue": b[13] || (b[13] = ($) => l.value = $),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
                }, null, 512), [
                  [rt, l.value]
                ])
              ]),
              m("label", fx, [
                b[43] || (b[43] = I("Folder", -1)),
                Pe(m("input", {
                  "onUpdate:modelValue": b[14] || (b[14] = ($) => c.value = $),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
                }, null, 512), [
                  [rt, c.value]
                ])
              ])
            ]),
            z(ee, {
              class: "cmst:mt-2",
              size: "sm",
              variant: "secondary",
              "data-testid": "vue-workflow-save-meta",
              onClick: X
            }, {
              default: F(() => [...b[44] || (b[44] = [
                I("Save metadata", -1)
              ])]),
              _: 1
            }),
            m("div", mx, [
              m("div", px, [
                b[47] || (b[47] = I("Mapping", -1)),
                b[48] || (b[48] = m("br", null, null, -1)),
                m("strong", null, K(g(t).mapping ? "configured" : "not configured"), 1),
                m("div", hx, [
                  z(ee, {
                    size: "sm",
                    variant: "ghost",
                    onClick: b[15] || (b[15] = ($) => g(t).loadMappingCandidates())
                  }, {
                    default: F(() => [...b[45] || (b[45] = [
                      I("Load candidates", -1)
                    ])]),
                    _: 1
                  })
                ]),
                g(t).mappingCandidates ? (D(), J("pre", gx, K(JSON.stringify(g(t).mappingCandidates, null, 1).slice(0, 800)), 1)) : be("", !0),
                Pe(m("textarea", {
                  "onUpdate:modelValue": b[16] || (b[16] = ($) => C.value = $),
                  rows: "3",
                  class: "cmst:mt-2 cmst:w-full cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-xs",
                  placeholder: '{"bindings": {...}}'
                }, null, 512), [
                  [rt, C.value]
                ]),
                z(ee, {
                  class: "cmst:mt-1",
                  size: "sm",
                  "data-testid": "vue-mapping-save",
                  onClick: ke
                }, {
                  default: F(() => [...b[46] || (b[46] = [
                    I("Save mapping", -1)
                  ])]),
                  _: 1
                })
              ]),
              m("div", vx, [
                b[49] || (b[49] = I("Dependencies", -1)),
                b[50] || (b[50] = m("br", null, null, -1)),
                m("strong", null, K(g(t).dependencies ? "loaded" : "not loaded"), 1),
                g(t).dependencies ? (D(), J("pre", yx, K(JSON.stringify(g(t).dependencies, null, 1).slice(0, 800)), 1)) : be("", !0)
              ]),
              m("div", bx, [
                b[53] || (b[53] = I("Portability", -1)),
                b[54] || (b[54] = m("br", null, null, -1)),
                m("strong", null, K(g(t).portability ? "analyzed" : "not analyzed"), 1),
                m("div", wx, [
                  z(ee, {
                    size: "sm",
                    variant: "ghost",
                    onClick: b[17] || (b[17] = ($) => g(t).recheckPortability())
                  }, {
                    default: F(() => [...b[51] || (b[51] = [
                      I("Recheck", -1)
                    ])]),
                    _: 1
                  }),
                  z(ee, {
                    size: "sm",
                    variant: "ghost",
                    "data-testid": "vue-manifest-export",
                    onClick: b[18] || (b[18] = ($) => g(t).exportManifest())
                  }, {
                    default: F(() => [...b[52] || (b[52] = [
                      I("Export manifest", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ]),
            m("div", _x, [
              b[57] || (b[57] = m("h4", { class: "cmst:text-sm cmst:font-semibold" }, "Presets (image-free configuration only)", -1)),
              m("div", xx, [
                Pe(m("input", {
                  "onUpdate:modelValue": b[19] || (b[19] = ($) => h.value = $),
                  class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                  placeholder: "Preset name"
                }, null, 512), [
                  [rt, h.value]
                ]),
                z(ee, {
                  size: "sm",
                  "data-testid": "vue-preset-create",
                  onClick: b[20] || (b[20] = ($) => {
                    g(t).createPreset({ name: h.value || "Untitled", studio_state: {} }), h.value = "";
                  })
                }, {
                  default: F(() => [...b[55] || (b[55] = [
                    I("Create preset", -1)
                  ])]),
                  _: 1
                })
              ]),
              m("ul", kx, [
                (D(!0), J(Ce, null, tt(g(t).presets, ($, ve) => (D(), J("li", {
                  key: ve,
                  class: "cmst:flex cmst:items-center cmst:gap-2"
                }, [
                  m("span", null, K(String($.name || `preset ${ve}`)), 1),
                  z(ee, {
                    size: "sm",
                    variant: "ghost",
                    onClick: (Fe) => g(t).removePreset(String($.preset_id || $.id || ""))
                  }, {
                    default: F(() => [...b[56] || (b[56] = [
                      I("Delete", -1)
                    ])]),
                    _: 1
                  }, 8, ["onClick"])
                ]))), 128))
              ])
            ]),
            m("div", Sx, [
              b[60] || (b[60] = m("h4", { class: "cmst:text-sm cmst:font-semibold" }, "Guidance mapping", -1)),
              m("div", Cx, [
                Pe(m("input", {
                  "onUpdate:modelValue": b[21] || (b[21] = ($) => d.value = $),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm",
                  placeholder: "model sha256"
                }, null, 512), [
                  [rt, d.value]
                ]),
                Pe(m("select", {
                  "onUpdate:modelValue": b[22] || (b[22] = ($) => y.value = $),
                  class: "cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
                }, [...b[58] || (b[58] = [
                  m("option", { value: "txt2img" }, "txt2img", -1),
                  m("option", { value: "i2i" }, "i2i", -1)
                ])], 512), [
                  [os, y.value]
                ]),
                z(ee, {
                  size: "sm",
                  variant: "outline",
                  onClick: b[23] || (b[23] = ($) => g(t).loadGuidance(d.value, y.value))
                }, {
                  default: F(() => [...b[59] || (b[59] = [
                    I("Load", -1)
                  ])]),
                  _: 1
                })
              ])
            ])
          ]),
          _: 1
        })) : be("", !0)
      ], 64)) : (D(), Be(Ze, {
        key: 1,
        class: "cmst:p-4"
      }, {
        default: F(() => [
          b[63] || (b[63] = m("h3", { class: "cmst:text-sm cmst:font-semibold" }, "Shared model inventory", -1)),
          b[64] || (b[64] = m("p", { class: "cmst:mt-1 cmst:text-sm cmst:opacity-70" }, "Owned by infrastructureStore; workflow dependencies reference this state.", -1)),
          m("div", Rx, "Models: " + K(g(s).models.length) + " · Custom nodes: " + K(g(s).customNodes.length), 1),
          m("div", Ax, [
            z(ee, {
              size: "sm",
              variant: "outline",
              onClick: b[24] || (b[24] = ($) => g(s).rescanModelsNow(!0))
            }, {
              default: F(() => [...b[61] || (b[61] = [
                I("Rescan models", -1)
              ])]),
              _: 1
            }),
            z(ee, {
              size: "sm",
              variant: "outline",
              onClick: b[25] || (b[25] = ($) => g(s).refreshCustomNodesNow())
            }, {
              default: F(() => [...b[62] || (b[62] = [
                I("Refresh nodes", -1)
              ])]),
              _: 1
            })
          ])
        ]),
        _: 1
      })),
      g(t).wizardOpen ? (D(), J("div", {
        key: 2,
        class: "cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6",
        "data-state": "open",
        "data-testid": "vue-workflow-wizard",
        tabindex: "-1",
        onKeydown: rn(Ai(ae, ["stop"]), ["esc"])
      }, [
        z(Ze, { class: "cmst:w-[min(42rem,94vw)] cmst:max-h-[90vh] cmst:overflow-auto cmst:p-5" }, {
          default: F(() => [
            m("div", Ix, [
              m("div", null, [
                b[65] || (b[65] = m("h2", { class: "cmst:text-lg cmst:font-semibold" }, "Setup workflow", -1)),
                m("p", Ox, "Step " + K(U.value + 1) + " of " + K(g(vs).length) + " · " + K(Q.value), 1)
              ]),
              z(ee, {
                variant: "ghost",
                size: "sm",
                onClick: ae
              }, {
                default: F(() => [...b[66] || (b[66] = [
                  I("Close", -1)
                ])]),
                _: 1
              })
            ]),
            m("div", Tx, [
              Q.value === "feature-type" ? (D(), J(Ce, { key: 0 }, [
                b[68] || (b[68] = m("h3", { class: "cmst:font-semibold" }, "Feature Type", -1)),
                b[69] || (b[69] = m("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Feature type is explicit and provider-neutral.", -1)),
                m("select", {
                  class: "cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                  value: g(t).wizardDraft?.featureType,
                  onChange: b[26] || (b[26] = ($) => g(t).updateWizard({ featureType: $.target.value }))
                }, [...b[67] || (b[67] = [
                  m("option", { value: "t2i" }, "Text to Image", -1),
                  m("option", { value: "i2i" }, "Image to Image", -1),
                  m("option", { value: "inpaint" }, "Inpaint", -1),
                  m("option", { value: "sketch" }, "Sketch", -1),
                  m("option", { value: "outpaint" }, "Outpaint", -1)
                ])], 40, $x)
              ], 64)) : Q.value === "required-bindings" ? (D(), J(Ce, { key: 1 }, [
                b[71] || (b[71] = m("h3", { class: "cmst:font-semibold" }, "Required Bindings", -1)),
                b[72] || (b[72] = m("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Graph binding is explicit: underlying ComfyUI graph interaction is enabled while this step is active.", -1)),
                m("div", Px, [
                  Pe(m("input", {
                    "onUpdate:modelValue": b[27] || (b[27] = ($) => o.value = $),
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                    placeholder: "Node/widget target"
                  }, null, 512), [
                    [rt, o.value]
                  ]),
                  z(ee, {
                    size: "sm",
                    onClick: ye
                  }, {
                    default: F(() => [...b[70] || (b[70] = [
                      I("Confirm binding", -1)
                    ])]),
                    _: 1
                  })
                ]),
                a.value ? (D(), J("p", Nx, K(a.value), 1)) : be("", !0)
              ], 64)) : Q.value === "exposed-controls" ? (D(), J(Ce, { key: 2 }, [
                b[75] || (b[75] = m("h3", { class: "cmst:font-semibold" }, "Exposed Controls", -1)),
                b[76] || (b[76] = m("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Workflow configuration controls live here — not a generic form builder.", -1)),
                m("div", Mx, [
                  Pe(m("input", {
                    "onUpdate:modelValue": b[28] || (b[28] = ($) => i.value = $),
                    class: "cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2",
                    placeholder: "Control label"
                  }, null, 512), [
                    [rt, i.value]
                  ]),
                  z(ee, {
                    size: "sm",
                    onClick: G
                  }, {
                    default: F(() => [...b[73] || (b[73] = [
                      I("Add control", -1)
                    ])]),
                    _: 1
                  })
                ]),
                m("ul", zx, [
                  (D(!0), J(Ce, null, tt(g(t).wizardDraft?.controls ?? [], ($, ve) => (D(), J("li", { key: ve }, "· " + K(String($.label ?? $)), 1))), 128))
                ]),
                m("div", Dx, [
                  z(ee, {
                    size: "sm",
                    variant: "outline",
                    onClick: re
                  }, {
                    default: F(() => [...b[74] || (b[74] = [
                      I("Capture output binding", -1)
                    ])]),
                    _: 1
                  })
                ])
              ], 64)) : (D(), J(Ce, { key: 3 }, [
                b[77] || (b[77] = m("h3", { class: "cmst:font-semibold" }, "Details", -1)),
                b[78] || (b[78] = m("p", { class: "cmst:mt-2 cmst:text-sm cmst:opacity-75" }, "Review the explicit bindings before saving the version mapping.", -1)),
                m("pre", jx, K(JSON.stringify({ bindings: g(t).wizardDraft?.bindings, output: g(t).wizardDraft?.outputBinding, controls: g(t).wizardDraft?.controls }, null, 1)), 1),
                g(t).wizardError ? (D(), J("p", Vx, K(g(t).wizardError), 1)) : be("", !0),
                z(ee, {
                  class: "cmst:mt-3",
                  size: "sm",
                  disabled: g(t).wizardSaving,
                  "data-testid": "vue-wizard-save",
                  onClick: j
                }, {
                  default: F(() => [
                    I(K(g(t).wizardSaving ? "Saving…" : "Save mapping"), 1)
                  ]),
                  _: 1
                }, 8, ["disabled"])
              ], 64))
            ]),
            m("div", Lx, [
              z(ee, {
                variant: "outline",
                size: "sm",
                disabled: U.value === 0,
                onClick: x
              }, {
                default: F(() => [...b[79] || (b[79] = [
                  I("Back", -1)
                ])]),
                _: 1
              }, 8, ["disabled"]),
              z(ee, {
                size: "sm",
                disabled: U.value === g(vs).length - 1,
                onClick: H
              }, {
                default: F(() => [...b[80] || (b[80] = [
                  I("Next", -1)
                ])]),
                _: 1
              }, 8, ["disabled"])
            ])
          ]),
          _: 1
        })
      ], 40, Ex)) : be("", !0)
    ], 2));
  }
}), Fx = {
  playground: xw,
  history: fw,
  workflows: Ux,
  backend: Ry,
  settings: d_
};
function Wx(e = {}) {
  let t;
  return e.memory || !e.win ? t = Zm() : t = Sv(e.win, e.initial), pp({
    history: t,
    routes: Oi.map((n) => ({
      path: `/${n}`,
      name: n,
      component: Fx[n]
    }))
  });
}
function Bx(e, t = {}) {
  const s = am(), n = Wx({
    win: window,
    initial: t.initialPage != null ? { page: t.initialPage, focus: t.initialFocus ?? null } : void 0
  }), r = rm(xv);
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
  Bx as mountStudioPreview
};

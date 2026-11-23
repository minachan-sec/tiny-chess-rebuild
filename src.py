# tiny-chess-01 engine (0x88, negamax/PVS, quiescence, LMR, TT move ordering); fixed node budget, never a clock. Packed by `makefun compress`.
import json, os, random, sys
import urllib.request

ENV = os.environ.get("MAKEFUN_ENV_URL") or sys.exit("MAKEFUN_ENV_URL is not set")
KD = (-33, -31, -18, -14, 14, 18, 31, 33)
GD = (-17, -16, -15, -1, 1, 15, 16, 17)
BD = (-17, -15, 15, 17)
RD = (-16, -1, 1, 16)
DR = (KD, BD, RD, GD, GD)
V = (0, 100, 320, 330, 500, 975, 0)
PB = (0, 5, 10, 20, 35, 60, 100, 0)
MATE = 100000
NB = 120000


def _x(h):
    out = []
    for r in range(8):
        row = h[r * 4:(r + 1) * 4]
        out += row + row[::-1]
    return tuple(out)


# Piece-square tables, rank 8 first, white's view; black mirrors sq^0x70.
# Stored as left halves and mirrored by _x, except the queen table, whose
# classic form is not quite symmetric; it is stored in full.
PM = (_x((0,0,0,0, 50,50,50,50, 10,10,20,30, 5,5,10,25,
          0,0,0,20, 5,-5,-10,0, 5,10,10,-20, 0,0,0,0)),
      _x((-50,-40,-30,-30, -40,-20,0,0, -30,0,10,15, -30,5,15,20,
          -30,0,15,20, -30,5,10,15, -40,-20,0,5, -50,-40,-30,-30)),
      _x((-20,-10,-10,-10, -10,0,0,0, -10,0,5,10, -10,5,5,10,
          -10,0,10,10, -10,10,10,10, -10,5,0,0, -20,-10,-10,-10)),
      _x((0,0,0,0, 5,10,10,10, -5,0,0,0, -5,0,0,0,
          -5,0,0,0, -5,0,0,0, -5,0,0,0, 0,0,0,5)),
      (-20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10,
       -10,0,5,5,5,5,0,-10, -5,0,5,5,5,5,0,-5, 0,0,5,5,5,5,0,-5,
       -10,5,5,5,5,5,0,-10, -10,0,5,0,0,0,0,-10,
       -20,-10,-10,-5,-5,-10,-10,-20),
      _x((-30,-40,-40,-50, -30,-40,-40,-50, -30,-40,-40,-50, -30,-40,-40,-50,
          -20,-30,-30,-40, -10,-20,-20,-20, 20,20,0,0, 20,30,10,0)))

_r = random.Random(0xC0FFEE)
ZP = [[_r.getrandbits(64) for _ in range(128)] for _ in range(13)]
ZS = _r.getrandbits(64)
FL = "abcdefgh"

B = [0] * 128
S = 1
C = 0
E = -1
KK = [0, 0]
ZH = 0
MG = 0
U = []


def fen(x):
    global B, S, C, E, KK, ZH, MG, U
    ps = x.split()
    B = [0] * 128
    MG = ZH = 0
    sq = 0
    for c in ps[0]:
        if c == "/":
            sq += 8
        elif c.isdigit():
            sq += int(c)
        else:
            p = "pnbrqk".index(c.lower()) + 1
            if c.islower():
                p = -p
            ad(sq, p, 1)
            B[sq] = p
            sq += 1
    S = 1 if ps[1] == "w" else -1
    C = 0
    for c, bit in (("K", 1), ("Q", 2), ("k", 4), ("q", 8)):
        if c in ps[2]:
            C |= bit
    E = -1
    if ps[3] != "-":
        E = (8 - int(ps[3][1])) * 16 + FL.index(ps[3][0])
    if S < 0:
        ZH ^= ZS
    U = []


def ad(sq, p, s):
    global MG, ZH
    a = abs(p)
    j = sq if p > 0 else sq ^ 0x70
    j = (j >> 4) * 8 + (j & 7)
    w = V[a] + PM[a - 1][j]
    if p < 0:
        w = -w
    MG += s * w
    ZH ^= ZP[p + 6][sq]
    if a == 6 and s > 0:
        KK[0 if p > 0 else 1] = sq


def atk(sq, by):
    for d in ((15, 17) if by > 0 else (-15, -17)):
        t = sq + d
        if not t & 0x88 and B[t] == by:
            return True
    for d in KD:
        t = sq + d
        if not t & 0x88 and B[t] == 2 * by:
            return True
    for d in GD:
        t = sq + d
        if not t & 0x88 and B[t] == 6 * by:
            return True
    for ds, ks in ((BD, (3, 5)), (RD, (4, 5))):
        for d in ds:
            t = sq + d
            while not t & 0x88:
                p = B[t]
                if p:
                    if p == ks[0] * by or p == ks[1] * by:
                        return True
                    break
                t += d
    return False


def ic(col):
    return atk(KK[0 if col > 0 else 1], -col)


# Move int: from | to<<7 | promo<<14, promo a piece type 2..5 or 0.
# mk() snapshots every square and scalar it is about to touch, so un()
# is a plain restore with nothing to re-derive.
def mk(m):
    global C, E, S, ZH
    frm, to, pr = m & 127, (m >> 7) & 127, (m >> 14) & 7
    pc = B[frm]
    cap = B[to]
    epc = pc in (1, -1) and to == E and not cap and (frm & 7) != (to & 7)
    if epc:
        cap = -pc
    cst = pc in (6, -6) and abs(to - frm) == 2
    sqs = [frm, to]
    if epc:
        sqs.append(to + 16 if pc > 0 else to - 16)
    if cst:
        rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
        sqs += [rf, rt]
    U.append((sqs, [B[q] for q in sqs], C, E, ZH, MG, KK[0], KK[1]))
    nep = -1
    if cap and not epc:
        ad(to, cap, -1)
    if epc:
        vic = sqs[2]
        ad(vic, B[vic], -1)
        B[vic] = 0
    B[frm] = 0
    ad(frm, pc, -1)
    placed = pr * S if pr else pc
    B[to] = placed
    ad(to, placed, 1)
    if cst:
        rk = B[rf]
        B[rf] = 0
        ad(rf, rk, -1)
        B[rt] = rk
        ad(rt, rk, 1)
    if pc in (1, -1) and abs(to - frm) == 32:
        nep = (frm + to) // 2
    if pc == 6:
        C &= ~3
    elif pc == -6:
        C &= ~12
    for sq, bit in ((119, 1), (112, 2), (7, 4), (0, 8)):
        if frm == sq or to == sq:
            C &= ~bit
    E = nep
    S = -S
    ZH ^= ZS


def un():
    global C, E, S, ZH, MG
    sqs, vals, C, E, ZH, MG, k0, k1 = U.pop()
    for q, v in zip(sqs, vals):
        B[q] = v
    KK[0], KK[1] = k0, k1
    S = -S


def pm(ms, sq, t, last):
    if (t >> 4) == last:
        for pr in (5, 4, 3, 2):
            ms.append(sq | t << 7 | pr << 14)
    else:
        ms.append(sq | t << 7)


def gn(cp=False):
    ms = []
    for sq in range(128):
        if sq & 0x88:
            continue
        p = B[sq]
        if not p or (p > 0) != (S > 0):
            continue
        a = abs(p)
        if a == 1:
            st = -16 if S > 0 else 16
            home = 6 if S > 0 else 1
            last = 0 if S > 0 else 7
            one = sq + st
            if not B[one] and (not cp or (one >> 4) == last):
                pm(ms, sq, one, last)
                if (one >> 4) != last:
                    two = sq + 2 * st
                    if (sq >> 4) == home and not B[two]:
                        ms.append(sq | two << 7)
            for d in (st - 1, st + 1):
                t = sq + d
                if t & 0x88:
                    continue
                if B[t] and (B[t] > 0) != (S > 0):
                    pm(ms, sq, t, last)
                elif t == E:
                    ms.append(sq | t << 7)
        else:
            for d in DR[a - 2]:
                t = sq + d
                while not t & 0x88:
                    q = B[t]
                    if not q:
                        if not cp:
                            ms.append(sq | t << 7)
                    else:
                        if (q > 0) != (S > 0):
                            ms.append(sq | t << 7)
                        break
                    if a == 2 or a == 6:
                        break
                    t += d
            if a == 6 and not cp:
                cs(sq, ms)
    return ms


def cs(sq, ms):
    ksq = 116 if S > 0 else 4
    if sq != ksq:
        return
    bits = (1, 2) if S > 0 else (4, 8)
    rk = 4 * S
    en = -S
    if C & bits[0] and B[ksq + 3] == rk and not B[ksq + 1] and not B[ksq + 2] \
            and not atk(ksq, en) and not atk(ksq + 1, en) \
            and not atk(ksq + 2, en):
        ms.append(ksq | (ksq + 2) << 7)
    if C & bits[1] and B[ksq - 4] == rk and not B[ksq - 1] \
            and not B[ksq - 2] and not B[ksq - 3] \
            and not atk(ksq, en) and not atk(ksq - 1, en) \
            and not atk(ksq - 2, en):
        ms.append(ksq | (ksq - 2) << 7)


def ev():
    sc = MG
    wps = []
    bps = []
    bmn = [9] * 8
    wmx = [-1] * 8
    for sq in range(128):
        if sq & 0x88:
            continue
        p = B[sq]
        if p == 1:
            wps.append(sq)
            if sq >> 4 > wmx[sq & 7]:
                wmx[sq & 7] = sq >> 4
        elif p == -1:
            bps.append(sq)
            if sq >> 4 < bmn[sq & 7]:
                bmn[sq & 7] = sq >> 4
    for sq in wps:
        f, row = sq & 7, sq >> 4
        if min(bmn[f - 1] if f else 9, bmn[f], bmn[f + 1] if f < 7 else 9) >= row:
            sc += PB[7 - row]
    for sq in bps:
        f, row = sq & 7, sq >> 4
        if max(wmx[f - 1] if f else -1, wmx[f], wmx[f + 1] if f < 7 else -1) <= row:
            sc -= PB[row]
    return sc * S


TT = {}
ND = 0
PATH = []


class Abort(Exception):
    pass


def oc(m, tm):
    if m == tm:
        return 1 << 28
    cap = B[(m >> 7) & 127]
    if cap:
        return (1 << 24) + V[abs(cap)] * 32 - V[abs(B[m & 127])]
    if (m >> 14) & 7:
        return (1 << 24) + 900
    return 0


def qs(a, b, ply):
    global ND
    ND += 1
    if ND > NB:
        raise Abort
    cl = S
    ck = ic(cl)
    if ck:
        st = -MATE - 1
    else:
        st = ev()
        if st >= b:
            return b
        if st > a:
            a = st
    if ply >= 40:
        return ev()
    ms = gn(cp=not ck)
    ms.sort(key=lambda m: oc(m, 0), reverse=True)
    lg = 0
    for m in ms:
        mk(m)
        if ic(cl):
            un()
            continue
        lg += 1
        sc = -qs(-b, -a, ply + 1)
        un()
        if sc >= b:
            return b
        if sc > a:
            a = sc
    if ck and lg == 0:
        return -MATE + ply
    return a


def sr(d, a, b, ply):
    global ND
    if ply > 0:
        if ZH in PATH:
            return 0
        ND += 1
        if ND > NB:
            raise Abort
    if d <= 0:
        return qs(a, b, ply)
    ck = ic(S)
    tm = TT.get(ZH, 0)
    PATH.append(ZH)
    try:
        ms = gn()
        ms.sort(key=lambda m: oc(m, tm), reverse=True)
        cl = S
        bs = -MATE - 1
        bm = 0
        lg = 0
        for m in ms:
            isp = bool(B[(m >> 7) & 127]) or (m >> 14) & 7
            mk(m)
            if ic(cl):
                un()
                continue
            lg += 1
            if lg == 1:
                sc = -sr(d - 1, -b, -a, ply + 1)
            else:
                red = False
                if d >= 3 and lg >= 4 and not ck and not isp and not ic(S):
                    sc = -sr(d - 2, -a - 1, -a, ply + 1)
                    red = True
                else:
                    sc = -sr(d - 1, -a - 1, -a, ply + 1)
                if red and sc > a:
                    sc = -sr(d - 1, -a - 1, -a, ply + 1)
                if a < sc < b:
                    sc = -sr(d - 1, -b, -a, ply + 1)
            un()
            if sc > bs:
                bs = sc
                bm = m
            if sc > a:
                a = sc
            if a >= b:
                break
    finally:
        PATH.pop()
    if lg == 0:
        return -MATE + ply if ck else 0
    TT[ZH] = bm
    return bs


def go(legal):
    global ND, PATH
    if len(legal) == 1:
        return pu(legal[0])
    if len(TT) > 300000:
        TT.clear()
    PATH = []
    best = pu(legal[0])
    ND = 0
    dp = 1
    while dp <= 64:
        st = ND
        try:
            sr(dp, -MATE - 1, MATE + 1, 0)
        except Abort:
            break
        if TT.get(ZH):
            best = TT[ZH]
        us = ND - st
        if us > NB // 2 or ND + 2 * us > NB:
            break
        dp += 1
    return best


def po(p, bd):
    rq = urllib.request.Request(
        ENV + p, data=json.dumps(bd).encode(),
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(rq) as r:
        return json.load(r)


def uu(m):
    f, t = m & 127, (m >> 7) & 127
    u = FL[f & 7] + str(8 - (f >> 4)) + FL[t & 7] + str(8 - (t >> 4))
    pr = (m >> 14) & 7
    if pr:
        u += "nbrq"[pr - 2]
    return u


def pu(u):
    frm = FL.index(u[0]) + (8 - int(u[1])) * 16
    to = FL.index(u[2]) + (8 - int(u[3])) * 16
    pr = "nbrq".index(u[4]) + 2 if len(u) > 4 else 0
    return frm | to << 7 | pr << 14


def main():
    while True:
        g = po("/game", {})
        if g["status"] == "done":
            break
        while g["status"] == "your_move":
            fen(g["fen"])
            m = go(g["legal_moves"])
            g = po("/move", {"game": g["game"], "move": uu(m)})


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pcd_to_map.py — FAST-LIO 가 저장한 3D 포인트클라우드(.pcd)를
Nav2 가 쓰는 2D 점유격자 지도(.pgm + .yaml)로 변환한다.

왜 필요한가
───────────────────────────────────────────────────────────────────────
주행 중에 SLAM 으로 지도와 위치를 동시에 추정하면 오차가 계속 쌓인다.
휴머노이드는 보행 진동 때문에 특히 심하다 — 로봇이 엉뚱한 방향으로 간다.

그래서 두 단계로 나눈다.

    1단계) 걸어다니며 지도를 만들고 저장한다 (FAST-LIO + savemap)
    2단계) 그 지도를 **고정**해두고, AMCL 이 현재 스캔을 지도에 맞춰
           위치만 찾는다. 지도가 안 변하므로 오차가 누적되지 않는다.

이 스크립트가 1단계와 2단계를 잇는다.

동작 방식
───────────────────────────────────────────────────────────────────────
3D 점을 위에서 내려다본 격자에 떨어뜨린다.

    · 장애물 판정: --z-min ~ --z-max 구간의 점.
      한 칸에 --hits 개 이상 모이면 장애물(검정)
    · 자유공간 판정: **바닥으로 본 점**(--z-min 미만)이 있는 칸.
      라이다가 바닥을 봤다는 것은 그 위가 비어 있다는 뜻이다 → 흰색
    · 관측 안 된 곳 → 미지(회색)

바닥 점으로 자유공간을 채우는 것이 핵심이다. 이걸 안 하면 방 안쪽이
전부 미지로 남아 Nav2 가 "갈 수 있는지 모르겠다"며 경로를 못 찾는다.

사용
───────────────────────────────────────────────────────────────────────
    pip install open3d          # 또는 numpy 만으로도 동작(ASCII pcd 한정)

    python3 pcd_to_map.py ~/g1_real/maps/lab.pcd \\
        -o ~/g1_real/maps/lab_2d \\
        --z-min -1.2 --z-max -0.2

    → lab_2d.pgm + lab_2d.yaml 생성

높이 범위(--z-min/--z-max)가 이 작업의 핵심이다.
FAST-LIO 지도의 원점은 **시작 시점의 LiDAR 위치**(바닥에서 약 1.3m)다.
따라서 바닥은 z ≈ -1.3, 사람 허리 높이는 z ≈ -0.7 근처다.

    · 너무 낮게 잡으면 바닥이 장애물로 찍힌다
    · 너무 높게 잡으면 책상·의자를 놓친다
    · 기본값(-1.2 ~ -0.2)은 바닥 위 10cm ~ 110cm 구간이다

변환 후 반드시 눈으로 확인할 것. 벽이 선으로 보이고 통로가 흰색이면 정상.
"""
import argparse
import os
import sys

import numpy as np


def load_pcd(path):
    """PCD 를 (N,3) numpy 배열로 읽는다. open3d 가 있으면 그걸 쓴다."""
    try:
        import open3d as o3d
        pcd = o3d.io.read_point_cloud(path)
        pts = np.asarray(pcd.points)
        if pts.size == 0:
            sys.exit(f"포인트가 없습니다: {path}")
        return pts
    except ImportError:
        pass

    # open3d 가 없으면 직접 파싱한다(binary/ascii 모두 시도).
    print("  open3d 가 없어 직접 파싱합니다. (pip install open3d 권장)")
    with open(path, "rb") as f:
        header, fields, size, typ, count = [], None, None, None, None
        n_points, data_type = 0, "ascii"
        while True:
            line = f.readline().decode("ascii", "ignore").strip()
            header.append(line)
            if line.startswith("FIELDS"):
                fields = line.split()[1:]
            elif line.startswith("SIZE"):
                size = [int(x) for x in line.split()[1:]]
            elif line.startswith("TYPE"):
                typ = line.split()[1:]
            elif line.startswith("COUNT"):
                count = [int(x) for x in line.split()[1:]]
            elif line.startswith("POINTS"):
                n_points = int(line.split()[1])
            elif line.startswith("DATA"):
                data_type = line.split()[1]
                break

        if data_type == "ascii":
            arr = np.loadtxt(f, usecols=(0, 1, 2))
            return arr.reshape(-1, 3)

        if data_type != "binary":
            sys.exit(f"binary_compressed 형식은 open3d 가 필요합니다: pip install open3d")

        np_type = {"F": "f", "U": "u", "I": "i"}
        dtype = np.dtype([(fields[i], np_type[typ[i]] + str(size[i]))
                          for i in range(len(fields)) if count[i] == 1])
        raw = np.frombuffer(f.read(n_points * dtype.itemsize), dtype=dtype)
        return np.stack([raw["x"], raw["y"], raw["z"]], axis=1).astype(np.float64)


def main():
    ap = argparse.ArgumentParser(
        description="FAST-LIO 의 3D PCD 를 Nav2 용 2D 점유격자로 변환")
    ap.add_argument("pcd", help="입력 .pcd 경로")
    ap.add_argument("-o", "--out", required=True,
                    help="출력 경로(확장자 없이). 예: ~/g1_real/maps/lab_2d")
    ap.add_argument("--resolution", type=float, default=0.05,
                    help="격자 한 칸 크기 [m] (기본 0.05)")
    ap.add_argument("--z-min", type=float, default=-1.2,
                    help="이 높이 미만은 버린다 [m]. 바닥 제거용 (기본 -1.2)")
    ap.add_argument("--z-max", type=float, default=-0.2,
                    help="이 높이 초과는 버린다 [m]. 천장 제거용 (기본 -0.2)")
    ap.add_argument("--hits", type=int, default=3,
                    help="한 칸에 이만큼 이상 점이 있어야 장애물로 본다 (기본 3)")
    ap.add_argument("--floor-margin", type=float, default=0.25,
                    help="바닥으로 볼 두께 [m]. z 최솟값부터 이만큼을 바닥으로 "
                         "보고 자유공간으로 채운다 (기본 0.25)")
    ap.add_argument("--fill", type=int, default=1,
                    help="자유공간을 넓힐 반경 [칸] (기본 1 = 5cm)")
    ap.add_argument("--margin", type=float, default=1.0,
                    help="지도 가장자리 여백 [m] (기본 1.0)")
    args = ap.parse_args()

    pcd_path = os.path.expanduser(args.pcd)
    out_base = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)

    print(f"\n  읽는 중: {pcd_path}")
    pts = load_pcd(pcd_path)
    print(f"  전체 점: {len(pts):,}")
    print(f"  z 범위 : {pts[:, 2].min():.2f} ~ {pts[:, 2].max():.2f} m")

    # ── 높이로 자르기 ────────────────────────────────────────────────
    # 장애물: 지정한 높이 구간의 점
    mask = (pts[:, 2] >= args.z_min) & (pts[:, 2] <= args.z_max)
    sel = pts[mask]
    print(f"  장애물 구간 {args.z_min} ~ {args.z_max} m: {len(sel):,} 점 "
          f"({100 * len(sel) / max(len(pts), 1):.1f}%)")

    # 자유공간: 바닥으로 본 점.
    # 라이다가 바닥을 봤다면 그 위는 비어 있다는 뜻이다.
    z_floor_lo = pts[:, 2].min()
    z_floor_hi = z_floor_lo + args.floor_margin
    floor = pts[(pts[:, 2] >= z_floor_lo) & (pts[:, 2] <= z_floor_hi)]
    print(f"  바닥 구간   {z_floor_lo:.2f} ~ {z_floor_hi:.2f} m: {len(floor):,} 점")

    if len(sel) < 100:
        sys.exit("\n  [실패] 남은 점이 너무 적습니다.\n"
                 "  --z-min / --z-max 를 조정하세요. 위에 찍힌 z 범위를 참고하면,\n"
                 "  바닥은 최솟값 근처이고 그보다 10cm~1.2m 위를 잡으면 됩니다.")

    # ── 격자 만들기 ──────────────────────────────────────────────────
    res = args.resolution
    x_min, y_min = sel[:, 0].min() - args.margin, sel[:, 1].min() - args.margin
    x_max, y_max = sel[:, 0].max() + args.margin, sel[:, 1].max() + args.margin
    w = int(np.ceil((x_max - x_min) / res))
    h = int(np.ceil((y_max - y_min) / res))
    print(f"  지도 크기: {w} x {h} 칸  ({w * res:.1f} x {h * res:.1f} m)")

    if w * h > 60_000_000:
        sys.exit("  [실패] 지도가 너무 큽니다. --resolution 을 키우세요(예: 0.1).")

    def to_grid(arr):
        gx = ((arr[:, 0] - x_min) / res).astype(np.int32)
        gy = ((arr[:, 1] - y_min) / res).astype(np.int32)
        np.clip(gx, 0, w - 1, out=gx)
        np.clip(gy, 0, h - 1, out=gy)
        return gx, gy

    # 장애물
    ix, iy = to_grid(sel)
    counts = np.zeros((h, w), dtype=np.int32)
    np.add.at(counts, (iy, ix), 1)
    occupied = counts >= args.hits
    print(f"  장애물 칸: {occupied.sum():,}")

    # ── 자유공간 = 바닥이 관측된 칸 ──────────────────────────────────
    free = np.zeros((h, w), dtype=bool)
    if len(floor):
        fx, fy = to_grid(floor)
        free[fy, fx] = True

    # 바닥 점이 성기면 칸 사이에 구멍이 생긴다. 조금 넓혀 메운다.
    r = args.fill
    if r > 0:
        ys, xs = np.nonzero(free)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > r * r:
                    continue
                free[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)] = True

    free &= ~occupied
    print(f"  자유공간 칸: {free.sum():,}")

    if free.sum() < occupied.sum():
        print("\n  [주의] 자유공간이 장애물보다 적습니다.")
        print("        --floor-margin 을 키우거나 --z-min 을 올려보세요.")
        print("        자유공간이 부족하면 Nav2 가 경로를 못 찾습니다.")

    # ── PGM 값 ───────────────────────────────────────────────────────
    #   0   = 장애물(검정)
    #   254 = 자유공간(흰색)
    #   205 = 미지(회색)
    img = np.full((h, w), 205, dtype=np.uint8)
    img[free] = 254
    img[occupied] = 0

    # PGM 은 위에서 아래로 저장한다. 지도 좌표는 아래에서 위이므로 뒤집는다.
    img = np.flipud(img)

    pgm_path = out_base + ".pgm"
    with open(pgm_path, "wb") as f:
        f.write(f"P5\n{w} {h}\n255\n".encode("ascii"))
        f.write(img.tobytes())

    yaml_path = out_base + ".yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(f"""image: {os.path.basename(pgm_path)}
mode: trinary
resolution: {res}
# origin: 지도 왼쪽아래 구석이 map 좌표계의 어디인지 [x, y, yaw]
origin: [{x_min:.4f}, {y_min:.4f}, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""")

    print(f"\n  저장 완료")
    print(f"    {pgm_path}")
    print(f"    {yaml_path}")
    print(f"\n  확인:  eog {pgm_path}     (또는 이미지 뷰어로 열기)")
    print("  벽이 검은 선, 로봇이 다닌 곳이 흰색으로 보이면 정상입니다.\n")
    print("  증상별 조정:")
    print("    바닥이 통째로 검다        → --z-min 을 올린다")
    print("    벽이 안 보인다            → --z-max 를 올리거나 --hits 를 낮춘다")
    print("    흰색 영역이 거의 없다     → --floor-margin 을 키운다 (0.4 등)")
    print("    흰색에 구멍이 숭숭하다    → --fill 을 2~3 으로 올린다\n")


if __name__ == "__main__":
    main()

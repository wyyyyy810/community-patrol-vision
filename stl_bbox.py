"""解析 STL（binary/ascii）并输出真实包围盒，用于独立校验 URDF 里手写的 collision box。"""
import struct, os, glob, sys

def read_stl(path):
    with open(path, "rb") as f:
        head = f.read(84)
        if len(head) < 84:
            return None
        n = struct.unpack("<I", head[80:84])[0]
        expect = 84 + n * 50
        size = os.path.getsize(path)
        pts = []
        if expect == size:  # binary
            f.seek(84)
            data = f.read()
            for i in range(n):
                off = i * 50
                # 12 floats: normal(3) + v1(3) + v2(3) + v3(3)
                vals = struct.unpack_from("<12f", data, off)
                for j in range(3, 12, 3):
                    pts.append((vals[j], vals[j+1], vals[j+2]))
            return pts
        # ascii fallback
        f.seek(0)
        pts = []
        for line in f.read().decode("utf-8", "ignore").splitlines():
            line = line.strip()
            if line.startswith("vertex"):
                p = line.split()
                pts.append((float(p[1]), float(p[2]), float(p[3])))
        return pts or None

def bbox(pts, scale):
    xs = [p[0]*scale for p in pts]; ys = [p[1]*scale for p in pts]; zs = [p[2]*scale for p in pts]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))

for path in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "rbot/src/robot/rlai_meshes/meshes/*.stl"))):
    pts = read_stl(path)
    name = os.path.basename(path)
    if not pts:
        print(f"{name:32s} -> 解析失败/空")
        continue
    (x0,x1),(y0,y1),(z0,z1) = bbox(pts, 0.001)
    print(f"{name:32s} tris={len(pts)//3:6d}")
    print(f"    X: [{x0:+.4f}, {x1:+.4f}]  尺寸 {x1-x0:.4f} m")
    print(f"    Y: [{y0:+.4f}, {y1:+.4f}]  尺寸 {y1-y0:.4f} m")
    print(f"    Z: [{z0:+.4f}, {z1:+.4f}]  尺寸 {z1-z0:.4f} m")

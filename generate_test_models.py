import struct
import math

def write_stl(filename, triangles):
    with open(filename, 'wb') as f:
        # Header (80 bytes)
        f.write(b'Generated Python Script' + b'\x00' * 57)
        # Number of triangles (4 bytes)
        f.write(struct.pack('<I', len(triangles)))
        
        for normal, v1, v2, v3 in triangles:
            # Normal
            f.write(struct.pack('<3f', *normal))
            # Vertices
            f.write(struct.pack('<3f', *v1))
            f.write(struct.pack('<3f', *v2))
            f.write(struct.pack('<3f', *v3))
            # Attribute byte count
            f.write(struct.pack('<H', 0))

def compute_normal(v1, v2, v3):
    ux, uy, uz = v2[0]-v1[0], v2[1]-v1[1], v2[2]-v1[2]
    vx, vy, vz = v3[0]-v1[0], v3[1]-v1[1], v3[2]-v1[2]
    nx = uy*vz - uz*vy
    ny = uz*vx - ux*vz
    nz = ux*vy - uy*vx
    l = math.sqrt(nx*nx + ny*ny + nz*nz)
    if l == 0: return (0,0,0)
    return (nx/l, ny/l, nz/l)

def generate_cube():
    # 8 vertices
    s = 1.0
    v = [
        (-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
        (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)
    ]
    # 12 triangles (2 per face)
    indices = [
        # Front
        (0, 1, 2), (0, 2, 3),
        # Back
        (5, 4, 7), (5, 7, 6),
        # Left
        (4, 0, 3), (4, 3, 7),
        # Right
        (1, 5, 6), (1, 6, 2),
        # Top
        (3, 2, 6), (3, 6, 7),
        # Bottom
        (4, 5, 1), (4, 1, 0)
    ]
    
    triangles = []
    for i1, i2, i3 in indices:
        v1, v2, v3 = v[i1], v[i2], v[i3]
        n = compute_normal(v1, v2, v3)
        triangles.append((n, v1, v2, v3))
        
    write_stl('Cube.stl', triangles)
    print("Cube.stl generated.")

def generate_sphere(radius=1.0, sectors=30, stacks=30):
    vertices = []
    for i in range(stacks + 1):
        stack_angle = math.pi / 2 - i * math.pi / stacks
        xy = radius * math.cos(stack_angle)
        z = radius * math.sin(stack_angle)
        
        for j in range(sectors + 1):
            sector_angle = j * 2 * math.pi / sectors
            x = xy * math.cos(sector_angle)
            y = xy * math.sin(sector_angle)
            vertices.append((x, y, z))
            
    triangles = []
    for i in range(stacks):
        k1 = i * (sectors + 1)
        k2 = k1 + sectors + 1
        
        for j in range(sectors):
            if i != 0:
                v1, v2, v3 = vertices[k1], vertices[k2], vertices[k1 + 1]
                triangles.append((compute_normal(v1, v2, v3), v1, v2, v3))
            if i != (stacks - 1):
                v1, v2, v3 = vertices[k1 + 1], vertices[k2], vertices[k2 + 1]
                triangles.append((compute_normal(v1, v2, v3), v1, v2, v3))
            k1 += 1
            k2 += 1

    write_stl('Sphere.stl', triangles)
    print("Sphere.stl generated.")

if __name__ == '__main__':
    generate_cube()
    generate_sphere()

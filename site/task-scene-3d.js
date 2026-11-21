(() => {
  'use strict';

  const ROOM = { width: 7.6, depth: 5.4, height: 3.2, gap: 0.72 };
  const MATERIALS = {
    wall: { color: '#776a61', grain: 0.018, specular: 0.12 },
    wallSide: { color: '#464149', grain: 0.018, specular: 0.12 },
    wallAccent: { color: '#71646c', specular: 0.18 },
    wallPanel: { color: '#3e3840', grain: 0.028, specular: 0.2 },
    floorBase: { color: '#514438', grain: 0.07, specular: 0.08 },
    floorA: { color: '#80664d', grain: 0.075, specular: 0.1 },
    floorB: { color: '#786047', grain: 0.075, specular: 0.1 },
    floorC: { color: '#846a50', grain: 0.075, specular: 0.1 },
    wood: { color: '#80634b', grain: 0.11, specular: 0.15 },
    woodLight: { color: '#ad8966', grain: 0.09, specular: 0.18 },
    woodDark: { color: '#443534', grain: 0.06, specular: 0.14 },
    fabric: { color: '#59545b', grain: 0.028, specular: 0.05 },
    fabricLight: { color: '#aaa0a0', grain: 0.022, specular: 0.06 },
    linen: { color: '#c0b3a8', grain: 0.028, specular: 0.05 },
    metal: { color: '#9899a0', grain: 0.008, specular: 0.78 },
    brass: { color: '#b18b5c', grain: 0.01, specular: 0.9 },
    fanBlade: { color: '#c9bdad', grain: 0.01, specular: 0.42 },
    darkMetal: { color: '#35383b', grain: 0.01, specular: 0.65 },
    glass: { color: '#78909a', grain: 0, specular: 0.65, emission: '#18242b' },
    screen: { color: '#172b35', grain: 0, specular: 0.5, emission: '#071219' },
    screenLine: { color: '#8aa6ad', grain: 0, specular: 0.1, emission: '#243b40' },
    lightStrip: { color: '#f0c995', grain: 0, specular: 0.16, emission: '#d49a50' },
    ceramic: { color: '#d3cbd0', grain: 0, specular: 0.48 },
    ceramicDark: { color: '#45434b', grain: 0, specular: 0.32 },
    plant: { color: '#4b6258', grain: 0.035, specular: 0.16 },
    plantLight: { color: '#748b7a', grain: 0.022, specular: 0.16 },
    skin: { color: '#b68c70', grain: 0.012, specular: 0.09 },
    hair: { color: '#463c39', grain: 0.02, specular: 0.08 },
    clothing: { color: '#777677', grain: 0.025, specular: 0.045 },
    clothingLight: { color: '#aca39b', grain: 0.02, specular: 0.045 },
    petal: { color: '#89916e', grain: 0.02, specular: 0.1 },
    bulbOff: { color: '#71695e', specular: 0.25 },
    bulbTarget: { color: '#c4a8d4', emission: '#33263b', specular: 0.35 },
    bulbCandidate: { color: '#b9a7c1', emission: '#201a24', specular: 0.35 },
    bulbScheduled: { color: '#d0b88d', emission: '#2d2517', specular: 0.35 },
    bulbOn: { color: '#ffe0a5', emission: '#ffb949', specular: 0.42 },
    bulbInspected: { color: '#ffe0a5', emission: '#e9a949', specular: 0.42 },
    bulbWarm: { color: '#ffc978', emission: '#9e5f20', specular: 0.42 },
    selection: { color: '#b497c4', emission: '#392448', specular: 0.16 },
    shadow: { color: '#202028', specular: 0 },
    shadowSoft: { color: '#3b3942', specular: 0 },
    white: { color: '#ded8cf', specular: 0.18 },
    black: { color: '#1b1c1e', specular: 0.28 },
    accent: { color: '#b68e6e', grain: 0.04, specular: 0.12 },
    tile: { color: '#79736e', grain: 0, specular: 0.22 }
  };

  const vertexSource = `
    attribute vec3 aPosition;
    attribute vec3 aNormal;
    uniform mat4 uViewProjection;
    varying vec3 vPosition;
    varying vec3 vNormal;
    void main() {
      vPosition = aPosition;
      vNormal = normalize(aNormal);
      gl_Position = uViewProjection * vec4(aPosition, 1.0);
    }
  `;
  const fragmentSource = `
    precision mediump float;
    uniform vec3 uCamera;
    uniform vec3 uColor;
    uniform vec3 uEmission;
    uniform float uSpecular;
    uniform float uGrain;
    uniform vec3 uPointPosition[4];
    uniform vec3 uPointColor[4];
    uniform float uPointPower[4];
    uniform float uTime;
    uniform float uActivity;
    varying vec3 vPosition;
    varying vec3 vNormal;
    float hash(vec3 p) {
      return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453);
    }
    void main() {
      vec3 normal = normalize(vNormal);
      vec3 viewDir = normalize(uCamera - vPosition);
      vec3 sunDir = normalize(vec3(-0.45, 0.82, 0.56));
      float diffuse = max(dot(normal, sunDir), 0.0);
      // A soft studio fill keeps the room readable while the directional and
      // device lights provide the scene's depth. The old flat 0.42 base made
      // unlit surfaces collapse into the black page.
      float hemisphere = 0.38 + 0.24 * max(normal.y, 0.0);
      vec3 color = uColor * (hemisphere + 0.54 * diffuse);
      vec3 halfDir = normalize(sunDir + viewDir);
      float spec = pow(max(dot(normal, halfDir), 0.0), 34.0) * uSpecular;
      color += vec3(spec * 0.72);
      for (int i = 0; i < 4; i++) {
        vec3 toLight = uPointPosition[i] - vPosition;
        float distanceToLight = length(toLight);
        vec3 lightDir = normalize(toLight);
        float attenuation = uPointPower[i] / (1.0 + distanceToLight * distanceToLight * 0.16);
        float contribution = max(dot(normal, lightDir), 0.0) * attenuation;
        color += uColor * uPointColor[i] * contribution * 0.92;
        vec3 pointHalf = normalize(lightDir + viewDir);
        color += uPointColor[i] * pow(max(dot(normal, pointHalf), 0.0), 40.0) * attenuation * uSpecular * 0.55;
      }
      float grain = (sin(vPosition.x * 19.0 + sin(vPosition.z * 5.0)) * 0.5 + hash(floor(vPosition * 18.0)) * 0.5) * uGrain;
      color *= 1.0 + grain;
      float signal = 0.76 + 0.24 * sin(uTime * 2.4 - (vPosition.x + vPosition.z) * 0.8);
      color += uEmission * (1.0 + uActivity * signal * 0.8);
      // A restrained rim catches the silhouette of furniture and gives the
      // low-poly forms a cleaner product-render edge.
      float rim = pow(1.0 - max(dot(normal, viewDir), 0.0), 3.0);
      color += vec3(0.055, 0.045, 0.06) * rim * (0.35 + uSpecular);
      color = color / (vec3(1.0) + max(color, vec3(0.0)) * 0.18);
      color = pow(max(color, vec3(0.0)), vec3(0.88));
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const vec3 = (x, y, z) => [x, y, z];
  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const mul = (a, value) => [a[0] * value, a[1] * value, a[2] * value];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const length = (a) => Math.hypot(a[0], a[1], a[2]);
  const normalize = (a) => mul(a, 1 / (length(a) || 1));

  function colorToVec(color) {
    const value = color.replace('#', '');
    return [0, 2, 4].map((index) => parseInt(value.slice(index, index + 2), 16) / 255);
  }

  function identity() {
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  }

  function multiplyMatrix(a, b) {
    const out = new Array(16);
    for (let column = 0; column < 4; column++) {
      for (let row = 0; row < 4; row++) {
        out[column * 4 + row] = a[row] * b[column * 4] + a[4 + row] * b[column * 4 + 1] + a[8 + row] * b[column * 4 + 2] + a[12 + row] * b[column * 4 + 3];
      }
    }
    return out;
  }

  function perspective(fovy, aspect, near, far) {
    const f = 1 / Math.tan(fovy / 2);
    const nf = 1 / (near - far);
    return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
  }

  function lookAt(eye, center, up) {
    const z = normalize(sub(eye, center));
    const x = normalize(cross(up, z));
    const y = cross(z, x);
    return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, eye), -dot(y, eye), -dot(z, eye), 1];
  }

  function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(shader) || 'Shader compilation failed.';
      gl.deleteShader(shader);
      throw new Error(message);
    }
    return shader;
  }

  function createProgram(gl) {
    const program = gl.createProgram();
    gl.attachShader(program, createShader(gl, gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, createShader(gl, gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const message = gl.getProgramInfoLog(program) || 'Shader program linking failed.';
      gl.deleteProgram(program);
      throw new Error(message);
    }
    return program;
  }

  function makeGeometry() {
    const batches = new Map();
    const lights = [];
    const anchors = [];
    const ensure = (material) => {
      if (!batches.has(material)) batches.set(material, []);
      return batches.get(material);
    };
    const emit = (material, a, b, c, normal) => {
      const target = ensure(material);
      const points = [a, b, c];
      const normals = Array.isArray(normal[0]) ? normal : [normal, normal, normal];
      points.forEach((point, index) => {
        const vertexNormal = normals[index];
        target.push(point[0], point[1], point[2], vertexNormal[0], vertexNormal[1], vertexNormal[2]);
      });
    };
    const polygon = (material, points, normal) => {
      for (let index = 1; index < points.length - 1; index++) emit(material, points[0], points[index], points[index + 1], normal);
    };
    const face = (material, corners, normal) => {
      emit(material, corners[0], corners[1], corners[2], normal);
      emit(material, corners[0], corners[2], corners[3], normal);
    };

    function box(center, size, material, yaw = 0, offset = 0) {
      const [sx, sy, sz] = size.map((value) => value / 2);
      const cosine = Math.cos(yaw);
      const sine = Math.sin(yaw);
      const point = (x, y, z) => [center[0] + x * cosine + z * sine + offset, center[1] + y, center[2] - x * sine + z * cosine];
      const normal = (x, y, z) => [x * cosine + z * sine, y, -x * sine + z * cosine];
      // Small chamfers catch the studio lights on every hard edge. This keeps
      // the scene physically simple but removes the toy-like unbroken boxes.
      const bevel = Math.min(0.045, sx * 0.38, sy * 0.38, sz * 0.38);
      const bx = sx - bevel; const by = sy - bevel; const bz = sz - bevel;
      const P = (x, y, z) => point(x, y, z);
      const N = (x, y, z) => normalize(normal(x, y, z));
      face(material, [P(-bx, -by, sz), P(bx, -by, sz), P(bx, by, sz), P(-bx, by, sz)], N(0, 0, 1));
      face(material, [P(bx, -by, -sz), P(-bx, -by, -sz), P(-bx, by, -sz), P(bx, by, -sz)], N(0, 0, -1));
      face(material, [P(sx, -by, bz), P(sx, -by, -bz), P(sx, by, -bz), P(sx, by, bz)], N(1, 0, 0));
      face(material, [P(-sx, -by, -bz), P(-sx, -by, bz), P(-sx, by, bz), P(-sx, by, -bz)], N(-1, 0, 0));
      face(material, [P(-bx, sy, bz), P(bx, sy, bz), P(bx, sy, -bz), P(-bx, sy, -bz)], N(0, 1, 0));
      face(material, [P(-bx, -sy, -bz), P(bx, -sy, -bz), P(bx, -sy, bz), P(-bx, -sy, bz)], N(0, -1, 0));
      // Twelve chamfer strips around the six faces.
      [
        [[-by, sz], [by, sz], N(1, 0, 1)],
        [[-by, -sz], [by, -sz], N(1, 0, -1)],
        [[-by, sz], [by, sz], N(-1, 0, 1)],
        [[-by, -sz], [by, -sz], N(-1, 0, -1)]
      ].forEach(([ys, nz], index) => {
        const sxSign = index < 2 ? 1 : -1;
        const szSign = index % 2 === 0 ? 1 : -1;
        const [y0, y1] = ys;
        const z = szSign * sz; const zInner = szSign * bz; const x = sxSign * sx; const xInner = sxSign * bx;
        face(material, [P(xInner, y0, z), P(x, y0, zInner), P(x, y1, zInner), P(xInner, y1, z)], nz);
      });
      [
        [[-bx, bx], [sz, bz], N(0, 1, 1)],
        [[-bx, bx], [-sz, -bz], N(0, 1, -1)],
        [[-bx, bx], [sz, bz], N(0, -1, 1)],
        [[-bx, bx], [-sz, -bz], N(0, -1, -1)]
      ].forEach(([xs, zs], index) => {
        const sySign = index < 2 ? 1 : -1;
        const szSign = index % 2 === 0 ? 1 : -1;
        const [x0, x1] = xs; const y = sySign * sy; const yInner = sySign * by; const z = szSign * sz; const zInner = szSign * bz;
        face(material, [P(x0, y, zInner), P(x1, y, zInner), P(x1, yInner, z), P(x0, yInner, z)], zs);
      });
      [
        [[sx, bx], [sy, by], N(1, 1, 0)],
        [[sx, bx], [-sy, -by], N(1, -1, 0)],
        [[-sx, -bx], [sy, by], N(-1, 1, 0)],
        [[-sx, -bx], [-sy, -by], N(-1, -1, 0)]
      ].forEach(([xs, ys, edgeNormal], index) => {
        const szSign = index % 2 === 0 ? 1 : -1;
        const [x, xInner] = xs; const [y, yInner] = ys; const z = szSign * sz; const zInner = szSign * bz;
        face(material, [P(xInner, y, z), P(x, yInner, z), P(x, yInner, zInner), P(xInner, y, zInner)], edgeNormal);
      });
      // Triangular corner caps complete the bevel without visible cracks.
      [-1, 1].forEach((sxSign) => [-1, 1].forEach((sySign) => [-1, 1].forEach((szSign) => {
        const cornerNormal = N(sxSign, sySign, szSign);
        emit(material,
          P(sxSign * bx, sySign * sy, szSign * bz),
          P(sxSign * sx, sySign * by, szSign * bz),
          P(sxSign * bx, sySign * by, szSign * sz),
          cornerNormal);
      })));
    }

    function cylinder(center, radius, height, material, segments = 20, topRadius = radius, offset = 0, axis = [0, 1, 0]) {
      const direction = normalize(axis);
      const u = normalize(cross(Math.abs(direction[1]) > 0.95 ? [1, 0, 0] : [0, 1, 0], direction));
      const v = normalize(cross(direction, u));
      const point = (r, y, angle) => add(add(add(center, mul(direction, y)), mul(u, r * Math.cos(angle))), mul(v, r * Math.sin(angle)));
      const slope = (radius - topRadius) / Math.max(height, 0.001);
      for (let index = 0; index < segments; index++) {
        const a0 = index / segments * Math.PI * 2;
        const a1 = (index + 1) / segments * Math.PI * 2;
        const b0 = point(radius, -height / 2, a0);
        const b1 = point(radius, -height / 2, a1);
        const t0 = point(topRadius, height / 2, a0);
        const t1 = point(topRadius, height / 2, a1);
        const n0 = normalize(add(add(mul(u, Math.cos(a0)), mul(v, Math.sin(a0))), mul(direction, slope)));
        const n1 = normalize(add(add(mul(u, Math.cos(a1)), mul(v, Math.sin(a1))), mul(direction, slope)));
        emit(material, b0, b1, t1, [n0, n1, n1]);
        emit(material, b0, t1, t0, [n0, n1, n0]);
        const topCenter = add(center, mul(direction, height / 2));
        const bottomCenter = add(center, mul(direction, -height / 2));
        emit(material, topCenter, t0, t1, direction);
        emit(material, bottomCenter, b1, b0, mul(direction, -1));
      }
    }

    function sphere(center, radius, material, offset = 0, scale = [1, 1, 1], segments = 18, rings = 12) {
      const c = [center[0] + offset, center[1], center[2]];
      const vertex = (u, v) => [c[0] + Math.cos(u) * Math.sin(v) * radius * scale[0], c[1] + Math.cos(v) * radius * scale[1], c[2] + Math.sin(u) * Math.sin(v) * radius * scale[2]];
      for (let row = 0; row < rings; row++) {
        const v0 = row / rings * Math.PI;
        const v1 = (row + 1) / rings * Math.PI;
        for (let column = 0; column < segments; column++) {
          const u0 = column / segments * Math.PI * 2;
          const u1 = (column + 1) / segments * Math.PI * 2;
          const p00 = vertex(u0, v0); const p10 = vertex(u1, v0); const p11 = vertex(u1, v1); const p01 = vertex(u0, v1);
          const normal = (point) => normalize([(point[0] - c[0]) / (scale[0] * scale[0]), (point[1] - c[1]) / (scale[1] * scale[1]), (point[2] - c[2]) / (scale[2] * scale[2])]);
          emit(material, p00, p10, p11, [normal(p00), normal(p10), normal(p11)]);
          emit(material, p00, p11, p01, [normal(p00), normal(p11), normal(p01)]);
        }
      }
    }

    function rod(a, b, radius, material, offset = 0) {
      const center = mul(add(a, b), 0.5);
      center[0] += offset;
      cylinder(center, radius, length(sub(b, a)), material, 12, radius, 0, sub(b, a));
      sphere([a[0], a[1], a[2]], radius, material, offset, [1, 1, 1], 10, 7);
      sphere([b[0], b[1], b[2]], radius, material, offset, [1, 1, 1], 10, 7);
    }

    function leaf(center, radius, material, yaw, offset) {
      sphere(center, radius, material, offset, [0.42, 0.18, 1.15], 12, 8);
      const leafBatch = ensure(material);
      // A small stem through the leaf makes the plant read as a real object at scene scale.
      const dx = Math.sin(yaw) * radius * 1.1;
      const dz = Math.cos(yaw) * radius * 1.1;
      const start = [center[0] + offset, center[1] - radius * 0.5, center[2]];
      const end = [center[0] + offset + dx, center[1] + radius * 0.35, center[2] + dz];
      const axis = normalize(sub(end, start));
      const side = normalize(cross(axis, [0, 0, 1]));
      const p0 = add(start, mul(side, radius * 0.13));
      const p1 = sub(start, mul(side, radius * 0.13));
      const p2 = end;
      [p0, p1, p2].forEach((point, index) => leafBatch.push(point[0], point[1], point[2], 0, 1, 0));
    }

    function torus(center, major, minor, material, offset = 0, segments = 36, sides = 7, axis = [0, 1, 0]) {
      const direction = normalize(axis);
      const uAxis = normalize(cross(Math.abs(direction[1]) > 0.95 ? [1, 0, 0] : [0, 1, 0], direction));
      const vAxis = normalize(cross(direction, uAxis));
      for (let index = 0; index < segments; index++) {
        const u0 = index / segments * Math.PI * 2;
        const u1 = (index + 1) / segments * Math.PI * 2;
        for (let side = 0; side < sides; side++) {
          const v0 = side / sides * Math.PI * 2;
          const v1 = (side + 1) / sides * Math.PI * 2;
          const point = (u, v) => add(add(add([center[0] + offset, center[1], center[2]], mul(uAxis, (major + minor * Math.cos(v)) * Math.cos(u))), mul(vAxis, (major + minor * Math.cos(v)) * Math.sin(u))), mul(direction, minor * Math.sin(v)));
          const p00 = point(u0, v0); const p10 = point(u1, v0); const p11 = point(u1, v1); const p01 = point(u0, v1);
          const normal = (u, v) => normalize(add(add(mul(uAxis, Math.cos(v) * Math.cos(u)), mul(vAxis, Math.cos(v) * Math.sin(u))), mul(direction, Math.sin(v))));
          emit(material, p00, p10, p11, [normal(u0, v0), normal(u1, v0), normal(u1, v1)]);
          emit(material, p00, p11, p01, [normal(u0, v0), normal(u1, v1), normal(u0, v1)]);
        }
      }
    }

    function ellipseShadow(x, z, rx, rz, offset = 0) {
      const layers = [
        { radius: 1, material: 'shadowSoft' },
        { radius: 0.88, material: 'shadowSoft' },
        { radius: 0.74, material: 'shadow' },
        { radius: 0.58, material: 'shadow' }
      ];
      layers.forEach(({ radius: ratio, material }) => {
        const center = [x + offset, 0.012, z];
        const segments = 30;
        for (let index = 0; index < segments; index++) {
          const a = index / segments * Math.PI * 2;
          const b = (index + 1) / segments * Math.PI * 2;
          const p1 = [center[0] + Math.cos(a) * rx * ratio, center[1], center[2] + Math.sin(a) * rz * ratio];
          const p2 = [center[0] + Math.cos(b) * rx * ratio, center[1], center[2] + Math.sin(b) * rz * ratio];
          emit(material, center, p1, p2, [0, 1, 0]);
        }
      });
    }

    return { batches, lights, anchors, box, cylinder, sphere, rod, leaf, torus, ellipseShadow, polygon };
  }

  function getDevice(room, id) {
    return room.devices.find((device) => device.id === id) || { id, label: id, presentation: null };
  }

  function lampBulbMaterial(device) {
    const kind = device.presentation?.kind;
    if (kind === 'on') return 'bulbOn';
    if (kind === 'inspected') return 'bulbInspected';
    if (kind === 'scheduled') return 'bulbScheduled';
    if (kind === 'candidate') return 'bulbCandidate';
    if (kind === 'target') return 'bulbTarget';
    if (kind === 'warm') return 'bulbWarm';
    return 'bulbOff';
  }

  function lampIsOn(device) {
    return ['on', 'inspected', 'warm'].includes(device.presentation?.kind);
  }

  function addSelectionIndicator(g, x, z, offset, kind = 'target') {
    if (!['target', 'candidate', 'scheduled'].includes(kind)) return;
    g.torus([x, 0.035, z], kind === 'candidate' ? 0.34 : 0.29, 0.018, 'selection', offset, 32, 5);
  }

  function addLamp(g, device, x, z, offset, style = 'floor') {
    const bulbMat = lampBulbMaterial(device);
    if (style === 'desk') {
      g.ellipseShadow(x, z, 0.42, 0.35, offset);
      g.cylinder([x + offset, 0.82, z], 0.3, 0.09, 'darkMetal', 24);
      g.cylinder([x + offset, 0.9, z], 0.23, 0.08, 'metal', 24);
      g.rod([x, 0.94, z], [x - 0.22, 1.22, z - 0.08], 0.045, 'metal', offset);
      g.rod([x - 0.22, 1.22, z - 0.08], [x + 0.12, 1.5, z - 0.13], 0.038, 'metal', offset);
      g.sphere([x + 0.12, 1.51, z - 0.13], 0.075, 'metal', offset, [1, 0.9, 1]);
      g.cylinder([x + 0.12 + offset, 1.62, z - 0.13], 0.34, 0.28, 'ceramic', 24, 0.22);
      g.sphere([x + 0.12, 1.49, z - 0.13], 0.095, bulbMat, offset, [0.75, 1, 0.75]);
      addSelectionIndicator(g, x + 0.12, z - 0.13, offset, device.presentation?.kind);
      return [x + 0.12 + offset, 1.5, z - 0.13];
    }
    if (style === 'bedside') {
      g.ellipseShadow(x, z, 0.44, 0.42, offset);
      g.cylinder([x + offset, 0.78, z], 0.32, 0.12, 'woodDark', 24);
      g.box([x + offset, 0.95, z], [0.62, 0.12, 0.56], 'wood');
      g.box([x + offset, 0.69, z], [0.56, 0.34, 0.5], 'woodLight');
      g.box([x + offset, 0.7, z + 0.258], [0.34, 0.08, 0.025], 'woodDark');
      g.cylinder([x + offset, 1.14, z], 0.07, 0.34, 'metal', 16);
      g.cylinder([x + offset, 1.37, z], 0.34, 0.34, 'linen', 24, 0.21);
      g.sphere([x, 1.2, z], 0.085, bulbMat, offset, [0.78, 1, 0.78]);
      addSelectionIndicator(g, x, z, offset, device.presentation?.kind);
      return [x + offset, 1.2, z];
    }
    if (style === 'pendant') {
      g.rod([x, 3.14, z], [x, 2.57, z], 0.018, 'darkMetal', offset);
      g.cylinder([x + offset, 2.48, z], 0.39, 0.24, 'metal', 24, 0.19);
      g.sphere([x, 2.38, z], 0.09, bulbMat, offset, [0.9, 0.7, 0.9]);
      addSelectionIndicator(g, x, z, offset, device.presentation?.kind);
      return [x + offset, 2.38, z];
    }
    g.ellipseShadow(x, z, 0.5, 0.48, offset);
    g.cylinder([x + offset, 0.08, z], 0.34, 0.14, 'darkMetal', 28);
    g.cylinder([x + offset, 0.18, z], 0.25, 0.08, 'metal', 24);
    g.cylinder([x + offset, 1.14, z], 0.035, 1.84, 'metal', 12);
    g.cylinder([x + offset, 2.02, z], 0.39, 0.34, 'linen', 28, 0.25);
    g.sphere([x, 1.86, z], 0.1, bulbMat, offset, [0.9, 0.75, 0.9]);
    addSelectionIndicator(g, x, z, offset, device.presentation?.kind);
    return [x + offset, 1.86, z];
  }

  function addRoomShell(g, offset, kind) {
    const W = ROOM.width; const D = ROOM.depth; const H = ROOM.height;
    g.box([offset, -0.1, 0], [W, 0.2, D], 'floorBase');
    const floorMaterials = ['floorA', 'floorB', 'floorA', 'floorC'];
    for (let index = 0; index < 12; index++) {
      const z = -D / 2 + 0.25 + index * 0.45;
      g.box([offset + (index % 2 ? 0.28 : -0.28), 0.008, z], [W - 0.04, 0.018, 0.435], floorMaterials[index % floorMaterials.length]);
    }
    g.box([offset, H / 2, -D / 2], [W, H, 0.16], kind === 'bedroom' ? 'wallAccent' : 'wall');
    const cutawayHeight = H * 0.42;
    g.box([offset - W / 2, cutawayHeight / 2, 0], [0.16, cutawayHeight, D], 'wallSide');
    g.box([offset, 0.11, -D / 2 + 0.095], [W, 0.22, 0.1], 'woodDark');
    g.box([offset - W / 2 + 0.095, 0.11, 0], [0.1, 0.22, D], 'woodDark');
    // Architectural details give the cutaway a finished interior-design feel:
    // a slim ceiling rail, a recessed warm wash, and a vertical timber panel.
    g.box([offset, H - 0.08, -1.18], [W - 0.42, 0.08, 0.1], 'woodDark');
    g.box([offset, H - 0.125, -1.18], [W * 0.68, 0.018, 0.028], 'lightStrip');
    g.box([offset + 1.85, 1.66, -2.405], [2.35, 1.96, 0.05], 'wallPanel');
    for (let index = 0; index < 6; index++) {
      const x = 0.72 + index * 0.42;
      g.box([offset + x, 1.66, -2.425], [0.055, 1.9, 0.045], 'wallPanel');
    }
    g.box([offset + 2.55, 1.62, -2.415], [0.025, 1.8, 0.02], 'lightStrip');
    g.ellipseShadow(offset, 0.2, W * 0.36, D * 0.31, 0);
  }

  function addWindow(g, offset, x = -2.15, y = 1.98) {
    const z = -ROOM.depth / 2 + 0.085;
    g.box([offset + x, y, z], [1.86, 1.12, 0.06], 'woodDark');
    g.box([offset + x, y, z + 0.04], [1.67, 0.94, 0.035], 'glass');
    g.box([offset + x, y, z + 0.075], [0.045, 0.95, 0.04], 'white');
    g.box([offset + x, y, z + 0.075], [1.68, 0.045, 0.04], 'white');
    g.box([offset + x - 0.96, y, z], [0.1, 1.24, 0.12], 'woodLight');
    g.box([offset + x + 0.96, y, z], [0.1, 1.24, 0.12], 'woodLight');
    g.box([offset + x, y + 0.62, z], [2.02, 0.12, 0.14], 'woodLight');
    g.box([offset + x, y - 0.62, z], [2.02, 0.12, 0.14], 'woodLight');
    // Curtains hang on the frame edges rather than covering the glass.
    g.box([offset + x - 1.13, y, z + 0.12], [0.22, 1.42, 0.12], 'fabric');
    g.box([offset + x + 1.13, y, z + 0.12], [0.22, 1.42, 0.12], 'fabric');
  }

  function addPicture(g, offset, x, y, width, height, mat = 'woodDark') {
    const z = -ROOM.depth / 2 + 0.12;
    g.box([offset + x, y, z], [width + 0.12, height + 0.12, 0.12], mat);
    g.box([offset + x, y, z + 0.07], [width, height, 0.035], 'ceramicDark');
    g.box([offset + x, y, z + 0.095], [width * 0.72, 0.022, 0.014], 'fabricLight');
    g.box([offset + x - width * 0.14, y - height * 0.12, z + 0.095], [0.022, height * 0.54, 0.014], 'accent');
  }

  function addPlant(g, offset, x, z, scale = 1) {
    g.ellipseShadow(x, z, 0.32 * scale, 0.28 * scale, offset);
    g.cylinder([x + offset, 0.28 * scale, z], 0.24 * scale, 0.48 * scale, 'ceramicDark', 18, 0.32 * scale);
    g.cylinder([x + offset, 0.52 * scale, z], 0.22 * scale, 0.035 * scale, 'woodDark', 18);
    for (let index = 0; index < 7; index++) {
      const angle = index * Math.PI * 2 / 7;
      g.rod([x, 0.52 * scale, z], [x + Math.cos(angle) * 0.1 * scale, 0.9 * scale, z + Math.sin(angle) * 0.1 * scale], 0.018 * scale, 'plant', offset);
      g.leaf([x + Math.cos(angle) * 0.18 * scale, 0.84 * scale, z + Math.sin(angle) * 0.18 * scale], 0.23 * scale, index % 2 ? 'plant' : 'plantLight', angle, offset);
    }
  }

  function buildWorkspace(g, room, offset) {
    addRoomShell(g, offset, 'workspace');
    addWindow(g, offset, -2.1, 2.0);
    addPicture(g, offset, 1.35, 2.18, 0.98, 0.64, 'brass');
    // Desk, trestles, monitor, keyboard and a small personal plant.
    g.ellipseShadow(offset, 0.55, 2.05, 0.88, 0);
    g.box([offset - 0.1, 0.82, 0.18], [3.65, 0.16, 1.62], 'wood');
    [-1.72, 1.52].forEach((x) => [-0.45, 1.0].forEach((z) => g.box([offset + x, 0.4, z], [0.11, 0.78, 0.11], 'darkMetal')));
    g.box([offset - 0.42, 1.2, -0.46], [1.38, 0.09, 0.12], 'darkMetal');
    g.box([offset - 0.42, 1.62, -0.52], [1.32, 0.83, 0.12], 'black');
    g.box([offset - 0.42, 1.64, -0.445], [1.18, 0.67, 0.025], 'screen');
    // A thin metal bezel and a weighted stand make the display read as a real
    // piece of hardware at the camera's close working distance.
    g.box([offset - 0.42, 2.04, -0.46], [1.28, 0.025, 0.028], 'metal');
    g.box([offset - 0.42, 1.24, -0.46], [1.28, 0.025, 0.028], 'metal');
    g.box([offset - 1.06, 1.64, -0.46], [0.025, 0.76, 0.028], 'metal');
    g.box([offset + 0.22, 1.64, -0.46], [0.025, 0.76, 0.028], 'metal');
    for (let index = 0; index < 4; index++) g.box([offset - 0.72 + index * 0.18, 1.78 - index * 0.09, -0.42], [0.36, 0.018, 0.012], 'screenLine');
    g.box([offset - 0.32, 0.95, 0.72], [1.02, 0.055, 0.34], 'darkMetal');
    for (let index = 0; index < 9; index++) g.box([offset - 0.73 + index * 0.1, 0.99, 0.72], [0.065, 0.012, 0.23], 'metal');
    g.box([offset + 0.5, 0.96, 0.72], [0.25, 0.045, 0.35], 'darkMetal');
    addPlant(g, offset, -1.55, 0.22, 0.74);
    const lamp = getDevice(room, 'desk');
    const lightPosition = addLamp(g, lamp, 1.16, 0.12, offset, 'desk');
    if (lampIsOn(lamp)) g.lights.push({ position: lightPosition, color: [1, 0.72, 0.36], power: 3.1 });
    // Swivel chair and castor base.
    g.ellipseShadow(0.2, 1.94, 0.63, 0.5, offset);
    g.cylinder([offset + 0.2, 0.18, 1.94], 0.38, 0.09, 'darkMetal', 20);
    g.cylinder([offset + 0.2, 0.5, 1.94], 0.065, 0.58, 'metal', 14);
    g.box([offset + 0.2, 0.79, 1.94], [0.78, 0.16, 0.7], 'fabric');
    g.box([offset + 0.2, 1.17, 2.2], [0.78, 0.78, 0.16], 'fabric');
    [-0.26, 0.66].forEach((x) => g.rod([x + 0.2, 0.78, 1.86], [x + 0.2, 0.78, 2.35], 0.035, 'darkMetal', offset));
  }

  function buildLiving(g, room, offset) {
    addRoomShell(g, offset, 'living');
    addWindow(g, offset, -2.2, 2.02);
    // Media cabinet and television.
    g.box([offset + 2.12, 0.46, -2.08], [2.05, 0.76, 0.58], 'woodDark');
    g.box([offset + 2.12, 0.9, -2.08], [2.18, 0.1, 0.67], 'woodLight');
    g.box([offset + 2.12, 1.68, -2.42], [1.86, 1.22, 0.12], 'black');
    g.box([offset + 2.12, 1.68, -2.34], [1.7, 1.05, 0.025], 'screen');
    g.box([offset + 2.12, 1.12, -2.16], [0.3, 0.24, 0.04], 'darkMetal');
    addPicture(g, offset, -0.25, 2.12, 1.02, 0.72, 'woodDark');
    // Deep sofa with separate seat/back cushions and arms.
    g.ellipseShadow(-0.28, -0.96, 2.38, 0.94, offset);
    g.box([offset - 0.28, 0.42, -1.02], [3.68, 0.65, 1.5], 'woodDark');
    g.box([offset - 0.28, 0.75, -1.68], [3.7, 1.2, 0.32], 'fabric');
    g.box([offset - 1.97, 0.72, -1.0], [0.36, 0.88, 1.55], 'fabric');
    g.box([offset + 1.41, 0.72, -1.0], [0.36, 0.88, 1.55], 'fabric');
    g.box([offset - 1.1, 0.72, -0.82], [1.4, 0.24, 1.02], 'fabricLight');
    g.box([offset + 0.48, 0.72, -0.82], [1.4, 0.24, 1.02], 'fabricLight');
    g.box([offset - 1.09, 1.15, -1.55], [1.03, 0.71, 0.22], 'fabricLight', -0.12);
    g.box([offset + 0.45, 1.15, -1.55], [1.03, 0.71, 0.22], 'fabricLight', 0.12);
    // Coffee table, books and ceramic cup.
    g.ellipseShadow(offset, 0.62, 1.56, 0.72, 0);
    g.box([offset, 0.48, 0.58], [2.38, 0.13, 1.23], 'woodLight');
    [-0.9, 0.9].forEach((x) => [-0.38, 1.52].forEach((z) => g.box([offset + x, 0.23, z], [0.09, 0.48, 0.09], 'woodDark')));
    g.box([offset - 0.55, 0.58, 0.42], [0.64, 0.06, 0.4], 'ceramicDark');
    g.cylinder([offset + 0.6, 0.62, 0.68], 0.12, 0.19, 'ceramic', 18, 0.15);
    // Floor lamp and pedestal fan; MSC preserves the fan's existing state.
    const floorLamp = getDevice(room, 'living');
    const floorPosition = addLamp(g, floorLamp, -2.9, -1.48, offset, 'floor');
    if (lampIsOn(floorLamp)) g.lights.push({ position: floorPosition, color: [1, 0.76, 0.48], power: 3.6 });
    const fan = getDevice(room, 'fan');
    const fx = 2.63; const fz = 0.48;
    g.ellipseShadow(fx, fz, 0.56, 0.47, offset);
    g.cylinder([offset + fx, 0.11, fz], 0.42, 0.16, 'darkMetal', 28, 0.52);
    g.cylinder([offset + fx, 0.22, fz], 0.28, 0.11, 'metal', 24);
    g.cylinder([offset + fx, 1.0, fz], 0.055, 1.55, 'metal', 16);
    g.torus([fx, 2.02, fz], 0.59, 0.04, 'metal', offset, 34, 7, [0, 0, 1]);
    g.sphere([fx, 2.02, fz], 0.16, 'darkMetal', offset, [1, 1, 0.65]);
    for (let index = 0; index < 8; index++) {
      const angle = index * Math.PI / 4;
      const start = [fx + Math.cos(angle) * 0.18, 2.02 + Math.sin(angle) * 0.18, fz + 0.015];
      const end = [fx + Math.cos(angle) * 0.57, 2.02 + Math.sin(angle) * 0.57, fz + 0.015];
      g.rod(start, end, 0.012, 'metal', offset);
    }
    for (let index = 0; index < 3; index++) {
      const angle = index * Math.PI * 2 / 3;
      const radial = [Math.cos(angle), Math.sin(angle)];
      const tangent = [-radial[1], radial[0]];
      const p0 = [fx + radial[0] * 0.1 + tangent[0] * 0.09 + offset, 2.02 + radial[1] * 0.1 + tangent[1] * 0.09, fz + 0.04];
      const p1 = [fx + radial[0] * 0.53 + tangent[0] * 0.15 + offset, 2.02 + radial[1] * 0.53 + tangent[1] * 0.15, fz + 0.04];
      const p2 = [fx + radial[0] * 0.57 - tangent[0] * 0.08 + offset, 2.02 + radial[1] * 0.57 - tangent[1] * 0.08, fz + 0.04];
      const p3 = [fx + radial[0] * 0.16 - tangent[0] * 0.08 + offset, 2.02 + radial[1] * 0.16 - tangent[1] * 0.08, fz + 0.04];
      const normal = [0, 0, 1];
      g.polygon('fabricLight', [p0, p1, p2, p3], normal);
    }
    g.cylinder([offset + fx, 2.02, fz + 0.055], 0.12, 0.13, 'ceramic', 20, 0.12, 0, [0, 0, 1]);
  }

  function buildBedroom(g, room, offset) {
    addRoomShell(g, offset, 'bedroom');
    addWindow(g, offset, -2.05, 2.02);
    addPicture(g, offset, 0.15, 2.25, 0.86, 0.58, 'woodDark');
    // Bed frame, mattress, folded cover and pillows.
    g.ellipseShadow(-0.24, 0.12, 1.8, 2.02, offset);
    g.box([offset - 0.24, 0.38, 0.12], [2.8, 0.55, 3.55], 'woodDark');
    g.box([offset - 0.24, 0.73, 0.08], [2.78, 0.45, 3.35], 'linen');
    g.box([offset - 0.24, 0.98, 0.84], [2.72, 0.12, 1.88], 'fabricLight');
    g.box([offset - 0.9, 1.02, -1.12], [0.92, 0.22, 0.58], 'white', -0.08);
    g.box([offset + 0.43, 1.02, -1.12], [0.92, 0.22, 0.58], 'white', 0.08);
    g.box([offset - 0.24, 1.06, -1.7], [2.9, 0.78, 0.2], 'woodLight');
    if (room.occupied) {
      // The resident is settled under the cover; only the head and shoulders remain visible.
      g.sphere([-0.24, 1.0, -1.16], 0.36, 'clothing', offset, [1.55, 0.54, 1.75]);
      g.sphere([-0.23, 1.13, -1.62], 0.16, 'skin', offset, [1.12, 0.76, 0.92]);
      g.sphere([-0.23, 1.23, -1.69], 0.16, 'hair', offset, [1.16, 0.45, 1.0]);
    }
    // Bedside cabinet and lamp on the right side.
    const bedside = getDevice(room, 'bedside');
    const bedsidePosition = addLamp(g, bedside, 2.25, -1.05, offset, 'bedside');
    if (lampIsOn(bedside)) g.lights.push({ position: bedsidePosition, color: [1, 0.74, 0.43], power: 3.2 });
    g.box([offset - 2.65, 0.49, -1.1], [0.88, 0.68, 0.78], 'wood');
    g.box([offset - 2.65, 0.86, -1.1], [1.02, 0.12, 0.9], 'woodLight');
    g.cylinder([offset - 2.65, 0.88, -1.1], 0.06, 0.08, 'ceramic', 16);
    g.ellipseShadow(-2.65, -1.1, 0.65, 0.58, offset);
    // A tall wardrobe gives the room a distinct silhouette.
    g.box([offset + 3.0, 1.24, -1.65], [1.08, 2.42, 1.28], 'woodDark');
    g.box([offset + 2.72, 1.24, -0.99], [0.5, 2.28, 0.035], 'wood');
    g.box([offset + 3.28, 1.24, -0.99], [0.5, 2.28, 0.035], 'woodLight');
    g.cylinder([offset + 3.0, 1.2, -0.94], 0.035, 0.12, 'metal', 12, 0.035, 0, [0, 0, 1]);
    // The bedroom fan stays still while off and uses a brighter finish so its blades read clearly in the cutaway.
    g.rod([0, 3.14, 0.05], [0, 2.92, 0.05], 0.025, 'darkMetal', offset);
    g.cylinder([offset, 2.86, 0.05], 0.14, 0.15, 'darkMetal', 20);
    for (let index = 0; index < 3; index++) {
      const angle = index * Math.PI * 2 / 3;
      g.box([offset + Math.cos(angle) * 0.48, 2.78, 0.05 + Math.sin(angle) * 0.48], [0.94, 0.055, 0.18], 'fanBlade', -angle);
    }
    g.cylinder([offset, 2.73, 0.05], 0.17, 0.13, 'metal', 20);
  }

  function buildKitchen(g, room, offset) {
    addRoomShell(g, offset, 'kitchen');
    // Rear cabinets, countertop and range.
    g.box([offset - 0.7, 1.08, -2.24], [5.25, 1.16, 0.75], 'wood');
    g.box([offset - 0.7, 1.7, -2.26], [5.48, 0.12, 0.85], 'tile');
    for (let index = 0; index < 4; index++) {
      const x = -2.55 + index * 1.24;
      g.box([offset + x, 2.45, -2.54], [1.12, 0.9, 0.24], index % 2 ? 'woodLight' : 'wood');
      g.box([offset + x, 2.4, -2.39], [0.045, 0.16, 0.035], 'metal');
    }
    // Island with inset sink and faucet.
    g.ellipseShadow(0.3, 0.42, 2.0, 1.05, offset);
    g.box([offset + 0.3, 0.66, 0.43], [3.24, 1.18, 1.62], 'woodLight');
    g.box([offset + 0.3, 1.29, 0.43], [3.52, 0.16, 1.86], 'tile');
    g.box([offset - 0.42, 1.39, 0.35], [0.9, 0.04, 0.56], 'darkMetal');
    g.box([offset - 0.42, 1.42, 0.35], [0.76, 0.02, 0.42], 'metal');
    g.rod([-0.42, 1.4, -0.02], [-0.42, 1.88, -0.02], 0.045, 'metal', offset);
    g.rod([-0.42, 1.88, -0.02], [-0.18, 1.88, -0.02], 0.045, 'metal', offset);
    // Low cabinet doors, handles, oven and a small herb pot.
    for (let index = 0; index < 3; index++) {
      const x = -0.7 + index * 0.96;
      g.box([offset + x, 0.62, 0.85], [0.88, 0.86, 0.035], 'wood');
      g.box([offset + x + 0.31, 0.62, 0.89], [0.03, 0.16, 0.025], 'metal');
    }
    g.box([offset + 2.16, 0.88, -2.0], [1.0, 0.62, 0.06], 'black');
    g.box([offset + 2.16, 0.9, -1.96], [0.82, 0.42, 0.02], 'screen');
    addPlant(g, offset, 2.45, -2.04, 0.62);
    // Two pendant fixtures; only the left is the benchmark device.
    const pendant = getDevice(room, 'kitchen');
    const firstLight = addLamp(g, pendant, -1.25, -0.24, offset, 'pendant');
    addLamp(g, { id: 'secondary-pendant', presentation: null }, 1.25, -0.24, offset, 'pendant');
    if (lampIsOn(pendant)) g.lights.push({ position: firstLight, color: [1, 0.75, 0.46], power: 3.4 });
    // Bar stools at the open edge of the island.
    [-1.0, 1.0].forEach((x) => {
      g.cylinder([offset + x, 0.51, 1.8], 0.42, 0.12, 'wood', 20);
      g.cylinder([offset + x, 0.27, 1.8], 0.04, 0.48, 'darkMetal', 12);
      for (let index = 0; index < 3; index++) {
        const angle = index * Math.PI * 2 / 3;
        g.rod([x, 0.28, 1.8], [x + Math.cos(angle) * 0.3, 0.05, 1.8 + Math.sin(angle) * 0.3], 0.025, 'darkMetal', offset);
      }
    });
  }

  const ROOM_BUILDERS = { workspace: buildWorkspace, living: buildLiving, bedroom: buildBedroom, kitchen: buildKitchen };

  function buildScene(rooms) {
    const geometry = makeGeometry();
    const positions = rooms.map((_, index) => (index - (rooms.length - 1) / 2) * (ROOM.width + ROOM.gap));
    const devicePositions = {
      workspace: { desk: [1.28, 1.5, -0.01] },
      living: { living: [-2.9, 1.86, -1.48], fan: [2.63, 2.02, 0.48] },
      bedroom: { bedside: [2.25, 1.2, -1.05], 'bedroom-fan': [0, 2.73, 0.05] },
      kitchen: { kitchen: [-1.25, 2.38, -0.24] }
    };
    rooms.forEach((room, index) => {
      const offset = positions[index];
      (ROOM_BUILDERS[room.id] || buildLiving)(geometry, room, offset);
      room.devices.forEach((device) => {
        const position = devicePositions[room.id]?.[device.id];
        if (!position) return;
        geometry.anchors.push({
          key: `${room.id}:${device.id}`,
          label: device.label,
          position: [position[0] + offset, position[1], position[2]],
          presentation: device.presentation
        });
      });
    });
    // Two quiet studio sources keep unlit rooms dimensional. Device lights are
    // still added by the task state and occupy the remaining light slots.
    const span = rooms.length * ROOM.width + Math.max(0, rooms.length - 1) * ROOM.gap;
    geometry.lights.unshift(
      { position: [-span * 0.42, 3.1, 1.8], color: [1.0, 0.78, 0.58], power: 0.72 },
      { position: [span * 0.36, 2.5, -1.1], color: [0.64, 0.69, 1.0], power: 0.2 }
    );
    return {
      ...geometry,
      center: [0, 0.95, 0],
      width: rooms.length * ROOM.width + Math.max(0, rooms.length - 1) * ROOM.gap
    };
  }

  function mount(host) {
    if (!host) return null;
    const videoSources = {
      DGC: '../assets/dgc-workspace.mp4',
      MSC: '../assets/msc-multi-device.mp4',
      AIR: '../assets/air-clarification.mp4',
      FAR: '../assets/far-summer.mp4',
      DCR: '../assets/dcr-context.mp4',
      PMU: '../assets/pmu-personalized-memory.mp4',
      REQ: '../assets/req-read-only.mp4'
    };
    const scene = document.createElement('div');
    scene.className = 'home-3d-scene';
    const video = document.createElement('video');
    video.className = 'home-scene-video';
    video.src = videoSources.DGC;
    video.muted = true;
    video.playsInline = true;
    video.loop = true;
    video.preload = 'auto';
    video.setAttribute('playsinline', '');
    video.setAttribute('aria-hidden', 'true');
    const canvas = document.createElement('canvas');
    canvas.className = 'home-scene-canvas';
    canvas.tabIndex = 0;
    canvas.setAttribute('role', 'group');
    canvas.setAttribute('aria-roledescription', 'interactive 3D home scene');
    canvas.setAttribute('aria-label', 'Interactive 3D home scene. The camera follows the current task. Select a device to inspect; use arrow keys to rotate and plus or minus to zoom.');
    const labels = document.createElement('div');
    labels.className = 'scene-room-labels';
    labels.setAttribute('aria-hidden', 'true');
    const devicePins = document.createElement('div');
    devicePins.className = 'scene-device-pins';
    devicePins.setAttribute('role', 'group');
    devicePins.setAttribute('aria-label', 'Devices in this scene');
    const controls = document.createElement('div');
    controls.className = 'scene-view-tools';
    const hint = document.createElement('span');
    hint.className = 'scene-view-hint';
    hint.textContent = 'Camera follows actions · click a device · drag / scroll to explore';
    const reset = document.createElement('button');
    reset.className = 'scene-reset';
    reset.type = 'button';
    reset.textContent = 'Reset view';
    reset.setAttribute('aria-label', 'Reset 3D scene view');
    controls.append(hint, reset);
    const description = document.createElement('p');
    description.className = 'scene-sr-only';
    description.id = 'scene-3d-description';
    description.setAttribute('aria-live', 'polite');
    canvas.setAttribute('aria-describedby', description.id);
    scene.append(video, canvas, labels, devicePins, controls, description);
    host.replaceChildren(scene);

    let gl;
    let program;
    let uniforms;
    let attributes;
    let gpuBatches = [];
    let currentScene;
    let activeLocale = localStorage.getItem('edgebench-locale') === 'zh' ? 'zh' : 'en';
    // The scene reads from the open front of the room. Keep the initial orbit
    // on the left side so drag and keyboard rotation move in the same direction.
    let azimuth = -0.72;
    let elevation = 0.48;
    let zoom = 1;
    let pointer = null;
    let resizeObserver;
    let drawRequest = 0;
    let animationRequest = 0;
    let lastFrameAt = 0;
    let sceneVisible = true;
    let phase = 'understand';
    let activity = 0.22;
    let targetActivity = 0.22;
    let actionFocus = 0;
    let targetActionFocus = 0;
    let focusPoint = [0, 0.95, 0];
    let targetFocusPoint = [0, 0.95, 0];
    let cameraSpan = ROOM.width;
    let targetCameraSpan = ROOM.width;
    let inspectionZoom = 1;
    let targetInspectionZoom = 1;
    let cameraRoute = null;
    let selectedDeviceKey = '';
    let activeVideoFamily = '';
    let videoLoadTimeout;
    let onDeviceSelect = null;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const intersectionObserver = 'IntersectionObserver' in window
      ? new IntersectionObserver((entries) => {
        sceneVisible = entries.some((entry) => entry.isIntersecting);
        if (sceneVisible) startAnimation();
        else stopAnimation();
      }, { threshold: 0.04 })
      : null;
    function updateVideo(data) {
      const videoSource = videoSources[data.family];
      if (videoSource) {
        if (activeVideoFamily !== data.family) {
          const requestedFamily = data.family;
          activeVideoFamily = requestedFamily;
          scene.classList.remove('uses-video');
          window.clearTimeout(videoLoadTimeout);
          const startPlayback = () => {
            if (activeVideoFamily !== requestedFamily) return;
            window.clearTimeout(videoLoadTimeout);
            video.currentTime = 0;
            video.play().then(() => {
              if (activeVideoFamily === requestedFamily) scene.classList.add('uses-video');
            }).catch(() => {
              if (gl && program && activeVideoFamily === requestedFamily) scene.classList.remove('uses-video');
            });
          };
          if (video.getAttribute('src') !== videoSource) {
            video.pause();
            video.src = videoSource;
            video.load();
            video.addEventListener('canplay', startPlayback, { once: true });
          } else if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
            startPlayback();
          } else {
            video.addEventListener('canplay', startPlayback, { once: true });
          }
          videoLoadTimeout = window.setTimeout(() => {
            if (gl && program && activeVideoFamily === requestedFamily && video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA) {
              scene.classList.remove('uses-video');
            }
          }, 5000);
        }
      } else {
        window.clearTimeout(videoLoadTimeout);
        scene.classList.remove('uses-video');
        video.pause();
        video.currentTime = 0;
        activeVideoFamily = '';
      }
    }

    try {
      gl = canvas.getContext('webgl', { antialias: true, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: false });
      if (!gl) throw new Error('WebGL is unavailable.');
      program = createProgram(gl);
      attributes = { position: gl.getAttribLocation(program, 'aPosition'), normal: gl.getAttribLocation(program, 'aNormal') };
      uniforms = {
        viewProjection: gl.getUniformLocation(program, 'uViewProjection'),
        camera: gl.getUniformLocation(program, 'uCamera'),
        color: gl.getUniformLocation(program, 'uColor'),
        emission: gl.getUniformLocation(program, 'uEmission'),
        specular: gl.getUniformLocation(program, 'uSpecular'),
        grain: gl.getUniformLocation(program, 'uGrain'),
        pointPosition: gl.getUniformLocation(program, 'uPointPosition[0]'),
        pointColor: gl.getUniformLocation(program, 'uPointColor[0]'),
        pointPower: gl.getUniformLocation(program, 'uPointPower[0]'),
        time: gl.getUniformLocation(program, 'uTime'),
        activity: gl.getUniformLocation(program, 'uActivity')
      };
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.disable(gl.CULL_FACE);
      gl.clearColor(0.055, 0.05, 0.058, 1);
    } catch (error) {
      // The task films play independently of the optional interactive renderer.
      scene.replaceChildren(video);
      scene.classList.add('uses-video');
      video.controls = true;
      return {
        update(data) {
          updateVideo(data);
          scene.classList.add('uses-video');
        },
        setPhase() {},
        setSelectionHandler() {},
        destroy() {
          activeVideoFamily = '';
          window.clearTimeout(videoLoadTimeout);
          video.pause();
        }
      };
    }

    function resize() {
      const bounds = canvas.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return false;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(bounds.width * ratio));
      const height = Math.max(1, Math.round(bounds.height * ratio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      gl.viewport(0, 0, width, height);
      return true;
    }

    function scheduleDraw() {
      if (drawRequest) return;
      drawRequest = window.requestAnimationFrame(() => {
        drawRequest = 0;
        draw();
      });
    }

    function canAnimate() {
      return !reducedMotion.matches && !document.hidden && sceneVisible;
    }

    function stopAnimation() {
      if (animationRequest) window.cancelAnimationFrame(animationRequest);
      animationRequest = 0;
    }

    function animate(timestamp) {
      animationRequest = 0;
      if (!canAnimate()) return;
      if (timestamp - lastFrameAt >= 40) {
        draw(timestamp);
        lastFrameAt = timestamp;
      }
      if (needsAnimation()) animationRequest = window.requestAnimationFrame(animate);
    }

    function startAnimation() {
      if (canAnimate() && needsAnimation() && !animationRequest) animationRequest = window.requestAnimationFrame(animate);
    }

    function needsAnimation() {
      return Boolean(cameraRoute)
        || length(sub(focusPoint, targetFocusPoint)) > 0.008
        || Math.abs(cameraSpan - targetCameraSpan) > 0.008
        || Math.abs(inspectionZoom - targetInspectionZoom) > 0.003
        || Math.abs(activity - targetActivity) > 0.008
        || Math.abs(actionFocus - targetActionFocus) > 0.008;
    }

    function phaseCameraStops(nextPhase) {
      const center = currentScene?.center || [0, 0.95, 0];
      const sceneSpan = currentScene?.width || ROOM.width;
      const anchors = currentScene?.anchors || [];
      const focusKinds = {
        ground: ['target', 'candidate', 'scheduled'],
        act: ['target', 'scheduled', 'on', 'warm'],
        confirm: ['target', 'scheduled', 'on', 'warm', 'inspected', 'unchanged']
      }[nextPhase] || [];
      const focused = anchors.filter((anchor) => focusKinds.includes(anchor.presentation?.kind));
      if (nextPhase === 'understand' || !focused.length) return [{ position: center, zoom: 1, span: sceneSpan }];

      const xs = focused.map((anchor) => anchor.position[0]);
      const ys = focused.map((anchor) => anchor.position[1]);
      const zs = focused.map((anchor) => anchor.position[2]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const mean = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
      const position = [(minX + maxX) / 2, Math.max(0.9, mean(ys) - 0.28), mean(zs)];
      const span = Math.max(ROOM.width * 0.62, maxX - minX + ROOM.width * 0.46);
      const zoom = nextPhase === 'act' ? 0.84 : nextPhase === 'confirm' ? 0.92 : 0.88;
      return [{ position, zoom, span }];
    }

    function steerCamera(nextPhase) {
      const stops = phaseCameraStops(nextPhase);
      if (!stops.length) return;
      const points = [{ position: focusPoint.slice(), zoom: inspectionZoom, span: cameraSpan }, ...stops];
      if (reducedMotion.matches) {
        cameraRoute = null;
        const final = points[points.length - 1];
        targetFocusPoint = final.position.slice();
        focusPoint = final.position.slice();
        targetCameraSpan = final.span;
        cameraSpan = final.span;
        targetInspectionZoom = final.zoom;
        inspectionZoom = final.zoom;
      } else {
        cameraRoute = { points, startedAt: performance.now(), segmentDuration: 420 };
      }
      scheduleDraw();
      startAnimation();
    }

    function advanceCameraRoute(timestamp) {
      if (!cameraRoute) return;
      const route = cameraRoute;
      const totalDuration = (route.points.length - 1) * route.segmentDuration;
      const elapsed = Math.max(0, timestamp - route.startedAt);
      if (elapsed >= totalDuration) {
        const final = route.points[route.points.length - 1];
        targetFocusPoint = final.position.slice();
        targetCameraSpan = final.span;
        targetInspectionZoom = final.zoom;
        cameraRoute = null;
        return;
      }
      const segment = Math.min(route.points.length - 2, Math.floor(elapsed / route.segmentDuration));
      const progress = (elapsed - segment * route.segmentDuration) / route.segmentDuration;
      const eased = progress * progress * (3 - 2 * progress);
      const from = route.points[segment];
      const to = route.points[segment + 1];
      targetFocusPoint = from.position.map((value, index) => value + (to.position[index] - value) * eased);
      targetCameraSpan = from.span + (to.span - from.span) * eased;
      targetInspectionZoom = from.zoom + (to.zoom - from.zoom) * eased;
    }

    function cancelCameraRoute() {
      cameraRoute = null;
      targetFocusPoint = focusPoint.slice();
      targetCameraSpan = cameraSpan;
      targetInspectionZoom = inspectionZoom;
    }

    function setPhase(nextPhase) {
      phase = nextPhase;
      targetActivity = ({ understand: 0.3, ground: 0.58, act: 1, confirm: 0.36 })[phase] || 0.28;
      targetActionFocus = phase === 'act' ? 1 : 0;
      steerCamera(phase);
    }

    function renderDevicePins(anchors) {
      devicePins.replaceChildren(...anchors.map((anchor) => {
        const button = document.createElement('button');
        button.className = 'scene-device-pin';
        button.type = 'button';
        button.dataset.deviceKey = anchor.key;
        button.setAttribute('aria-pressed', 'false');
        const status = anchor.presentation?.status || (activeLocale === 'zh' ? '可用' : 'Available');
        button.setAttribute('aria-label', activeLocale === 'zh' ? `查看${anchor.label}。${status}。` : `Inspect ${anchor.label}. ${status}.`);
        const marker = document.createElement('span');
        marker.className = 'scene-device-marker';
        marker.setAttribute('aria-hidden', 'true');
        const caption = document.createElement('span');
        caption.className = 'scene-device-caption';
        caption.textContent = anchor.label;
        button.append(marker, caption);
        button.addEventListener('click', () => {
          selectedDeviceKey = anchor.key;
          cancelCameraRoute();
          targetFocusPoint = anchor.position;
          targetCameraSpan = ROOM.width;
          targetInspectionZoom = 0.78;
          devicePins.querySelectorAll('.scene-device-pin').forEach((item) => {
            const selected = item.dataset.deviceKey === selectedDeviceKey;
            item.classList.toggle('is-selected', selected);
            item.setAttribute('aria-pressed', String(selected));
          });
          if (reducedMotion.matches) {
            focusPoint = targetFocusPoint;
            cameraSpan = targetCameraSpan;
            inspectionZoom = targetInspectionZoom;
          }
          onDeviceSelect?.({ label: anchor.label, status, presentation: anchor.presentation });
          scheduleDraw();
          startAnimation();
        });
        return button;
      }));
    }

    function positionDevicePins(viewProjection) {
      if (!currentScene?.anchors?.length) return;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      currentScene.anchors.forEach((anchor) => {
        const button = devicePins.querySelector(`[data-device-key="${anchor.key}"]`);
        if (!button) return;
        const [x, y, z] = anchor.position;
        const clipX = viewProjection[0] * x + viewProjection[4] * y + viewProjection[8] * z + viewProjection[12];
        const clipY = viewProjection[1] * x + viewProjection[5] * y + viewProjection[9] * z + viewProjection[13];
        const clipW = viewProjection[3] * x + viewProjection[7] * y + viewProjection[11] * z + viewProjection[15];
        const screenX = clipX / clipW;
        const screenY = clipY / clipW;
        const visible = clipW > 0 && screenX > -1.1 && screenX < 1.1 && screenY > -1.1 && screenY < 1.1;
        button.hidden = !visible;
        if (visible) {
          button.style.left = `${(screenX + 1) * 50}%`;
          button.style.top = `${(1 - screenY) * 50}%`;
        }
      });
    }

    function resetCamera() {
      azimuth = -0.72;
      elevation = 0.68;
      zoom = 1;
      cameraRoute = null;
      selectedDeviceKey = '';
      targetFocusPoint = [0, 0.95, 0];
      targetCameraSpan = currentScene?.width || ROOM.width;
      targetInspectionZoom = 1;
      if (reducedMotion.matches) {
        focusPoint = targetFocusPoint;
        cameraSpan = targetCameraSpan;
        inspectionZoom = targetInspectionZoom;
      }
      devicePins.querySelectorAll('.scene-device-pin').forEach((item) => {
        item.classList.remove('is-selected');
        item.setAttribute('aria-pressed', 'false');
      });
      scheduleDraw();
      startAnimation();
    }


    function uploadGeometry(nextScene) {
      gpuBatches.forEach((batch) => gl.deleteBuffer(batch.buffer));
      gpuBatches = [];
      nextScene.batches.forEach((vertices, name) => {
        if (!vertices.length || !MATERIALS[name]) return;
        const buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
        gpuBatches.push({ name, buffer, count: vertices.length / 6 });
      });
      currentScene = nextScene;
    }

    function draw(timestamp = performance.now()) {
      if (!currentScene || !resize()) return;
      advanceCameraRoute(timestamp);
      activity += (targetActivity - activity) * 0.09;
      actionFocus += (targetActionFocus - actionFocus) * 0.07;
      const cameraEase = reducedMotion.matches ? 1 : 0.22;
      focusPoint = focusPoint.map((value, index) => value + (targetFocusPoint[index] - value) * cameraEase);
      cameraSpan += (targetCameraSpan - cameraSpan) * cameraEase;
      inspectionZoom += (targetInspectionZoom - inspectionZoom) * cameraEase;
      const seconds = timestamp * 0.001;
      const aspect = canvas.width / canvas.height;
      const fovy = 35 * Math.PI / 180;
      const horizontalHalf = Math.atan(Math.tan(fovy / 2) * aspect);
      const verticalFit = 5.9 / (2 * Math.tan(fovy / 2));
      const horizontalFit = cameraSpan / (2 * Math.tan(horizontalHalf) * 0.88);
      const distance = Math.max(verticalFit, horizontalFit, 7.6) * zoom * inspectionZoom * (1 - actionFocus * 0.045);
      const center = focusPoint;
      const drift = pointer ? 0 : Math.sin(seconds * 0.38) * 0.003;
      const direction = [Math.sin(azimuth + drift) * Math.cos(elevation), Math.sin(elevation + Math.sin(seconds * 0.31) * 0.002), Math.cos(azimuth + drift) * Math.cos(elevation)];
      const camera = add(center, mul(direction, distance));
      const projection = perspective(fovy, aspect, 0.1, 90);
      const view = lookAt(camera, center, [0, 1, 0]);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(program);
      const viewProjection = multiplyMatrix(projection, view);
      gl.uniformMatrix4fv(uniforms.viewProjection, false, new Float32Array(viewProjection));
      gl.uniform3fv(uniforms.camera, new Float32Array(camera));
      positionDevicePins(viewProjection);
      const pointPositions = new Float32Array(12);
      const pointColors = new Float32Array(12);
      const pointPowers = new Float32Array(4);
      currentScene.lights.slice(0, 4).forEach((light, index) => {
        pointPositions.set(light.position, index * 3);
        pointColors.set(light.color, index * 3);
        pointPowers[index] = light.power;
      });
      gl.uniform3fv(uniforms.pointPosition, pointPositions);
      gl.uniform3fv(uniforms.pointColor, pointColors);
      const lightPulse = 1 + activity * (0.055 + 0.06 * Math.sin(seconds * 2.4));
      for (let index = 0; index < pointPowers.length; index++) pointPowers[index] *= lightPulse;
      gl.uniform1fv(uniforms.pointPower, pointPowers);
      gl.uniform1f(uniforms.time, seconds);
      gl.uniform1f(uniforms.activity, activity);
      gpuBatches.forEach((batch) => {
        const material = MATERIALS[batch.name];
        gl.bindBuffer(gl.ARRAY_BUFFER, batch.buffer);
        gl.enableVertexAttribArray(attributes.position);
        gl.enableVertexAttribArray(attributes.normal);
        gl.vertexAttribPointer(attributes.position, 3, gl.FLOAT, false, 24, 0);
        gl.vertexAttribPointer(attributes.normal, 3, gl.FLOAT, false, 24, 12);
        gl.uniform3fv(uniforms.color, new Float32Array(colorToVec(material.color)));
        gl.uniform3fv(uniforms.emission, new Float32Array(material.emission ? colorToVec(material.emission) : [0, 0, 0]));
        gl.uniform1f(uniforms.specular, material.specular || 0.12);
        gl.uniform1f(uniforms.grain, material.grain || 0);
        gl.drawArrays(gl.TRIANGLES, 0, batch.count);
      });
    }

    reset.addEventListener('click', resetCamera);
    canvas.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      cancelCameraRoute();
      pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
      canvas.focus({ preventScroll: true });
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!pointer || pointer.id !== event.pointerId) return;
      const dx = event.clientX - pointer.x;
      const dy = event.clientY - pointer.y;
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      azimuth -= dx * 0.008;
      elevation = clamp(elevation + dy * 0.006, 0.12, 1.12);
      scheduleDraw();
    });
    const endPointer = (event) => {
      if (pointer?.id === event.pointerId) pointer = null;
    };
    canvas.addEventListener('pointerup', endPointer);
    canvas.addEventListener('pointercancel', endPointer);
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      cancelCameraRoute();
      zoom = clamp(zoom * Math.exp(event.deltaY * 0.001), 0.72, 1.8);
      scheduleDraw();
    }, { passive: false });
    canvas.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? 0.2 : 0.09;
      if (event.key === 'ArrowLeft') azimuth += step;
      else if (event.key === 'ArrowRight') azimuth -= step;
      else if (event.key === 'ArrowUp') elevation = clamp(elevation - step, 0.12, 1.12);
      else if (event.key === 'ArrowDown') elevation = clamp(elevation + step, 0.12, 1.12);
      else if (event.key === '+' || event.key === '=') zoom = clamp(zoom * 0.9, 0.72, 1.8);
      else if (event.key === '-' || event.key === '_') zoom = clamp(zoom * 1.1, 0.72, 1.8);
      else if (event.key === 'Home') resetCamera();
      else return;
      if (event.key !== 'Home') cancelCameraRoute();
      event.preventDefault();
      scheduleDraw();
    });

    if ('ResizeObserver' in window) {
      resizeObserver = new ResizeObserver(scheduleDraw);
      resizeObserver.observe(scene);
    } else {
      window.addEventListener('resize', scheduleDraw, { passive: true });
    }
    intersectionObserver?.observe(scene);
    video.addEventListener('error', () => {
      window.clearTimeout(videoLoadTimeout);
      if (video.getAttribute('src') === videoSources[activeVideoFamily]) scene.classList.remove('uses-video');
    });
    document.addEventListener('visibilitychange', startAnimation);
    const onMotionPreferenceChange = () => {
      if (canAnimate()) startAnimation();
      else stopAnimation();
    };
    if (reducedMotion.addEventListener) reducedMotion.addEventListener('change', onMotionPreferenceChange);
    else reducedMotion.addListener(onMotionPreferenceChange);

    return {
      update(data) {
        const rooms = data.rooms || [];
        const sceneLocale = data.locale || 'en';
        activeLocale = sceneLocale;
        const sceneCopy = data.scene || {};
        hint.textContent = sceneLocale === 'zh' ? '镜头跟随任务 · 点击设备查看 · 拖动 / 滚动浏览' : 'Camera follows actions · click a device · drag / scroll to explore';
        reset.textContent = sceneLocale === 'zh' ? '重置视角' : 'Reset view';
        reset.setAttribute('aria-label', sceneCopy.reset || (sceneLocale === 'zh' ? '重置 3D 视角' : 'Reset 3D scene view'));
        devicePins.setAttribute('aria-label', sceneLocale === 'zh' ? '场景中的设备' : 'Devices in this scene');
        updateVideo(data);
        selectedDeviceKey = '';
        cameraRoute = null;
        host.dataset.roomCount = String(rooms.length);
        const labelsText = rooms.map((room) => room.label);
        labels.replaceChildren(...labelsText.map((label) => {
          const pill = document.createElement('span');
          pill.className = 'scene-room-label';
          const room = rooms.find((item) => item.label === label);
          const name = document.createElement('span');
          name.textContent = label;
          pill.appendChild(name);
          if (typeof room?.occupied === 'boolean') {
            const occupancy = document.createElement('small');
            occupancy.textContent = room.occupied ? (room.occupancyText?.occupied || 'Occupied') : (room.occupancyText?.empty || 'Empty');
            pill.appendChild(occupancy);
          }
          return pill;
        }));
        const status = rooms.flatMap((room) => room.devices.filter((device) => device.presentation).map((device) => `${room.label}: ${device.label}, ${device.presentation.status}.`));
        const sceneLabel = `${data.title}. ${data.stepTitle}. ${data.stepCopy} ${status.join(' ')}`;
        canvas.setAttribute('aria-label', sceneLocale === 'zh' ? `${sceneLabel}${sceneCopy.sceneLabel ? ` ${sceneCopy.sceneLabel}` : ''}` : `${sceneLabel} The camera follows the active task. Select a device to inspect. Use arrow keys to rotate. Use plus and minus to zoom.`);
        description.textContent = sceneLabel;
        uploadGeometry(buildScene(rooms));
        renderDevicePins(currentScene.anchors);
        scheduleDraw();
        startAnimation();
      },
      setPhase,
      setSelectionHandler(callback) {
        onDeviceSelect = callback;
      },
      destroy() {
        video.pause();
        stopAnimation();
        document.removeEventListener('visibilitychange', startAnimation);
        intersectionObserver?.disconnect();
        if (reducedMotion.removeEventListener) reducedMotion.removeEventListener('change', onMotionPreferenceChange);
        else reducedMotion.removeListener(onMotionPreferenceChange);
        if (drawRequest) window.cancelAnimationFrame(drawRequest);
        resizeObserver?.disconnect();
        gpuBatches.forEach((batch) => gl.deleteBuffer(batch.buffer));
        gl.deleteProgram(program);
      }
    };
  }

  window.EdgeBenchTaskScene3D = { mount };
})();

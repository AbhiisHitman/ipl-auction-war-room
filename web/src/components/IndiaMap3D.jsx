import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { useNavigate } from 'react-router-dom';
import { useReducedMotion } from 'framer-motion';
import { TeamLogo, Pill } from './ui';
import { loadJSON } from '../lib/data';
import { TEAM_CODES, theme } from '../lib/themes';
import { ordinal } from '../lib/format';

const LAT0 = 22.5;
const LON0 = 81;
const K = 0.55; // world units per degree
const COS0 = Math.cos((LAT0 * Math.PI) / 180);
const DEPTH = 1.1;

const project = (lon, lat) => new THREE.Vector2((lon - LON0) * COS0 * K, (lat - LAT0) * K);

export default function IndiaMap3D({ teams, height = 620 }) {
  const mountRef = useRef(null);
  const labelRefs = useRef({});
  const hoverRef = useRef(null);
  const [geo, setGeo] = useState(null);
  const [hover, setHover] = useState(null);
  const [failed, setFailed] = useState(false);
  const navigate = useNavigate();
  const reduce = useReducedMotion();

  useEffect(() => { loadJSON('india').then(setGeo).catch(() => setFailed(true)); }, []);
  useEffect(() => { hoverRef.current = hover; }, [hover]);

  useEffect(() => {
    if (!geo || !mountRef.current) return;
    const mount = mountRef.current;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFailed(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const world = new THREE.Group();
    scene.add(world);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
    camera.up.set(0, 0, 1); // the map lies in the XY plane with Z pointing up
    camera.position.set(0, -15, 19);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 12;
    controls.maxDistance = 34;
    controls.minPolarAngle = 0.15;
    controls.maxPolarAngle = Math.PI / 2.15;
    controls.target.set(0, 0.5, 0);
    let userMoved = false;

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(-8, -10, 18);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x6f8cff, 0.8);
    rim.position.set(10, 12, 6);
    scene.add(rim);

    // ---------- India landmass (extruded) ----------
    const land = new THREE.Group();
    const topMat = new THREE.MeshStandardMaterial({ color: 0x24304d, metalness: 0.3, roughness: 0.5 });
    const sideMat = new THREE.MeshStandardMaterial({ color: 0x111a30, metalness: 0.2, roughness: 0.7 });
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x8fb0ff, transparent: true, opacity: 0.85 });
    geo.rings.forEach(ring => {
      const pts = ring.map(([lon, lat]) => project(lon, lat));
      const shape = new THREE.Shape(pts);
      const g = new THREE.ExtrudeGeometry(shape, { depth: DEPTH, bevelEnabled: true, bevelThickness: 0.08,
        bevelSize: 0.06, bevelSegments: 2 });
      land.add(new THREE.Mesh(g, [topMat, sideMat]));
      const edge = new THREE.BufferGeometry().setFromPoints(pts.map(p => new THREE.Vector3(p.x, p.y, DEPTH + 0.1)));
      land.add(new THREE.LineLoop(edge, edgeMat));
    });
    world.add(land);

    // ---------- floor grid of dots ----------
    const dots = [];
    for (let x = -16; x <= 16; x += 0.8) for (let y = -14; y <= 14; y += 0.8) dots.push(x, y, -0.05);
    const dotGeo = new THREE.BufferGeometry();
    dotGeo.setAttribute('position', new THREE.Float32BufferAttribute(dots, 3));
    world.add(new THREE.Points(dotGeo, new THREE.PointsMaterial({ color: 0x3a4a72, size: 0.05, transparent: true, opacity: 0.6 })));

    // ---------- franchise pins ----------
    const pins = [];
    TEAM_CODES.forEach(code => {
      const h = geo.homes[code];
      if (!h) return;
      const p = project(h.lon, h.lat);
      const color = new THREE.Color(theme(code).accent);
      const group = new THREE.Group();
      group.position.set(p.x, p.y, DEPTH + 0.1);
      const beamH = 2.2;
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, beamH, 12),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9 }));
      beam.rotation.x = Math.PI / 2;
      beam.position.z = beamH / 2;
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.2, 24, 16),
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.6 }));
      head.position.z = beamH;
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.3, 40),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
      ring.position.z = 0.02;
      const hit = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.45, beamH + 0.6, 8),
        new THREE.MeshBasicMaterial({ visible: false }));
      hit.rotation.x = Math.PI / 2;
      hit.position.z = beamH / 2;
      hit.userData.code = code;
      group.add(beam, head, ring, hit);
      world.add(group);
      pins.push({ code, group, ring, head, hit, top: new THREE.Vector3(p.x, p.y, DEPTH + 0.1 + beamH + 0.35) });
    });

    // ---------- interaction ----------
    const ray = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const onMove = e => {
      const r = renderer.domElement.getBoundingClientRect();
      mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(mouse, camera);
      const hitObj = ray.intersectObjects(pins.map(p => p.hit))[0];
      const code = hitObj ? hitObj.object.userData.code : null;
      if (code !== hoverRef.current) setHover(code);
      renderer.domElement.style.cursor = code ? 'pointer' : 'grab';
    };
    const onClick = () => { if (hoverRef.current) navigate(`/team/${hoverRef.current}`); };
    renderer.domElement.addEventListener('pointermove', onMove);
    renderer.domElement.addEventListener('click', onClick);
    controls.addEventListener('start', () => { userMoved = true; });

    const resize = () => {
      const w = mount.clientWidth || 1;
      const hgt = mount.clientHeight || 1;
      renderer.setSize(w, hgt, false);
      camera.aspect = w / hgt;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    // ---------- loop ----------
    const clock = new THREE.Clock();
    const v = new THREE.Vector3();
    let raf;
    const loop = () => {
      const t = clock.getElapsedTime();
      if (!reduce && !userMoved) world.rotation.z = Math.sin(t * 0.25) * 0.08; // gentle idle sway
      controls.update();
      world.updateMatrixWorld();
      pins.forEach((p, i) => {
        const active = hoverRef.current === p.code;
        const s = reduce ? 1 : 1 + ((t * 0.8 + i * 0.13) % 1) * 2.2;
        p.ring.scale.setScalar(s);
        p.ring.material.opacity = reduce ? 0.6 : 0.8 * (1 - ((t * 0.8 + i * 0.13) % 1));
        p.head.scale.setScalar(active ? 1.6 : 1);
        // move the HTML label to the pin's screen position
        const el = labelRefs.current[p.code];
        if (el) {
          v.copy(p.top).applyMatrix4(world.matrixWorld).project(camera);
          const x = (v.x * 0.5 + 0.5) * mount.clientWidth;
          const y = (-v.y * 0.5 + 0.5) * mount.clientHeight;
          el.style.transform = `translate(-50%, -100%) translate(${x}px, ${y}px)`;
          el.style.zIndex = String(Math.round((1 - v.z) * 1000));
          el.style.opacity = v.z < 1 ? '1' : '0';
        }
      });
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener('pointermove', onMove);
      renderer.domElement.removeEventListener('click', onClick);
      controls.dispose();
      scene.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose());
      });
      renderer.dispose();
      renderer.forceContextLoss();
      if (renderer.domElement.parentElement === mount) mount.removeChild(renderer.domElement);
    };
  }, [geo, navigate, reduce]);

  const info = hover && teams?.[hover];
  const home = hover && geo?.homes?.[hover];

  if (failed) {
    return <div className="map-fallback glass">The 3D map needs WebGL. Use the team list below.</div>;
  }

  return (
    <div className="map-wrap" style={{ height }}>
      <div ref={mountRef} className="map-canvas" />
      <div className="map-labels">
        {geo && TEAM_CODES.map(code => (
          <button key={code} type="button" ref={el => { labelRefs.current[code] = el; }}
            className={`map-label ${hover === code ? 'is-hover' : ''}`}
            style={{ '--team': theme(code).accent }}
            onMouseEnter={() => setHover(code)} onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(code)} onBlur={() => setHover(null)}
            onClick={() => navigate(`/team/${code}`)}
            aria-label={`${theme(code).name}, ${geo.homes[code]?.city}. Open war room`}>
            <TeamLogo code={code} size={28} />
            <span className="map-label-code">{code}</span>
          </button>
        ))}
      </div>
      <div className="map-help">Drag to rotate · scroll to zoom · select a franchise</div>
      {info && home && (
        <div className="map-card glass" style={{ '--team': theme(hover).accent }}>
          <div className="map-card-head">
            <TeamLogo code={hover} size={44} />
            <div>
              <div className="map-card-name">{theme(hover).name}</div>
              <div className="map-card-sub">{home.ground}, {home.city}</div>
            </div>
          </div>
          <div className="map-card-row">
            <span>{ordinal(info.brief.finish_2026)} in 2026</span>
            <Pill tone={info.brief.stance === 'Win Now' ? 'pill-win' : 'pill-build'}>{info.brief.stance}</Pill>
          </div>
          <div className="map-card-gaps">
            {info.brief.red_roles.length ? `Must fix: ${info.brief.red_roles.join(', ')}` : 'No red gaps'}
          </div>
        </div>
      )}
      <div className="map-credit">Boundary: datameet (CC BY 4.0)</div>
    </div>
  );
}

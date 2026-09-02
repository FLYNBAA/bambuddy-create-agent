import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { ThreeMFLoader } from 'three/addons/loaders/3MFLoader.js';
import { Loader2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from './Button';
import { getAuthToken } from '../api/client';

interface BuildVolume { x: number; y: number; z: number; }
interface ModelViewerProps {
  url: string;
  fileType?: string;
  buildVolume?: BuildVolume;
  filamentColors?: string[];
  selectedPlateId?: number | null;
  className?: string;
  showControls?: boolean;
}

const DEFAULT_BUILD_VOLUME: BuildVolume = { x: 256, y: 256, z: 256 };

function disposeGroup(group: THREE.Object3D): void {
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  group.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;
    child.geometry.dispose();
    const values = Array.isArray(child.material) ? child.material : [child.material];
    for (const material of values) {
      for (const value of Object.values(material)) {
        if (value && typeof value === 'object' && 'isTexture' in value) textures.add(value as THREE.Texture);
      }
      materials.add(material);
    }
  });
  materials.forEach((material) => material.dispose());
  textures.forEach((texture) => {
    const source = texture.source.data;
    if (typeof ImageBitmap !== 'undefined' && source instanceof ImageBitmap) source.close();
    texture.dispose();
  });
}

function fitCamera(camera: THREE.PerspectiveCamera, controls: OrbitControls, group: THREE.Object3D): void {
  const box = new THREE.Box3().setFromObject(group);
  if (box.isEmpty()) throw new Error('Model contains no renderable geometry');
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.001);
  const verticalFov = THREE.MathUtils.degToRad(camera.fov);
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect);
  const distance = 1.18 * Math.max(radius / Math.sin(verticalFov / 2), radius / Math.sin(horizontalFov / 2));
  camera.position.copy(center).addScaledVector(new THREE.Vector3(.7, .5, .7).normalize(), distance);
  camera.near = Math.max(distance / 1000, .01);
  camera.far = distance + radius * 4;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

async function loadModel(url: string, fileType: string, headers: HeadersInit): Promise<THREE.Group> {
  const response = await fetch(url, { headers });
  if (!response.ok) throw new Error(`Model request failed (${response.status})`);
  const data = await response.arrayBuffer();
  if (fileType === '3mf') {
    const group = new ThreeMFLoader().parse(data);
    // 3MF coordinates are Z-up whereas this WebGL scene is Y-up. ThreeMFLoader
    // preserves source positions, so convert the loaded root once instead of
    // mutating every geometry and losing its material/color associations.
    group.rotation.x = -Math.PI / 2;
    return group;
  }
  if (fileType === 'glb' || fileType === 'gltf') {
    return await new Promise<THREE.Group>((resolve, reject) => new GLTFLoader().parse(data, '', (gltf) => resolve(gltf.scene), reject));
  }
  if (fileType === 'stl') {
    const geometry = new STLLoader().parse(data);
    geometry.computeVertexNormals();
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshStandardMaterial({ color: new THREE.Color('#00ae42'), roughness: .62, metalness: 0 });
    const group = new THREE.Group();
    group.add(new THREE.Mesh(geometry, material));
    return group;
  }
  throw new Error('Unsupported model format');
}

export function ModelViewer({ url, fileType, buildVolume = DEFAULT_BUILD_VOLUME, filamentColors, selectedPlateId, className = '', showControls = true }: ModelViewerProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const renderRef = useRef<(() => void) | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void filamentColors;
    void selectedPlateId;
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a1a);
    const camera = new THREE.PerspectiveCamera(45, Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1), .1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = .85;
    container.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    const pmrem = new THREE.PMREMGenerator(renderer);
    const environment = pmrem.fromScene(new RoomEnvironment(), .04);
    scene.environment = environment.texture;
    const light = new THREE.DirectionalLight(0xffffff, .8);
    light.position.set(60, 200, 90);
    scene.add(light, new THREE.HemisphereLight(0xffffff, 0x303030, 1.1));
    const render = () => renderer.render(scene, camera);
    controls.addEventListener('change', render);
    cameraRef.current = camera;
    controlsRef.current = controls;
    renderRef.current = render;

    const resize = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (!width || !height) return;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize(); setLoading(true); setError(null);
    const normalizedType = (fileType || url.split('?')[0].split('.').pop() || '').toLowerCase();
    const headers: Record<string, string> = {};
    const token = getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    void loadModel(url, normalizedType, headers).then((group) => {
      if (cancelled) { disposeGroup(group); return; }
      modelRef.current = group;
      scene.add(group);
      const box = new THREE.Box3().setFromObject(group);
      group.position.y -= box.min.y;
      fitCamera(camera, controls, group);
      render(); setLoading(false);
    }).catch((reason: unknown) => {
      if (!cancelled) { setError(reason instanceof Error ? reason.message : t('modelViewer.errors.failedToLoad')); setLoading(false); }
    });

    return () => {
      cancelled = true;
      observer.disconnect(); controls.removeEventListener('change', render); controls.dispose();
      if (modelRef.current) { scene.remove(modelRef.current); disposeGroup(modelRef.current); modelRef.current = null; }
      scene.environment = null; environment.texture.dispose(); pmrem.dispose(); renderer.dispose(); renderer.domElement.remove();
      cameraRef.current = null; controlsRef.current = null; renderRef.current = null;
    };
  }, [url, fileType, buildVolume, filamentColors, selectedPlateId, t]);

  const zoom = (factor: number) => { if (cameraRef.current) { cameraRef.current.position.multiplyScalar(factor); renderRef.current?.(); } };
  const reset = () => { if (cameraRef.current && controlsRef.current && modelRef.current) { fitCamera(cameraRef.current, controlsRef.current, modelRef.current); renderRef.current?.(); } };
  return <div className={`relative ${className}`}>
    <div ref={containerRef} className="w-full h-full min-h-[400px]" />
    {loading && <div className="absolute inset-0 flex items-center justify-center bg-bambu-dark/80"><Loader2 className="w-8 h-8 text-bambu-green animate-spin" /></div>}
    {error && <div className="absolute inset-0 flex items-center justify-center bg-bambu-dark/80"><p className="text-red-400">{error}</p></div>}
    {showControls && !loading && !error && <div className="absolute bottom-4 right-4 flex gap-2"><Button variant="secondary" size="sm" onClick={() => zoom(.8)} aria-label="Zoom in model"><ZoomIn className="w-4 h-4" /></Button><Button variant="secondary" size="sm" onClick={() => zoom(1.25)} aria-label="Zoom out model"><ZoomOut className="w-4 h-4" /></Button><Button variant="secondary" size="sm" onClick={reset} aria-label="Reset model view"><RotateCcw className="w-4 h-4" /></Button></div>}
  </div>;
}

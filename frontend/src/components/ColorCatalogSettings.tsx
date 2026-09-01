import { Fragment, useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Palette, Plus, Trash2, RotateCcw, Loader2, Pencil, Check, X, Search, Download, Upload, Cloud } from 'lucide-react';
import { api, getAuthToken } from '../api/client';
import type { BambuddyColorCatalogEntry, ColorCatalogEntry } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { Card, CardHeader, CardContent } from './Card';
import { ConfirmModal } from './ConfirmModal';
import { FilamentSwatch } from './FilamentSwatch';
import { FILAMENT_EFFECT_OPTIONS } from './filamentSwatchHelpers';

export function ColorCatalogSettings() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [catalog, setCatalog] = useState<ColorCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterManufacturer, setFilterManufacturer] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Add/Edit form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formManufacturer, setFormManufacturer] = useState('');
  const [formColorName, setFormColorName] = useState('');
  const [formHexColor, setFormHexColor] = useState('#FFFFFF');
  const [formMaterial, setFormMaterial] = useState('');
  const [formExtraColors, setFormExtraColors] = useState('');
  const [formEffectType, setFormEffectType] = useState('');
  const [saving, setSaving] = useState(false);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState<{ fetched: number; total: number } | null>(null);
  const [showBambuddyChooser, setShowBambuddyChooser] = useState(false);
  const [bambuddyColors, setBambuddyColors] = useState<BambuddyColorCatalogEntry[]>([]);
  const [bambuddyLoading, setBambuddyLoading] = useState(false);
  const [bambuddyImporting, setBambuddyImporting] = useState(false);
  const [bambuddyError, setBambuddyError] = useState<string | null>(null);
  const [bambuddySearch, setBambuddySearch] = useState('');
  const [selectedBambuddyKeys, setSelectedBambuddyKeys] = useState<Set<string>>(new Set());

  // Confirmation modals
  const [deleteEntry, setDeleteEntry] = useState<ColorCatalogEntry | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const loadCatalog = useCallback(async () => {
    try {
      const entries = await api.getColorCatalog();
      setCatalog(entries);
    } catch {
      showToast(t('settings.colorCatalog.loadFailed'), 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast, t]);

  const loadBambuddyColors = useCallback(async () => {
    setBambuddyLoading(true);
    setBambuddyError(null);
    try {
      const entries = await api.getBambuddyColorCatalog();
      setBambuddyColors(entries);
      setSelectedBambuddyKeys(prev => new Set(
        [...prev].filter(key => entries.some(entry => entry.selection_key === key && !entry.exists)),
      ));
    } catch {
      setBambuddyError(t('settings.colorCatalog.bambuddyLoadFailed', {
        defaultValue: 'Could not load Bambu Lab colors. Try again.',
      }));
    } finally {
      setBambuddyLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  const manufacturers = [...new Set(catalog.map(e => e.manufacturer))].sort();

  const filteredCatalog = catalog.filter(entry => {
    const matchesSearch = search === '' ||
      entry.manufacturer.toLowerCase().includes(search.toLowerCase()) ||
      entry.color_name.toLowerCase().includes(search.toLowerCase()) ||
      (entry.material?.toLowerCase().includes(search.toLowerCase()) ?? false);
    const matchesManufacturer = filterManufacturer === '' || entry.manufacturer === filterManufacturer;
    return matchesSearch && matchesManufacturer;
  });

  const filteredBambuddyColors = bambuddyColors.filter(entry => {
    const query = bambuddySearch.trim().toLowerCase();
    return !query || [entry.manufacturer, entry.material, entry.color_name, entry.hex_color]
      .some(value => value.toLowerCase().includes(query));
  });

  const selectableBambuddyColors = filteredBambuddyColors.filter(entry => !entry.exists);

  const toggleBambuddyChooser = async () => {
    const willShow = !showBambuddyChooser;
    setShowBambuddyChooser(willShow);
    if (willShow && bambuddyColors.length === 0 && !bambuddyLoading) {
      await loadBambuddyColors();
    }
  };

  const toggleBambuddyColor = (selectionKey: string) => {
    setSelectedBambuddyKeys(prev => {
      const next = new Set(prev);
      if (next.has(selectionKey)) next.delete(selectionKey);
      else next.add(selectionKey);
      return next;
    });
  };

  const toggleAllBambuddyColors = () => {
    setSelectedBambuddyKeys(prev => {
      const next = new Set(prev);
      const allSelected = selectableBambuddyColors.length > 0 && selectableBambuddyColors
        .every(entry => next.has(entry.selection_key));
      for (const entry of selectableBambuddyColors) {
        if (allSelected) next.delete(entry.selection_key);
        else next.add(entry.selection_key);
      }
      return next;
    });
  };

  const handleBambuddyImport = async () => {
    const selectionKeys = [...selectedBambuddyKeys];
    if (selectionKeys.length === 0) return;
    setBambuddyImporting(true);
    setBambuddyError(null);
    try {
      const result = await api.importBambuddyColorCatalog(selectionKeys);
      setSelectedBambuddyKeys(new Set());
      await Promise.all([loadCatalog(), loadBambuddyColors()]);
      showToast(
        result.imported > 0
          ? t('settings.colorCatalog.bambuddyImportSuccess', {
            count: result.imported,
            defaultValue: `Imported ${result.imported} Bambu Lab color${result.imported === 1 ? '' : 's'}.`,
          })
          : t('settings.colorCatalog.bambuddyUpToDate', {
            defaultValue: 'All selected Bambu Lab colors are already available.',
          }),
        'success',
      );
    } catch {
      const message = t('settings.colorCatalog.bambuddyImportFailed', {
        defaultValue: 'Could not import Bambu Lab colors. Try again.',
      });
      setBambuddyError(message);
      showToast(message, 'error');
    } finally {
      setBambuddyImporting(false);
    }
  };

  const resetForm = () => {
    setFormManufacturer('');
    setFormColorName('');
    setFormHexColor('#FFFFFF');
    setFormMaterial('');
    setFormExtraColors('');
    setFormEffectType('');
  };

  const handleAdd = async () => {
    if (!formManufacturer.trim() || !formColorName.trim() || !formHexColor) {
      showToast(t('settings.colorCatalog.fieldsRequired'), 'error');
      return;
    }
    setSaving(true);
    try {
      const entry = await api.addColorEntry({
        manufacturer: formManufacturer.trim(),
        color_name: formColorName.trim(),
        hex_color: formHexColor,
        material: formMaterial.trim() || null,
        extra_colors: formExtraColors.trim() || null,
        effect_type: formEffectType.trim() || null,
      });
      setCatalog(prev => [...prev, entry].sort((a, b) =>
        a.manufacturer.localeCompare(b.manufacturer) ||
        (a.material || '').localeCompare(b.material || '') ||
        a.color_name.localeCompare(b.color_name)
      ));
      setShowAddForm(false);
      resetForm();
      showToast(t('settings.colorCatalog.colorAdded'), 'success');
    } catch {
      showToast(t('settings.colorCatalog.addFailed'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (entry: ColorCatalogEntry) => {
    setEditingId(entry.id);
    setFormManufacturer(entry.manufacturer);
    setFormColorName(entry.color_name);
    setFormHexColor(entry.hex_color);
    setFormMaterial(entry.material || '');
    setFormExtraColors(entry.extra_colors || '');
    setFormEffectType(entry.effect_type || '');
  };

  const cancelEdit = () => {
    setEditingId(null);
    resetForm();
  };

  const handleUpdate = async (id: number) => {
    if (!formManufacturer.trim() || !formColorName.trim() || !formHexColor) {
      showToast(t('settings.colorCatalog.fieldsRequired'), 'error');
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateColorEntry(id, {
        manufacturer: formManufacturer.trim(),
        color_name: formColorName.trim(),
        hex_color: formHexColor,
        material: formMaterial.trim() || null,
        extra_colors: formExtraColors.trim() || null,
        effect_type: formEffectType.trim() || null,
      });
      setCatalog(prev =>
        prev.map(e => e.id === id ? updated : e).sort((a, b) =>
          a.manufacturer.localeCompare(b.manufacturer) ||
          (a.material || '').localeCompare(b.material || '') ||
          a.color_name.localeCompare(b.color_name)
        )
      );
      setEditingId(null);
      resetForm();
      showToast(t('settings.colorCatalog.colorUpdated'), 'success');
    } catch {
      showToast(t('settings.colorCatalog.updateFailed'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteEntry) return;
    try {
      await api.deleteColorEntry(deleteEntry.id);
      setCatalog(prev => prev.filter(e => e.id !== deleteEntry.id));
      showToast(t('settings.colorCatalog.colorDeleted'), 'success');
    } catch {
      showToast(t('settings.colorCatalog.deleteFailed'), 'error');
    } finally {
      setDeleteEntry(null);
    }
  };

  const handleReset = async () => {
    setShowResetConfirm(false);
    setLoading(true);
    try {
      await api.resetColorCatalog();
      await loadCatalog();
      showToast(t('settings.colorCatalog.resetSuccess'), 'success');
    } catch {
      showToast(t('settings.colorCatalog.resetFailed'), 'error');
      setLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncProgress(null);
    try {
      const headers: Record<string, string> = {};
      const token = getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const response = await fetch('/api/v1/inventory/colors/sync', { method: 'POST', headers });
      if (!response.ok) throw new Error('Failed to start sync');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'progress') {
                setSyncProgress({ fetched: data.total_fetched, total: data.total_available });
              } else if (data.type === 'complete') {
                if (data.added === 0) {
                  showToast(t('settings.colorCatalog.syncUpToDate', { count: data.total_fetched }), 'success');
                } else {
                  showToast(t('settings.colorCatalog.syncComplete', { added: data.added, skipped: data.skipped }), 'success');
                }
              } else if (data.type === 'error') {
                showToast(`${t('settings.colorCatalog.syncError')}: ${data.error}`, 'error');
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
      await loadCatalog();
    } catch {
      showToast(t('settings.colorCatalog.syncFailed'), 'error');
    } finally {
      setSyncing(false);
      setSyncProgress(null);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredCatalog.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredCatalog.map(e => e.id)));
    }
  };

  const handleBulkDelete = async () => {
    setShowBulkDeleteConfirm(false);
    if (selectedIds.size === 0) return;
    try {
      const result = await api.bulkDeleteColorEntries([...selectedIds]);
      setCatalog(prev => prev.filter(e => !selectedIds.has(e.id)));
      setSelectedIds(new Set());
      showToast(t('settings.colorCatalog.bulkDeleted', { count: result.deleted }), 'success');
    } catch {
      showToast(t('settings.colorCatalog.bulkDeleteFailed'), 'error');
    }
  };

  const handleExport = () => {
    const exportData = catalog.map(({ manufacturer, color_name, hex_color, material, extra_colors, effect_type }) => ({
      manufacturer, color_name, hex_color, material, extra_colors, effect_type,
    }));
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'color-catalog.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(t('settings.colorCatalog.exported', { count: catalog.length }), 'success');
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text) as Array<{
        manufacturer: string; color_name: string; hex_color: string; material?: string | null;
        extra_colors?: string | null; effect_type?: string | null;
      }>;
      if (!Array.isArray(data)) throw new Error('Invalid format');

      let added = 0;
      let skipped = 0;
      for (const item of data) {
        if (!item.manufacturer || !item.color_name || !item.hex_color) { skipped++; continue; }
        const exists = catalog.some(c =>
          c.manufacturer.toLowerCase() === item.manufacturer.toLowerCase() &&
          c.color_name.toLowerCase() === item.color_name.toLowerCase() &&
          (c.material || '').toLowerCase() === (item.material || '').toLowerCase()
        );
        if (exists) { skipped++; continue; }
        try {
          const entry = await api.addColorEntry({
            manufacturer: item.manufacturer,
            color_name: item.color_name,
            hex_color: item.hex_color,
            material: item.material || null,
            extra_colors: item.extra_colors || null,
            effect_type: item.effect_type || null,
          });
          setCatalog(prev => [...prev, entry].sort((a, b) =>
            a.manufacturer.localeCompare(b.manufacturer) ||
            (a.material || '').localeCompare(b.material || '') ||
            a.color_name.localeCompare(b.color_name)
          ));
          added++;
        } catch { skipped++; }
      }
      showToast(t('settings.colorCatalog.imported', { added, skipped }), 'success');
    } catch {
      showToast(t('settings.colorCatalog.importFailed'), 'error');
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <Card id="card-color-catalog">
      <CardHeader>
        <div className="flex items-center gap-2 mb-3">
          <Palette className="w-5 h-5 text-bambu-gray" />
          <h2 className="text-lg font-semibold text-white">{t('settings.colorCatalog.title')}</h2>
          <span className="text-sm text-bambu-gray">({catalog.length})</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={handleExport}
            className="px-3 py-1.5 text-sm bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-bambu-gray hover:text-white transition-colors flex items-center gap-1.5"
          >
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.export')}</span>
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3 py-1.5 text-sm bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-bambu-gray hover:text-white transition-colors flex items-center gap-1.5"
          >
            <Upload className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.import')}</span>
          </button>
          <input ref={fileInputRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
          <button
            onClick={handleSync}
            disabled={syncing}
            className="px-3 py-1.5 text-sm bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-bambu-gray hover:text-white transition-colors flex items-center gap-1.5"
            title={t('settings.colorCatalog.syncTooltip')}
          >
            {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cloud className="w-4 h-4" />}
            <span className="hidden sm:inline">
              {syncing
                ? syncProgress
                  ? `${Math.min(syncProgress.fetched, syncProgress.total)} / ${syncProgress.total}`
                  : t('settings.colorCatalog.starting')
                : t('settings.colorCatalog.sync')}
            </span>
          </button>
          <button
            type="button"
            onClick={toggleBambuddyChooser}
            aria-expanded={showBambuddyChooser}
            aria-controls="bambuddy-color-import"
            className="px-3 py-1.5 text-sm bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-bambu-gray hover:text-white transition-colors flex items-center gap-1.5"
          >
            <Palette className="w-4 h-4" />
            <span>{t('settings.colorCatalog.bambuddyImport', { defaultValue: 'Bambu Lab colors' })}</span>
          </button>
          <button
            onClick={() => setShowResetConfirm(true)}
            className="px-3 py-1.5 text-sm bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-bambu-gray hover:text-white transition-colors flex items-center gap-1.5"
          >
            <RotateCcw className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.reset')}</span>
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            className="px-3 py-1.5 text-sm bg-bambu-green text-white rounded-lg hover:bg-bambu-green/80 transition-colors flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.add')}</span>
          </button>
        </div>
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-red-50 dark:bg-red-500/10 border border-red-300 dark:border-red-500/30 rounded-lg">
            <span className="text-sm text-red-700 dark:text-red-400">
              {t('settings.colorCatalog.selectedCount', { count: selectedIds.size })}
            </span>
            <button
              onClick={() => setShowBulkDeleteConfirm(true)}
              className="ml-auto px-3 py-1.5 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors flex items-center gap-1.5"
            >
              <Trash2 className="w-4 h-4" />
              {t('settings.colorCatalog.deleteSelected')}
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 text-sm text-bambu-gray hover:text-white transition-colors"
            >
              {t('common.cancel')}
            </button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-bambu-gray">
          {t('settings.colorCatalog.description')}
        </p>

        {showBambuddyChooser && (
          <section
            id="bambuddy-color-import"
            aria-labelledby="bambuddy-color-import-heading"
            className="p-4 bg-bambu-dark rounded-lg border border-bambu-dark-tertiary space-y-3"
          >
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <h3 id="bambuddy-color-import-heading" className="text-sm font-medium text-white">
                  {t('settings.colorCatalog.bambuddyImportHeading', { defaultValue: 'Import Bambu Lab colors' })}
                </h3>
                <p className="text-sm text-bambu-gray mt-1">
                  {t('settings.colorCatalog.bambuddyImportDescription', {
                    defaultValue: 'Select missing built-in colors to add them without changing catalog entries you already have.',
                  })}
                </p>
              </div>
              <button
                type="button"
                onClick={loadBambuddyColors}
                disabled={bambuddyLoading || bambuddyImporting}
                className="px-3 py-1.5 text-sm border border-bambu-dark-tertiary rounded-lg text-bambu-gray hover:text-white disabled:opacity-50 transition-colors"
              >
                {t('common.refresh', { defaultValue: 'Refresh' })}
              </button>
            </div>

            <label htmlFor="bambuddy-color-search" className="sr-only">
              {t('settings.colorCatalog.bambuddySearch', { defaultValue: 'Search Bambu Lab colors' })}
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray" />
              <input
                id="bambuddy-color-search"
                type="search"
                value={bambuddySearch}
                onChange={(event) => setBambuddySearch(event.target.value)}
                placeholder={t('settings.colorCatalog.bambuddySearch', { defaultValue: 'Search Bambu Lab colors' })}
                className="w-full pl-10 pr-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
              />
            </div>

            {bambuddyLoading ? (
              <div className="flex items-center py-4 text-sm text-bambu-gray" role="status">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                {t('common.loading')}
              </div>
            ) : bambuddyError ? (
              <p className="text-sm text-red-400" role="alert">{bambuddyError}</p>
            ) : (
              <>
                <div className="flex items-center justify-between gap-3 flex-wrap text-sm">
                  <span className="text-bambu-gray">
                    {t('settings.colorCatalog.bambuddyShowing', {
                      count: filteredBambuddyColors.length,
                      defaultValue: `${filteredBambuddyColors.length} built-in colors`,
                    })}
                  </span>
                  <button
                    type="button"
                    onClick={toggleAllBambuddyColors}
                    disabled={selectableBambuddyColors.length === 0 || bambuddyImporting}
                    className="text-bambu-green hover:text-white disabled:text-bambu-gray disabled:cursor-not-allowed transition-colors"
                  >
                    {t('settings.colorCatalog.bambuddySelectVisible', { defaultValue: 'Select all visible missing colors' })}
                  </button>
                </div>
                <div className="max-h-64 overflow-auto border border-bambu-dark-tertiary rounded-lg divide-y divide-bambu-dark-tertiary">
                  {filteredBambuddyColors.length === 0 ? (
                    <p className="px-3 py-6 text-sm text-center text-bambu-gray">
                      {t('settings.colorCatalog.bambuddyNoMatch', { defaultValue: 'No Bambu Lab colors match this search.' })}
                    </p>
                  ) : (
                    filteredBambuddyColors.map(entry => (
                      <label
                        key={entry.selection_key}
                        className={`flex items-center gap-3 px-3 py-2 ${entry.exists ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-bambu-dark-secondary'}`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedBambuddyKeys.has(entry.selection_key)}
                          disabled={entry.exists || bambuddyImporting}
                          onChange={() => toggleBambuddyColor(entry.selection_key)}
                          aria-label={`${entry.material} ${entry.color_name}${entry.exists ? ' (already available)' : ''}`}
                          className="w-4 h-4 accent-bambu-green cursor-pointer disabled:cursor-not-allowed"
                        />
                        <FilamentSwatch
                          rgba={`${entry.hex_color.replace(/^#/, '')}FF`}
                          className="w-7 h-7 shrink-0"
                          shape="square"
                          title={entry.hex_color}
                          effectSize="table"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm text-white truncate">{entry.color_name}</span>
                          <span className="block text-xs text-bambu-gray truncate">{entry.material} · {entry.hex_color}</span>
                        </span>
                        {entry.exists && (
                          <span className="text-xs text-bambu-gray whitespace-nowrap">
                            {t('settings.colorCatalog.bambuddyAvailable', { defaultValue: 'Already available' })}
                          </span>
                        )}
                      </label>
                    ))
                  )}
                </div>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <p className="text-sm text-bambu-gray" aria-live="polite">
                    {t('settings.colorCatalog.bambuddySelected', {
                      count: selectedBambuddyKeys.size,
                      defaultValue: `${selectedBambuddyKeys.size} color${selectedBambuddyKeys.size === 1 ? '' : 's'} selected`,
                    })}
                  </p>
                  <button
                    type="button"
                    onClick={handleBambuddyImport}
                    disabled={selectedBambuddyKeys.size === 0 || bambuddyImporting}
                    className="px-3 py-2 text-sm bg-bambu-green text-white rounded-lg hover:bg-bambu-green/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                  >
                    {bambuddyImporting && <Loader2 className="w-4 h-4 animate-spin" />}
                    {t('settings.colorCatalog.bambuddyImportSelected', {
                      count: selectedBambuddyKeys.size,
                      defaultValue: `Import ${selectedBambuddyKeys.size} selected color${selectedBambuddyKeys.size === 1 ? '' : 's'}`,
                    })}
                  </button>
                </div>
              </>
            )}
          </section>
        )}

        {/* Search and filter */}
        <div className="flex gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray" />
            <input
              type="text"
              className="w-full pl-10 pr-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
              placeholder={t('settings.colorCatalog.searchColors')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className="px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
            value={filterManufacturer}
            onChange={(e) => setFilterManufacturer(e.target.value)}
          >
            <option value="">{t('settings.colorCatalog.allManufacturers')}</option>
            {manufacturers.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* Add form */}
        {showAddForm && (
          <div className="p-4 bg-bambu-dark rounded-lg border border-bambu-dark-tertiary">
            <h3 className="text-sm font-medium text-white mb-3">{t('settings.colorCatalog.addNewColor')}</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 items-end">
              <input
                type="text"
                className="px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
                placeholder={t('settings.colorCatalog.manufacturer')}
                value={formManufacturer}
                onChange={(e) => setFormManufacturer(e.target.value)}
              />
              <input
                type="text"
                className="px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
                placeholder={t('settings.colorCatalog.colorName')}
                value={formColorName}
                onChange={(e) => setFormColorName(e.target.value)}
              />
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="w-20 h-10 rounded cursor-pointer border border-bambu-dark-tertiary"
                  value={formHexColor}
                  onChange={(e) => setFormHexColor(e.target.value)}
                />
                <input
                  type="text"
                  className="w-32 px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
                  placeholder="#FFFFFF"
                  value={formHexColor}
                  onChange={(e) => setFormHexColor(e.target.value)}
                />
              </div>
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  className="flex-1 max-w-lg min-w-[200px] px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
                  placeholder={t('settings.colorCatalog.materialOptional')}
                  value={formMaterial}
                  onChange={(e) => setFormMaterial(e.target.value)}
                />
                <button
                  onClick={handleAdd}
                  disabled={saving}
                  className="w-24 px-3 py-2 bg-bambu-green text-white rounded-lg hover:bg-bambu-green/80 flex items-center justify-center gap-3"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  {t('common.add')}
                </button>
                <button
                  onClick={() => { setShowAddForm(false); resetForm(); }}
                  className="p-2 ml-2 rounded-lg text-bambu-gray hover:text-white hover:bg-bambu-dark-tertiary"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
            {/* #1154: optional multi-colour stops + visual effect. */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
              <input
                type="text"
                className="px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white text-sm font-mono placeholder-bambu-gray focus:border-bambu-green focus:outline-none"
                placeholder={t('inventory.extraColorsPlaceholder')}
                value={formExtraColors}
                onChange={(e) => setFormExtraColors(e.target.value)}
              />
              <select
                className="px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:border-bambu-green focus:outline-none"
                value={formEffectType}
                onChange={(e) => setFormEffectType(e.target.value)}
              >
                {FILAMENT_EFFECT_OPTIONS.map((opt) => (
                  <option key={opt.value || 'none'} value={opt.value}>
                    {t(opt.labelKey)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Filter info */}
        {(search || filterManufacturer) && (
          <div className="text-xs text-bambu-gray">
            {t('settings.colorCatalog.showing', { filtered: filteredCatalog.length, total: catalog.length })}
          </div>
        )}

        {/* Catalog list */}
        {loading ? (
          <div className="flex items-center justify-center py-8 text-bambu-gray">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            {t('common.loading')}
          </div>
        ) : (
          <div className="max-h-[600px] overflow-auto border border-bambu-dark-tertiary rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-bambu-dark sticky top-0">
                <tr>
                  <th className="px-2 py-2 w-10">
                    <input
                      type="checkbox"
                      checked={filteredCatalog.length > 0 && selectedIds.size === filteredCatalog.length}
                      onChange={toggleSelectAll}
                      className="w-4 h-4 accent-bambu-green cursor-pointer"
                    />
                  </th>
                  <th className="px-3 py-2 text-left text-bambu-gray font-medium w-12"></th>
                  <th className="px-3 py-2 text-left text-bambu-gray font-medium">{t('settings.colorCatalog.manufacturer')}</th>
                  <th className="px-3 py-2 text-left text-bambu-gray font-medium">{t('inventory.material')}</th>
                  <th className="px-3 py-2 text-left text-bambu-gray font-medium">{t('settings.colorCatalog.colorName')}</th>
                  <th className="px-3 py-2 text-left text-bambu-gray font-medium w-24">{t('settings.colorCatalog.hex')}</th>
                  <th className="px-3 py-2 w-16"></th>
                </tr>
              </thead>
              <tbody>
                {filteredCatalog.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-bambu-gray">
                      {search || filterManufacturer ? t('settings.colorCatalog.noMatch') : t('settings.colorCatalog.empty')}
                    </td>
                  </tr>
                ) : (
                  filteredCatalog.map(entry => (
                    <Fragment key={entry.id}>
                    <tr className={`border-t border-bambu-dark-tertiary hover:bg-bambu-dark ${selectedIds.has(entry.id) ? 'bg-bambu-dark' : ''}`}>
                      {editingId === entry.id ? (
                        <>
                          <td className="px-2 py-2">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(entry.id)}
                              onChange={() => toggleSelect(entry.id)}
                              className="w-4 h-4 accent-bambu-green cursor-pointer"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="color"
                              className="w-8 h-8 rounded cursor-pointer border border-bambu-dark-tertiary"
                              value={formHexColor}
                              onChange={(e) => setFormHexColor(e.target.value)}
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="text"
                              className="w-full px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
                              value={formManufacturer}
                              onChange={(e) => setFormManufacturer(e.target.value)}
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="text"
                              className="w-full px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
                              value={formMaterial}
                              onChange={(e) => setFormMaterial(e.target.value)}
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="text"
                              className="w-full px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
                              value={formColorName}
                              onChange={(e) => setFormColorName(e.target.value)}
                            />
                          </td>
                          <td className="px-3 py-2">
                            <input
                              type="text"
                              className="w-full px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
                              value={formHexColor}
                              onChange={(e) => setFormHexColor(e.target.value)}
                            />
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex justify-end gap-1">
                              <button
                                onClick={() => handleUpdate(entry.id)}
                                disabled={saving}
                                className="p-1.5 rounded hover:bg-green-500/20 text-green-500"
                              >
                                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                              </button>
                              <button onClick={cancelEdit} className="p-1.5 rounded hover:bg-bambu-dark-tertiary text-bambu-gray">
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-2 py-2">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(entry.id)}
                              onChange={() => toggleSelect(entry.id)}
                              className="w-4 h-4 accent-bambu-green cursor-pointer"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <FilamentSwatch
                              rgba={entry.hex_color.replace(/^#/, '') + (entry.hex_color.length === 7 ? 'FF' : '')}
                              extraColors={entry.extra_colors}
                              effectType={entry.effect_type}
                              className="w-8 h-8"
                              shape="square"
                              title={entry.hex_color}
                              effectSize="table"
                            />
                          </td>
                          <td className="px-3 py-2 text-white">{entry.manufacturer}</td>
                          <td className="px-3 py-2 text-bambu-gray">{entry.material || '-'}</td>
                          <td className="px-3 py-2 text-white">{entry.color_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-bambu-gray">{entry.hex_color}</td>
                          <td className="px-3 py-2">
                            <div className="flex justify-end gap-1">
                              <button
                                onClick={() => startEdit(entry)}
                                className="p-1.5 rounded hover:bg-bambu-dark-tertiary text-bambu-gray hover:text-white"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => setDeleteEntry(entry)}
                                className="p-1.5 rounded bg-red-500/10 hover:bg-red-500/20 text-red-500"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                    {editingId === entry.id && (
                      <tr className="border-t border-bambu-dark-tertiary/50 bg-bambu-dark">
                        <td colSpan={2}></td>
                        <td className="px-3 py-2" colSpan={2}>
                          <input
                            type="text"
                            className="w-full px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm font-mono focus:border-bambu-green focus:outline-none"
                            placeholder={t('inventory.extraColorsPlaceholder')}
                            value={formExtraColors}
                            onChange={(e) => setFormExtraColors(e.target.value)}
                          />
                        </td>
                        <td className="px-3 py-2" colSpan={2}>
                          <select
                            className="w-full px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
                            value={formEffectType}
                            onChange={(e) => setFormEffectType(e.target.value)}
                          >
                            {FILAMENT_EFFECT_OPTIONS.map((opt) => (
                              <option key={opt.value || 'none'} value={opt.value}>
                                {t(opt.labelKey)}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td></td>
                      </tr>
                    )}
                    </Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      {/* Delete confirmation */}
      {deleteEntry && (
        <ConfirmModal
          title={t('settings.colorCatalog.deleteColor')}
          message={t('settings.colorCatalog.deleteConfirm', { name: `${deleteEntry.manufacturer} - ${deleteEntry.color_name}` })}
          confirmText={t('common.delete')}
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleteEntry(null)}
        />
      )}

      {/* Bulk delete confirmation */}
      {showBulkDeleteConfirm && (
        <ConfirmModal
          title={t('settings.colorCatalog.deleteSelected')}
          message={t('settings.colorCatalog.bulkDeleteConfirm', { count: selectedIds.size })}
          confirmText={t('common.delete')}
          variant="danger"
          onConfirm={handleBulkDelete}
          onCancel={() => setShowBulkDeleteConfirm(false)}
        />
      )}

      {/* Reset confirmation */}
      {showResetConfirm && (
        <ConfirmModal
          title={t('settings.colorCatalog.resetCatalog')}
          message={t('settings.colorCatalog.resetConfirm')}
          confirmText={t('common.reset')}
          variant="danger"
          onConfirm={handleReset}
          onCancel={() => setShowResetConfirm(false)}
        />
      )}
    </Card>
  );
}

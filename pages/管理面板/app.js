// NoteSift 管理面板 - 合并版

// Wait for bridge to be available
function waitForBridge() {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const maxAttempts = 50;

    const checkBridge = () => {
      attempts++;
      if (window.AstrBotPluginPage) {
        console.log('[Bridge] Found after', attempts, 'attempts');
        resolve(window.AstrBotPluginPage);
      } else if (attempts >= maxAttempts) {
        reject(new Error('Bridge SDK 加载超时'));
      } else {
        setTimeout(checkBridge, 100);
      }
    };

    checkBridge();
  });
}

let bridge = null;
let vaults = [];
let searchQuery = '';
let currentView = 'dashboard';
let selectedZipFile = null;

// Toast notifications
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// API helpers
async function apiGet(endpoint, params = {}) {
  try {
    console.log(`[API] GET ${endpoint}`, params);
    const result = await bridge.apiGet(endpoint, params);
    console.log(`[API] GET ${endpoint} response:`, result);
    return result;
  } catch (error) {
    console.error(`[API] GET ${endpoint} error:`, error);
    showToast(error.message || 'API 请求失败', 'error');
    throw error;
  }
}

async function apiPost(endpoint, body = {}) {
  try {
    console.log(`[API] POST ${endpoint}`, body);
    const result = await bridge.apiPost(endpoint, body);
    console.log(`[API] POST ${endpoint} response:`, result);
    return result;
  } catch (error) {
    console.error(`[API] POST ${endpoint} error:`, error);
    showToast(error.message || 'API 请求失败', 'error');
    throw error;
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',', 2)[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error('文件读取失败'));
    reader.readAsDataURL(file);
  });
}

function formatLocalDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).format(date);
}

// Theme sync
function syncTheme() {
  try {
    const context = bridge.getContext();
    let theme = 'light';
    if (context?.theme) {
      theme = context.theme;
    }
    document.documentElement.setAttribute('data-theme', theme);
  } catch (error) {
    console.error('[Theme] Sync failed:', error);
    document.documentElement.setAttribute('data-theme', 'light');
  }
}

// View switching
function switchView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  document.getElementById(`${viewName}View`).classList.add('active');
  document.querySelector(`[data-view="${viewName}"]`).classList.add('active');

  currentView = viewName;
  window.location.hash = viewName;

  if (viewName === 'settings') {
    loadConfig();
  } else if (viewName === 'vault') {
    loadVaults();
  }
}

// Dashboard functions
async function loadVaults() {
  try {
    console.log('[Dashboard] Loading vaults...');
    const data = await apiGet('vaults');
    console.log('[Dashboard] API response:', data);
    vaults = data.vaults || [];
    console.log('[Dashboard] Parsed vaults:', vaults);
    renderStats();
    renderVaults();
    renderVaultManager();
  } catch (error) {
    console.error('[Dashboard] Load error:', error);
    renderError();
  }
}

function renderStats() {
  const totalVaults = vaults.length;
  const totalFiles = vaults.reduce((sum, v) => sum + (v.file_count || 0), 0);
  const indexedVaults = vaults.filter(v => v.has_index).length;

  document.getElementById('stats').innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${totalVaults}</div>
      <div class="stat-label">知识库总数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${totalFiles}</div>
      <div class="stat-label">文件总数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${indexedVaults}</div>
      <div class="stat-label">已索引</div>
    </div>
  `;
}

function renderVaults() {
  const container = document.getElementById('vaultList');

  if (vaults.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
          <polyline points="9 22 9 12 15 12 15 22"></polyline>
        </svg>
        <p>暂无知识库</p>
        <p style="font-size: 12px; color: var(--text-secondary);">请在插件配置中上传 ZIP 文件</p>
      </div>
    `;
    return;
  }

  const filteredVaults = vaults.filter(v =>
    !searchQuery || String(v.name || v.vault_id || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (filteredVaults.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>未找到匹配的知识库</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filteredVaults.map(vault => `
    <div class="vault-card">
      <div class="vault-header">
        <div class="vault-title">
          <div class="vault-icon">${(vault.name || 'V').charAt(0).toUpperCase()}</div>
          <h3 class="vault-name">${escapeHtml(vault.name || '未命名')}</h3>
        </div>
        <div class="vault-status">
          ${vault.has_index
            ? '<span class="badge badge-success">已索引</span>'
            : '<span class="badge badge-warning">未索引</span>'}
        </div>
      </div>
      <div class="vault-meta">
        <div class="meta-item">
          <span class="meta-label">文件数量</span>
          <span class="meta-value">${escapeHtml(vault.file_count || 0)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">导入时间</span>
          <span class="meta-value">${escapeHtml(formatLocalDateTime(vault.imported_at))}</span>
        </div>
      </div>
    </div>
  `).join('');
}

function renderVaultManager() {
  const container = document.getElementById('vaultManagerList');
  if (!container) return;

  if (vaults.length === 0) {
    container.innerHTML = `
      <div class="empty-state manager-empty">
        <p>暂无可管理的知识库</p>
        <p style="font-size: 12px;">上传 zip 后会在这里显示操作入口</p>
      </div>
    `;
    return;
  }

  container.innerHTML = vaults.map(vault => {
    const vaultId = escapeHtml(vault.vault_id || 'default');
    const name = escapeHtml(vault.name || vault.vault_id || '未命名');
    const importedAt = escapeHtml(formatLocalDateTime(vault.imported_at));
    const fileCount = escapeHtml(vault.file_count || 0);
    return `
      <article class="vault-manager-card">
        <div class="vault-manager-main">
          <div class="vault-icon">${name.charAt(0).toUpperCase()}</div>
          <div>
            <h3>${name}</h3>
            <p><code>${vaultId}</code></p>
          </div>
        </div>
        <div class="vault-manager-meta">
          <span>文件 ${fileCount}</span>
          <span>导入 ${importedAt}</span>
          ${vault.has_manifest ? '<span class="badge badge-success">manifest</span>' : '<span class="badge badge-warning">no manifest</span>'}
          ${vault.has_index ? '<span class="badge badge-success">index</span>' : '<span class="badge badge-warning">no index</span>'}
        </div>
        <div class="vault-actions">
          <button class="btn btn-secondary" data-action="rebuild" data-vault-id="${vaultId}">重建索引</button>
          <button class="btn btn-danger" data-action="delete" data-vault-id="${vaultId}">删除</button>
        </div>
      </article>
    `;
  }).join('');
}

function setSelectedZipFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.zip')) {
    showToast('请选择 zip 文件', 'error');
    return;
  }
  selectedZipFile = file;
  document.getElementById('selectedFileName').textContent = file.name;
}

async function importVault() {
  if (!selectedZipFile) {
    showToast('请先选择 zip 文件', 'error');
    return;
  }

  const btn = document.getElementById('importVaultBtn');
  btn.disabled = true;
  btn.textContent = '导入中...';

  try {
    const contentBase64 = await fileToBase64(selectedZipFile);
    const vaultId = document.getElementById('vaultIdInput').value.trim();
    const result = await apiPost('vault/import', {
      filename: selectedZipFile.name,
      vault_id: vaultId,
      content_base64: contentBase64
    });
    showToast(`导入完成：${result.manifest?.vault_id || vaultId || selectedZipFile.name}`, 'success');
    selectedZipFile = null;
    document.getElementById('zipFileInput').value = '';
    document.getElementById('vaultIdInput').value = '';
    document.getElementById('selectedFileName').textContent = '选择或拖入 zip 文件';
    await loadVaults();
  } catch (error) {
    showToast('导入失败: ' + error.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '上传并导入';
  }
}

async function rebuildVault(vaultId, button) {
  button.disabled = true;
  button.textContent = '重建中...';
  try {
    await apiPost('vault/rebuild', { vault_id: vaultId });
    showToast(`已重建 ${vaultId}`, 'success');
    await loadVaults();
  } catch (error) {
    showToast('重建失败: ' + error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = '重建索引';
  }
}

function getActionButton(target) {
  let node = target;
  while (node && node !== document) {
    if (node.matches && node.matches('button[data-action]')) {
      return node;
    }
    node = node.parentNode;
  }
  return null;
}

async function deleteVault(vaultId, button) {
  if (button.dataset.confirming !== 'true') {
    button.dataset.confirming = 'true';
    button.textContent = '确认删除';
    button.classList.add('confirming');
    showToast(`再次点击确认删除 ${vaultId}`, 'error');
    setTimeout(() => {
      if (button.dataset.confirming === 'true') {
        button.dataset.confirming = 'false';
        button.textContent = '删除';
        button.classList.remove('confirming');
      }
    }, 5000);
    return;
  }

  button.disabled = true;
  button.textContent = '删除中...';
  try {
    await apiPost('vault/delete', { vault_id: vaultId });
    showToast(`已删除 ${vaultId}`, 'success');
    await loadVaults();
  } catch (error) {
    showToast('删除失败: ' + error.message, 'error');
  } finally {
    button.disabled = false;
    button.dataset.confirming = 'false';
    button.classList.remove('confirming');
    button.textContent = '删除';
  }
}

function renderError() {
  document.getElementById('vaultList').innerHTML = `
    <div class="empty-state">
      <p style="color: var(--error-color);">加载失败</p>
      <p style="font-size: 12px;">请检查控制台日志</p>
    </div>
  `;
}

// Settings functions
async function loadConfig() {
  try {
    const config = await apiGet('config');
    populateForm(config);
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('settingsForm').style.display = 'block';
  } catch (error) {
    document.getElementById('loadingState').innerHTML = `
      <p style="color: var(--error-color);">加载配置失败</p>
      <p style="font-size: 12px;">${error.message}</p>
    `;
  }
}

function populateForm(config) {
  document.getElementById('maxDiscoverSnippetChars').value = config.max_discover_snippet_chars || 300;
  document.getElementById('defaultReadMode').value = config.default_read_mode || 'outline';
  document.getElementById('maxReadChars').value = config.max_read_chars || 8000;
  document.getElementById('fullOverLimitStrategy').value = config.full_over_limit_strategy || 'strict';
  document.getElementById('compressedSectionPreviewChars').value = config.compressed_section_preview_chars || 200;
  document.getElementById('enableAcl').checked = config.enable_acl || false;
  document.getElementById('allowedSessions').value = config.allowed_sessions || '';

  toggleAllowedSessions();
}

function toggleAllowedSessions() {
  const enabled = document.getElementById('enableAcl').checked;
  document.getElementById('allowedSessionsGroup').style.display = enabled ? 'block' : 'none';
}

async function saveConfig() {
  const btn = document.getElementById('saveBtn');
  btn.disabled = true;
  btn.textContent = '保存中...';

  try {
    const config = {
      max_discover_snippet_chars: parseInt(document.getElementById('maxDiscoverSnippetChars').value),
      default_read_mode: document.getElementById('defaultReadMode').value,
      max_read_chars: parseInt(document.getElementById('maxReadChars').value),
      full_over_limit_strategy: document.getElementById('fullOverLimitStrategy').value,
      compressed_section_preview_chars: parseInt(document.getElementById('compressedSectionPreviewChars').value),
      enable_acl: document.getElementById('enableAcl').checked,
      allowed_sessions: document.getElementById('allowedSessions').value
    };

    await apiPost('config', config);
    showToast('设置保存成功', 'success');
  } catch (error) {
    showToast('保存失败: ' + error.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>保存设置';
  }
}

// Event bindings
function bindEvents() {
  // Navigation
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const view = item.dataset.view;
      switchView(view);
    });
  });

  // Dashboard events
  document.getElementById('refreshBtn').addEventListener('click', loadVaults);
  document.getElementById('searchInput').addEventListener('input', (e) => {
    searchQuery = e.target.value;
    renderVaults();
  });

  // Vault management events
  document.getElementById('vaultRefreshBtn').addEventListener('click', loadVaults);
  document.getElementById('zipFileInput').addEventListener('change', (e) => {
    setSelectedZipFile(e.target.files[0]);
  });
  document.getElementById('uploadDrop').addEventListener('click', () => {
    document.getElementById('zipFileInput').click();
  });
  document.getElementById('uploadDrop').addEventListener('dragover', (e) => {
    e.preventDefault();
    e.currentTarget.classList.add('dragging');
  });
  document.getElementById('uploadDrop').addEventListener('dragleave', (e) => {
    e.currentTarget.classList.remove('dragging');
  });
  document.getElementById('uploadDrop').addEventListener('drop', (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('dragging');
    setSelectedZipFile(e.dataTransfer.files[0]);
  });
  document.getElementById('importVaultBtn').addEventListener('click', importVault);
  document.getElementById('vaultManagerList').addEventListener('click', (e) => {
    const button = getActionButton(e.target);
    if (!button) return;
    const vaultId = button.dataset.vaultId;
    if (button.dataset.action === 'rebuild') {
      rebuildVault(vaultId, button);
    } else if (button.dataset.action === 'delete') {
      deleteVault(vaultId, button);
    }
  });

  // Settings events
  document.getElementById('enableAcl').addEventListener('change', toggleAllowedSessions);
  document.getElementById('saveBtn').addEventListener('click', async (e) => {
    e.preventDefault();
    await saveConfig();
  });
}

// Initialization
async function init() {
  console.log('[App] Initializing...');
  try {
    bridge = await waitForBridge();
    console.log('[App] Bridge loaded:', bridge);

    const context = await bridge.ready();
    console.log('[App] Bridge ready, context:', context);
    syncTheme();
    bridge.onContext(syncTheme);

    // Load initial view based on hash
    const hash = window.location.hash.slice(1);
    if (hash === 'settings') {
      switchView('settings');
    } else if (hash === 'vault') {
      switchView('vault');
    } else {
      await loadVaults();
    }

    bindEvents();
    console.log('[App] Init complete');
  } catch (error) {
    console.error('[App] Init failed:', error);
    showToast('初始化失败: ' + error.message, 'error');
  }
}

init();

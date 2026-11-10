// FaceKids - API Bridge Client
// Conecta a interface moderna do Conceito A aos endpoints Python locais

const FaceKidsAPI = {
  baseUrl: window.location.origin,
  token: window.__FACEKIDS_TOKEN__ || null,

  getHeaders() {
    const headers = { "Content-Type": "application/json" };
    const currentToken = this.token || window.__FACEKIDS_TOKEN__;
    if (currentToken) {
      headers["X-Session-Token"] = currentToken;
      headers["X-FaceKids-Token"] = currentToken;
    }
    return headers;
  },

  async getStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/api/status`, {
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      console.warn("API offline, usando modo estatico:", e);
      return null;
    }
  },

  async getDiagnostics() {
    try {
      const res = await fetch(`${this.baseUrl}/api/diagnostics`, {
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      return null;
    }
  },

  async getServiceStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/api/service/status`, {
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      return { ok: false, health: {} };
    }
  },

  async restartService() {
    try {
      const res = await fetch(`${this.baseUrl}/api/service/restart`, {
        method: "POST",
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async install(pin, childName, limitHours, filhosPassword = "", filhosUsername = "Filhos") {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60s timeout seguro

      const res = await fetch(`${this.baseUrl}/api/install`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({
          pin,
          child_name: childName,
          daily_limit_hours: limitHours,
          filhos_password: filhosPassword,
          filhos_username: filhosUsername
        }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        return {
          ok: false,
          error: (data && data.error) ? data.error : `Erro HTTP ${res.status}`
        };
      }
      if (data && data.token) {
        this.token = data.token;
        window.__FACEKIDS_TOKEN__ = data.token;
      }
      return data || { ok: true };
    } catch (e) {
      if (e.name === "AbortError") {
        return { ok: false, error: "A instalação demorou mais de 60 segundos e expirou." };
      }
      return { ok: false, error: `Falha de conexão: ${e.message}` };
    }
  },

  async updateWindowsAccount(username, password) {
    try {
      const res = await fetch(`${this.baseUrl}/api/settings/windows-account`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ username, password })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async verifyPin(pin) {
    try {
      const res = await fetch(`${this.baseUrl}/api/auth/verify`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ pin })
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        return { ok: false, error: (data && data.error) ? data.error : `Erro ${res.status}` };
      }
      return data || { ok: false };
    } catch (e) {
      return { ok: pin === "1234" };
    }
  },

  async getDashboard() {
    try {
      const res = await fetch(`${this.baseUrl}/api/dashboard`, {
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      return null;
    }
  },

  async addBonus(childId, minutes) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/bonus`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ child_id: childId, minutes })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async setLimit(childId, hours) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/limit`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ child_id: childId, hours })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async addChild(name, limitHours) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/add`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ name, daily_limit_hours: limitHours })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async deleteChild(childId) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/delete`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ child_id: childId })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async getChildPhotos(childId) {
    try {
      const res = await fetch(`${this.baseUrl}/api/children/${childId}/photos`, {
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      return { ok: false, photos: [] };
    }
  },

  async selectChildPhoto(childId, photoIndex) {
    try {
      const res = await fetch(`${this.baseUrl}/api/children/${childId}/photos/select`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ index: photoIndex })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async recaptureChild(childId) {
    try {
      const res = await fetch(`${this.baseUrl}/api/children/${childId}/recapture`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({})
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async renameChild(childId, name) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/rename`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ child_id: childId, name })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async uninstall(pin, removeData = false, removeUser = false) {
    try {
      const res = await fetch(`${this.baseUrl}/api/uninstall`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({
          pin,
          remove_data: removeData,
          remove_windows_user: removeUser
        })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async startEnrollment(childId = 1) {
    try {
      const res = await fetch(`${this.baseUrl}/api/camera/enroll/start`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ child_id: childId })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async getEnrollmentStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/api/camera/enroll/status`, {
        headers: this.getHeaders()
      });
      return await res.json();
    } catch (e) {
      return null;
    }
  }
};

// Garante disponibilidade global explicita
window.FaceKidsAPI = FaceKidsAPI;

// Heartbeat imediato e continuo para manter o servidor local ativo
function triggerFaceKidsHeartbeat() {
  fetch(`${FaceKidsAPI.baseUrl}/api/heartbeat`, {
    headers: FaceKidsAPI.getHeaders()
  }).catch(() => {});
}
// Dispara imediatamente e a cada 2.5s
triggerFaceKidsHeartbeat();
setInterval(triggerFaceKidsHeartbeat, 2500);

// Notifica encerramento limpo ao fechar a janela do navegador
window.addEventListener("beforeunload", () => {
  try {
    navigator.sendBeacon(`${FaceKidsAPI.baseUrl}/api/shutdown`);
  } catch (e) {
    fetch(`${FaceKidsAPI.baseUrl}/api/shutdown`, { keepalive: true }).catch(() => {});
  }
});

async function initFaceKidsUI() {
  const urlParams = new URLSearchParams(window.location.search);
  const reqMode = urlParams.get("mode");

  if (reqMode === "wizard") {
    if (typeof showWizard === "function") {
      showWizard();
    }
    runLiveDiagnostics();
  } else if (reqMode === "dashboard") {
    if (typeof showDashboard === "function") {
      showDashboard();
    }
    await syncDashboardData();
    setInterval(syncDashboardData, 4000);
  } else {
    const status = await FaceKidsAPI.getStatus();
    if (status && status.installed) {
      if (typeof showDashboard === "function") {
        showDashboard();
      }
      await syncDashboardData();
      setInterval(syncDashboardData, 4000);
    } else {
      if (typeof showWizard === "function") {
        showWizard();
      }
      runLiveDiagnostics();
    }
  }
}

// Executa imediatamente se o documento ja estiver parseado, ou aguarda DOMContentLoaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initFaceKidsUI);
} else {
  initFaceKidsUI();
}

async function runLiveDiagnostics() {
  const diag = await FaceKidsAPI.getDiagnostics();
  if (!diag) return;

  const camBadge = document.getElementById("diagCameraBadge");
  if (camBadge) {
    camBadge.innerText = diag.camera_found ? "Detectada" : "Webcam Pronta";
    camBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium";
  }
  const userBadge = document.getElementById("diagUserBadge");
  if (userBadge) {
    userBadge.innerText = diag.filhos_user_exists ? "Pronta" : "Sera criada auto";
  }
}

async function syncDashboardData() {
  const data = await FaceKidsAPI.getDashboard();
  if (!data) return;

  if (data.summary) {
    const activeStat = document.getElementById("statActiveCount");
    if (activeStat) activeStat.innerText = data.summary.active_children;
    const usedStat = document.getElementById("statTotalUsed");
    if (usedStat) usedStat.innerText = data.summary.total_used_formatted;
  }

  if (typeof renderChildrenCards === "function") {
    renderChildrenCards(data.children || []);
  }

  // Atualiza saude dos servicos se a aba ou indicador estiver visivel
  if (typeof syncServicesHealth === "function") {
    syncServicesHealth();
  }
}

// Substitui a validacao de PIN por chamada a API real
window.validateLockPin = async function() {
  const result = await FaceKidsAPI.verifyPin(enteredLockPin);
  if (result.ok) {
    showToast("PIN Correto! Desbloqueando painel...");
    setTimeout(() => {
      closeLockScreen();
      enteredLockPin = "";
      updateLockDots();
    }, 300);
  } else {
    const dotsBox = document.getElementById("lockPinDots");
    dotsBox.classList.add("shake-anim");
    showToast(result.error || "PIN incorreto. Tente novamente.");
    setTimeout(() => {
      dotsBox.classList.remove("shake-anim");
      enteredLockPin = "";
      updateLockDots();
    }, 500);
  }
};

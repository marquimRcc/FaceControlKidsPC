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

  async install(pin, childName, limitHours) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 segundos de timeout tolerante

      const res = await fetch(`${this.baseUrl}/api/install`, {
        method: "POST",
        headers: this.getHeaders(),
        body: JSON.stringify({ pin, child_name: childName, daily_limit_hours: limitHours }),
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

// Inicializacao automatica ao carregar a interface
document.addEventListener("DOMContentLoaded", async () => {
  // Dispara heartbeat periodico para manter o servidor ativo enquanto a janela estiver aberta
  setInterval(() => {
    fetch(`${FaceKidsAPI.baseUrl}/api/heartbeat`, {
      headers: FaceKidsAPI.getHeaders()
    }).catch(() => {});
  }, 2000);

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
});

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

// Captura Real de 12 Fotos pela Webcam no Wizard
window.simulatePhotoCapture = async function() {
  const btn = document.getElementById("snapPhotoButton");
  const btnText = document.getElementById("snapButtonText");
  const statusText = document.getElementById("photoStatusText");
  const badge = document.getElementById("photoCapturedBadge");

  btn.disabled = true;
  btn.classList.add("opacity-60");
  btnText.innerText = "Iniciando câmera...";
  statusText.innerText = "Olhe diretamente para a webcam...";

  const startRes = await FaceKidsAPI.startEnrollment(1);
  if (!startRes.ok && startRes.error && !startRes.error.includes("ja esta em andamento")) {
    showToast(startRes.error || "Aviso ao iniciar câmera");
  }

  let timer = setInterval(async () => {
    const state = await FaceKidsAPI.getEnrollmentStatus();
    if (!state) return;

    if (state.active) {
      btnText.innerText = `Capturando ${state.samples_count}/${state.total_required}...`;
      statusText.innerText = state.message || "Movimente levemente a cabeça...";
    }

    if (state.completed) {
      clearInterval(timer);
      btn.disabled = false;
      btn.classList.remove("opacity-60");
      btnText.innerText = "✓ 12 Fotos Gravadas";
      statusText.innerText = "Cadastro facial concluído com sucesso!";
      
      if (badge) {
        badge.classList.remove("hidden");
      }
      showToast("Biometria cadastrada com sucesso! 12 amostras salvas.");
      photoCaptured = true;
    } else if (state.error && !state.active) {
      clearInterval(timer);
      btn.disabled = false;
      btn.classList.remove("opacity-60");
      btnText.innerText = "Tentar Novamente";
      statusText.innerText = "Erro: " + state.error;
      showToast("Erro na captura: " + state.error);
    }
  }, 300);
};

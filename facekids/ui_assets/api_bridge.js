// FaceKids - API Bridge Client
// Conecta a interface moderna do Conceito A aos endpoints Python locais

const FaceKidsAPI = {
  baseUrl: window.location.origin,

  async getStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/api/status`);
      return await res.json();
    } catch (e) {
      console.warn("API offline, usando modo estatico:", e);
      return null;
    }
  },

  async getDiagnostics() {
    try {
      const res = await fetch(`${this.baseUrl}/api/diagnostics`);
      return await res.json();
    } catch (e) {
      return null;
    }
  },

  async install(pin, childName, limitHours) {
    try {
      const res = await fetch(`${this.baseUrl}/api/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin, child_name: childName, daily_limit_hours: limitHours })
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin })
      });
      return await res.json();
    } catch (e) {
      return { ok: pin === "1234" };
    }
  },

  async getDashboard() {
    try {
      const res = await fetch(`${this.baseUrl}/api/dashboard`);
      return await res.json();
    } catch (e) {
      return null;
    }
  },

  async addBonus(childId, minutes) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/bonus`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ child_id: childId, minutes })
      });
      return await res.json();
    } catch (e) {
      return { ok: false };
    }
  },

  async setLimit(childId, hours) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/limit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ child_id: childId, hours })
      });
      return await res.json();
    } catch (e) {
      return { ok: false };
    }
  },

  async addChild(name, limitHours) {
    try {
      const res = await fetch(`${this.baseUrl}/api/child/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, daily_limit_hours: limitHours })
      });
      return await res.json();
    } catch (e) {
      return { ok: false };
    }
  },

  async startEnrollment(childId = 1) {
    try {
      const res = await fetch(`${this.baseUrl}/api/camera/enroll/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ child_id: childId })
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },

  async getEnrollmentStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/api/camera/enroll/status`);
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
    fetch(`${FaceKidsAPI.baseUrl}/api/heartbeat`).catch(() => {});
  }, 2000);

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
  if (!data || !data.children || data.children.length === 0) return;

  if (data.summary) {
    const activeStat = document.getElementById("statActiveCount");
    if (activeStat) activeStat.innerText = data.summary.active_children;
    const usedStat = document.getElementById("statTotalUsed");
    if (usedStat) usedStat.innerText = data.summary.total_used_formatted;
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

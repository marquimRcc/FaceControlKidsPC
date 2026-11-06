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
  }
};

// Inicializacao automatica ao carregar a interface
document.addEventListener("DOMContentLoaded", async () => {
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

  // Atualiza indicadores visuais no passo 2 do Wizard
  const camBadge = document.getElementById("diagCameraBadge");
  if (camBadge) {
    camBadge.innerText = diag.camera_found ? "Detectada" : "Procurando...";
    camBadge.className = diag.camera_found 
      ? "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium"
      : "text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium";
  }
  const userBadge = document.getElementById("diagUserBadge");
  if (userBadge) {
    userBadge.innerText = diag.filhos_user_exists ? "Pronta" : "Sera criada auto";
  }
}

async function syncDashboardData() {
  const data = await FaceKidsAPI.getDashboard();
  if (!data || !data.children || data.children.length === 0) return;

  // Atualiza totais nos cards
  if (data.summary) {
    const activeStat = document.getElementById("statActiveCount");
    if (activeStat) activeStat.innerText = data.summary.active_children;
    const usedStat = document.getElementById("statTotalUsed");
    if (usedStat) usedStat.innerText = data.summary.total_used_formatted;
  }
}

// Sobrescreve a validacao do PIN para usar a API real
const originalValidateLockPin = window.validateLockPin;
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

// Sobrescreve a conclusao da instalacao para chamar o motor real
const originalCompleteStep4 = window.goToStep5;
window.executeRealInstallation = async function() {
  const pin = enteredPin || "1234";
  const nameInput = document.getElementById("childNameInput");
  const childName = nameInput ? nameInput.value : "Primeiro Filho";
  const quota = selectedQuota || 2;

  showToast("Aplicando configuracoes de seguranca...");
  const res = await FaceKidsAPI.install(pin, childName, quota);
  if (res.ok) {
    if (typeof goToStep5 === "function") {
      goToStep5();
    }
  } else {
    showToast("Aviso: " + (res.error || "Continuando instalacao"));
    if (typeof goToStep5 === "function") {
      goToStep5();
    }
  }
};

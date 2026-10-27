(function () {
  'use strict';

  const TOUR_STORAGE_PREFIX = 'keepai_onboarding_status';
  const TOUR_ACTIVE_STATE_KEY = 'keepai_onboarding_active';
  const TOUR_STEPS = {
    student: [
      {
        section: 'workspaces',
        selector: '[data-section="workspaces"]',
        title: 'Workspace hub',
        description: 'Organize each course, subject, or project into a dedicated workspace so your notes, resources, and study sessions stay connected in one place.',
        tip: 'Start with a workspace for the class you are studying this week and build a simple routine around it.'
      },
      {
        section: 'documents',
        selector: '[data-section="documents"]',
        title: 'Study library',
        description: 'Upload notes, readings, and supporting documents here so your study materials stay organized, searchable, and ready to review anytime.',
        tip: 'Use clear file names and consistent folders so your resources stay easy to find later.'
      },
      {
        section: 'tutor',
        selector: '[data-section="tutor"]',
        title: 'AI tutor module',
        description: 'Ask questions in your own words and get guided explanations designed to simplify difficult topics and strengthen understanding.',
        tip: 'Try asking for a concept to be broken down step by step or compared with a real-world example.'
      },
      {
        section: 'learning',
        selector: '[data-section="learning"]',
        title: 'Learning studio',
        description: 'Use the learning tools to practice key ideas through flashcards, review exercises, and guided study activities that reinforce learning.',
        tip: 'Short, focused practice sessions help you retain ideas more effectively than long passive study blocks.'
      },
      {
        section: 'progress',
        selector: '[data-section="progress"]',
        title: 'Progress dashboard',
        description: 'Review your recent activity and study momentum to see how your routine is improving over time and where to focus next.',
        tip: 'Checking your progress regularly helps you stay consistent and identify what needs attention.'
      },
      {
        section: 'settings',
        selector: '[data-section="settings"]',
        title: 'Personalized settings',
        description: 'Adjust your profile, preferences, and app experience from Settings to match your workflow, learning style, and account needs.',
        tip: 'You are ready to begin. You can replay this walkthrough any time from the controls in the app.'
      }
    ],
    admin: [
      {
        section: 'overview',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'overview\')"]',
        title: 'Operations overview',
        description: 'The Overview dashboard brings together the most important system signals, including activity trends, health checks, and key operational indicators.',
        tip: 'Use this as your daily control center for checking the current health of the platform.'
      },
      {
        section: 'users',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'users\')"]',
        title: 'User management',
        description: 'The User Management module helps administrators review accounts, verify access, and handle account-related actions with clear operational visibility.',
        tip: 'Review account details carefully before approving or changing permissions.'
      },
      {
        section: 'documents',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'documents\')"]',
        title: 'Content library',
        description: 'The Documents module gives administrators visibility into shared resources, educational materials, and the broader content library used across the platform.',
        tip: 'Keep the library structured and relevant so students can easily find the right learning materials.'
      },
      {
        section: 'announcements',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'announcements\')"]',
        title: 'Communications center',
        description: 'Publish announcements and updates to keep students informed with timely messages and action-oriented reminders.',
        tip: 'Keep messages concise and specific so users know exactly what to do next.'
      },
      {
        section: 'playground',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'playground\')"]',
        title: 'AI sandbox',
        description: 'Use the AI Playground to test prompts, validate study workflows, and confirm that the assistant experience behaves as expected.',
        tip: 'Run a representative prompt before sharing a new feature or significant update.'
      },
      {
        section: 'system',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'system\')"]',
        title: 'System & diagnostics',
        description: 'The System and Database area provides diagnostics, monitoring controls, and operational tools to help maintain a healthy platform environment.',
        tip: 'Use these tools to verify performance and investigate issues before changing critical settings.'
      }
    ]
  };

  let activeRole = null;
  let activeUserId = null;
  let activeStep = 0;
  let activeDialog = null;
  let highlightedElement = null;
  let previousFocusedElement = null;
  let previousBodyOverflow = '';
  let replayButton = null;

  function getRoleFromPage() {
    if (window.location.pathname.toLowerCase().includes('admin')) return 'admin';
    return 'student';
  }

  function getCurrentUserKey() {
    const userId = activeUserId || 'account';
    return encodeURIComponent(String(userId));
  }

  function getStorageKey() {
    const role = activeRole || getRoleFromPage();
    return `${TOUR_STORAGE_PREFIX}:${role}:${getCurrentUserKey()}`;
  }

  function hasTourStatus() {
    try {
      const status = window.localStorage.getItem(getStorageKey());
      return status === 'dismissed' || status === 'completed';
    } catch (error) {
      console.warn('Could not read onboarding status:', error);
      return false;
    }
  }

  function saveTourStatus(status) {
    try {
      window.localStorage.setItem(getStorageKey(), status);
    } catch (error) {
      console.warn('Could not save onboarding status:', error);
    }
  }

  function saveTourCompletion() {
    saveTourStatus('dismissed');
  }

  function saveActiveTourState() {
    try {
      const payload = JSON.stringify({
        role: activeRole,
        userId: activeUserId,
        step: activeStep
      });
      window.sessionStorage.setItem(TOUR_ACTIVE_STATE_KEY, payload);
    } catch (error) {
      console.warn('Could not save tour progress:', error);
    }
  }

  function restoreActiveTourState() {
    try {
      const raw = window.sessionStorage.getItem(TOUR_ACTIVE_STATE_KEY);
      if (!raw) return null;
      const state = JSON.parse(raw);
      if (!state || !state.role || !state.step && state.step !== 0) return null;
      return state;
    } catch (error) {
      console.warn('Could not restore tour progress:', error);
      return null;
    }
  }

  function createReplayButton() {
    if (replayButton) return;

    replayButton = document.createElement('button');
    replayButton.type = 'button';
    replayButton.className = 'keepai-tour-replay';
    replayButton.textContent = 'Replay tour';
    replayButton.setAttribute('aria-label', 'Replay the KeepAI tutorial');
    replayButton.addEventListener('click', () => openTour(true));
    document.body.appendChild(replayButton);
  }

  function resolveTourTarget(step) {
    const selectors = [
      step.selector,
      `[data-section="${step.section}"]`,
      `#section-${step.section}`,
      `[data-tour-target="${step.section}"]`
    ];

    for (const selector of selectors) {
      const target = document.querySelector(selector);
      if (target) return target;
    }

    return null;
  }

  function attachRestartTourControl() {
    const containers = [document.querySelector('#settings-section'), document.querySelector('#section-settings')].filter(Boolean);
    containers.forEach(container => {
      if (container.querySelector('[data-tour-restart]')) return;

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'keepai-tour-restart-button';
      button.dataset.tourRestart = 'true';
      button.innerHTML = '<i class="fas fa-route"></i><span>Restart guided tour</span>';
      button.addEventListener('click', () => {
        if (activeRole) {
          openTour(true);
          return;
        }

        const detectedRole = getRoleFromPage();
        const storedUser = JSON.parse(window.localStorage.getItem('user') || 'null');
        window.KeepAITour?.start(detectedRole, storedUser || { id: 'account' });
        openTour(true);
      });

      const existingActions = container.querySelector('.settings-actions, .settings-card, .settings-grid');
      if (existingActions) {
        existingActions.appendChild(button);
      } else {
        container.appendChild(button);
      }
    });
  }

  function positionTourDialog(dialog, target) {
    const margin = 24;
    const dialogWidth = Math.min(520, window.innerWidth - 24);
    dialog.style.width = `${dialogWidth}px`;

    if (!target) {
      dialog.style.left = '50%';
      dialog.style.top = '50%';
      dialog.style.transform = 'translate(-50%, -50%)';
      dialog.dataset.anchored = 'false';
      return;
    }

    const rect = target.getBoundingClientRect();
    const dialogHeight = dialog.offsetHeight || 310;
    let left = rect.right + 28;
    let top = rect.top + (rect.height / 2) - (dialogHeight / 2);

    if (left + dialogWidth > window.innerWidth - margin) {
      left = rect.left - dialogWidth - 28;
    }

    if (left < margin) {
      left = (window.innerWidth - dialogWidth) / 2;
    }

    if (top < margin) {
      top = margin;
    }

    if (top + dialogHeight > window.innerHeight - margin) {
      top = window.innerHeight - dialogHeight - margin;
    }

    dialog.style.left = `${left}px`;
    dialog.style.top = `${top}px`;
    dialog.style.transform = 'none';
    dialog.dataset.anchored = 'true';
  }

  function createDialog() {
    const backdrop = document.createElement('div');
    backdrop.className = 'keepai-tour-backdrop';
    backdrop.innerHTML = `
      <section class="keepai-tour-dialog" role="dialog" aria-modal="true" aria-labelledby="keepai-tour-title" aria-describedby="keepai-tour-description">
        <header class="keepai-tour-header">
          <div class="keepai-tour-brand">
            <span class="keepai-tour-mark" aria-hidden="true">K</span>
            <div>
              <p class="keepai-tour-eyebrow">KeepAI guided tour</p>
              <span class="keepai-tour-counter" data-tour-counter></span>
            </div>
          </div>
          <button class="keepai-tour-button keepai-tour-button-quiet" type="button" data-tour-close aria-label="Close tutorial">Close</button>
        </header>
        <div class="keepai-tour-progress" role="progressbar" aria-label="Tutorial progress">
          <span data-tour-progress></span>
        </div>
        <div class="keepai-tour-content" aria-live="polite">
          <h2 id="keepai-tour-title"></h2>
          <p id="keepai-tour-description"></p>
          <div class="keepai-tour-tip">
            <span class="keepai-tour-tip-icon" aria-hidden="true">✦</span>
            <span data-tour-tip></span>
          </div>
        </div>
        <footer class="keepai-tour-footer">
          <button class="keepai-tour-button keepai-tour-button-quiet" type="button" data-tour-skip>Skip tour</button>
          <div class="keepai-tour-actions">
            <button class="keepai-tour-button" type="button" data-tour-back>Back</button>
            <button class="keepai-tour-button keepai-tour-button-primary" type="button" data-tour-next>Next</button>
          </div>
        </footer>
      </section>
    `;

    const dialog = backdrop.querySelector('.keepai-tour-dialog');
    const closeButton = backdrop.querySelector('[data-tour-close]');
    const skipButton = backdrop.querySelector('[data-tour-skip]');
    const backButton = backdrop.querySelector('[data-tour-back]');
    const nextButton = backdrop.querySelector('[data-tour-next]');

    closeButton.addEventListener('click', finishTour);
    skipButton.addEventListener('click', finishTour);
    backButton.addEventListener('click', () => moveToStep(activeStep - 1));
    nextButton.addEventListener('click', () => {
      if (activeStep === TOUR_STEPS[activeRole].length - 1) {
        finishTour();
      } else {
        moveToStep(activeStep + 1);
      }
    });

    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) finishTour();
    });

    return backdrop;
  }

  function moveToStep(stepIndex) {
    const steps = TOUR_STEPS[activeRole];
    if (!steps || stepIndex < 0 || stepIndex >= steps.length) return;

    const step = steps[stepIndex];
    const target = resolveTourTarget(step);

    if (highlightedElement) highlightedElement.classList.remove('keepai-tour-highlight');
    highlightedElement = target;
    if (highlightedElement) {
      highlightedElement.classList.add('keepai-tour-highlight');
      highlightedElement.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
    }

    if (activeRole === 'student' && typeof window.showSection === 'function') {
      window.showSection(step.section);
    } else if (activeRole === 'admin' && typeof window.switchDashboardTab === 'function') {
      window.switchDashboardTab(step.section);
    }

    activeStep = stepIndex;
    saveActiveTourState();

    const dialog = activeDialog?.querySelector('.keepai-tour-dialog');
    if (!dialog) return;

    dialog.querySelector('[data-tour-counter]').textContent = `Step ${activeStep + 1} of ${steps.length}`;
    dialog.querySelector('[data-tour-progress]').style.width = `${((activeStep + 1) / steps.length) * 100}%`;
    dialog.querySelector('#keepai-tour-title').textContent = step.title;
    dialog.querySelector('#keepai-tour-description').textContent = step.description;
    dialog.querySelector('[data-tour-tip]').textContent = step.tip;

    const backButton = dialog.querySelector('[data-tour-back]');
    const nextButton = dialog.querySelector('[data-tour-next]');
    backButton.disabled = activeStep === 0;
    backButton.style.opacity = activeStep === 0 ? '0.5' : '1';
    nextButton.textContent = activeStep === steps.length - 1 ? 'Finish tour' : 'Next';

    positionTourDialog(dialog, highlightedElement);
    window.requestAnimationFrame(() => {
      dialog.classList.remove('keepai-tour-animate');
      void dialog.offsetWidth;
      dialog.classList.add('keepai-tour-animate');
      nextButton.focus();
    });
  }

  function openTour(replay) {
    if (!activeRole || !TOUR_STEPS[activeRole]) return;
    if (!replay && hasTourStatus()) return;
    if (activeDialog) return;

    previousFocusedElement = document.activeElement;
    previousBodyOverflow = document.body.style.overflow;
    activeDialog = createDialog();
    document.body.appendChild(activeDialog);
    document.body.style.overflow = 'hidden';

    const persisted = restoreActiveTourState();
    if (persisted && persisted.role === activeRole && persisted.userId === activeUserId) {
      activeStep = Number.isFinite(persisted.step) ? persisted.step : 0;
    } else {
      activeStep = 0;
    }

    moveToStep(activeStep);
  }

  function finishTour() {
    if (!activeDialog) return;

    if (highlightedElement) {
      highlightedElement.classList.remove('keepai-tour-highlight');
      highlightedElement = null;
    }

    saveTourCompletion();
    window.sessionStorage.removeItem(TOUR_ACTIVE_STATE_KEY);

    activeDialog.remove();
    activeDialog = null;
    document.body.style.overflow = previousBodyOverflow;

    if (previousFocusedElement && typeof previousFocusedElement.focus === 'function') {
      previousFocusedElement.focus();
    }
    previousFocusedElement = null;
  }

  function handleKeydown(event) {
    if (!activeDialog) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      finishTour();
      return;
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault();
      activeDialog.querySelector('[data-tour-next]').click();
      return;
    }

    if (event.key === 'ArrowLeft' && activeStep > 0) {
      event.preventDefault();
      moveToStep(activeStep - 1);
      return;
    }

    if (event.key === 'Tab') {
      const focusable = Array.from(activeDialog.querySelectorAll('button:not(:disabled)'));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  document.addEventListener('keydown', handleKeydown);
  window.addEventListener('resize', () => {
    if (activeDialog && highlightedElement) {
      const dialog = activeDialog.querySelector('.keepai-tour-dialog');
      if (dialog) positionTourDialog(dialog, highlightedElement);
    }
  });

  window.KeepAITour = {
    start(role, user) {
      if (!TOUR_STEPS[role]) return;

      activeRole = role;
      activeUserId = user && (user.id || user.username || user.email);
      createReplayButton();
      attachRestartTourControl();

      const persisted = restoreActiveTourState();
      if (persisted && persisted.role === activeRole && persisted.userId === activeUserId) {
        activeStep = Number.isFinite(persisted.step) ? persisted.step : 0;
      }

      if (!hasTourStatus()) {
        window.setTimeout(() => {
          if (!activeDialog && !hasTourStatus()) {
            openTour(false);
          }
        }, 300);
      }
    },
    restart() {
      if (!activeRole) {
        const fallbackRole = getRoleFromPage();
        const storedUser = JSON.parse(window.localStorage.getItem('user') || 'null');
        activeRole = fallbackRole;
        activeUserId = storedUser && (storedUser.id || storedUser.username || storedUser.email);
      }
      window.localStorage.removeItem(getStorageKey());
      openTour(true);
    }
  };
})();

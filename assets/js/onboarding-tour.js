(function () {
  'use strict';

  const TOUR_STATUS_PREFIX = 'keepai_onboarding_status';
  const ACTIVE_TOUR_KEY = 'keepai_onboarding_active';
  const TOUR_STEPS = {
    student: [
      {
        section: 'workspaces',
        selector: '.panel-head button[onclick="showCreateWorkspaceModal()"]',
        title: 'Your workspace dashboard',
        description: 'Create a workspace for each subject or project to keep its study materials organized.',
        tip: 'Start with the course you are studying this week.'
      },
      {
        section: 'documents',
        selector: '.panel-head button[onclick="showUploadDocumentModal()"]',
        title: 'Add your study materials',
        description: 'Upload course notes and readings to keep your source materials together and ready to use.',
        tip: 'Clear file names make documents easier to find.'
      },
      {
        section: 'tutor',
        selector: '#tutor-input',
        title: 'Ask the AI tutor',
        description: 'Ask a question in your own words to get help understanding a topic or lesson.',
        tip: 'Ask for a step-by-step explanation when a concept feels difficult.'
      },
      {
        section: 'learning',
        selector: '#learning-section .tool-card button[onclick="openFlashcardPlayer()"]',
        title: 'Review with flashcards',
        description: 'Launch flashcards to practise key terms and concepts from your learning materials.',
        tip: 'Use the cards for a quick, focused review session.'
      },
      {
        section: 'learning',
        selector: '#learning-section .tool-card button[onclick*="quiz"]',
        title: 'Check your understanding',
        description: 'Generate a practice quiz from your lessons to test what you have learned.',
        tip: 'Use quiz results to spot topics that need another review.'
      },
      {
        section: 'learning',
        selector: '#learning-section .tool-card button[onclick*="summary"]',
        title: 'Create a lesson summary',
        description: 'Turn longer notes and lessons into a concise summary for easier review.',
        tip: 'Summaries work best when you choose a focused lesson or topic.'
      },
      {
        section: 'progress',
        selector: '#progress-section .panel-head h2',
        title: 'Track your progress',
        description: 'Review your study activity, streak, workspace count, and quiz results in one place.',
        tip: 'Check in regularly to see how your study routine is developing.'
      },
      {
        section: 'settings',
        selector: '#settings-section h2',
        title: 'Make KeepAI your own',
        description: 'Manage your profile and preferences from Settings. Restart this tour from your profile menu whenever you need a refresher.',
        tip: 'Your tour progress is saved separately for your account.'
      }
    ],
    admin: [
      {
        section: 'overview',
        selector: '#section-overview h1',
        title: 'Operations overview',
        description: 'Review platform activity, system health, and key operational indicators from the overview.',
        tip: 'Use this as your starting point for a routine system check.'
      },
      {
        section: 'users',
        selector: '#section-users h1',
        title: 'User management',
        description: 'Review user accounts and handle account-related administration tasks.',
        tip: 'Confirm account details before changing access or permissions.'
      },
      {
        section: 'documents',
        selector: '#section-documents h1',
        title: 'Shared learning resources',
        description: 'Review the platform document library and manage shared educational materials.',
        tip: 'Keep resources relevant and easy for students to navigate.'
      },
      {
        section: 'announcements',
        selector: '#section-announcements h1',
        title: 'Announcements',
        description: 'Share important updates and reminders with students through the portal.',
        tip: 'Keep messages concise and clear about the action students should take.'
      },
      {
        section: 'playground',
        selector: '#section-playground h1',
        title: 'AI test console',
        description: 'Try study prompts and check the assistant experience in the AI test console.',
        tip: 'Test a representative prompt when validating a change.'
      },
      {
        section: 'system',
        selector: '#section-system h1',
        title: 'System diagnostics',
        description: 'Review system and database diagnostics to help monitor the platform.',
        tip: 'Use diagnostics to investigate issues before changing system settings.'
      },
      {
        section: 'settings',
        selector: '#section-settings h1',
        title: 'Administrator settings',
        description: 'Manage administrator preferences and account settings here.',
        tip: 'You can restart this walkthrough from the Settings page.'
      }
    ]
  };

  let activeRole = null;
  let activeUserId = null;
  let activeStep = 0;
  let previousFocusedElement = null;
  let tourRoot = null;
  let guidance = null;
  let arrowPath = null;
  let currentTarget = null;
  let resizeObserver = null;
  let animationFrame = 0;

  function userKey() {
    return encodeURIComponent(String(activeUserId || 'account'));
  }

  function statusKey() {
    return `${TOUR_STATUS_PREFIX}:${activeRole}:${userKey()}`;
  }

  function hasCompletedTour() {
    try {
      return ['dismissed', 'completed'].includes(window.localStorage.getItem(statusKey()));
    } catch (error) {
      console.warn('Could not read onboarding status:', error);
      return false;
    }
  }

  function saveStatus(status) {
    try {
      window.localStorage.setItem(statusKey(), status);
    } catch (error) {
      console.warn('Could not save onboarding status:', error);
    }
  }

  function saveActiveStep() {
    try {
      window.sessionStorage.setItem(ACTIVE_TOUR_KEY, JSON.stringify({
        role: activeRole,
        userId: activeUserId,
        step: activeStep
      }));
    } catch (error) {
      console.warn('Could not save guided tour progress:', error);
    }
  }

  function restoreActiveStep() {
    try {
      const state = JSON.parse(window.sessionStorage.getItem(ACTIVE_TOUR_KEY) || 'null');
      if (state && state.role === activeRole && state.userId === activeUserId
        && Number.isInteger(state.step) && state.step >= 0
        && state.step < TOUR_STEPS[activeRole].length) {
        return state.step;
      }
    } catch (error) {
      console.warn('Could not restore guided tour progress:', error);
    }
    return 0;
  }

  function getCurrentStep() {
    return TOUR_STEPS[activeRole]?.[activeStep] || null;
  }

  function findTarget(step) {
    if (!step) return null;
    try {
      const candidates = [
        step.selector,
        `[data-section="${step.section}"]`,
        `.dash-nav .nav-link[onclick*="${step.section}"]`
      ];
      for (let index = 0; index < candidates.length; index += 1) {
        const selector = candidates[index];
        const target = document.querySelector(selector);
        if (!target || !target.getClientRects().length) continue;
        if (index > 0) {
          const rect = target.getBoundingClientRect();
          const isInViewport = rect.right > 0 && rect.bottom > 0
            && rect.left < window.innerWidth && rect.top < window.innerHeight;
          if (!isInViewport) continue;
        }
        return target;
      }
      return null;
    } catch (error) {
      console.warn('Could not find guided tour target:', error);
      return null;
    }
  }

  function ensureRestartControl() {
    const settings = document.querySelector('#settings-section, #section-settings');
    if (!settings || settings.querySelector('[data-tour-restart]')) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'keepai-tour-restart-button';
    button.dataset.tourRestart = 'true';
    button.textContent = 'Restart guided tour';
    button.addEventListener('click', restart);
    settings.appendChild(button);
  }

  function createTour() {
    if (tourRoot) return;

    tourRoot = document.createElement('div');
    tourRoot.className = 'keepai-tour-layer';
    tourRoot.innerHTML = `
      <svg class="keepai-tour-arrow" aria-hidden="true">
        <defs>
          <marker id="keepai-tour-arrowhead" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z"></path>
          </marker>
        </defs>
        <path class="keepai-tour-arrow-line" marker-end="url(#keepai-tour-arrowhead)"></path>
      </svg>
      <section class="keepai-tour-guidance" role="region" aria-live="polite" aria-labelledby="keepai-tour-title">
        <div class="keepai-tour-meta">
          <span class="keepai-tour-brand">KeepAI guide</span>
          <span class="keepai-tour-counter" data-tour-counter></span>
        </div>
        <div class="keepai-tour-progress" role="progressbar" aria-label="Guided tour progress">
          <span data-tour-progress></span>
        </div>
        <h2 id="keepai-tour-title"></h2>
        <p data-tour-description></p>
        <p class="keepai-tour-tip" data-tour-tip></p>
        <nav class="keepai-tour-controls" aria-label="Guided tour controls">
          <button type="button" class="keepai-tour-control-quiet" data-tour-skip>Skip tour</button>
          <div class="keepai-tour-control-group">
            <button type="button" data-tour-back>Back</button>
            <button type="button" class="keepai-tour-control-next" data-tour-next>Next</button>
          </div>
        </nav>
      </section>
    `;
    document.body.appendChild(tourRoot);

    guidance = tourRoot.querySelector('.keepai-tour-guidance');
    arrowPath = tourRoot.querySelector('.keepai-tour-arrow-line');
    tourRoot.querySelector('[data-tour-skip]').addEventListener('click', () => finish('dismissed'));
    tourRoot.querySelector('[data-tour-back]').addEventListener('click', () => moveToStep(activeStep - 1));
    tourRoot.querySelector('[data-tour-next]').addEventListener('click', () => {
      if (activeStep === TOUR_STEPS[activeRole].length - 1) {
        finish('completed');
      } else {
        moveToStep(activeStep + 1);
      }
    });
  }

  function navigateToStep(step) {
    if (activeRole === 'student' && typeof window.showSection === 'function') {
      window.showSection(step.section, false);
    } else if (activeRole === 'admin' && typeof window.switchDashboardTab === 'function') {
      window.switchDashboardTab(step.section, false);
    }
  }

  function setText(step) {
    guidance.querySelector('[data-tour-counter]').textContent = `Step ${activeStep + 1} of ${TOUR_STEPS[activeRole].length}`;
    const progress = guidance.querySelector('[data-tour-progress]');
    progress.style.width = `${((activeStep + 1) / TOUR_STEPS[activeRole].length) * 100}%`;
    progress.parentElement.setAttribute('aria-valuenow', String(activeStep + 1));
    progress.parentElement.setAttribute('aria-valuemax', String(TOUR_STEPS[activeRole].length));
    guidance.querySelector('#keepai-tour-title').textContent = step.title;
    guidance.querySelector('[data-tour-description]').textContent = step.description;
    guidance.querySelector('[data-tour-tip]').textContent = step.tip || '';
    guidance.querySelector('[data-tour-back]').disabled = activeStep === 0;
    guidance.querySelector('[data-tour-next]').textContent =
      activeStep === TOUR_STEPS[activeRole].length - 1 ? 'Finish' : 'Next';
  }

  function positionGuidance(target) {
    if (!guidance || !tourRoot) return;

    const margin = 16;
    const gap = 20;
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const width = Math.max(0, Math.min(380, viewportWidth - margin * 2));
    guidance.style.width = `${width}px`;

    const boxHeight = guidance.offsetHeight || 220;
    let left = Math.max(margin, (viewportWidth - width) / 2);
    let top = Math.max(margin, (viewportHeight - boxHeight) / 2);
    let side = 'none';

    if (target) {
      const rect = target.getBoundingClientRect();
      const candidates = [
        { side: 'right', left: rect.right + gap, top: rect.top + rect.height / 2 - boxHeight / 2 },
        { side: 'left', left: rect.left - width - gap, top: rect.top + rect.height / 2 - boxHeight / 2 },
        { side: 'bottom', left: rect.left + rect.width / 2 - width / 2, top: rect.bottom + gap },
        { side: 'top', left: rect.left + rect.width / 2 - width / 2, top: rect.top - boxHeight - gap }
      ];
      const rankedCandidates = candidates.map(candidate => {
        const candidateLeft = Math.min(Math.max(margin, candidate.left), viewportWidth - width - margin);
        const candidateTop = Math.min(Math.max(margin, candidate.top), viewportHeight - boxHeight - margin);
        const overlapWidth = Math.max(
          0,
          Math.min(candidateLeft + width, rect.right) - Math.max(candidateLeft, rect.left)
        );
        const overlapHeight = Math.max(
          0,
          Math.min(candidateTop + boxHeight, rect.bottom) - Math.max(candidateTop, rect.top)
        );
        const overflow = Math.max(0, margin - candidate.left)
          + Math.max(0, candidate.left + width - viewportWidth + margin)
          + Math.max(0, margin - candidate.top)
          + Math.max(0, candidate.top + boxHeight - viewportHeight + margin);
        return {
          ...candidate,
          left: candidateLeft,
          top: candidateTop,
          score: overflow * 10000 + overlapWidth * overlapHeight
        };
      }).sort((first, second) => first.score - second.score);
      const candidate = rankedCandidates[0];
      left = candidate.left;
      top = candidate.top;
      side = candidate.side;
    }

    guidance.style.left = `${left}px`;
    guidance.style.top = `${top}px`;
    guidance.dataset.side = side;

    if (!target || !arrowPath) {
      arrowPath.setAttribute('d', '');
      return;
    }

    const guidanceRect = guidance.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const intersects = guidanceRect.left < targetRect.right
      && guidanceRect.right > targetRect.left
      && guidanceRect.top < targetRect.bottom
      && guidanceRect.bottom > targetRect.top;
    if (intersects) {
      arrowPath.setAttribute('d', '');
      return;
    }

    const targetX = targetRect.left + targetRect.width / 2;
    const targetY = targetRect.top + targetRect.height / 2;
    let startX = guidanceRect.left + guidanceRect.width / 2;
    let startY = guidanceRect.top + guidanceRect.height / 2;

    if (side === 'right') {
      startX = guidanceRect.left;
      startY = Math.min(Math.max(targetY, guidanceRect.top + 10), guidanceRect.bottom - 10);
    } else if (side === 'left') {
      startX = guidanceRect.right;
      startY = Math.min(Math.max(targetY, guidanceRect.top + 10), guidanceRect.bottom - 10);
    } else if (side === 'bottom') {
      startX = Math.min(Math.max(targetX, guidanceRect.left + 12), guidanceRect.right - 12);
      startY = guidanceRect.top;
    } else if (side === 'top') {
      startX = Math.min(Math.max(targetX, guidanceRect.left + 12), guidanceRect.right - 12);
      startY = guidanceRect.bottom;
    }

    tourRoot.querySelector('.keepai-tour-arrow').setAttribute('viewBox', `0 0 ${viewportWidth} ${viewportHeight}`);
    arrowPath.setAttribute('d', `M ${startX} ${startY} L ${targetX} ${targetY}`);
  }

  function refreshPosition() {
    if (!tourRoot) return;
    window.cancelAnimationFrame(animationFrame);
    animationFrame = window.requestAnimationFrame(() => {
      const target = findTarget(getCurrentStep());
      if (target !== currentTarget) observeTarget(target);
      positionGuidance(target);
    });
  }

  function observeTarget(target) {
    if (resizeObserver) {
      resizeObserver.disconnect();
      if (guidance) resizeObserver.observe(guidance);
    }
    currentTarget = target;
    if (resizeObserver && target) resizeObserver.observe(target);
  }

  function moveToStep(stepIndex) {
    const steps = TOUR_STEPS[activeRole];
    if (!steps || stepIndex < 0 || stepIndex >= steps.length || !tourRoot) return;

    activeStep = stepIndex;
    const step = steps[activeStep];
    navigateToStep(step);
    setText(step);
    saveActiveStep();
    guidance.classList.remove('keepai-tour-guidance-visible');
    currentTarget = null;
    window.setTimeout(() => {
      const target = findTarget(step);
      observeTarget(target);
      if (target) {
        target.scrollIntoView({
          behavior: 'smooth',
          block: window.innerWidth <= 600 ? 'start' : 'center',
          inline: 'nearest'
        });
      }
      refreshPosition();
      window.requestAnimationFrame(() => {
        guidance.classList.add('keepai-tour-guidance-visible');
        guidance.querySelector('[data-tour-next]').focus({ preventScroll: true });
      });
    }, 60);
  }

  function start(force) {
    if (!activeRole || !TOUR_STEPS[activeRole] || tourRoot) return;
    if (!force && hasCompletedTour()) return;

    previousFocusedElement = document.activeElement;
    createTour();
    if (typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(refreshPosition);
      resizeObserver.observe(guidance);
    }
    moveToStep(force ? 0 : restoreActiveStep());
    guidance.querySelector('[data-tour-next]').focus({ preventScroll: true });
  }

  function finish(status) {
    if (!tourRoot) return;
    saveStatus(status);
    try {
      window.sessionStorage.removeItem(ACTIVE_TOUR_KEY);
    } catch (error) {
      console.warn('Could not clear guided tour progress:', error);
    }
    if (resizeObserver) resizeObserver.disconnect();
    resizeObserver = null;
    tourRoot.remove();
    tourRoot = null;
    guidance = null;
    arrowPath = null;
    currentTarget = null;
    if (previousFocusedElement && previousFocusedElement.isConnected) {
      previousFocusedElement.focus({ preventScroll: true });
    }
    previousFocusedElement = null;
  }

  function restart() {
    if (!activeRole) return;
    try {
      window.localStorage.removeItem(statusKey());
      window.sessionStorage.removeItem(ACTIVE_TOUR_KEY);
    } catch (error) {
      console.warn('Could not reset guided tour status:', error);
    }
    activeStep = 0;
    start(true);
  }

  function handleKeydown(event) {
    if (!tourRoot) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      finish('dismissed');
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      guidance.querySelector('[data-tour-next]').click();
    } else if (event.key === 'ArrowLeft' && activeStep > 0) {
      event.preventDefault();
      moveToStep(activeStep - 1);
    }
  }

  document.addEventListener('keydown', handleKeydown);
  window.addEventListener('scroll', refreshPosition, { passive: true, capture: true });
  window.addEventListener('resize', refreshPosition, { passive: true });

  window.KeepAITour = {
    start(role, user) {
      if (!TOUR_STEPS[role]) return;
      activeRole = role;
      activeUserId = user && (user.id || user.username || user.email);
      ensureRestartControl();
      if (!hasCompletedTour()) {
        window.setTimeout(start, 350);
      }
    },
    restart
  };
})();

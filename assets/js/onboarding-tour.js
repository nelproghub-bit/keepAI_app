(function () {
  'use strict';

  const TOUR_STORAGE_PREFIX = 'keepai_onboarding_completed';
  const TOUR_STEPS = {
    student: [
      {
        section: 'workspaces',
        selector: '[data-section="workspaces"]',
        title: 'Your study starts here',
        description: 'Workspaces keep each subject or project organized. Create one for a course, then bring its notes and study sessions together.',
        tip: 'Start with a workspace for the class you are studying this week.'
      },
      {
        section: 'documents',
        selector: '[data-section="documents"]',
        title: 'Bring your materials along',
        description: 'Upload your course notes and supported documents in the Study Documents area. Keep your source material organized and ready to use.',
        tip: 'Use clear file names so your materials are easy to find later.'
      },
      {
        section: 'tutor',
        selector: '[data-section="tutor"]',
        title: 'Ask the AI Study Tutor',
        description: 'Ask questions in your own words and get explanations designed to make difficult topics easier to understand.',
        tip: 'Try asking for a concept to be explained step by step.'
      },
      {
        section: 'learning',
        selector: '[data-section="learning"]',
        title: 'Turn learning into practice',
        description: 'Use the learning tools to create study resources, review key ideas, and check your understanding with practice activities.',
        tip: 'A short practice session is a useful way to reinforce a lesson.'
      },
      {
        section: 'progress',
        selector: '[data-section="progress"]',
        title: 'See how you are progressing',
        description: 'Visit your progress area to review your study activity and see how your learning routine is developing.',
        tip: 'Check in regularly to keep your study goals in view.'
      },
      {
        section: 'settings',
        selector: '[data-section="settings"]',
        title: 'Make KeepAI yours',
        description: 'Manage your account and preferences from Settings. You can return to any area at any time using the sidebar.',
        tip: 'You are ready to begin. Your tour can be replayed from the button on this page.'
      }
    ],
    admin: [
      {
        section: 'overview',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'overview\')"]',
        title: 'Your administration overview',
        description: 'The Overview brings together the main system statistics and a quick snapshot of activity across KeepAI.',
        tip: 'Use this as your starting point for a regular system check.'
      },
      {
        section: 'users',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'users\')"]',
        title: 'Manage user accounts',
        description: 'User Management is where administrators can review accounts and handle account-related tasks.',
        tip: 'Review account details carefully before making changes.'
      },
      {
        section: 'documents',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'documents\')"]',
        title: 'Review shared documents',
        description: 'The Documents area gives administrators a place to review the document library and manage shared learning resources.',
        tip: 'Keep the library relevant and easy for students to navigate.'
      },
      {
        section: 'announcements',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'announcements\')"]',
        title: 'Keep students informed',
        description: 'Publish announcements to share important updates and reminders with students using the portal.',
        tip: 'Make announcements concise and include the action students need to take.'
      },
      {
        section: 'playground',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'playground\')"]',
        title: 'Check the AI experience',
        description: 'Use the AI Test Console to try the available study modes and verify the assistant experience.',
        tip: 'Test a representative prompt before sharing a change or update.'
      },
      {
        section: 'system',
        selector: '.dash-nav .nav-link[onclick*="switchDashboardTab(\'system\')"]',
        title: 'Monitor system health',
        description: 'System & Database contains diagnostics and operational information to help you review the application status.',
        tip: 'Use these tools for monitoring; avoid changing settings unless you understand their impact.'
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

  function getStorageKey() {
    return `${TOUR_STORAGE_PREFIX}:${activeRole}:${encodeURIComponent(String(activeUserId || 'account'))}`;
  }

  function hasCompletedTour() {
    try {
      return window.localStorage.getItem(getStorageKey()) === 'true';
    } catch (error) {
      console.warn('Could not read onboarding status:', error);
      return false;
    }
  }

  function saveTourCompletion() {
    try {
      window.localStorage.setItem(getStorageKey(), 'true');
    } catch (error) {
      console.warn('Could not save onboarding status:', error);
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

    backdrop.querySelector('[data-tour-close]').addEventListener('click', finishTour);
    backdrop.querySelector('[data-tour-skip]').addEventListener('click', finishTour);
    backdrop.querySelector('[data-tour-back]').addEventListener('click', () => moveToStep(activeStep - 1));
    backdrop.querySelector('[data-tour-next]').addEventListener('click', () => {
      if (activeStep === TOUR_STEPS[activeRole].length - 1) {
        finishTour();
      } else {
        moveToStep(activeStep + 1);
      }
    });
    backdrop.addEventListener('click', event => {
      if (event.target === backdrop) finishTour();
    });
    return backdrop;
  }

  function moveToStep(stepIndex) {
    const steps = TOUR_STEPS[activeRole];
    if (stepIndex < 0 || stepIndex >= steps.length) return;

    activeStep = stepIndex;
    const step = steps[activeStep];
    const navTarget = document.querySelector(step.selector);

    if (highlightedElement) highlightedElement.classList.remove('keepai-tour-highlight');
    highlightedElement = navTarget;
    if (highlightedElement) highlightedElement.classList.add('keepai-tour-highlight');

    if (activeRole === 'student' && typeof window.showSection === 'function') {
      window.showSection(step.section);
    } else if (activeRole === 'admin' && typeof window.switchDashboardTab === 'function') {
      window.switchDashboardTab(step.section);
    }

    activeDialog.querySelector('[data-tour-counter]').textContent = `Step ${activeStep + 1} of ${steps.length}`;
    activeDialog.querySelector('[data-tour-progress]').style.width = `${((activeStep + 1) / steps.length) * 100}%`;
    activeDialog.querySelector('[data-tour-progress]').parentElement.setAttribute('aria-valuenow', String(activeStep + 1));
    activeDialog.querySelector('[data-tour-progress]').parentElement.setAttribute('aria-valuemax', String(steps.length));
    activeDialog.querySelector('#keepai-tour-title').textContent = step.title;
    activeDialog.querySelector('#keepai-tour-description').textContent = step.description;
    activeDialog.querySelector('[data-tour-tip]').textContent = step.tip;
    activeDialog.querySelector('[data-tour-back]').disabled = activeStep === 0;
    activeDialog.querySelector('[data-tour-back]').style.opacity = activeStep === 0 ? '0.5' : '1';
    activeDialog.querySelector('[data-tour-next]').textContent = activeStep === steps.length - 1 ? 'Finish tour' : 'Next';
    activeDialog.querySelector('[data-tour-next]').focus();
  }

  function openTour(replay) {
    if (!activeRole || !TOUR_STEPS[activeRole] || activeDialog) return;
    if (!replay && hasCompletedTour()) return;

    previousFocusedElement = document.activeElement;
    previousBodyOverflow = document.body.style.overflow;
    activeStep = 0;
    activeDialog = createDialog();
    document.body.appendChild(activeDialog);
    document.body.style.overflow = 'hidden';
    moveToStep(0);
  }

  function finishTour() {
    if (!activeDialog) return;
    saveTourCompletion();
    if (highlightedElement) highlightedElement.classList.remove('keepai-tour-highlight');
    highlightedElement = null;
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
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      const nextButton = activeDialog.querySelector('[data-tour-next]');
      nextButton.click();
    } else if (event.key === 'ArrowLeft' && activeStep > 0) {
      event.preventDefault();
      moveToStep(activeStep - 1);
    } else if (event.key === 'Tab') {
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

  window.KeepAITour = {
    start(role, user) {
      if (!TOUR_STEPS[role]) return;
      activeRole = role;
      activeUserId = user && (user.id || user.username || user.email);
      createReplayButton();
      if (!hasCompletedTour()) {
        window.setTimeout(() => openTour(false), 300);
      }
    }
  };
})();

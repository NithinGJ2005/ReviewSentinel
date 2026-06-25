// Mock Repository Diff Data
const MOCK_FILE_DIFF = [
  { lineNum: 1, type: 'context', text: 'import os' },
  { lineNum: 2, type: 'context', text: 'import sqlite3' },
  { lineNum: 3, type: 'context', text: 'import logging' },
  { lineNum: 4, type: 'context', text: '' },
  { lineNum: 5, type: 'removed', text: 'def init_session(session_data={}):' },
  { lineNum: 5, type: 'added', text: 'def init_session(session_data=None):', id: 'mutable-arg-target' },
  { lineNum: 6, type: 'context', text: '    """Initialize a user session record in local storage."""' },
  { lineNum: 7, type: 'context', text: '    conn = sqlite3.connect("users.db")' },
  { lineNum: 8, type: 'context', text: '    cursor = conn.cursor()' },
  { lineNum: 9, type: 'context', text: '    user_id = session_data.get("user_id") if session_data else None' },
  { lineNum: 10, type: 'context', text: '    username = session_data.get("username") if session_data else "guest"' },
  { lineNum: 11, type: 'context', text: '    password = session_data.get("password") if session_data else ""' },
  { lineNum: 12, type: 'context', text: '    ' },
  { lineNum: 13, type: 'removed', text: '    # Fetch matching users' },
  { lineNum: 14, type: 'removed', text: '    cursor.execute(f"SELECT * FROM users WHERE username = \'{username}\' AND password = \'{password}\'")' },
  { lineNum: 13, type: 'added', text: '    # Fetch matching users securely', id: 'sql-inj-target' },
  { lineNum: 14, type: 'added', text: '    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))' },
  { lineNum: 15, type: 'context', text: '    user = cursor.fetchone()' },
  { lineNum: 16, type: 'context', text: '    ' },
  { lineNum: 17, type: 'context', text: '    if user:' },
  { lineNum: 18, type: 'context', text: '        # Log logging event' },
  { lineNum: 19, type: 'removed', text: '        file = open(\'session_log.txt\', \'a\')' },
  { lineNum: 20, type: 'removed', text: '        file.write(f"Session started for {user_id}\\n")' },
  { lineNum: 19, type: 'added', text: '        with open(\'session_log.txt\', \'a\') as file:', id: 'file-leak-target' },
  { lineNum: 20, type: 'added', text: '            file.write(f"Session started for {user_id}\\n")' },
  { lineNum: 21, type: 'context', text: '            return True' },
  { lineNum: 22, type: 'context', text: '    return False' }
];

// Mock Student Mode Pedagogical Findings
const MOCK_FINDINGS = [
  {
    id: 'sql-inj',
    severity: 'critical',
    category: 'Security Vulnerability',
    lines: '13-14',
    concept: 'This is about SQL Injection, where user-supplied inputs are directly concatenated into database query strings instead of using parameter bindings.',
    whyItMatters: 'Using string interpolation (`f"..."`) allows malicious input data to rewrite the structure of your SQL queries. In assignments or course projects, this is a common security failure flagged by autograders, and in real life, it represents the single most frequently exploited category of database leaks.',
    mentorTip: 'Always separate your SQL statements from the parameters by passing query parameters as a tuple in execution arguments (e.g. `cursor.execute("SELECT... WHERE x = %s", (param,))`). This guarantees inputs are sanitized.',
    suggestedOriginal: `cursor.execute(f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'")`,
    suggestedNew: `cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))`,
    suggestedExpl: 'Using query parameters separates code and data, blocking any attempts at injection.',
    targetLine: 14
  },
  {
    id: 'mutable-arg',
    severity: 'warning',
    category: 'Logic Bug',
    lines: '5',
    concept: 'This concerns Python\'s evaluation of Mutable Default Arguments. Python evaluates a function\'s default parameter expressions only once when the module loads, not every time the function runs.',
    whyItMatters: 'Using an empty dictionary (`session_data={}`) as a default means every function call that omits the parameter will share the exact same dictionary object. If you edit `session_data` inside the function, it will persist side-effects in subsequent runs, causing unexpected state errors and test run breakages.',
    mentorTip: 'Use `None` as the default value instead. Inside the function body, check if the variable is `None`, and if so, dynamically initialize a fresh empty dictionary (e.g. `session_data = {}`).',
    suggestedOriginal: `def init_session(session_data={}):`,
    suggestedNew: `def init_session(session_data=None):\n    if session_data is None:\n        session_data = {}`,
    suggestedExpl: 'Using None as the default and dynamically allocating the dictionary guarantees a unique object per function call.',
    targetLine: 5
  },
  {
    id: 'file-leak',
    severity: 'suggestion',
    category: 'Code Smell',
    lines: '19-20',
    concept: 'This covers Resource Management and File Descriptor Leakage. When you open a file handler manually and do not call `.close()`, the operating system resource stays locked.',
    whyItMatters: 'Leaving files open can lead to file lock locks, data corruption when writing buffers, and performance degradation in systems processing many files. Wrap file actions inside Python\'s context managers.',
    mentorTip: 'Always write file manipulations within a `with open(...) as file:` block. Python automatically closes the file descriptor when execution leaves the block, even if exceptions are raised.',
    suggestedOriginal: `file = open('session_log.txt', 'a')\nfile.write(f"Session started for {user_id}\\n")`,
    suggestedNew: `with open('session_log.txt', 'a') as file:\n    file.write(f"Session started for {user_id}\\n")`,
    suggestedExpl: 'The with context manager guarantees safe release of file pointers immediately upon completion of the block.',
    targetLine: 19
  }
];

// Mock Instructor Portal PR Triage List (SQLite history data)
const MOCK_INSTRUCTOR_PR_LOGS = [
  { student: 'Alex Chen', pr: 42, risk: 'high', errors: '1 Security, 1 Bug, 1 Smell', status: 'Unresolved' },
  { student: 'Samantha Ray', pr: 39, risk: 'low', errors: 'None (Clean Run)', status: 'Approved' },
  { student: 'David Miller', pr: 41, risk: 'medium', errors: '2 Style Smells, 1 Warning', status: 'Unresolved' },
  { student: 'Emily Watson', pr: 38, risk: 'high', errors: '2 Security (SQL Injection)', status: 'Under Review' },
  { student: 'James Taylor', pr: 35, risk: 'low', errors: '1 minor Suggestion', status: 'Approved' }
];

// Load and Render Diff
function renderDiff(highlightedLine = null) {
  const container = document.getElementById('code-diff-content');
  container.innerHTML = '';
  
  MOCK_FILE_DIFF.forEach(line => {
    const lineEl = document.createElement('div');
    lineEl.className = `diff-line ${line.type}`;
    if (highlightedLine !== null && line.lineNum === highlightedLine && (line.type === 'added' || line.type === 'removed')) {
      lineEl.classList.add('highlight');
    }
    
    // Add id to scroll to
    if (line.id) {
      lineEl.id = line.id;
    }
    
    const prefix = line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' ';
    
    lineEl.innerHTML = `
      <span class="line-num">${line.lineNum}</span>
      <span class="line-text">${prefix} ${escapeHtml(line.text)}</span>
    `;
    container.appendChild(lineEl);
  });
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Render Pedagogical Feedback Cards
function renderFeedbackCards() {
  const container = document.getElementById('student-feedback-list');
  container.innerHTML = '';
  
  MOCK_FINDINGS.forEach(finding => {
    const card = document.createElement('div');
    card.className = `feedback-card glass ${finding.severity}`;
    card.id = `card-${finding.id}`;
    
    card.innerHTML = `
      <div class="card-header">
        <span class="card-badge">${finding.severity}</span>
        <span class="card-loc">Line ${finding.lines}</span>
      </div>
      <div class="concept-title">${finding.category}</div>
      <div class="pedagogical-sections">
        <div class="p-sec">
          <span class="p-lbl concept">CS Concept</span>
          <p>${finding.concept}</p>
        </div>
        <div class="p-sec">
          <span class="p-lbl why">Why it Matters</span>
          <p>${finding.whyItMatters}</p>
        </div>
        <div class="p-sec">
          <span class="p-lbl mentor">Mentor Tip</span>
          <p>${finding.mentorTip}</p>
        </div>
      </div>
      
      <!-- suggested fix code block -->
      <div class="feedback-suggest-box">
        <div class="suggest-line removed">- ${escapeHtml(finding.suggestedOriginal)}</div>
        <div class="suggest-line added">+ ${escapeHtml(finding.suggestedNew)}</div>
        <div class="suggest-action-row">
          <button class="btn btn-xs apply-btn" data-id="${finding.id}">Apply Suggestion</button>
        </div>
      </div>
    `;
    
    // Clicking card highlights the line
    card.addEventListener('click', (e) => {
      // Don't trigger if they click the apply button
      if (e.target.classList.contains('apply-btn')) return;
      
      document.querySelectorAll('.feedback-card').forEach(c => c.classList.remove('active-focus'));
      card.classList.add('active-focus');
      
      renderDiff(finding.targetLine);
      scrollToTargetLine(finding.id);
    });
    
    container.appendChild(card);
  });
  
  // Set up Apply button listeners
  document.querySelectorAll('.apply-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = e.target.getAttribute('data-id');
      applyMockFix(id, e.target);
    });
  });
}

function scrollToTargetLine(findingId) {
  let targetId = '';
  if (findingId === 'sql-inj') targetId = 'sql-inj-target';
  if (findingId === 'mutable-arg') targetId = 'mutable-arg-target';
  if (findingId === 'file-leak') targetId = 'file-leak-target';
  
  const targetEl = document.getElementById(targetId);
  if (targetEl) {
    targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// Simulates applying a fix inside the UI
function applyMockFix(id, buttonEl) {
  buttonEl.innerText = '✓ Applied';
  buttonEl.style.backgroundColor = 'var(--accent-green)';
  buttonEl.style.boxShadow = '0 0 10px rgba(var(--accent-green-rgb), 0.4)';
  buttonEl.disabled = true;
  
  // Find which file diff line is affected and modify it locally in the view
  if (id === 'sql-inj') {
    const idx = MOCK_FILE_DIFF.findIndex(line => line.id === 'sql-inj-target');
    if (idx !== -1) {
      MOCK_FILE_DIFF[idx].text = '    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))';
      MOCK_FILE_DIFF[idx-1].text = '    # Fetch matching users securely (Sanitized!)';
    }
  } else if (id === 'mutable-arg') {
    const idx = MOCK_FILE_DIFF.findIndex(line => line.id === 'mutable-arg-target');
    if (idx !== -1) {
      MOCK_FILE_DIFF[idx].text = 'def init_session(session_data=None):';
    }
  } else if (id === 'file-leak') {
    const idx = MOCK_FILE_DIFF.findIndex(line => line.id === 'file-leak-target');
    if (idx !== -1) {
      MOCK_FILE_DIFF[idx].text = '        with open(\'session_log.txt\', \'a\') as file:';
    }
  }
  
  // Re-render the diff with highlight
  const finding = MOCK_FINDINGS.find(f => f.id === id);
  renderDiff(finding.targetLine);
  
  // Add a cool green flash to code container
  const codeContainer = document.querySelector('.code-container');
  codeContainer.style.boxShadow = 'inset 0 0 20px rgba(var(--accent-green-rgb), 0.3)';
  setTimeout(() => {
    codeContainer.style.boxShadow = 'none';
  }, 1000);
}

// Render Instructor PR logs
function renderInstructorLogs() {
  const container = document.getElementById('instructor-logs-body');
  container.innerHTML = '';
  
  MOCK_INSTRUCTOR_PR_LOGS.forEach(log => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-weight: 500; color: var(--text-primary);">👤 ${log.student}</td>
      <td style="font-family: 'Fira Code', monospace; color: var(--accent-blue);">#${log.pr}</td>
      <td>
        <span class="triage-indicator ${log.risk}">
          ${log.risk === 'high' ? '🔴 High Risk' : log.risk === 'medium' ? '🟡 Medium Risk' : '🔵 Low Risk'}
        </span>
      </td>
      <td>${log.errors}</td>
      <td>
        <button class="btn btn-xs btn-outline view-student-btn" data-pr="${log.pr}">View Review</button>
      </td>
    `;
    
    // Clicking View Review navigates back to student feedback tab loaded with that data
    tr.querySelector('.view-student-btn').addEventListener('click', () => {
      switchTab('student');
    });
    
    container.appendChild(tr);
  });
}

// Tab switcher logic
function switchTab(tabId) {
  // Update nav buttons
  document.querySelectorAll('.nav-item').forEach(btn => {
    if (btn.getAttribute('data-tab') === tabId) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
  
  // Update view panes
  document.querySelectorAll('.tab-pane').forEach(pane => {
    if (pane.id === `tab-${tabId}`) {
      pane.classList.add('active');
    } else {
      pane.classList.remove('active');
    }
  });
  
  // Update header titles and status labels
  const pageTitle = document.getElementById('page-title');
  const badge = document.querySelector('.meta-badge');
  const breadcrumb = document.getElementById('breadcrumb-current');
  
  if (tabId === 'student') {
    pageTitle.innerText = '🎓 Student Feedback Portal';
    breadcrumb.innerText = 'PR #42 Review';
    badge.className = 'meta-badge student-badge';
    badge.innerHTML = '<span class="badge-dot"></span> Student Mode Enabled';
  } else {
    pageTitle.innerText = '🏫 Instructor Analytics Portal';
    breadcrumb.innerText = 'Classroom Trends';
    badge.className = 'meta-badge instructor-badge';
    badge.style.backgroundColor = 'rgba(187, 92, 255, 0.1)';
    badge.style.borderColor = 'rgba(187, 92, 255, 0.2)';
    badge.style.color = 'hsl(280, 100%, 75%)';
    badge.innerHTML = '<span class="badge-dot" style="background-color: hsl(280, 100%, 75%); box-shadow: 0 0 6px hsl(280, 100%, 75%);"></span> SQLite Trend Sync Active';
  }
}

// App Initialization
document.addEventListener('DOMContentLoaded', () => {
  renderDiff();
  renderFeedbackCards();
  renderInstructorLogs();
  
  // Bind Nav clicks
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      switchTab(tabId);
    });
  });
});

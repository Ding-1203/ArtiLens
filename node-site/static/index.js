// 全局变量
let currentPaper = null;
let papers = [];
let user_id = 0;

// DOM元素
const tabButtons = document.querySelectorAll('.nav-btn');
const tabContents = document.querySelectorAll('.tab-content');
const fileInput = document.getElementById('file-input');
const uploadArea = document.getElementById('upload-area');
const uploadBtn = document.getElementById('upload-btn');
const uploadProgress = document.getElementById('upload-progress');
const papersGrid = document.getElementById('papers-grid');
const refreshBtn = document.getElementById('refresh-papers');

const loading = document.getElementById('loading');
const notification = document.getElementById('notification');

const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const chatMessages = document.getElementById('chat-messages');

let textToTranslate = ''; // FIX: 移至全局作用域

// 初始化
document.addEventListener('DOMContentLoaded', function () {
    initEventListeners();
    loadPapers();
});

function activateTab(tabName) {
    const tabs = document.querySelectorAll('.tab-content');
    const buttons = document.querySelectorAll('.nav-btn');

    // 移除所有激活状态
    tabs.forEach(tab => tab.classList.remove('active'));
    buttons.forEach(btn => btn.classList.remove('active'));

    // 激活当前 tab
    const currentTab = document.getElementById(`${tabName}-tab`);
    const currentBtn = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
    if (currentTab) currentTab.classList.add('active');
    if (currentBtn) currentBtn.classList.add('active');

    // 控制页面是否可滚动
    const noScrollTabs = ['upload', 'login', 'register', 'viewer'];
    if (noScrollTabs.includes(tabName)) {
        document.body.classList.add('no-scroll');
    } else {
        document.body.classList.remove('no-scroll');
    }
}

document.querySelectorAll('.nav-btn').forEach(button => {
    button.addEventListener('click', () => {
        const tab = button.getAttribute('data-tab');
        activateTab(tab);
    });
});

// 事件监听器
function initEventListeners() {
    // 标签切换
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // 文件上传
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);
    uploadBtn.addEventListener('click', uploadFile);

    // 论文管理
    refreshBtn.addEventListener('click', loadPapers);

    // 聊天功能
    //paperSelect.addEventListener('change', selectPaper);
    chatInput.addEventListener('keypress', (e) => {
        // if (e.key === 'Enter') sendMessage();
        if (e.key === 'Enter') sendMessageSync();
    });
    console.log('sendBtn');
    sendBtn.addEventListener('click', sendMessageSync);

    // 清除历史记录功能
    const clearHistoryBtn = document.getElementById('clear-history-btn');
    if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener('click', clearChatHistory);
    }

    // 分割器功能
    initSplitters();

    //监听确认翻译这个按钮
    // document.getElementById('execute-translate-btn').addEventListener('click', executeTranslation);
    document.addEventListener('click', function (e) {
        if (e.target && e.target.id === 'execute-translate-btn') {
            executeTranslation();
        }
    });
    document.addEventListener('click', function (e) {
        if (e.target && (e.target.id === 'confirm-analysis-btn' || e.target.closest('#confirm-analysis-btn'))) {
            startImageAnalysisRequest();
        }
    });
    //监听pdf高光内容
    //修改了PDF的展示框架iframe，现在的iframe有一个高光信息传递通信，次数需要监听
    window.addEventListener('message', handlePdfMessage);

    // 通知关闭
    document.getElementById('notification-close').addEventListener('click', hideNotification);


    // 新增：为“开始截图”按钮添加监听器
    document.addEventListener('click', function (e) {
        if (e.target && (e.target.id === 'start-screenshot-btn' || e.target.closest('#start-screenshot-btn'))) {
            const iframe = document.getElementById('pdf-viewer-frame');
            if (iframe && iframe.contentWindow) {
                // 向 iframe 发送消息，激活截图模式
                iframe.contentWindow.postMessage({type: 'activateScreenshotMode'}, '*');
                document.getElementById('cancel-screenshot-btn').style.display = 'inline-block';
                showNotification('截图模式已激活，请在左侧PDF中拖拽选择区域。', 'info');
            }
        }
    });
    document.addEventListener('click', function (e) {
        if (e.target && (e.target.id === 'cancel-screenshot-btn' || e.target.closest('#cancel-screenshot-btn'))) {
            const iframe = document.getElementById('pdf-viewer-frame');
            if (iframe && iframe.contentWindow) {
                // 向 iframe 发送消息，取消截图模式
                iframe.contentWindow.postMessage({type: 'deactivateScreenshotMode'}, '*');
                document.getElementById('cancel-screenshot-btn').style.display = 'none';
                showNotification('已取消', 'info');
            }
        }
    });
}

// 标签切换
function switchTab(tabName) {
    tabButtons.forEach(btn => btn.classList.remove('active'));
    tabContents.forEach(content => content.classList.remove('active'));

    // document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    // document.getElementById(`${tabName}-tab`).classList.add('active');
    // FIX 1: 检查导航按钮是否存在，存在才激活
    const tabButton = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
    if (tabButton) {
        tabButton.classList.add('active');
    }
    // 激活对应的内容区域
    const tabContent = document.getElementById(`${tabName}-tab`);
    if (tabContent) {
        tabContent.classList.add('active');
    }

    if (tabName === 'papers') {
        loadPapers();
    } else if (tabName === 'chat') {
        loadPapersForChat();
    }
}

// 文件拖拽处理
function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        handleFileSelect();
    }
}

// 文件选择处理
function handleFileSelect() {
    const file = fileInput.files[0];
    if (file) {
        if (file.type === 'application/pdf') {
            uploadBtn.disabled = false;
            uploadArea.querySelector('span').textContent = `已选择: ${file.name}`;
        } else {
            showNotification('请选择PDF文件', 'error');
            fileInput.value = '';
        }
    }
}

// 上传文件
async function uploadFile() {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', user_id);

    showLoading();
    uploadProgress.style.display = 'block';

    try {
        const response = await fetch('http://localhost:8000/api/papers/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            showNotification('文件上传成功！正在后台分析...', 'success');

            // 立即启动异步分析
            startAsyncAnalysis(result.paper_id);

            // 重置上传界面
            fileInput.value = '';
            uploadBtn.disabled = true;
            uploadArea.querySelector('span').textContent = '点击或拖拽文件到此处';
            uploadProgress.style.display = 'none';

            // 立即切换到论文列表
            switchTab('papers');
        } else {
            showNotification(result.error || '上传失败', 'error');
        }
    } catch (error) {
        showNotification('上传失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// 启动异步分析
async function startAsyncAnalysis(paperId) {
    try {
        const response = await fetch(`http://localhost:8000/api/papers/${paperId}/analyze/async`, {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok) {
            console.log('异步分析已启动:', result);
            // 启动状态轮询
            startStatusPolling(paperId);
        } else {
            console.error('启动分析失败:', result);
            showNotification('启动分析失败', 'error');
        }
    } catch (error) {
        console.error('启动分析失败:', error);
        showNotification('启动分析失败: ' + error.message, 'error');
    }
}

// 加载论文列表
async function loadPapers() {
    try {
        const response = await fetch(`http://localhost:8000/api/papers?user_id=${user_id}`);
        const data = await response.json();

        papers = data;
        // console.log(papers)
        renderPapers();
    } catch (error) {
        showNotification('加载论文列表失败', 'error');
    }
}

// 渲染论文列表
function renderPapers() {
    let current_paper = [];
    let j = 0;
    for (let i = 0; i < papers.length; i++) {
        const paper = papers[i];
        if (paper.user_id == user_id) {
            current_paper[j] = paper;
            j++;
        }
    }
    if (current_paper.length === 0) {
        papersGrid.innerHTML = '<div class="empty-state">暂无论文，请先上传论文</div>';
        return;
    }

    papersGrid.innerHTML = current_paper.map(paper => `
        <div class="paper-card" onclick="showPaperDetails(${paper.id})">
            <div class="paper-title">${paper.title || paper.original_filename}</div>
            <div class="paper-meta">
                上传时间: ${new Date(paper.upload_time).toLocaleString()}
            </div>
            <div class="paper-status status-${paper.processing_status}">
                ${getStatusText(paper.processing_status)}
            </div>
        </div>
    `).join('');
}

// 获取状态文本
function getStatusText(status) {
    const statusMap = {
        'uploaded': '已上传',
        'processing': '分析中',
        'completed': '已完成',
        'failed': '分析失败'
    };
    return statusMap[status] || status;
}

// 状态轮询管理
const pollingIntervals = new Map(); // 存储每个论文的轮询定时器

let currentPollingPaperId = null;

function startStatusPolling(paperId) {
    stopStatusPolling(currentPollingPaperId);
    currentPollingPaperId = paperId;

    const interval = setInterval(async () => {
        try {
            const response = await fetch(`http://localhost:8000/api/papers/${paperId}/status`);
            const status = await response.json();

            // 更新论文状态显示（显示进度条等）
            updatePaperStatus(paperId, status);

            if (status.status === 'completed' || status.status === 'failed') {
                clearInterval(interval);
                pollingIntervals.delete(paperId);

                // 重新拉一次论文详情，刷新内容！
                await showPaperDetails(paperId);

                // 论文列表也刷新
                await loadPapers();

                // 弹通知
                if (status.status === 'completed') {
                    showNotification(`论文《${status.title}》分析完成！`, 'success');
                } else {
                    showNotification(`论文《${status.title}》分析失败`, 'error');
                }
            }
        } catch (error) {
            console.error('状态查询失败:', error);
        }
    }, 3000);

    pollingIntervals.set(paperId, interval);
}

// 更新论文状态显示
function updatePaperStatus(paperId, status) {
    // 更新论文列表中的状态
    const paperCard = document.querySelector(`[onclick="showPaperDetails(${paperId})"]`);
    if (paperCard) {
        const statusElement = paperCard.querySelector('.paper-status');
        if (statusElement) {
            statusElement.className = `paper-status status-${status.status}`;
            statusElement.textContent = getStatusText(status.status);
        }
    }

    // 如果当前正在查看这篇论文，更新详情页面
    if (currentPaper === paperId) {
        updatePaperDetailsStatus(status);
    }
}

// 更新论文详情页面的状态显示
function updatePaperDetailsStatus(status) {
    // 如果论文还在分析中，显示进度信息
    if (status.status === 'processing') {
        const progressHtml = `
            <div class="analysis-progress">
                <div class="progress-header">
                    <h3>📊 论文分析中...</h3>
                    <p>请稍候，我们正在为您分析这篇论文</p>
                </div>
                <div class="progress-info">
                    <h4>分析进度: ${status.progress}%</h4>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${status.progress}%"></div>
                    </div>
                </div>
                <div class="progress-details">
                    <h5>已完成的步骤:</h5>
                    ${status.progress_details.map(detail => `<p class="progress-step">✓ ${detail}</p>`).join('')}
                </div>
                <div class="progress-tip">
                    <p>💡 您可以继续浏览其他论文，分析完成后会自动通知您</p>
                </div>
            </div>
        `;

        // 在各个视图中显示进度信息
        const sections = ['info-summary', 'translation', 'terminology', 'research-context', 'image-formula-understanding', 'related-papers'];
        sections.forEach(sectionId => {
            const section = document.querySelector(`[data-section="${sectionId}"]`);
            if (section) {
                section.innerHTML = progressHtml;
            }
        });
    }
}


async function showPaperDetails(paperId) {
    try {
        // 停止轮询上一个正在轮询的论文
        if (currentPollingPaperId && currentPollingPaperId !== paperId) {
            stopStatusPolling(currentPollingPaperId);
        }
        const response = await fetch(`http://localhost:8000/api/papers/${paperId}`);
        const paper = await response.json();

        // FIX 2: 修正PDF文件URL的构建方式，加入 user_id
        const pdfUrl = `http://localhost:8000/uploads/${encodeURIComponent(paper.filename || paper.original_filename)}`;
        document.getElementById('pdf-viewer-frame').src = `viewer.html?file=${pdfUrl}`;

        currentPaper = paperId;
        switchTab('viewer');

        // 重置视图到核心信息
        document.querySelectorAll('.viewer-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelector('.viewer-tab-btn[data-target="info-summary"]').classList.add('active');
        document.querySelectorAll('.viewer-section').forEach(sec => sec.style.display = 'none');
        document.querySelector('.viewer-section[data-section="info-summary"]').style.display = 'block';


        // 检查论文状态
        if (paper.processing_status === 'processing') {
            // 如果正在分析中，显示进度信息并启动轮询
            showAnalysisProgress(paperId);
            startStatusPolling(paperId);
        } else if (paper.processing_status === 'completed') {
            // 如果已完成，显示完整内容
            showCompletedPaperDetails(paper);
        } else if (paper.processing_status === 'failed') {
            // 如果分析失败，显示错误信息
            showFailedPaperDetails(paper);
        } else {
            // 其他状态（如已上传但未开始分析）
            showPendingPaperDetails(paper);
        }

    } catch (error) {
        showNotification('加载论文详情失败', 'error');
        console.error(error);
    }
}

function stopStatusPolling(paperId) {
    if (pollingIntervals.has(paperId)) {
        clearInterval(pollingIntervals.get(paperId));
        pollingIntervals.delete(paperId);
    }
}

// 显示分析进度
async function showAnalysisProgress(paperId) {
    try {
        const response = await fetch(`http://localhost:8000/api/papers/${paperId}/status`);
        const status = await response.json();

        const progressHtml = `
            <div class="analysis-progress">
                <div class="progress-header">
                    <h3>📊 论文分析中...</h3>
                    <p>请稍候，我们正在为您分析这篇论文</p>
                </div>
                <div class="progress-info">
                    <h4>分析进度: ${status.progress}%</h4>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${status.progress}%"></div>
                    </div>
                </div>
                <div class="progress-details">
                    <h5>已完成的步骤:</h5>
                    ${status.progress_details.map(detail => `<p class="progress-step">✓ ${detail}</p>`).join('')}
                </div>
                <div class="progress-tip">
                    <p>💡 您可以继续浏览其他论文，分析完成后会自动通知您</p>
                </div>
            </div>
        `;

        // 在所有视图中显示进度信息
        const sections = ['info-summary', 'translation', 'terminology', 'research-context', 'image-formula-understanding', 'related-papers'];
        sections.forEach(sectionId => {
            const section = document.querySelector(`[data-section="${sectionId}"]`);
            if (section) {
                section.innerHTML = progressHtml;
            }
        });

        // 禁用聊天功能
        const chatInput = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        if (chatInput && sendBtn) {
            chatInput.disabled = true;
            chatInput.placeholder = '论文分析完成后即可开始问答...';
            sendBtn.disabled = true;
        }

    } catch (error) {
        console.error('获取分析状态失败:', error);
        // 如果获取状态失败，显示错误信息
        const errorHtml = `
            <div class="analysis-error">
                <h3>⚠️ 无法获取分析状态</h3>
                <p>请刷新页面重试</p>
            </div>
        `;

        const sections = ['info-summary', 'translation', 'terminology', 'research-context', 'image-formula-understanding', 'related-papers'];
        sections.forEach(sectionId => {
            const section = document.querySelector(`[data-section="${sectionId}"]`);
            if (section) {
                section.innerHTML = errorHtml;
            }
        });
    }
}


// 显示已完成论文的详情
function showCompletedPaperDetails(paper) {
    const viewerContent = document.querySelector('.viewer-content');
    if (!viewerContent) return;

    viewerContent.innerHTML = `
        <div class="viewer-nav">
            <button class="viewer-tab-btn active" data-target="info-summary">核心信息</button>
            <button class="viewer-tab-btn" data-target="translation">中文翻译</button>
            <button class="viewer-tab-btn" data-target="terminology">术语解释</button>
            <button class="viewer-tab-btn" data-target="image-formula-understanding">图像公式</button>
            <button class="viewer-tab-btn" data-target="research-context">研究脉络</button>
            <button class="viewer-tab-btn" data-target="related-papers">相关论文</button>
        </div>
        
        <!-- 1. 核心信息 -->
<!--        <div class="viewer-section" data-section="info-summary" style="display: block;">-->
<!--            <div class="detail-section">-->
<!--                <h3 id="viewer-title"></h3>-->
<!--                <p><strong>作者：</strong><span id="viewer-authors"></span></p>-->
<!--                <p><strong>上传时间：</strong><span id="viewer-upload-time"></span></p>-->
<!--            </div>-->
<!--            <div class="detail-section">-->
<!--                <h4>摘要</h4>-->
<!--                <p id="viewer-abstract"></p>-->
<!--            </div>-->
<!--            <div class="detail-section">-->
<!--                <h4>关键内容</h4>-->
<!--                <pre id="viewer-key-content"></pre>-->
<!--            </div>-->
<!--        </div>-->
        <div class="viewer-section" data-section="info-summary" id="paper-info-summary" style="display: block;">
        </div>

        <!-- 2. 中文翻译 -->
        <div class="viewer-section" data-section="translation" style="display: none;">
            <div class="detail-section">
                <h3>上下文感知翻译</h3>
                <div id="interactive-translation-ui">
                    <div class="instructions">
                        <i class="fas fa-mouse-pointer"></i>
                        <strong>翻译支持:</strong> 在左侧 PDF 中高亮选择文本。
                    </div>
                    <div id="staged-text-container" style="display: none; margin-top: 1rem;">
                        <p><strong>待翻译原文:</strong></p>
                        <blockquote id="staged-text-preview" style="background: #f8f9fa; border-left: 3px solid var(--primary-color); padding: 0.5rem 1rem; margin: 0.5rem 0; font-style: italic;"></blockquote>
                        <button id="execute-translate-btn" class="btn btn-primary">
                            <i class="fas fa-language"></i> 确认翻译
                        </button>
                    </div>
                    <hr style="margin: 1.5rem 0;">
                    <div id="translation-output-container">
                        <div id="translation-output">
                            <p class="placeholder">文段翻译将显示于此。使用上方工具进行实时翻译。</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 3. 术语解释 -->
        <div class="viewer-section" data-section="terminology" style="display: none;">
            <div class="detail-section">
                <pre id="viewer-terminology"></pre>
                <div id="viewer-terminology-answer"></div>
            </div>
        </div>
        
        <div class="viewer-section" data-section="image-formula-understanding"
             style="display: none;">
            <div class="detail-section">
                <h3>图片/公式理解</h3>
                <div id="image-understanding-ui">
                    <div class="instructions">
                        <i class="fas fa-crop-alt"></i>
                        <strong>操作方法:</strong>
                        <ol style="margin-left: 20px; margin-top: 5px; font-size: 0.85rem;">
                            <li>点击下方的“开始截图”按钮。</li>
                            <li>在左侧PDF区域，按住鼠标左键并拖拽以选择您想分析的图片或公式。</li>
                            <li>松开鼠标即可完成截图。</li>
                        </ol>
                    </div>
                    <button id="start-screenshot-btn" class="btn btn-secondary"
                            style="margin-top: 1rem;">
                        <i class="fas fa-crop-alt"></i>开始截图
                    </button>
                    <button id="cancel-screenshot-btn" class="btn btn-danger"
                            style="display:none; margin-left:8px;">
                        <i class="fas fa-times"></i> 取消
                    </button>
                    <!-- This container will show the clicked image and the analysis -->
                    <div id="image-analysis-container" style="margin-top: 1rem;">
                        <!-- The result will be populated here by JS -->
                    </div>
                </div>
            </div>
        </div>

        <!-- 4. 研究脉络 -->
        <div class="viewer-section" data-section="research-context" style="display: none;">
            <div class="detail-section">
                <div id="viewer-research-context" class="markdown-body"></div>
            </div>
        </div>

        <!-- 5. 相关论文 -->
        <div class="viewer-section" data-section="related-papers" style="display: none;">
            <div class="detail-section">
                <div id="viewer-related-papers"></div>
            </div>
        </div>
    `;
    // --- 更新填充逻辑 ---
    // 核心信息 (合并后的视图)
    const titleElement = document.getElementById('viewer-title');
    const authorsElement = document.getElementById('viewer-authors');
    const uploadTimeElement = document.getElementById('viewer-upload-time');
    const abstractElement = document.getElementById('viewer-abstract');
    const keyContentElement = document.getElementById('viewer-key-content');
    const terminologyElement = document.getElementById('viewer-terminology');
    const researchContextElement = document.getElementById('viewer-research-context');

    renderPaperCoreInfo(paper)

    // 安全检查并设置内容
    // if (titleElement) {
    //     titleElement.innerHTML = marked && marked.parse ? marked.parse(paper.title || '未提取标题') : (paper.title || '未提取标题');
    // }
    // if (authorsElement) {
    //     authorsElement.innerHTML = marked && marked.parse ? marked.parse(paper.authors || '未提取作者') : (paper.authors || '未提取作者');
    // }
    // if (uploadTimeElement) {
    //     uploadTimeElement.textContent = new Date(paper.upload_time).toLocaleString();
    // }
    // if (abstractElement) {
    //     abstractElement.innerHTML = marked && marked.parse ? marked.parse(paper.abstract || '暂无摘要') : (paper.abstract || '暂无摘要');
    // }
    // if (keyContentElement) {
    //     keyContentElement.innerHTML = marked && marked.parse ? marked.parse(paper.key_content || '暂无关键内容') : (paper.key_content || '暂无关键内容');
    // }

    if (typeof renderTerminology === 'function') {
        renderTerminology(paper.terminology);
    } else if (terminologyElement) {
        terminologyElement.innerHTML = marked && marked.parse ? marked.parse(paper.terminology || '未生成术语解释') : (paper.terminology || '未生成术语解释');
    }

    if (researchContextElement) {
        researchContextElement.innerHTML = marked && marked.parse ? marked.parse(paper.research_context || '未生成研究脉络') : (paper.research_context || '未生成研究脉络');
    }

    // --- 新增：渲染相关论文 ---
    if (typeof renderRelatedPapers === 'function') {
        renderRelatedPapers(paper.related_papers_json);
    }

    // 启用聊天功能
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    if (chatInput && sendBtn) {
        chatInput.disabled = false;
        chatInput.placeholder = '请输入您的问题...';
        sendBtn.disabled = false;
    }

    // 加载聊天历史
    if (typeof loadChatHistory === 'function') {
        loadChatHistory(paper.id);
    }

    bindViewerTabSwitch();
}

// 显示分析失败的论文
function showFailedPaperDetails(paper) {
    const errorHtml = `
        <div class="analysis-error">
            <div class="error-header">
                <h3>❌ 分析失败</h3>
                <p>很抱歉，这篇论文的分析过程中出现了错误</p>
            </div>
            <div class="error-info">
                <h4>基本信息</h4>
                <p><strong>文件名:</strong> ${paper.original_filename || '未知文件'}</p>
                <p><strong>上传时间:</strong> ${paper.upload_time ? new Date(paper.upload_time).toLocaleString() : '未知时间'}</p>
            </div>
            <div class="error-actions">
                <button onclick="retryAnalysis(${paper.id})" class="retry-btn">重新分析</button>
            </div>
        </div>
    `;

    // 在所有视图中显示错误信息
    const sections = ['info-summary', 'translation', 'terminology', 'image-formula-understanding', 'research-context', 'related-papers'];
    sections.forEach(sectionId => {
        const section = document.querySelector(`[data-section="${sectionId}"]`);
        if (section) {
            section.innerHTML = errorHtml;
        }
    });

    // 禁用聊天功能
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    if (chatInput && sendBtn) {
        chatInput.disabled = true;
        chatInput.placeholder = '分析失败，无法进行问答';
        sendBtn.disabled = true;
    }
}

// 显示等待分析的论文
function showPendingPaperDetails(paper) {
    const pendingHtml = `
        <div class="analysis-pending">
            <div class="pending-header">
                <h3>⏳ 等待分析</h3>
                <p>这篇论文还未开始分析</p>
            </div>
            <div class="pending-info">
                <h4>基本信息</h4>
                <p><strong>文件名:</strong> ${paper.original_filename || '未知文件'}</p>
                <p><strong>上传时间:</strong> ${paper.upload_time ? new Date(paper.upload_time).toLocaleString() : '未知时间'}</p>
            </div>
            <div class="pending-actions">
                <button onclick="startAsyncAnalysis(${paper.id})" class="start-analysis-btn">开始分析</button>
            </div>
        </div>
    `;

    // 在所有视图中显示等待信息
    const sections = ['info-summary', 'translation', 'terminology', 'image-formula-understanding', 'research-context', 'related-papers'];
    sections.forEach(sectionId => {
        const section = document.querySelector(`[data-section="${sectionId}"]`);
        if (section) {
            section.innerHTML = pendingHtml;
        }
    });

    // 禁用聊天功能
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    if (chatInput && sendBtn) {
        chatInput.disabled = true;
        chatInput.placeholder = '请先开始分析论文';
        sendBtn.disabled = true;
    }
}

// 重新分析论文
async function retryAnalysis(paperId) {
    try {
        await startAsyncAnalysis(paperId);
        showNotification('重新分析已启动', 'success');
        // 刷新当前页面
        showPaperDetails(paperId);
    } catch (error) {
        showNotification('启动分析失败', 'error');
    }
}

// 更新 Tab 切换的JS逻辑
// 确保这个逻辑在 DOMContentLoaded 之后运行
document.addEventListener('DOMContentLoaded', () => {
    // 使用 event delegation 来处理按钮点击
    const viewerNav = document.querySelector('.viewer-nav');
    if (viewerNav) {
        viewerNav.addEventListener('click', (e) => {
            if (e.target.matches('.viewer-tab-btn')) {
                const btn = e.target;
                const target = btn.dataset.target;

                // 切换按钮高亮
                document.querySelectorAll('.viewer-tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // 显示对应内容块
                document.querySelectorAll('.viewer-section').forEach(sec => {
                    sec.style.display = (sec.dataset.section === target) ? 'block' : 'none';
                });
            }
        });
    }
    const activeTab = document.querySelector('.tab-content.active');
    if (activeTab) {
        const id = activeTab.id.replace('-tab', '');
        activateTab(id);
    }
});

// 加载聊天历史
async function loadChatHistory(paperId) {
    try {
        const response = await fetch(`http://localhost:8000/api/papers/${paperId}/chat/history?user_id=${user_id}`);
        const chats = await response.json();

        if (chats.length === 0) {
            // 清空聊天界面
            chatMessages.innerHTML = '<div class="welcome-message"><i class="fas fa-robot"></i><p>您好！我是您的论文分析助手。您可以向我提问关于论文的任何问题。</p ></div>';
        }

        if (chats.length > 0) {
            chatMessages.innerHTML = '';
            chats.forEach(chat => {
                addMessage(chat.question, 'user');
                addMessage(chat.answer, 'assistant');
            });
        }
    } catch (error) {
        console.error('加载聊天历史失败:', error);
    }
}

// 清除聊天历史
async function clearChatHistory() {
    if (!currentPaper) {
        showNotification('请先选择一篇论文', 'warning');
        return;
    }

    // 确认对话框
    if (!confirm('确定要清除当前论文的所有聊天历史记录吗？此操作不可撤销。')) {
        return;
    }

    try {
        const response = await fetch(`http://localhost:8000/api/papers/${currentPaper}/chat/history?user_id=${user_id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            const result = await response.json();

            // 清空聊天界面
            chatMessages.innerHTML = '<div class="welcome-message"><i class="fas fa-robot"></i><p>您好！我是您的论文分析助手。您可以向我提问关于论文的任何问题。</p></div>';

            showNotification(`成功清除了 ${result.deleted_count} 条聊天记录`, 'success');
        } else {
            throw new Error('清除失败');
        }
    } catch (error) {
        console.error('清除聊天历史失败:', error);
        showNotification('清除聊天历史失败，请稍后重试', 'error');
    }
}

// 同步问答
async function sendMessageSync() {
    const chatInput = document.getElementById('chat-input');
    console.log('发送消息');
    const question = chatInput.value.trim();
    if (!question || !currentPaper) return;

    // 添加用户消息
    addMessage(question, 'user');
    chatInput.value = '';

    // 显示加载状态
    const loadingMsg = addMessage('正在思考中...', 'assistant', true);

    try {
        const response = await fetch(`http://localhost:8000/api/papers/${currentPaper}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                user_id: user_id
            })
        });

        const result = await response.json();

        // 移除加载消息
        loadingMsg.remove();

        if (response.ok) {
            addMessage(result.answer, 'assistant');
        } else {
            addMessage('抱歉，回答问题时出现错误: ' + (result.error || '未知错误'), 'assistant');
        }
    } catch (error) {
        loadingMsg.remove();
        addMessage('抱歉，网络错误，请稍后重试。', 'assistant');
    }
}

//解析问答返回的json，并且对有图像和没图像进行处理
function addMessage(content, sender, isLoading = false) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    let messageContentHTML = '';

    if (sender === 'assistant' && !isLoading) {
        try {
            const data = JSON.parse(content);
            if (data.diagram && data.diagram.type === 'mermaid') {
                const diagramId = `mermaid-${Date.now()}`;
                const diagramCode = data.diagram.code;
                const diagramTitle = data.diagram.title || '生成的图表';

                // --- 修改：添加“放大”按钮，并用一个容器包裹按钮 ---
                messageContentHTML = `
                    <div class="message-content">
                        ${data.answer ? marked.parse(data.answer) : ''}
                        <div class="diagram-container">
                            <div class="diagram-header">
                                <h4>${diagramTitle}</h4>
                                <div class="diagram-actions">
                                    <button class="btn-action btn-enlarge" title="在新标签页中打开">
                                        <i class="fas fa-search-plus"></i> 放大
                                    </button>
                                    <button class="btn-action btn-download" title="下载为PNG图片">
                                        <i class="fas fa-download"></i> 下载
                                    </button>
                                </div>
                            </div>
                            <div class="mermaid" id="${diagramId}">${diagramCode}</div>
                        </div>
                    </div>
                `;

                messageDiv.innerHTML = messageContentHTML;
                chatMessages.appendChild(messageDiv);

                // 异步渲染 Mermaid 图表，并直接绑定事件
                setTimeout(() => {
                    try {
                        mermaid.run({nodes: [document.getElementById(diagramId)]});

                        // --- 修改：直接为新创建的按钮绑定事件 ---
                        const enlargeBtn = messageDiv.querySelector('.btn-enlarge');
                        enlargeBtn.addEventListener('click', () => enlargeDiagram(diagramId));

                        const downloadBtn = messageDiv.querySelector('.btn-download');
                        downloadBtn.addEventListener('click', () => downloadDiagram(diagramId, diagramTitle));

                    } catch (e) {
                        console.error("Mermaid渲染失败:", e);
                        const diagramNode = document.getElementById(diagramId);
                        if (diagramNode) diagramNode.innerText = "图表渲染失败，请检查Mermaid代码。";
                    }
                }, 100);

            } else {
                messageContentHTML = `<div class="message-content">${marked.parse(data.answer || content)}</div>`;
                messageDiv.innerHTML = messageContentHTML;
                chatMessages.appendChild(messageDiv);
            }
        } catch (e) {
            messageContentHTML = `<div class="message-content">${marked.parse(content)}</div>`;
            messageDiv.innerHTML = messageContentHTML;
            chatMessages.appendChild(messageDiv);
        }
    } else {
        messageContentHTML = `<div class="message-content">${isLoading ? content : marked.parse(content)}</div>`;
        messageDiv.innerHTML = messageContentHTML;
        chatMessages.appendChild(messageDiv);
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
    return messageDiv;
}

// 显示加载状态
function showLoading() {
    loading.style.display = 'flex';
}

// 隐藏加载状态
function hideLoading() {
    loading.style.display = 'none';
}

// 显示通知
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    const notificationText = document.getElementById('notification-text');

    if (!notification || !notificationText) return;

    notificationText.textContent = message;
    notification.className = `notification ${type} show`;

    clearTimeout(notification.timer);
    notification.timer = setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

// 隐藏通知
function hideNotification() {
    notification.classList.remove('show');
}


// 核心信息渲染
function renderPaperCoreInfo(paper) {
    const container = document.getElementById('paper-info-summary');
    if (!container) return;

    // 处理字段
    const title = paper.title || '未提取标题';
    const arxivUrl = paper.arxiv_url ? `<a href="${paper.arxiv_url}" target="_blank" rel="noopener noreferrer"><i class="fas fa-link"></i> arXiv</a>` : '';
    const publishedTime = paper.published_time ? paper.published_time.replace(/T.*$/, '') : '';
    const authors = paper.authors || '未提取作者';
    const summary = paper.summary || '';
    const abstract = paper.abstract || '暂无摘要';
    const keyContent = paper.key_content || '暂无关键内容';

    // 生成HTML
//     container.innerHTML = `
//     <div class="detail-section paper-summary-info">
//         <h2 style="margin-bottom: .3em;">
//             ${title}
//             ${arxivUrl ? `<span style="font-size:1rem;margin-left:1em;">${arxivUrl}</span>` : ''}
//         </h2>
//         <div class="paper-meta paper-summary-meta">
//             <span class="paper-summary-authors"><i class="fas fa-user"></i> ${authors}</span>
//             ${publishedTime ? `<span class="paper-summary-date"><i class="fas fa-calendar-alt"></i> ${publishedTime}</span>` : ""}
//         </div>
//     </div>
//     <div class="detail-section">
//         <h4>一句话总结</h4>
//         <blockquote class="summary-block">${marked && marked.parse ? marked.parse(summary) : (summary || '暂无总结')}</blockquote>
//     </div>
//     <div class="detail-section">
//         <h4>摘要</h4>
//         <div>${marked && marked.parse ? marked.parse(abstract) : abstract}</div>
//     </div>
//     <div class="detail-section">
//         <h4>核心内容</h4>
//         <div class="markdown-body" id="key-content-display">
//             ${marked && marked.parse ? marked.parse(keyContent) : keyContent}
//         </div>
//     </div>
// `;

    container.innerHTML = `
<div class="detail-section paper-summary-info detail-main-info">
    <h2 class="detail-title">
        ${title}
        ${arxivUrl ? `<span class="detail-arxiv-url">${arxivUrl}</span>` : ''}
    </h2>
    <div class="paper-meta paper-summary-meta detail-meta">
        <span class="paper-summary-authors"><i class="fas fa-user"></i> ${authors}</span>
        ${publishedTime ? `<span class="paper-summary-date"><i class="fas fa-calendar-alt"></i> ${publishedTime}</span>` : ""}
    </div>
</div>
<div class="detail-section detail-main-info">
    <h4 class="detail-h4">一句话总结</h4>
    <blockquote class="summary-block">${marked && marked.parse ? marked.parse(summary) : (summary || '暂无总结')}</blockquote>
</div>
<div class="detail-section detail-main-info">
    <h4 class="detail-h4">摘要</h4>
    <div id="detail-abstract-container">${marked && marked.parse ? marked.parse(abstract) : abstract}</div>
</div>
<div class="detail-section">
    <h4 class="detail-h4">核心内容</h4>
    <div class="markdown-body key-content-md" id="key-content-display">
        ${marked && marked.parse ? marked.parse(keyContent) : keyContent}
    </div>
</div>

`;
    // 如需支持公式（LaTeX），自动排版
    if (window.MathJax && window.MathJax.typesetPromise) {
        MathJax.typesetPromise([container]);
    }
}

function renderTerminology(terminology) {
    const container = document.getElementById('viewer-terminology');
    const blank_container = document.getElementById('viewer-terminology-answer');
    if (!container) return;
    let terms = [];
    try {
        terms = JSON.parse(terminology);
    } catch {
        terms = [];
    }
    container.innerHTML = `
        <div class="term-header">
            <span class="term-tip"><i class="fas fa-lightbulb"></i> 本文关键词（中英文）</span>
            <div class="term-keywords-row" id="term-btn-list">
                ${terms.map(term =>
        `<button class="term-btn modern-btn" data-term="${term.en}">
                       <span class="term-text">${term.en}（${term.zh}）</span>
                    </button>`
    ).join('')}
            </div>
        </div>
    `;
    blank_container.innerHTML = `   
        <div class="term-search-row">
            <input type="text" id="term-search-input" class="modern-input" placeholder="输入术语获取详细解析">
            <button id="term-search-btn" class="btn btn-primary">解析</button>
        </div>
        <div id="term-explain-output" class="markdown-body">
            <p class="placeholder">术语解释将显示于此。</p>
        </div>
    `;

    setTimeout(() => {
        document.querySelectorAll('.term-btn').forEach(btn => {
            btn.onclick = () => {
                // 高亮当前按钮
                document.querySelectorAll('.term-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                explainTerm(btn.dataset.term);
            };
        });
        const doSearch = () => {
            document.querySelectorAll('.term-btn').forEach(b => b.classList.remove('active'));
            const kw = document.getElementById('term-search-input').value.trim();
            if (kw) explainTerm(kw);
        };
        document.getElementById('term-search-btn').onclick = doSearch;
        document.getElementById('term-search-input').onkeydown = e => {
            if (e.key === 'Enter') doSearch();
        };
    }, 30);
}


function renderRelatedPapers(relatedDataJson) {
    const container = document.getElementById('viewer-related-papers');
    if (!container) {
        console.error('相关论文容器元素不存在');
        return;
    }

    // 解析原始论文数据
    let references = [];
    try {
        references = JSON.parse(relatedDataJson) || [];
    } catch (e) {
        container.innerHTML = '<p class="related-paper-error">论文数据格式有误。</p>';
        return;
    }

    // 搜索栏和列表区域
    container.innerHTML = `
        <div id="reference-query-bar" style="margin-bottom:1em;padding:1em;background:#f8f9fa;border-radius:8px;box-shadow:0 1px 6px #eee;">
            <h3 style="margin:0 0 0.5em;">相关论文搜索</h3>
            <input id="reference-search-input" type="text" style="width:200px;padding:6px;border-radius:4px;border:1px solid #ddd;" placeholder="输入论文标题" />
            <button id="reference-search-btn" style="margin-left:8px;padding:6px 18px;border:none;background:#007bff;color:white;border-radius:4px;cursor:pointer;">搜索</button>
            <button id="reference-reset-btn" style="margin-left:8px;padding:6px 18px;border:none;background:#6c757d;color:white;border-radius:4px;cursor:pointer;display:none;">返回全部</button>
        </div>
        <div id="related-papers-list"></div>
    `;

    const searchBtn = container.querySelector('#reference-search-btn');
    const resetBtn = container.querySelector('#reference-reset-btn');
    const searchInput = container.querySelector('#reference-search-input');

    // 渲染论文列表
    function renderList(papers, mode = 'all', keyword = '') {
        const listDiv = container.querySelector('#related-papers-list');
        let titleHtml = '';
        if (mode === 'search-local') {
            titleHtml = `<div style="color:#007bff;font-weight:600;margin-bottom:0.5em;">本地搜索结果（共${papers.length}条）</div>`;
            resetBtn.style.display = 'inline-block';
        } else if (mode === 'search-remote') {
            titleHtml = `<div style="color:#007bff;font-weight:600;margin-bottom:0.5em;">arXiv 检索结果（共${papers.length}条）</div>`;
            resetBtn.style.display = 'inline-block';
        } else {
            titleHtml = '';
            resetBtn.style.display = 'none';
        }

        if (!papers || papers.length === 0) {
            listDiv.innerHTML = `${titleHtml}<p>未找到相关论文。</p>`;
            return;
        }
        let html = '<ul class="related-papers-list" style="padding-left:0;">';
        papers.forEach(paper => {
            if (!paper) return;
            let title = paper.title || 'N/A';
            // 关键词高亮
            if (keyword && title !== 'N/A') {
                const reg = new RegExp(keyword, "gi");
                title = title.replace(reg, match => `<span style="background:yellow;">${match}</span>`);
            }
            const published = paper.published ? paper.published.slice(0, 10) : 'N/A';
            const authors = Array.isArray(paper.authors) ? paper.authors.join(', ') : 'N/A';
            const link = paper.link || '#';
            const summary = paper.summary || '';
            html += `
                <li class="related-paper-item" style="list-style:none;margin-bottom:1em;padding:1em;background:#fff;border-radius:8px;box-shadow:0 1px 3px #eee;">
                    <a href="${link}" target="_blank" class="related-paper-title" style="font-weight:600;font-size:1.1em;color:#007bff;text-decoration:none;">${title}</a>
                    <div class="related-paper-meta" style="color:#666;font-size:.95em;margin:0.3em 0;">
                        <span><strong>作者:</strong> ${authors}</span><br>
                        <span><strong>发布时间:</strong> ${published}</span>
                    </div>
                    <div class="related-paper-summary" style="font-size:.95em;line-height:1.5;">
                        <strong>摘要:</strong> ${summary}
                    </div>
                </li>
            `;
        });
        html += '</ul>';
        listDiv.innerHTML = titleHtml + html;
    }

    // 默认展示全部
    renderList(references.filter(p => p));

    // 搜索按钮事件
    searchBtn.onclick = async function () {
        const keyword = searchInput.value.trim();
        if (!keyword) {
            renderList(references.filter(p => p));
            return;
        }
        // 本地模糊查找
        const matched = references.filter(p => p && p.title && p.title.toLowerCase().includes(keyword.toLowerCase()));
        if (matched.length > 0) {
            renderList(matched, 'search-local', keyword);
        } else {
            // 远端 arXiv 检索
            const listDiv = container.querySelector('#related-papers-list');
            listDiv.innerHTML = `<p style="color:#888;">本地无结果，正在从 arXiv 检索...</p>`;
            try {
                // 支持多条
                const resp = await fetch(`http://localhost:8000/api/papers/search_arxiv?title=${encodeURIComponent(keyword)}&max_results=5`);
                if (!resp.ok) throw new Error("接口异常");
                const newList = await resp.json();
                renderList(newList.filter(p => p), 'search-remote', keyword);
            } catch (err) {
                listDiv.innerHTML = '<p style="color:red;">检索失败，请稍后重试。</p>';
            }
        }
    };

    // “返回全部”按钮事件
    resetBtn.onclick = function () {
        searchInput.value = '';
        renderList(references.filter(p => p));
    };

    // 回车键直接搜索
    searchInput.addEventListener('keyup', function (event) {
        if (event.key === 'Enter') {
            searchBtn.click();
        }
    });
}

function enlargeDiagram(diagramId) {
    const svgElement = document.querySelector(`#${diagramId} > svg`);
    if (!svgElement) {
        showNotification('找不到图表以放大，请稍候。', 'error');
        return;
    }

    // 1. 获取SVG的完整代码字符串
    const svgString = new XMLSerializer().serializeToString(svgElement);

    // 2. 创建一个包含SVG和居中样式的完整HTML文档字符串
    const htmlContent = `
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Diagram Viewer</title>
            <style>
                /* 在这个新页面中应用样式 */
                html, body {
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    height: 100%;
                    display: flex;
                    justify-content: center; /* 水平居中 */
                    align-items: center;   /* 垂直居中 */
                    background-color: #f0f2f5; /* 添加一个舒适的背景色 */
                }
                svg {
                    /* 确保SVG不会超出屏幕 */
                    max-width: 95%;
                    max-height: 95%;
                }
            </style>
        </head>
        <body>
            <!-- 将SVG代码直接嵌入到body中 -->
            ${svgString}
        </body>
        </html>
    `;

    // 3. 创建一个类型为 'text/html' 的Blob
    const blob = new Blob([htmlContent], {type: 'text/html'});
    const url = URL.createObjectURL(blob);

    // 4. 在新标签页中打开这个HTML页面
    const newWindow = window.open(url, '_blank');

    if (!newWindow) {
        showNotification('无法打开新窗口，请检查您的弹窗拦截设置。', 'error');
    }
}

// --- 下载图表的函数<没实现> ---
async function downloadDiagram(diagramId, filename) {
    showNotification('正在生成图片...', 'info');
    try {
        const svgElement = document.querySelector(`#${diagramId} > svg`);
        if (!svgElement) {
            showNotification('找不到图表元素，无法下载', 'error');
            return;
        }

        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const svgString = new XMLSerializer().serializeToString(svgElement);

        // 使用 canvg 将 SVG 渲染到 Canvas 上
        const v = await Canvg.from(ctx, svgString);

        // 添加一些内边距，让下载的图片更好看
        const padding = 20;
        canvas.width = v.width + padding * 2;
        canvas.height = v.height + padding * 2;

        // 填充白色背景
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // 在画布上渲染SVG，并应用内边距
        await v.render({
            offsetX: padding,
            offsetY: padding
        });

        // 创建下载链接
        const link = document.createElement('a');
        link.href = canvas.toDataURL('image/png');
        // 清理文件名中的非法字符
        link.download = `${filename.replace(/[\s/\\?%*:|"<>]/g, '_')}.png`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showNotification('图片已开始下载！', 'success');

    } catch (error) {
        console.error('下载图表失败:', error);
        showNotification('下载失败，请查看控制台错误信息', 'error');
    }
}


// 注册表单提交
document.getElementById('register-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    const username = document.getElementById('register-username').value;
    const email = document.getElementById('register-email').value;

    try {
        const res = await fetch('http://localhost:8000/api/users/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, email})
        });
        const data = await res.json();
        alert('注册成功: ' + data.username);
        //清空输入框
        document.getElementById('register-username').value = '';
        document.getElementById('register-email').value = '';
    } catch (err) {
        alert('注册失败');
        //清空输入框
        document.getElementById('register-username').value = '';
        document.getElementById('register-email').value = '';
    }
});

// 登录表单提交
document.getElementById('login-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const email = document.getElementById('login-email').value;

    try {
        const res = await fetch('http://localhost:8000/api/users/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, email})
        });
        const data = await res.json();
        alert('登录成功: ' + data.username);
        console.log("here");
        user_id = data.id;
        document.getElementById('current-user').textContent = data.username;
        //清空输入框
        document.getElementById('login-username').value = '';
        document.getElementById('login-email').value = '';
    } catch (err) {
        alert('登录失败');
        console.error("登录", err)
        //清空输入框
        document.getElementById('login-username').value = '';
        document.getElementById('login-email').value = '';
    }
});


// ========== 分割器功能 ==========

// 分割器状态
let splitterState = {
    isDragging: false,
    currentSplitter: null,
    startPos: 0,
    startSize: 0,
    dragMask: null
};

// 在initSplitters中添加遮罩生成
function createDragMask() {
    let mask = document.createElement('div');
    mask.style.position = 'fixed';
    mask.style.left = '0';
    mask.style.top = '0';
    mask.style.width = '100vw';
    mask.style.height = '100vh';
    mask.style.zIndex = '99999';
    mask.style.background = 'rgba(0,0,0,0)'; // 完全透明
    mask.style.cursor = splitterState.currentSplitter === 'horizontal' ? 'col-resize' : 'row-resize';
    document.body.appendChild(mask);
    splitterState.dragMask = mask;
}

function removeDragMask() {
    if (splitterState.dragMask) {
        document.body.removeChild(splitterState.dragMask);
        splitterState.dragMask = null;
    }
}

// 初始化分割器
function initSplitters() {
    const horizontalSplitter = document.getElementById('horizontal-splitter');
    const verticalSplitter = document.getElementById('vertical-splitter');

    if (horizontalSplitter) {
        horizontalSplitter.addEventListener('mousedown', (e) => startDrag(e, 'horizontal'));
    }

    if (verticalSplitter) {
        verticalSplitter.addEventListener('mousedown', (e) => startDrag(e, 'vertical'));
    }

    // 全局鼠标事件
    document.addEventListener('mousemove', handleDrag);
    document.addEventListener('mouseup', stopDrag);

    // 防止选择文本
    document.addEventListener('selectstart', (e) => {
        if (splitterState.isDragging) {
            e.preventDefault();
        }
    });

    // 加载保存的布局
    loadLayout();
}

// 开始拖拽
function startDrag(e, type) {
    e.preventDefault();

    splitterState.isDragging = true;
    splitterState.currentSplitter = type;

    const splitter = document.getElementById(`${type}-splitter`);
    splitter.classList.add('dragging');

    if (type === 'horizontal') {
        splitterState.startPos = e.clientX;
        const pdfPane = document.getElementById('pdf-pane');
        splitterState.startSize = pdfPane.offsetWidth;
    } else {
        splitterState.startPos = e.clientY;
        const infoPane = document.getElementById('info-pane');
        splitterState.startSize = infoPane.offsetHeight;
    }

    // 添加拖拽时的样式
    document.body.style.cursor = type === 'horizontal' ? 'col-resize' : 'row-resize';
    document.body.style.userSelect = 'none';

    // 新增：生成全局遮罩，彻底避免拖拽断开
    createDragMask();
}

// 处理拖拽
function handleDrag(e) {
    if (!splitterState.isDragging) return;

    e.preventDefault();

    if (splitterState.currentSplitter === 'horizontal') {
        handleHorizontalDrag(e);
    } else {
        handleVerticalDrag(e);
    }
}

// 处理水平拖拽
function handleHorizontalDrag(e) {
    const viewerWrapper = document.querySelector('.viewer-wrapper');
    const pdfPane = document.getElementById('pdf-pane');

    const deltaX = e.clientX - splitterState.startPos;
    const newWidth = splitterState.startSize + deltaX;
    const wrapperWidth = viewerWrapper.offsetWidth;
    const splitterWidth = 4; // 分割器宽度

    // 计算百分比，确保最小宽度
    const minWidth = 300;
    const maxWidth = wrapperWidth - minWidth - splitterWidth;

    if (newWidth >= minWidth && newWidth <= maxWidth) {
        const percentage = (newWidth / wrapperWidth) * 100;
        pdfPane.style.width = `${percentage}%`;
    }
}

// 处理垂直拖拽
function handleVerticalDrag(e) {
    const detailsPane = document.getElementById('details-pane');
    const infoPane = document.getElementById('info-pane');
    const chatContainer = document.getElementById('chat-container');

    const deltaY = e.clientY - splitterState.startPos;
    const newHeight = splitterState.startSize + deltaY;
    const detailsHeight = detailsPane.offsetHeight;
    const splitterHeight = 4; // 分割器高度

    // 计算百分比，确保最小高度
    const minHeight = 100;
    const maxHeight = detailsHeight - minHeight - splitterHeight;

    if (newHeight >= minHeight && newHeight <= maxHeight) {
        const infoPercentage = (newHeight / detailsHeight) * 100;
        const chatPercentage = 100 - infoPercentage;

        infoPane.style.height = `${infoPercentage}%`;
        chatContainer.style.height = `${chatPercentage}%`;
    }
}

// 停止拖拽
function stopDrag() {
    if (!splitterState.isDragging) return;

    const splitter = document.getElementById(`${splitterState.currentSplitter}-splitter`);
    splitter.classList.remove('dragging');

    // 恢复样式
    document.body.style.cursor = '';
    document.body.style.userSelect = '';

    // 拖拽结束，移除遮罩
    removeDragMask();

    // 保存布局
    saveLayout();

    // 重置状态
    splitterState.isDragging = false;
    splitterState.currentSplitter = null;
}

// 保存布局到localStorage
function saveLayout() {
    try {
        const pdfPane = document.getElementById('pdf-pane');
        const infoPane = document.getElementById('info-pane');
        const chatContainer = document.getElementById('chat-container');

        const layout = {
            pdfWidth: pdfPane.style.width || '50%',
            infoHeight: infoPane.style.height || '60%',
            chatHeight: chatContainer.style.height || '40%'
        };

        localStorage.setItem('artilens-layout', JSON.stringify(layout));
    } catch (error) {
        console.warn('无法保存布局设置:', error);
    }
}

// 加载保存的布局
function loadLayout() {
    try {
        const savedLayout = localStorage.getItem('artilens-layout');
        if (savedLayout) {
            const layout = JSON.parse(savedLayout);

            const pdfPane = document.getElementById('pdf-pane');
            const infoPane = document.getElementById('info-pane');
            const chatContainer = document.getElementById('chat-container');

            if (pdfPane && layout.pdfWidth) {
                pdfPane.style.width = layout.pdfWidth;
            }

            if (infoPane && layout.infoHeight) {
                infoPane.style.height = layout.infoHeight;
            }

            if (chatContainer && layout.chatHeight) {
                chatContainer.style.height = layout.chatHeight;
            }
        }
    } catch (error) {
        console.warn('无法加载布局设置:', error);
    }
}

// 重置布局为默认值
function resetLayout() {
    const pdfPane = document.getElementById('pdf-pane');
    const infoPane = document.getElementById('info-pane');
    const chatContainer = document.getElementById('chat-container');

    if (pdfPane) pdfPane.style.width = '50%';
    if (infoPane) infoPane.style.height = '60%';
    if (chatContainer) chatContainer.style.height = '40%';

    // 清除保存的布局
    localStorage.removeItem('artilens-layout');
}

// 双击分割器重置布局
document.addEventListener('DOMContentLoaded', function () {
    const horizontalSplitter = document.getElementById('horizontal-splitter');
    const verticalSplitter = document.getElementById('vertical-splitter');

    if (horizontalSplitter) {
        horizontalSplitter.addEventListener('dblclick', () => {
            const pdfPane = document.getElementById('pdf-pane');
            if (pdfPane) {
                pdfPane.style.width = '50%';
                saveLayout();
            }
        });
    }

    if (verticalSplitter) {
        verticalSplitter.addEventListener('dblclick', () => {
            const infoPane = document.getElementById('info-pane');
            const chatContainer = document.getElementById('chat-container');
            if (infoPane && chatContainer) {
                infoPane.style.height = '60%';
                chatContainer.style.height = '40%';
                saveLayout();
            }
        });
    }
});

//处理pdf.js监听的信息
function handlePdfMessage(event) {
    if (event.data && event.data.type === 'pdfTextSelection') {
        const selectedText = event.data.text;

        if (!currentPaper) return;

        textToTranslate = selectedText;

        const stagedTextContainer = document.getElementById('staged-text-container');
        const stagedTextPreview = document.getElementById('staged-text-preview');

        stagedTextPreview.textContent = textToTranslate;
        stagedTextContainer.style.display = 'block';

        console.log(`[TRANSLATE] Text staged: "${textToTranslate.substring(0, 50)}..."`);
    } else if (event.data && event.data.type === 'screenshotEnded') {
        document.getElementById('cancel-screenshot-btn').style.display = 'none';
    } else if (event.data && event.data.type === 'pdfError') {
        showNotification(`PDF 查看器错误: ${event.data.message}`, 'error');
    } else if (event.data && event.data.type === 'pdfRegionCropped') { // 处理手动截图完成的消息
        const {payload} = event.data;
        handleImageAnalysis(payload);
    }
}

async function executeTranslation() {
    if (!textToTranslate) {
        showNotification('没有待翻译的文本。请先从PDF中选择。', 'info');
        return;
    }
    if (!currentPaper) return;

    const translationOutput = document.getElementById('translation-output');
    let buffer = '';

    translationOutput.innerHTML = `
        <div class="loading-state" id="translation-loading">
            <i class="fas fa-spinner fa-spin"></i> 
            正在翻译...
        </div>`;

    try {
        const response = await fetch(`http://localhost:8000/api/papers/${currentPaper}/interactive-translate`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: textToTranslate})
        });

        if (response.ok) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const {done, value} = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, {stream: true});
                // 逐行处理数据
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            buffer += data.content;
                            translationOutput.innerHTML = marked.parse(buffer);
                        } catch (e) {
                            console.error('Parsing error:', e);
                        }
                    }
                }
            }
            // 翻译结束，移除 loading
            const loadingDiv = document.getElementById('translation-loading');
            if (loadingDiv) loadingDiv.remove();
        } else {
            const errorResult = await response.json();
            translationOutput.innerHTML = `<div class="error">翻译失败: ${errorResult.detail || '未知错误'}</div>`;
        }
    } catch (error) {
        console.error("Interactive translation fetch failed:", error);
        translationOutput.innerHTML = `<div class="error">网络请求失败，无法连接到翻译服务。</div>`;
    }
}

async function explainTerm(term) {
    const output = document.getElementById('term-explain-output');
    output.innerHTML = '';
    output.innerHTML = `
<span class="loading-state" id="explain-loading">
    <i class="fas fa-spinner fa-spin"></i> 正在生成关键词解释...
</span>
    `;
    let buffer = '';

    try {
        const response = await fetch(`http://localhost:8000/api/papers/${currentPaper}/explain-term`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({term})
        });

        if (response.ok) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            // 开始流式接收内容，直接写入 output（每次全覆盖）
            while (true) {
                const {done, value} = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, {stream: true});
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            buffer += data.content;
                            output.innerHTML = `<b>${term}：</b> ${buffer}`;
                        } catch (e) {
                            console.error('Parsing error:', e);
                        }
                    }
                }
            }
        } else {
            const errorResult = await response.json();
            output.innerHTML = `<div class="error">解释失败: ${errorResult.detail || '未知错误'}</div>`;
        }
    } catch (error) {
        console.error("Explanation fetch failed:", error);
        output.innerHTML = `<div class="error">网络请求失败，无法连接到解释服务。</div>`;
    }
}


function bindViewerTabSwitch() {
    const viewerNav = document.querySelector('.viewer-nav');
    if (!viewerNav) return;
    // 先移除之前所有绑定，防止重复
    viewerNav.replaceWith(viewerNav.cloneNode(true));
    const newViewerNav = document.querySelector('.viewer-nav');
    newViewerNav.addEventListener('click', (e) => {
        if (e.target.matches('.viewer-tab-btn')) {
            const btn = e.target;
            const target = btn.dataset.target;
            document.querySelectorAll('.viewer-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.viewer-section').forEach(sec => {
                sec.style.display = (sec.dataset.section === target) ? 'block' : 'none';
            });
        }
    });
}

let stagedImagePayloadForAnalysis = null;

//新增图像处理的确认弹窗
async function startImageAnalysisRequest() {
    if (!stagedImagePayloadForAnalysis || !currentPaper) {
        showNotification('没有待分析的对象或论文未选择。', 'error');
        return;
    }

    // 获取类型和caption
    const typeSelect = document.getElementById('analysis-type-select');
    const typeValue = typeSelect ? typeSelect.value : '';
    if (!typeValue) {
        showNotification('请先选择分析对象类型（图片/表格/公式）', 'error');
        return;
    }
    const captionInput = document.getElementById('caption-input');
    const captionText = captionInput ? captionInput.value.trim() : '';

    const confirmBtn = document.getElementById('confirm-analysis-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在分析...';
    }

    const resultDiv = document.getElementById('analysis-result');
    resultDiv.innerHTML = `
        <div class="message assistant">
            <div class="message-content">
                <div class="typing-indicator">AI正在思考...</div>
            </div>
        </div>
    `;

    let accumulatedContent = '';
    try {
        const response = await fetch(`http://localhost:8000/api/papers/${currentPaper}/understand-image`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                image_data: stagedImagePayloadForAnalysis.imageData,
                type: typeValue,
                caption_text: captionText,
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        resultDiv.innerHTML = ''; // 清空“正在思考”提示，准备接收内容


        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n').filter(line => line.trim());

            function renderMathIfReady(el) {
                if (window.MathJax && window.MathJax.typesetPromise) {
                    MathJax.typesetClear();
                    MathJax.typesetPromise([el]);
                } else {
                    // 没加载好就延迟重试
                    setTimeout(() => renderMathIfReady(el), 100);
                }
            }

            function preserveMath(content) {
                return content
                    .replace(/\$\$(.*?)\$\$/gs, (_, m) => `%%DISPLAY_MATH%%${m}%%END_DISPLAY_MATH%%`)
                    .replace(/\$(.*?)\$/gs, (_, m) => `%%INLINE_MATH%%${m}%%END_INLINE_MATH%%`);
            }

            function restoreMath(html) {
                return html
                    .replace(/%%DISPLAY_MATH%%(.*?)%%END_DISPLAY_MATH%%/gs, (_, m) => `$$${m}$$`)
                    .replace(/%%INLINE_MATH%%(.*?)%%END_INLINE_MATH%%/gs, (_, m) => `$${m}$`);
            }

            function isBalanced(text) {
                return (text.match(/\$\$/g) || []).length % 2 === 0;
            }

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonData = line.substring(6);
                    try {
                        const parsedData = JSON.parse(jsonData);
                        if (parsedData.content) {
                            accumulatedContent += parsedData.content;
                            if (isBalanced(accumulatedContent)) {
                                let raw = preserveMath(accumulatedContent);
                                let html = marked.parse(raw);
                                html = restoreMath(html);
                                resultDiv.innerHTML = html;
                                console.log(html)
                                renderMathIfReady(resultDiv);
                            }
                        }
                        if (parsedData.error) {
                            throw new Error(parsedData.error);
                        }
                    } catch (e) {
                        console.error('Error parsing stream data:', e, jsonData);
                    }
                }
            }
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="error-message">分析失败: ${error.message}</div>`;
        console.error('Image analysis failed:', error);
    } finally {
        // --- 修改开始 ---
        // 请求结束后，只隐藏确认按钮，但保留图片预览和分隔线
        const confirmBtn = document.getElementById('confirm-analysis-btn');
        if (confirmBtn) {
            confirmBtn.style.display = 'none';
        }

        // 清理暂存的图片数据
        stagedImagePayloadForAnalysis = null;
        // --- 修改结束 ---
    }
}

//处理确认截图键之后的事件
async function handleImageAnalysis(payload) {
    if (!currentPaper) {
        showNotification('请先选择并加载一篇论文', 'error');
        return;
    }

    // 暂存收到的图片数据
    stagedImagePayloadForAnalysis = payload;

    // 切换到“图像公式”标签页
    document.querySelectorAll('.viewer-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.viewer-tab-btn[data-target="image-formula-understanding"]').classList.add('active');
    document.querySelectorAll('.viewer-section').forEach(sec => sec.style.display = 'none');
    document.querySelector('.viewer-section[data-section="image-formula-understanding"]').style.display = 'block';

    const analysisContainer = document.getElementById('image-analysis-container');
    analysisContainer.innerHTML = `
    <div class="analysis-preview" style="margin-bottom: 1rem;">
        <h4>待分析对象</h4>
        <p style="font-size: 0.9rem; color: #666;">请确认是否要分析下图（或公式）：</p>
        <img src="data:image/png;base64,${payload.imageData}" alt="Captured from PDF" style="max-width: 100%; border: 1px solid var(--border-color); border-radius: var(--radius-md); margin-top: 0.5rem; background: #fff; padding: 5px;">
        
        <div style="margin-top:1rem;">
            <label for="analysis-type-select" style="font-size:0.95em;">类型：</label>
            <select id="analysis-type-select" style="margin-left:8px;">
                <option value="">请选择类型</option>
                <option value="image">图片</option>
                <option value="table">表格</option>
                <option value="formula">公式</option>
            </select>
        </div>
        <div style="margin-top:1rem;">
            <label for="caption-input" style="font-size:0.95em;">图片/表格/公式说明（可选）：</label>
            <input id="caption-input" type="text" placeholder="如：Figure 2. Loss curve..." style="width:90%;margin-top:3px;">
        </div>
    </div>
    <button id="confirm-analysis-btn" class="btn btn-primary" style="margin-top: 1rem; width: auto;">
        <i class="fas fa-check"></i> 确认分析
    </button>
    <hr style="margin: 1.5rem 0;">
    <div id="analysis-result" class="markdown-body">
         <p class="placeholder">点击“确认分析”后，结果将在此处显示。</p>
    </div>
`;
}

window.addEventListener('beforeunload', () => {
    if (currentPollingPaperId) {
        stopStatusPolling(currentPollingPaperId);
    }
});


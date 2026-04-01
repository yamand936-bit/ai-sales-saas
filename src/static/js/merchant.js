                function toggleSystemAI(storeId, event) {
                    event.preventDefault();
                    fetch(`/merchant/${storeId}/toggle_system_ai`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.AppConfig.csrfToken
                        },
                        body: JSON.stringify({ csrf_token: window.AppConfig.csrfToken })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'success') {
                            const btn = document.getElementById("systemAiToggleBtn");
                            const feedback = document.getElementById("aiFeedbackMsg");
                            if (data.ai_enabled) {
                                btn.className = "text-[10px] font-bold px-4 py-2 rounded shadow-sm border bg-green-100 text-green-700 border-green-200 hover:bg-green-200 transition whitespace-nowrap";
                                btn.innerText = "🟢 AI ON";
                                if (feedback) { feedback.innerText = "AI is now enabled"; feedback.classList.remove("hidden"); setTimeout(() => feedback.classList.add("hidden"), 3000); }
                            } else {
                                btn.className = "text-[10px] font-bold px-4 py-2 rounded shadow-sm border bg-red-100 text-red-700 border-red-200 hover:bg-red-200 transition whitespace-nowrap";
                                btn.innerText = "🔴 AI OFF";
                                if (feedback) { feedback.innerText = "AI is now disabled"; feedback.classList.remove("hidden"); setTimeout(() => feedback.classList.add("hidden"), 3000); }
                            }
                            console.log("TOGGLE AI:", data.ai_enabled);
                        }
                    });
                }
        function switchTab(tabId) {
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('[id^="nav-"]').forEach(el => {
                el.classList.remove('bg-primary', 'text-white');
                el.classList.add('text-slate-300', 'hover:bg-slate-800');
            });
            document.getElementById(`tab-${tabId}`).classList.remove('hidden');
            let navBtn = document.getElementById(`nav-${tabId}`);
            navBtn.classList.remove('text-slate-300', 'hover:bg-slate-800');
            navBtn.classList.add('bg-primary', 'text-white');
        }
        function filterChats() {
            const query = document.getElementById('chatSearch').value.toLowerCase();
            const items = document.querySelectorAll('.chat-item');
            items.forEach(item => {
                const name = item.getAttribute('data-name').toLowerCase();
                const phone = (item.getAttribute('data-phone') || '').toLowerCase();
                const isHuman = item.getAttribute('data-human') === 'true';
                
                let matchesSearch = name.includes(query) || phone.includes(query);
                let matchesFilter = true;
                if (currentStatusFilter === 'human' && !isHuman) matchesFilter = false;
                if (currentStatusFilter === 'ai' && isHuman) matchesFilter = false;
                
                item.style.display = (matchesSearch && matchesFilter) ? 'block' : 'none';
            });
        }
        let sortAsc = false;
        function sortChats() {
            sortAsc = !sortAsc;
            document.getElementById('sortDirection').innerText = sortAsc ? '⬆️' : '⬇️';
            const list = document.getElementById('chatListDOM');
            const items = Array.from(list.querySelectorAll('.chat-item'));
            items.sort((a, b) => {
                const tsA = parseFloat(a.getAttribute('data-timestamp') || 0);
                const tsB = parseFloat(b.getAttribute('data-timestamp') || 0);
                return sortAsc ? tsA - tsB : tsB - tsA;
            });
            items.forEach(item => list.appendChild(item));
        }
        async function openChat(storeId, userId, telegramId, name, requiresHuman) {
            document.getElementById('chatEmptyState').classList.add('hidden');
            document.getElementById('activeChatName').innerText = name;
            
            // Set Form Data
            document.getElementById('activeStoreId').value = storeId;
            document.getElementById('activeTelegramId').value = telegramId;
            
            // Setup AI Toggle Button
            const aiBtn = document.getElementById('aiToggleBtn');
            const toggleForm = document.getElementById('aiToggleForm');
            toggleForm.action = `/merchant/${storeId}/toggle_ai/${userId}`;
            
            if (requiresHuman) {
                document.getElementById('activeChatStatus').innerHTML = '<span class="text-red-500">تدخل بشري معلق 🔴</span>';
                aiBtn.className = "text-xs font-bold px-4 py-2 rounded-lg transition shadow-sm border bg-green-50 text-green-700 border-green-200 hover:bg-green-100";
                aiBtn.innerText = "▶️ تفعيل AI";
            } else {
                document.getElementById('activeChatStatus').innerHTML = '<span class="text-green-600">' + window.AppConfig.translations.ai_active + '</span>';
                aiBtn.className = "text-xs font-bold px-4 py-2 rounded-lg transition shadow-sm border bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100";
                aiBtn.innerText = "⏸️ إيقاف AI مؤقتاً";
            }

            // Fetch Messages via AJAX (Pagination mechanism for limits)
            const canvas = document.getElementById('chatCanvas');
            canvas.innerHTML = '<div class="text-center text-slate-400 mt-10">جاري تحميل الرسائل...</div>';
            
            try {
                const res = await fetch(`/api/merchant/${storeId}/messages/${userId}?page=1`);
                const responsePayload = await res.json();
                
                let msgArray = responsePayload?.data?.messages || responsePayload?.messages || responsePayload?.data || [];
                if (!Array.isArray(msgArray)) msgArray = [];
                
                canvas.innerHTML = '';
                
                msgArray?.forEach(msg => {
                    const isAi = msg?.role === 'assistant';
                    const content = msg?.content || '';
                    const bubble = document.createElement('div');
                    bubble.className = `max-w-[80%] p-4 rounded-xl text-sm shadow-sm relative ${
                        isAi ? 'bg-white border border-slate-100 self-start rounded-tr-none text-slate-800' 
                             : 'bg-primary text-white self-end rounded-tl-none'
                    }`;
                    bubble.innerHTML = `
                        <p class="leading-relaxed whitespace-pre-wrap">${content}</p>
                        <span class="text-[10px] absolute -bottom-4 right-1 opacity-50 text-slate-500">${msg?.time || 'now'}</span>
                    `;
                    canvas.appendChild(bubble);
                });
                
                if(msgArray.length === 0) {
                     canvas.innerHTML = '<div class="text-center text-slate-400 mt-10">لا توجد رسائل سابقة.</div>';
                }
                
                canvas.scrollTop = canvas.scrollHeight;
            } catch(e) {
                canvas.innerHTML = '<div class="text-center text-red-500">حدث خطأ في جلب الشبكة.</div>';
            }
        }
// --- Window Exports ---
window.toggleSystemAI = toggleSystemAI;
window.switchTab = switchTab;
window.filterChats = filterChats;
window.sortChats = sortChats;
window.openChat = openChat;


function parseData(el) {
    return {
        storeId: el.dataset.storeId ? Number(el.dataset.storeId) : null,
        userId: el.dataset.userId ? Number(el.dataset.userId) : null,
        telegramId: el.dataset.telegramId,
        name: el.dataset.name,
        requiresHuman: el.dataset.human === "true",
        tab: el.dataset.tab
    };
}

// --- Event Listeners Mapping ---
function handleAction(el, event) {
    const action = el.dataset.action;
    
    if (!action) {
        console.warn("handleAction called on element with no data-action attribute", el);
        return;
    }

    // Prevent double clicking temporarily
    if (el.hasAttribute('disabled')) return;
    el.setAttribute('disabled', 'true');
    el.style.pointerEvents = 'none';
    setTimeout(() => {
        el.removeAttribute('disabled');
        el.style.pointerEvents = 'auto';
    }, 500);

    const data = parseData(el);

    if (action === "openChat") {
        openChat(
            data.storeId,
            data.userId,
            data.telegramId,
            data.name,
            data.requiresHuman
        );
    }

    if (action === "toggleAI") {
        event.preventDefault();
        toggleSystemAI(data.storeId, event);
    }

    if (action === "switchTab") {
        switchTab(data.tab);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.body.addEventListener("click", (e) => {
        const el = e.target.closest("[data-action]");
        if (!el) return;
        handleAction(el, e);
    });
});



(function () {
    "use strict";

    const state = {
        activeTab: "subscriptions",
        subscriptions: [],
        warranties: [],
        summary: null,
        subStatusFilter: "all",
        subSearch: "",
        warrantyFilter: "all",
        warrantySearch: ""
    };

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content && !meta.content.includes("csrf_token")) {
            return meta.content.trim();
        }
        const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    async function apiRequest(url, options) {
        const opts = Object.assign({ method: "GET", headers: {} }, options || {});
        const csrfToken = getCsrfToken();
        if (csrfToken && opts.method !== "GET") {
            opts.headers["X-CSRF-Token"] = csrfToken;
        }

        const response = await fetch(url, opts);
        let payload = null;
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            payload = await response.json();
        } else {
            const text = await response.text();
            payload = text ? { detail: text } : null;
        }

        if (!response.ok) {
            let message = "Ошибка при выполнении запроса (" + response.status + ")";
            if (payload) {
                if (typeof payload.detail === "string") {
                    message = payload.detail;
                } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
                    message = payload.detail.map(function (err) {
                        return err.msg || JSON.stringify(err);
                    }).join("; ");
                }
            }
            throw new Error(message);
        }

        return payload;
    }

    function showBanner(message, type) {
        const banner = document.getElementById("statusBanner");
        if (!banner) {
            return;
        }
        banner.textContent = String(message || "");
        banner.className = "status-banner " + (type === "error" ? "error" : "info");
        banner.classList.remove("hidden");

        if (banner._hideTimer) {
            clearTimeout(banner._hideTimer);
        }
        banner._hideTimer = setTimeout(function () {
            banner.classList.add("hidden");
        }, 5000);
    }

    function formatMoney(amount, currency) {
        const num = Number(amount || 0);
        const cur = String(currency || "RUB").toUpperCase();
        return num.toFixed(2) + " " + cur;
    }

    function sanitizeHttpUrl(rawUrl) {
        if (!rawUrl || typeof rawUrl !== "string") {
            return null;
        }
        const trimmed = rawUrl.trim();
        if (!trimmed) {
            return null;
        }
        try {
            const parsed = new URL(trimmed);
            if (parsed.protocol === "http:" || parsed.protocol === "https:") {
                return parsed.href;
            }
        } catch (err) {
            return null;
        }
        return null;
    }

    function formatCycleLabel(cycle, cycleDays) {
        if (cycle === "monthly") {
            return "Ежемесячно";
        }
        if (cycle === "yearly") {
            return "Ежегодно";
        }
        if (cycle === "custom_days") {
            return "Каждые " + Number(cycleDays || 30) + " дн.";
        }
        return String(cycle || "-");
    }

    function formatStatusLabel(status) {
        if (status === "active") {
            return "Активна";
        }
        if (status === "paused") {
            return "На паузе";
        }
        if (status === "cancelled") {
            return "Отменена";
        }
        return String(status || "-");
    }

    function formatDaysNote(days) {
        if (days === null || days === undefined) {
            return "";
        }
        const d = Number(days);
        if (Number.isNaN(d)) {
            return "";
        }
        if (d < 0) {
            return "Просрочено на " + Math.abs(d) + " дн.";
        }
        if (d === 0) {
            return "Сегодня";
        }
        if (d === 1) {
            return "Завтра";
        }
        return "Через " + d + " дн.";
    }

    function clearElement(el) {
        while (el.firstChild) {
            el.removeChild(el.firstChild);
        }
    }

    function renderSummary() {
        const s = state.summary || {};
        const monthlyEl = document.getElementById("summaryMonthly");
        const yearlyEl = document.getElementById("summaryYearly");
        const activeSubsEl = document.getElementById("summaryActiveSubs");
        const warrantiesEl = document.getElementById("summaryWarranties");
        const alertsBadge = document.getElementById("alertsCountBadge");
        const alertsEmpty = document.getElementById("alertsEmpty");
        const alertsGrid = document.getElementById("alertsGrid");
        const upcomingSubsList = document.getElementById("upcomingSubsList");
        const expiringWarrantiesList = document.getElementById("expiringWarrantiesList");

        if (monthlyEl) {
            monthlyEl.textContent = formatMoney(s.monthly_total || 0, "RUB");
        }
        if (yearlyEl) {
            yearlyEl.textContent = formatMoney(s.yearly_total || 0, "RUB");
        }
        if (activeSubsEl) {
            activeSubsEl.textContent = String(s.active_subscriptions_count || 0);
        }
        if (warrantiesEl) {
            warrantiesEl.textContent = String(s.warranties_count || 0);
        }

        const upcoming = Array.isArray(s.upcoming_subscriptions) ? s.upcoming_subscriptions : [];
        const expiring = Array.isArray(s.expiring_warranties) ? s.expiring_warranties : [];
        const totalAlerts = typeof s.alerts_count === "number" ? s.alerts_count : (upcoming.length + expiring.length);

        if (alertsBadge) {
            alertsBadge.textContent = String(totalAlerts);
        }

        clearElement(upcomingSubsList);
        clearElement(expiringWarrantiesList);

        if (upcoming.length === 0 && expiring.length === 0) {
            alertsEmpty.classList.remove("hidden");
            alertsGrid.classList.add("hidden");
            return;
        }

        alertsEmpty.classList.add("hidden");
        alertsGrid.classList.remove("hidden");

        if (upcoming.length === 0) {
            const li = document.createElement("li");
            li.className = "alert-item-meta";
            li.textContent = "Нет скорых списаний.";
            upcomingSubsList.appendChild(li);
        } else {
            upcoming.forEach(function (sub) {
                const li = document.createElement("li");
                li.className = "alert-item";

                const left = document.createElement("div");
                const title = document.createElement("div");
                title.className = "alert-item-title";
                title.textContent = sub.name || "Подписка";

                const meta = document.createElement("div");
                meta.className = "alert-item-meta";
                meta.textContent = "Дата: " + (sub.next_billing_date || "-") + " (" + formatDaysNote(sub.days_until_billing) + ")";

                left.appendChild(title);
                left.appendChild(meta);

                const badge = document.createElement("span");
                badge.className = "badge badge-warning";
                badge.textContent = formatMoney(sub.amount, sub.currency);

                li.appendChild(left);
                li.appendChild(badge);
                upcomingSubsList.appendChild(li);
            });
        }

        if (expiring.length === 0) {
            const li = document.createElement("li");
            li.className = "alert-item-meta";
            li.textContent = "Нет истекающих гарантий.";
            expiringWarrantiesList.appendChild(li);
        } else {
            expiring.forEach(function (w) {
                const li = document.createElement("li");
                li.className = "alert-item";

                const left = document.createElement("div");
                const title = document.createElement("div");
                title.className = "alert-item-title";
                title.textContent = w.item_name || "Товар";

                const meta = document.createElement("div");
                meta.className = "alert-item-meta";
                meta.textContent = "До: " + (w.warranty_end_date || "-") + (w.store ? " | " + w.store : "");

                left.appendChild(title);
                left.appendChild(meta);

                const badge = document.createElement("span");
                badge.className = "badge badge-warning";
                badge.textContent = formatDaysNote(w.days_left);

                li.appendChild(left);
                li.appendChild(badge);
                expiringWarrantiesList.appendChild(li);
            });
        }
    }

    function renderSubscriptions() {
        const tbody = document.getElementById("subscriptionsTableBody");
        const emptyState = document.getElementById("subsEmptyState");
        const tableWrap = document.getElementById("subsTableWrap");
        clearElement(tbody);

        const search = state.subSearch.trim().toLowerCase();
        const filtered = state.subscriptions.filter(function (sub) {
            if (state.subStatusFilter !== "all" && sub.status !== state.subStatusFilter) {
                return false;
            }
            if (!search) {
                return true;
            }
            const nameMatch = (sub.name || "").toLowerCase().includes(search);
            const catMatch = (sub.category || "").toLowerCase().includes(search);
            const notesMatch = (sub.notes || "").toLowerCase().includes(search);
            return nameMatch || catMatch || notesMatch;
        });

        if (filtered.length === 0) {
            emptyState.classList.remove("hidden");
            tableWrap.classList.add("hidden");
            return;
        }

        emptyState.classList.add("hidden");
        tableWrap.classList.remove("hidden");

        filtered.forEach(function (sub) {
            const tr = document.createElement("tr");

            const tdInfo = document.createElement("td");
            const nameSpan = document.createElement("span");
            nameSpan.className = "item-primary";
            nameSpan.textContent = sub.name || "-";
            tdInfo.appendChild(nameSpan);

            const catSpan = document.createElement("span");
            catSpan.className = "item-secondary";
            catSpan.textContent = sub.category || "Без категории";
            tdInfo.appendChild(catSpan);

            if (sub.notes) {
                const notesSpan = document.createElement("span");
                notesSpan.className = "item-secondary";
                notesSpan.textContent = sub.notes;
                tdInfo.appendChild(notesSpan);
            }

            const safeUrl = sanitizeHttpUrl(sub.cancel_url);
            if (safeUrl) {
                const cancelLink = document.createElement("a");
                cancelLink.className = "item-link";
                cancelLink.href = safeUrl;
                cancelLink.target = "_blank";
                cancelLink.rel = "noopener noreferrer";
                cancelLink.textContent = "Страница управления подпиской";
                tdInfo.appendChild(cancelLink);
            }

            const tdAmount = document.createElement("td");
            const amountStrong = document.createElement("strong");
            amountStrong.textContent = formatMoney(sub.amount, sub.currency);
            tdAmount.appendChild(amountStrong);

            const tdCycle = document.createElement("td");
            tdCycle.textContent = formatCycleLabel(sub.billing_cycle, sub.cycle_days);

            const tdNext = document.createElement("td");
            const dateSpan = document.createElement("span");
            dateSpan.className = "item-primary";
            dateSpan.textContent = sub.next_billing_date || "-";
            tdNext.appendChild(dateSpan);

            const daysNote = formatDaysNote(sub.days_until_billing);
            if (daysNote && sub.status === "active") {
                const daysSpan = document.createElement("span");
                daysSpan.className = "item-secondary";
                daysSpan.textContent = daysNote + " (напомнить за " + Number(sub.remind_days_before ?? 3) + " дн.)";
                tdNext.appendChild(daysSpan);
            }

            const tdStatus = document.createElement("td");
            const statusBadge = document.createElement("span");
            let badgeClass = "badge-neutral";
            if (sub.status === "active") {
                badgeClass = "badge-active";
            } else if (sub.status === "cancelled") {
                badgeClass = "badge-cancelled";
            } else if (sub.status === "paused") {
                badgeClass = "badge-paused";
            }
            statusBadge.className = "badge " + badgeClass;
            statusBadge.textContent = formatStatusLabel(sub.status);
            tdStatus.appendChild(statusBadge);

            const tdActions = document.createElement("td");
            const actionsWrap = document.createElement("div");
            actionsWrap.className = "action-group";

            const btnAdvance = document.createElement("button");
            btnAdvance.type = "button";
            btnAdvance.className = "btn btn-secondary btn-sm";
            btnAdvance.textContent = "Продлить период";
            btnAdvance.addEventListener("click", function () {
                handleAdvanceSubscription(sub.id);
            });
            actionsWrap.appendChild(btnAdvance);

            if (sub.status !== "active") {
                const btnActivate = document.createElement("button");
                btnActivate.type = "button";
                btnActivate.className = "btn btn-outline btn-sm";
                btnActivate.textContent = "Активировать";
                btnActivate.addEventListener("click", function () {
                    handleChangeSubscriptionStatus(sub.id, "active");
                });
                actionsWrap.appendChild(btnActivate);
            }

            if (sub.status === "active") {
                const btnPause = document.createElement("button");
                btnPause.type = "button";
                btnPause.className = "btn btn-outline btn-sm";
                btnPause.textContent = "Пауза";
                btnPause.addEventListener("click", function () {
                    handleChangeSubscriptionStatus(sub.id, "paused");
                });
                actionsWrap.appendChild(btnPause);
            }

            if (sub.status !== "cancelled") {
                const btnCancel = document.createElement("button");
                btnCancel.type = "button";
                btnCancel.className = "btn btn-outline btn-sm";
                btnCancel.textContent = "Отменить";
                btnCancel.addEventListener("click", function () {
                    handleChangeSubscriptionStatus(sub.id, "cancelled");
                });
                actionsWrap.appendChild(btnCancel);
            }

            const btnDelete = document.createElement("button");
            btnDelete.type = "button";
            btnDelete.className = "btn btn-danger btn-sm";
            btnDelete.textContent = "Удалить";
            btnDelete.addEventListener("click", function () {
                handleDeleteSubscription(sub.id, sub.name);
            });
            actionsWrap.appendChild(btnDelete);

            tdActions.appendChild(actionsWrap);

            tr.appendChild(tdInfo);
            tr.appendChild(tdAmount);
            tr.appendChild(tdCycle);
            tr.appendChild(tdNext);
            tr.appendChild(tdStatus);
            tr.appendChild(tdActions);

            tbody.appendChild(tr);
        });
    }

    function renderWarranties() {
        const tbody = document.getElementById("warrantiesTableBody");
        const emptyState = document.getElementById("warrantiesEmptyState");
        const tableWrap = document.getElementById("warrantiesTableWrap");
        clearElement(tbody);

        const search = state.warrantySearch.trim().toLowerCase();
        const filtered = state.warranties.filter(function (w) {
            if (state.warrantyFilter === "active" && w.is_expired) {
                return false;
            }
            if (state.warrantyFilter === "expired" && !w.is_expired) {
                return false;
            }
            if (!search) {
                return true;
            }
            const nameMatch = (w.item_name || "").toLowerCase().includes(search);
            const storeMatch = (w.store || "").toLowerCase().includes(search);
            const serialMatch = (w.serial_number || "").toLowerCase().includes(search);
            return nameMatch || storeMatch || serialMatch;
        });

        if (filtered.length === 0) {
            emptyState.classList.remove("hidden");
            tableWrap.classList.add("hidden");
            return;
        }

        emptyState.classList.add("hidden");
        tableWrap.classList.remove("hidden");

        filtered.forEach(function (w) {
            const tr = document.createElement("tr");

            const tdItem = document.createElement("td");
            const itemSpan = document.createElement("span");
            itemSpan.className = "item-primary";
            itemSpan.textContent = w.item_name || "-";
            tdItem.appendChild(itemSpan);

            const storeSpan = document.createElement("span");
            storeSpan.className = "item-secondary";
            storeSpan.textContent = w.store ? "Магазин: " + w.store : "Магазин не указан";
            tdItem.appendChild(storeSpan);

            if (w.notes) {
                const notesSpan = document.createElement("span");
                notesSpan.className = "item-secondary";
                notesSpan.textContent = w.notes;
                tdItem.appendChild(notesSpan);
            }

            const tdPurchase = document.createElement("td");
            tdPurchase.textContent = w.purchase_date || "-";

            const tdEnd = document.createElement("td");
            const endSpan = document.createElement("span");
            endSpan.className = "item-primary";
            endSpan.textContent = w.warranty_end_date || "-";
            tdEnd.appendChild(endSpan);

            const statusBadge = document.createElement("span");
            if (w.is_expired || (typeof w.days_left === "number" && w.days_left < 0)) {
                statusBadge.className = "badge badge-expired";
                statusBadge.textContent = "Гарантия истекла";
            } else if (typeof w.days_left === "number" && w.days_left <= Number(w.remind_days_before ?? 14)) {
                statusBadge.className = "badge badge-warning";
                statusBadge.textContent = "Осталось " + w.days_left + " дн.";
            } else {
                statusBadge.className = "badge badge-ok";
                statusBadge.textContent = typeof w.days_left === "number" ? ("Осталось " + w.days_left + " дн.") : "Действует";
            }
            tdEnd.appendChild(statusBadge);

            const tdPrice = document.createElement("td");
            tdPrice.textContent = formatMoney(w.price || 0, w.currency || "RUB");

            const tdSerial = document.createElement("td");
            tdSerial.textContent = w.serial_number || "-";

            const tdReceipt = document.createElement("td");
            if (w.receipt_filename) {
                const link = document.createElement("a");
                link.className = "btn btn-outline btn-sm";
                link.href = "/api/warranties/" + encodeURIComponent(String(w.id)) + "/receipt";
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = w.receipt_original_name || "Открыть чек";
                tdReceipt.appendChild(link);
            } else {
                const noFile = document.createElement("span");
                noFile.className = "item-secondary";
                noFile.textContent = "Без файла";
                tdReceipt.appendChild(noFile);
            }

            const tdActions = document.createElement("td");
            const btnDelete = document.createElement("button");
            btnDelete.type = "button";
            btnDelete.className = "btn btn-danger btn-sm";
            btnDelete.textContent = "Удалить";
            btnDelete.addEventListener("click", function () {
                handleDeleteWarranty(w.id, w.item_name);
            });
            tdActions.appendChild(btnDelete);

            tr.appendChild(tdItem);
            tr.appendChild(tdPurchase);
            tr.appendChild(tdEnd);
            tr.appendChild(tdPrice);
            tr.appendChild(tdSerial);
            tr.appendChild(tdReceipt);
            tr.appendChild(tdActions);

            tbody.appendChild(tr);
        });
    }

    async function loadAllData() {
        try {
            const subUrl = state.subStatusFilter !== "all"
                ? "/api/subscriptions?status=" + encodeURIComponent(state.subStatusFilter)
                : "/api/subscriptions";

            const results = await Promise.all([
                apiRequest("/api/summary"),
                apiRequest(subUrl),
                apiRequest("/api/warranties")
            ]);

            state.summary = results[0] || {};
            state.subscriptions = Array.isArray(results[1]) ? results[1] : [];
            state.warranties = Array.isArray(results[2]) ? results[2] : [];

            renderSummary();
            renderSubscriptions();
            renderWarranties();
        } catch (err) {
            showBanner(err.message || "Не удалось загрузить данные с сервера", "error");
        }
    }

    async function handleAdvanceSubscription(id) {
        try {
            await apiRequest("/api/subscriptions/" + encodeURIComponent(String(id)) + "/advance", {
                method: "POST"
            });
            showBanner("Дата следующего списания сдвинута на новый период.", "info");
            await loadAllData();
        } catch (err) {
            showBanner(err.message, "error");
        }
    }

    async function handleChangeSubscriptionStatus(id, newStatus) {
        try {
            await apiRequest("/api/subscriptions/" + encodeURIComponent(String(id)) + "/status", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: newStatus })
            });
            showBanner("Статус подписки обновлен.", "info");
            await loadAllData();
        } catch (err) {
            showBanner(err.message, "error");
        }
    }

    async function handleDeleteSubscription(id, name) {
        if (!window.confirm("Удалить подписку «" + (name || "") + "»?")) {
            return;
        }
        try {
            await apiRequest("/api/subscriptions/" + encodeURIComponent(String(id)), {
                method: "DELETE"
            });
            showBanner("Подписка удалена.", "info");
            await loadAllData();
        } catch (err) {
            showBanner(err.message, "error");
        }
    }

    async function handleDeleteWarranty(id, itemName) {
        if (!window.confirm("Удалить гарантию на «" + (itemName || "") + "» и прикрепленный чек?")) {
            return;
        }
        try {
            await apiRequest("/api/warranties/" + encodeURIComponent(String(id)), {
                method: "DELETE"
            });
            showBanner("Гарантийная запись удалена.", "info");
            await loadAllData();
        } catch (err) {
            showBanner(err.message, "error");
        }
    }

    async function handleCheckNotifications() {
        try {
            const result = await apiRequest("/api/notifications/check", {
                method: "POST"
            });
            let count = 0;
            if (result && typeof result.alerts_count === "number") {
                count = result.alerts_count;
            } else if (result && typeof result.triggered_count === "number") {
                count = result.triggered_count;
            } else if (result && Array.isArray(result.notifications)) {
                count = result.notifications.length;
            } else if (result && Array.isArray(result.alerts)) {
                count = result.alerts.length;
            }
            showBanner("Проверка напоминаний выполнена. Активных уведомлений: " + count + ".", "info");
            await loadAllData();
        } catch (err) {
            showBanner(err.message, "error");
        }
    }

    function setDefaultFormDates() {
        const today = new Date().toISOString().slice(0, 10);
        const nextYearDate = new Date();
        nextYearDate.setFullYear(nextYearDate.getFullYear() + 1);
        const nextYear = nextYearDate.toISOString().slice(0, 10);

        const subNextDate = document.getElementById("subNextDate");
        if (subNextDate && !subNextDate.value) {
            subNextDate.value = today;
        }
        const warPurchaseDate = document.getElementById("warPurchaseDate");
        if (warPurchaseDate && !warPurchaseDate.value) {
            warPurchaseDate.value = today;
        }
        const warEndDate = document.getElementById("warEndDate");
        if (warEndDate && !warEndDate.value) {
            warEndDate.value = nextYear;
        }
    }

    function switchTab(tabName) {
        state.activeTab = tabName;
        const tabSubs = document.getElementById("tabBtnSubscriptions");
        const tabWarranties = document.getElementById("tabBtnWarranties");
        const panelSubs = document.getElementById("tabPanelSubscriptions");
        const panelWarranties = document.getElementById("tabPanelWarranties");
        const btnOpenSub = document.getElementById("btnOpenSubModal");
        const btnOpenWarranty = document.getElementById("btnOpenWarrantyModal");

        if (tabName === "subscriptions") {
            tabSubs.classList.add("active");
            tabSubs.setAttribute("aria-selected", "true");
            tabWarranties.classList.remove("active");
            tabWarranties.setAttribute("aria-selected", "false");
            panelSubs.classList.remove("hidden");
            panelWarranties.classList.add("hidden");
            btnOpenSub.classList.remove("hidden");
            btnOpenWarranty.classList.add("hidden");
        } else {
            tabWarranties.classList.add("active");
            tabWarranties.setAttribute("aria-selected", "true");
            tabSubs.classList.remove("active");
            tabSubs.setAttribute("aria-selected", "false");
            panelWarranties.classList.remove("hidden");
            panelSubs.classList.add("hidden");
            btnOpenWarranty.classList.remove("hidden");
            btnOpenSub.classList.add("hidden");
        }
    }

    function initTheme() {
        const saved = localStorage.getItem("swt_theme") || "light";
        applyTheme(saved);
        const btn = document.getElementById("btnToggleTheme");
        if (btn) {
            btn.addEventListener("click", function () {
                const current = document.documentElement.getAttribute("data-theme") || "light";
                const next = current === "dark" ? "light" : "dark";
                applyTheme(next);
                localStorage.setItem("swt_theme", next);
            });
        }
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        const btn = document.getElementById("btnToggleTheme");
        if (btn) {
            btn.textContent = theme === "dark" ? "Светлая тема" : "Темная тема";
        }
    }

    function initEvents() {
        document.getElementById("tabBtnSubscriptions").addEventListener("click", function () {
            switchTab("subscriptions");
        });
        document.getElementById("tabBtnWarranties").addEventListener("click", function () {
            switchTab("warranties");
        });

        document.getElementById("btnCheckNotifications").addEventListener("click", handleCheckNotifications);

        const subStatusFilter = document.getElementById("subStatusFilter");
        subStatusFilter.addEventListener("change", function () {
            state.subStatusFilter = subStatusFilter.value;
            loadAllData();
        });

        const subSearchInput = document.getElementById("subSearchInput");
        subSearchInput.addEventListener("input", function () {
            state.subSearch = subSearchInput.value;
            renderSubscriptions();
        });

        const warrantyFilter = document.getElementById("warrantyFilter");
        warrantyFilter.addEventListener("change", function () {
            state.warrantyFilter = warrantyFilter.value;
            renderWarranties();
        });

        const warrantySearchInput = document.getElementById("warrantySearchInput");
        warrantySearchInput.addEventListener("input", function () {
            state.warrantySearch = warrantySearchInput.value;
            renderWarranties();
        });

        const modalSub = document.getElementById("modalSubscription");
        const formSub = document.getElementById("formSubscription");
        const subCycle = document.getElementById("subCycle");
        const subCycleDaysWrap = document.getElementById("subCycleDaysWrap");

        subCycle.addEventListener("change", function () {
            if (subCycle.value === "custom_days") {
                subCycleDaysWrap.classList.remove("hidden");
            } else {
                subCycleDaysWrap.classList.add("hidden");
            }
        });

        function openSubModal() {
            formSub.reset();
            subCycleDaysWrap.classList.add("hidden");
            setDefaultFormDates();
            modalSub.classList.remove("hidden");
        }

        function closeSubModal() {
            modalSub.classList.add("hidden");
        }

        document.getElementById("btnOpenSubModal").addEventListener("click", openSubModal);
        document.getElementById("btnCloseSubModal").addEventListener("click", closeSubModal);
        document.getElementById("btnCancelSubModal").addEventListener("click", closeSubModal);

        formSub.addEventListener("submit", async function (e) {
            e.preventDefault();
            const rawCancelUrl = document.getElementById("subCancelUrl").value.trim();
            if (rawCancelUrl && !sanitizeHttpUrl(rawCancelUrl)) {
                showBanner("Ссылка на отмену должна начинаться с http:// или https://", "error");
                return;
            }

            const billingCycle = document.getElementById("subCycle").value;
            const cycleDaysVal = document.getElementById("subCycleDays").value;

            const payload = {
                name: document.getElementById("subName").value.trim(),
                category: document.getElementById("subCategory").value.trim() || "Цифровые сервисы",
                amount: Number(document.getElementById("subAmount").value),
                currency: document.getElementById("subCurrency").value,
                billing_cycle: billingCycle,
                cycle_days: billingCycle === "custom_days" ? Number(cycleDaysVal || 30) : null,
                next_billing_date: document.getElementById("subNextDate").value,
                remind_days_before: Number(document.getElementById("subRemindDays").value || 3),
                status: document.getElementById("subStatus").value,
                cancel_url: rawCancelUrl ? rawCancelUrl : null,
                notes: document.getElementById("subNotes").value.trim() || null
            };

            try {
                await apiRequest("/api/subscriptions", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                closeSubModal();
                showBanner("Подписка добавлена.", "info");
                await loadAllData();
            } catch (err) {
                showBanner(err.message, "error");
            }
        });

        const modalWarranty = document.getElementById("modalWarranty");
        const formWarranty = document.getElementById("formWarranty");

        function openWarrantyModal() {
            formWarranty.reset();
            setDefaultFormDates();
            modalWarranty.classList.remove("hidden");
        }

        function closeWarrantyModal() {
            modalWarranty.classList.add("hidden");
        }

        document.getElementById("btnOpenWarrantyModal").addEventListener("click", openWarrantyModal);
        document.getElementById("btnCloseWarrantyModal").addEventListener("click", closeWarrantyModal);
        document.getElementById("btnCancelWarrantyModal").addEventListener("click", closeWarrantyModal);

        formWarranty.addEventListener("submit", async function (e) {
            e.preventDefault();
            const formData = new FormData(formWarranty);
            const fileInput = document.getElementById("warReceipt");
            if (!fileInput.files || fileInput.files.length === 0) {
                formData.delete("receipt");
            }

            try {
                await apiRequest("/api/warranties", {
                    method: "POST",
                    body: formData
                });
                closeWarrantyModal();
                showBanner("Гарантия сохранена.", "info");
                await loadAllData();
            } catch (err) {
                showBanner(err.message, "error");
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initTheme();
        initEvents();
        setDefaultFormDates();
        loadAllData();
    });
})();

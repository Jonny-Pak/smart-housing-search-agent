<script setup>
import { ref, nextTick, computed, onMounted } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix default Leaflet icon paths when using Vite/bundlers
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({ iconRetinaUrl, iconUrl, shadowUrl })

// ─── i18n / Language Toggle ───────────────────────────────────────────────────
const currentLang = ref('vi')
const toggleLanguage = () => {
  const oldLang = currentLang.value
  const newLang = oldLang === 'vi' ? 'en' : 'vi'
  currentLang.value = newLang

  const defaultTitles = [translations.vi.newSessionDefault, translations.en.newSessionDefault, translations.vi.newChat, translations.en.newChat, 'Chat mới', 'New chat', 'Cuộc trò chuyện mới', 'New Conversation']
  if (sessions.value) {
    sessions.value.forEach(s => {
      if (defaultTitles.includes(s.title)) {
        s.title = translations[newLang].newSessionDefault
      }
    })
  }

  if (sessionMessages.value) {
    Object.values(sessionMessages.value).forEach(msgs => {
      if (msgs && msgs.length > 0) {
        const firstMsg = msgs[0]
        if (firstMsg.role === 'ai' && (firstMsg.content === translations.vi.welcomeMsg || firstMsg.content === translations.en.welcomeMsg)) {
          firstMsg.content = translations[newLang].welcomeMsg
        }
      }
    })
  }
}

const translations = {
  vi: {
    newChat: 'Cuộc trò chuyện mới',
    chatHistory: 'Lịch sử chat',
    placeholder: 'Nhập yêu cầu tìm kiếm phòng trọ...',
    sendBtn: 'Gửi',
    systemTitle: 'SmartHousing in Viet Nam',
    systemSubtitle: 'Nền tảng Tìm kiếm Bất động sản thông minh bằng AI & GIS tại Việt Nam',
    welcomeMsg: 'Xin chào! Chào mừng bạn đến với SmartHousing - Nền tảng Bất động sản AI thông minh tại Việt Nam. Tôi có thể giúp bạn tìm kiếm phòng trọ, nhà nguyên căn theo vị trí GIS hoặc hỗ trợ bạn đăng tin cho thuê một cách dễ dàng. Bạn cần tôi giúp gì hôm nay?',
    loading: 'Đang phân tích & tính toán GIS...',
    price: 'Mức giá',
    address: 'Địa chỉ cụ thể',
    phone: 'Số điện thoại',
    distance: 'Khoảng cách',
    coordinates: 'Tọa độ GIS',
    noPhone: 'Đang cập nhật',
    newSessionDefault: 'Chat mới',
    justNow: 'Vừa xong',
    successPost: 'Đăng tin thành công!',
  },
  en: {
    newChat: 'New Conversation',
    chatHistory: 'Chat History',
    placeholder: 'Type your rental request...',
    sendBtn: 'Send',
    systemTitle: 'SmartHousing in Vietnam',
    systemSubtitle: 'Intelligent AI & GIS Real Estate Platform in Vietnam',
    welcomeMsg: 'Hello! Welcome to SmartHousing - The Premier AI Real Estate Platform in Vietnam. I can help you find rental rooms or houses by GIS coordinates, or assist you in posting property listings easily. How can I help you today?',
    loading: 'Analyzing & computing GIS...',
    price: 'Price',
    address: 'Address',
    phone: 'Phone Number',
    distance: 'Distance',
    coordinates: 'GIS Coordinates',
    noPhone: 'Not available',
    newSessionDefault: 'New chat',
    justNow: 'Just now',
    successPost: 'Listing posted!',
  }
}
const t = computed(() => translations[currentLang.value])

const isSidebarOpen = ref(false)

// ─── Session Management ───────────────────────────────────────────────────────
const makeWelcomeMsg = () => ({ role: 'ai', type: 'text', content: translations[currentLang.value].welcomeMsg })

const sessions = ref([
  { id: 'session-' + Date.now() + '-' + Math.floor(Math.random() * 1000), title: translations[currentLang.value].newSessionDefault, timestamp: new Date() }
])
const currentSessionId = ref(sessions.value[0].id)
const createdSessions = ref(new Set())

// Per-session messages store: sessionId -> messages[]
const sessionMessages = ref({
  [sessions.value[0].id]: [makeWelcomeMsg()]
})

const messages = computed(() => sessionMessages.value[currentSessionId.value] || [])

const createNewSession = async () => {
  isSidebarOpen.value = false
  const newId = 'session-' + Date.now() + '-' + Math.floor(Math.random() * 1000)
  sessions.value.unshift({ id: newId, title: t.value.newSessionDefault, timestamp: new Date() })
  currentSessionId.value = newId
  sessionMessages.value[newId] = [makeWelcomeMsg()]
  // Cleanup old maps
  Object.values(mapInstances.value).forEach(m => m && m.remove())
  mapInstances.value = {}
  userQuery.value = ''
  lastQuery.value = ''
  await nextTick()
  scrollToBottom()
}

const selectSession = async (id) => {
  isSidebarOpen.value = false
  if (currentSessionId.value === id) return
  Object.values(mapInstances.value).forEach(m => m && m.remove())
  mapInstances.value = {}
  currentSessionId.value = id
  userQuery.value = ''
  await nextTick()
  // Re-init maps for any MapCard messages in this session
  const msgs = sessionMessages.value[id] || []
  msgs.forEach(msg => {
    if (msg.type === 'room-card' && msg.ui_type === 'A2UI_MapCard') initMap(msg)
  })
  scrollToBottom()
}

const formatSessionTime = (timestamp) => {
  const now = new Date()
  const diff = now - timestamp
  if (diff < 60000) return t.value.justNow
  if (diff < 3600000) return `${Math.floor(diff / 60000)}${currentLang.value === 'vi' ? ' phút trước' : 'm ago'}`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}${currentLang.value === 'vi' ? ' giờ trước' : 'h ago'}`
  return timestamp.toLocaleDateString(currentLang.value === 'vi' ? 'vi-VN' : 'en-US')
}

// ─── Leaflet Map ──────────────────────────────────────────────────────────────
const mapInstances = ref({})
const lastQuery = ref('')

const cleanPriceDisplay = (val) => {
  if (val == null) return currentLang.value === 'vi' ? 'Đang cập nhật' : 'Updating'
  const str = String(val).replace(/VND|\s|₫/gi, '').replace(/,/g, '')
  const num = Number(str)
  if (isNaN(num)) return val
  return num.toLocaleString(currentLang.value === 'vi' ? 'vi-VN' : 'en-US') + ' VND'
}

const initMap = async (item) => {
  await nextTick()
  const mapId = 'map-' + item.data.id
  const mapEl = document.getElementById(mapId)
  if (!mapEl) return
  if (mapInstances.value[mapId]) mapInstances.value[mapId].remove()

  const { lat, lng, title, address } = item.data
  if (!lat || !lng) return

  const map = L.map(mapId).setView([lat, lng], 15)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
  }).addTo(map)

  L.marker([lat, lng])
    .addTo(map)
    .bindPopup(`<b>🏠 ${title || address}</b><br>${cleanPriceDisplay(item.data.price)}`)
    .openPopup()

  // Detect landmark for radius visualization
  let centerLat = null, centerLng = null, centerName = ''
  const q = lastQuery.value
  const isVI = currentLang.value === 'vi'
  if (q.includes('tài nguyên') || q.includes('tn&mt') || q.includes('tnmt') || q.includes('hcmunre') || q.includes('natural resources')) {
    centerLat = 10.8205; centerLng = 106.6880
    centerName = isVI ? '🏛️ ĐH Tài nguyên & Môi trường TP.HCM' : '🏛️ HCMC Univ. of Natural Resources'
  } else if (q.includes('công nghiệp') || q.includes('nguyễn văn bảo') || q.includes('nguyen van bao') || q.includes('iuh') || q.includes('industry')) {
    centerLat = 10.8198; centerLng = 106.6876
    centerName = isVI ? '🏛️ ĐH Công nghiệp TP.HCM' : '🏛️ HCMC Univ. of Industry'
  }

  if (centerLat && centerLng) {
    let radiusMeters = 3000
    const kmMatch = q.match(/(\d+(?:\.\d+)?)\s*km/)
    if (kmMatch) radiusMeters = parseFloat(kmMatch[1]) * 1000
    else {
      const mMatch = q.match(/(\d+)\s*(?:mét|meters?|m\b)/)
      if (mMatch && parseInt(mMatch[1]) > 100) radiusMeters = parseInt(mMatch[1])
    }
    L.circle([centerLat, centerLng], { radius: radiusMeters, color: '#ef4444', weight: 2, dashArray: '6,6', fillColor: '#f87171', fillOpacity: 0.12 }).addTo(map)
    L.circleMarker([centerLat, centerLng], { radius: 8, fillColor: '#2563eb', color: '#fff', weight: 2, fillOpacity: 1 }).addTo(map).bindPopup(`<b>${centerName}</b><br>r = ${radiusMeters / 1000}km`)
    L.polyline([[centerLat, centerLng], [lat, lng]], { color: '#f97316', weight: 2, dashArray: '4,4' }).addTo(map)
    map.fitBounds(L.latLngBounds([[centerLat, centerLng], [lat, lng]]), { padding: [30, 30], maxZoom: 16 })
  }
  mapInstances.value[mapId] = map
  setTimeout(() => { if (mapInstances.value[mapId]) mapInstances.value[mapId].invalidateSize() }, 250)
  setTimeout(() => { if (mapInstances.value[mapId]) mapInstances.value[mapId].invalidateSize() }, 600)
}

// ─── Chat State ───────────────────────────────────────────────────────────────
const userQuery = ref('')
const isSearching = ref(false)
const chatBoxRef = ref(null)
const currentFilter = ref('all') // 'all', 'nha_nguyen_can', 'phong_tro'

const selectFilter = (type) => {
  currentFilter.value = type
  if (!userQuery.value.trim() && !isSearching.value) {
    const promptText = type === 'nha_nguyen_can'
      ? (currentLang.value === 'vi' ? 'Tìm nhà nguyên căn cho thuê' : 'Find houses for rent')
      : type === 'phong_tro'
      ? (currentLang.value === 'vi' ? 'Tìm phòng trọ cho thuê' : 'Find rooms for rent')
      : (currentLang.value === 'vi' ? 'Tìm tất cả phòng trọ và nhà nguyên căn' : 'Find all rental properties')
    userQuery.value = promptText
    handleSearch()
  }
}

const triggerBudgetSearch = (maxPrice) => {
  if (!maxPrice) return
  const promptText = currentLang.value === 'vi'
    ? `Tìm phòng trọ có giá thuê dưới ${maxPrice} VND`
    : `Find rooms for rent under ${maxPrice} VND`
  userQuery.value = promptText
  handleSearch()
}

const userLocation = ref({ lat: null, lng: null })
const isLocating = ref(false)

const getUserLocation = () => {
  if (!navigator.geolocation) {
    console.warn('Geolocation is not supported by your browser.')
    return
  }
  isLocating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLocation.value = {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude
      }
      isLocating.value = false
    },
    (err) => {
      console.warn('Geolocation error:', err)
      isLocating.value = false
    },
    { enableHighAccuracy: true, timeout: 10000 }
  )
}

onMounted(() => {
  getUserLocation()
})


const scrollToBottom = () => {
  nextTick(() => {
    if (chatBoxRef.value) chatBoxRef.value.scrollTop = chatBoxRef.value.scrollHeight
  })
}

const pushMessage = (msg) => {
  const id = currentSessionId.value
  if (!sessionMessages.value[id]) sessionMessages.value[id] = []
  sessionMessages.value[id].push(msg)
  scrollToBottom()
}

// ─── Search / API Handler ─────────────────────────────────────────────────────
const handleSearch = async () => {
  if (!userQuery.value.trim() || isSearching.value) return

  const queryText = userQuery.value.trim()
  lastQuery.value = queryText.toLowerCase()
  userQuery.value = ''

  // Auto-rename session title from first message
  const currentSession = sessions.value.find(s => s.id === currentSessionId.value)
  const defaultTitles = ['Chat mới', 'New chat', 'Cuộc trò chuyện mới', 'New conversation']
  if (currentSession && defaultTitles.includes(currentSession.title)) {
    currentSession.title = queryText.length > 28 ? queryText.substring(0, 28) + '...' : queryText
  }

  // 1. Append user message to chat
  pushMessage({ role: 'user', type: 'text', content: queryText })
  isSearching.value = true

  const activeSessionId = currentSessionId.value

  try {
    // Create backend session if needed
    if (!createdSessions.value.has(activeSessionId)) {
      try {
        await fetch(`/apps/app/users/thuan-dev-user/sessions/${activeSessionId}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
        })
        createdSessions.value.add(activeSessionId)
      } catch (e) { console.log('Session init:', e) }
    }

    let queryToSend = queryText
    if (currentFilter.value === 'nha_nguyen_can' && !queryToSend.toLowerCase().includes('nhà')) {
      queryToSend += (currentLang.value === 'vi' ? ' [Yêu cầu ưu tiên lọc property_type: nha_nguyen_can (nhà nguyên căn)]' : ' [Filter property_type: nha_nguyen_can (house)]')
    } else if (currentFilter.value === 'phong_tro' && !queryToSend.toLowerCase().includes('phòng') && !queryToSend.toLowerCase().includes('trọ')) {
      queryToSend += (currentLang.value === 'vi' ? ' [Yêu cầu ưu tiên lọc property_type: phong_tro (phòng trọ)]' : ' [Filter property_type: phong_tro (room)]')
    }

    if (userLocation.value.lat !== null && userLocation.value.lng !== null) {
      queryToSend += ` [Vị trí người dùng / User Location payload: lat=${userLocation.value.lat}, lng=${userLocation.value.lng}]`
    }

    let rawTextBuffer = ''
    let resultCommitted = false

    await fetchEventSource('/run_sse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        appName: 'app', userId: 'thuan-dev-user', sessionId: activeSessionId,
        newMessage: { role: 'user', parts: [{ text: queryToSend }] },
        location: userLocation.value,
        streaming: true
      }),
      openWhenHidden: true,
      onmessage(event) {
        if (!event.data || resultCommitted) return
        try {
          const parsed = JSON.parse(event.data)
          if (parsed.author === 'query_classifier') return

          let foundCards = null

          if (parsed.output && Array.isArray(parsed.output)) {
            foundCards = parsed.output
          } else if (parsed.node_output && Array.isArray(parsed.node_output)) {
            foundCards = parsed.node_output
          } else if (Array.isArray(parsed)) {
            foundCards = parsed
          } else if (parsed.content?.parts?.[0]?.text) {
            const chunkText = parsed.content.parts[0].text
            if (parsed.partial === false || chunkText.startsWith(rawTextBuffer) || (chunkText.length >= rawTextBuffer.length && chunkText.includes(rawTextBuffer))) {
              rawTextBuffer = chunkText
            } else if (!rawTextBuffer.includes(chunkText)) {
              rawTextBuffer += chunkText
            }

            // Robust JSON bracket balancing parser
            let brackets = 0
            let startIdx = -1
            for (let i = 0; i < rawTextBuffer.length; i++) {
              if (rawTextBuffer[i] === '[') {
                if (brackets === 0) startIdx = i
                brackets++
              } else if (rawTextBuffer[i] === ']') {
                brackets--
                if (brackets === 0 && startIdx !== -1) {
                  try {
                    const inner = JSON.parse(rawTextBuffer.substring(startIdx, i + 1))
                    if (Array.isArray(inner) && inner[0]?.ui_type) {
                      foundCards = inner
                      break
                    }
                  } catch (_) {}
                  startIdx = -1
                }
              }
            }
          }

          if (foundCards && foundCards.length > 0 && foundCards[0].ui_type) {
            resultCommitted = true
            isSearching.value = false
            const firstBracketIdx = rawTextBuffer.indexOf('[')
            if (firstBracketIdx > 0) {
              const introText = rawTextBuffer.substring(0, firstBracketIdx).replace(/```json/g, '').replace(/```/g, '').trim()
              if (introText) {
                pushMessage({ role: 'ai', type: 'text', content: introText })
              }
            }
            foundCards.forEach(item => {
              if (item.ui_type === 'A2UI_Card' && item.data?.lat != null && item.data?.lng != null) {
                item.ui_type = 'A2UI_MapCard'
              }
              pushMessage({ role: 'ai', type: 'room-card', ui_type: item.ui_type, data: item.data })
            })
            // Init Leaflet maps after DOM renders
            nextTick(() => {
              foundCards.forEach(item => { if (item.ui_type === 'A2UI_MapCard') initMap(item) })
            })
          }
        } catch (_) { /* skip non-JSON */ }
      },
      onclose() {
        isSearching.value = false
        // If nothing structured came back but we have raw text, show it
        if (!resultCommitted && rawTextBuffer.trim()) {
          // Last chance check if there's a valid JSON array inside
          try {
            const first = rawTextBuffer.indexOf('[')
            const last = rawTextBuffer.lastIndexOf(']')
            if (first !== -1 && last > first) {
              const inner = JSON.parse(rawTextBuffer.substring(first, last + 1))
              if (Array.isArray(inner) && inner[0]?.ui_type) {
                resultCommitted = true
                if (first > 0) {
                  const introText = rawTextBuffer.substring(0, first).replace(/```json/g, '').replace(/```/g, '').trim()
                  if (introText) pushMessage({ role: 'ai', type: 'text', content: introText })
                }
                inner.forEach(item => {
                  if (item.ui_type === 'A2UI_Card' && item.data?.lat != null && item.data?.lng != null) {
                    item.ui_type = 'A2UI_MapCard'
                  }
                  pushMessage({ role: 'ai', type: 'room-card', ui_type: item.ui_type, data: item.data })
                })
                nextTick(() => inner.forEach(item => { if (item.ui_type === 'A2UI_MapCard') initMap(item) }))
                return
              }
            }
          } catch (_) {}

          let cleaned = rawTextBuffer.replace(/\{.*?\}/gs, '').replace(/\[\s*\]/g, '').trim()
          cleaned = cleaned.replace(/^\[|\]$/g, '').trim()
          if (cleaned) {
            const sentences = cleaned.split(/(?<=[.!?])\s+/)
            cleaned = [...new Set(sentences)].join(' ').trim()
            pushMessage({ role: 'ai', type: 'text', content: cleaned })
          }
        }
      },
      onerror(err) {
        console.error('AI error:', err)
        isSearching.value = false
        throw err
      }
    })
  } catch (err) {
    console.error('API failed:', err)
    isSearching.value = false
  }
}
</script>

<template>
  <div class="chat-app-container">

    <!-- Mobile Sidebar Backdrop Overlay -->
    <div v-if="isSidebarOpen" class="sidebar-backdrop" @click="isSidebarOpen = false"></div>

    <!-- ═══ SIDEBAR ═══ -->
    <aside :class="['sidebar', { 'sidebar-open': isSidebarOpen }]">
      <div class="sidebar-brand">
        <i class="fa-solid fa-building-shield brand-icon"></i>
        <span class="brand-name">{{ t.systemTitle }}</span>
      </div>

      <!-- Side-by-Side Action Buttons Row -->
      <div class="sidebar-actions-row">
        <button :class="['action-box-btn gis-row-btn', { active: userLocation.lat !== null }]" @click="getUserLocation" :title="userLocation.lat !== null ? (currentLang === 'vi' ? 'GPS đang hoạt động' : 'GPS Active') : (currentLang === 'vi' ? 'Bật định vị GIS' : 'Enable GIS')">
          <div class="action-icon-wrap">
            <i class="fa-solid fa-location-crosshairs" :class="{ 'fa-spin': isLocating }"></i>
          </div>
          <div class="action-text-wrap">
            <span class="action-label">{{ currentLang === 'vi' ? 'Định vị GIS' : 'GIS Engine' }}</span>
            <span class="action-sub">{{ userLocation.lat !== null ? (currentLang === 'vi' ? '• Đang bật' : '• Active') : (currentLang === 'vi' ? '• Chưa bật' : '• Off') }}</span>
          </div>
          <div class="gis-pulse-dot" v-if="userLocation.lat !== null"></div>
        </button>

        <button class="action-box-btn new-chat-row-btn" @click="createNewSession" :title="t.newChat">
          <div class="action-icon-wrap blue-icon">
            <i class="fa-solid fa-plus"></i>
          </div>
          <div class="action-text-wrap">
            <span class="action-label">{{ currentLang === 'vi' ? 'Chat mới' : 'New Chat' }}</span>
            <span class="action-sub">{{ currentLang === 'vi' ? 'Tạo phiên' : 'Start new' }}</span>
          </div>
        </button>
      </div>

      <div class="session-list-label">
        <i class="fa-regular fa-clock"></i>
        <span>{{ t.chatHistory }}</span>
      </div>

      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === currentSessionId }"
          @click="selectSession(session.id)"
        >
          <div class="session-item-icon"><i class="fa-regular fa-message"></i></div>
          <div class="session-item-info">
            <p class="session-title">{{ session.title }}</p>
            <p class="session-time">{{ formatSessionTime(session.timestamp) }}</p>
          </div>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="footer-info">
          <i class="fa-solid fa-map-location-dot"></i>
          <span>GIS AI Agent v2.0</span>
        </div>
      </div>
    </aside>

    <!-- ═══ MAIN CONTENT ═══ -->
    <main class="main-content">
      <header class="app-header">
        <div class="header-left-action">
          <button class="mobile-menu-btn" @click="isSidebarOpen = !isSidebarOpen" title="Toggle Menu">
            <i class="fa-solid fa-bars"></i>
          </button>
        </div>

        <div class="header-center-content">
          <div class="logo-wrapper">
            <i class="fa-solid fa-building-shield logo-icon"></i>
            <h1>{{ t.systemTitle }} <span class="ai-badge">AI</span></h1>
          </div>
          <p class="subtitle"><i class="fa-solid fa-map-location-dot subtitle-icon"></i> {{ t.systemSubtitle }}</p>
        </div>

        <div class="header-right-action">
          <div class="premium-lang-widget" @click="toggleLanguage" :title="currentLang === 'vi' ? 'Nhấn để đổi sang Tiếng Anh' : 'Click to switch to Vietnamese'">
            <div class="lang-widget-prefix">
              <i class="fa-solid fa-earth-asia prefix-icon" :class="{ 'gold-icon': currentLang === 'vi', 'blue-icon-spin': currentLang === 'en' }"></i>
              <span class="prefix-text">{{ currentLang === 'vi' ? 'Ngôn ngữ' : 'Language' }}</span>
            </div>
            <div class="lang-divider"></div>
            <div class="lang-toggle-track">
              <div class="lang-glider" :class="currentLang"></div>
              <div :class="['track-opt opt-vi', { active: currentLang === 'vi' }]">
                <svg class="opt-flag-svg" viewBox="0 0 900 600">
                  <rect width="900" height="600" fill="#da251d" rx="60"/>
                  <polygon points="450,160 520.5,377 336,243 564,243 379.5,377" fill="#ffff00"/>
                </svg>
                <span class="opt-label">VI</span>
              </div>
              <div :class="['track-opt opt-en', { active: currentLang === 'en' }]">
                <svg class="opt-flag-svg" viewBox="0 0 60 40">
                  <rect width="60" height="40" fill="#012169" rx="4"/>
                  <path d="M0,0 L60,40 M60,0 L0,40" stroke="#fff" stroke-width="6"/>
                  <path d="M0,0 L60,40 M60,0 L0,40" stroke="#C8102E" stroke-width="3"/>
                  <path d="M30,0 v40 M0,20 h60" stroke="#fff" stroke-width="10"/>
                  <path d="M30,0 v40 M0,20 h60" stroke="#C8102E" stroke-width="6"/>
                </svg>
                <span class="opt-label">EN</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <!-- ═══ CHAT BOX ═══ -->
      <div class="chat-box">
        <!-- Messages Area -->
        <div class="messages-area" ref="chatBoxRef">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            :class="['message', 'message-row', msg.role]"
          >
            <!-- AI Avatar -->
            <div v-if="msg.role === 'ai'" class="avatar ai-avatar">
              <i class="fa-solid fa-robot"></i>
            </div>

            <!-- Text bubble -->
            <div v-if="msg.type === 'text'" class="message-content bubble" :class="msg.role">
              {{ msg.content }}
            </div>

            <!-- Room Card -->
            <div v-if="msg.type === 'room-card'" class="card-wrapper room-card">

              <!-- A2UI_Card (listing result / post success) -->
              <div v-if="msg.ui_type === 'A2UI_Card'" class="card-inner">
                <div class="card-header">
                  <i class="fa-solid fa-tag card-icon"></i>
                  <span class="card-title">{{ msg.data.title || msg.data.address || 'Thông tin phòng trọ' }}</span>
                  <span v-if="msg.data.property_type" class="pt-badge">
                    {{ msg.data.property_type === 'nha_nguyen_can' || msg.data.property_type === 'house' ? (currentLang === 'vi' ? 'Nhà nguyên căn' : 'House') : (currentLang === 'vi' ? 'Phòng trọ' : 'Room') }}
                  </span>
                </div>
                <div class="card-body">
                  <div v-if="msg.data.price" class="card-row">
                    <i class="fa-solid fa-money-bill-wave field-icon price-icon"></i>
                    <span class="field-label">{{ t.price }}:</span>
                    <span class="price-val">{{ cleanPriceDisplay(msg.data.price) }}</span>
                  </div>
                  <p v-if="msg.data.distance_meters != null && !isNaN(Number(msg.data.distance_meters))" class="card-row" style="margin: 0;">
                    <i class="fa-solid fa-route field-icon dist-icon"></i>
                    <strong>{{ t.distance }}:</strong> <span>{{ (Number(msg.data.distance_meters) / 1000).toFixed(1) }} km</span>
                  </p>
                  <p v-if="msg.data.address" class="card-row" style="margin: 0;">
                    <i class="fa-solid fa-location-dot field-icon"></i>
                    <strong>{{ t.address }}:</strong> <span>{{ msg.data.address }}</span>
                  </p>
                  <p v-if="msg.data.phone !== undefined" class="card-row" style="margin: 0;">
                    <i class="fa-solid fa-phone field-icon"></i>
                    <strong>{{ t.phone }}:</strong> <span :class="{ muted: !msg.data.phone }">{{ msg.data.phone || 'Đang cập nhật' }}</span>
                  </p>
                  <p v-if="msg.data.description" class="card-row" style="margin: 0; color: #475569; line-height: 1.4;">
                    <i class="fa-solid fa-circle-info field-icon" style="color: #3b82f6;"></i>
                    <span>{{ msg.data.description }}</span>
                  </p>
                  <div v-if="msg.data.message" class="card-row success-row">
                    <i class="fa-solid fa-circle-check field-icon"></i>
                    <span>{{ msg.data.message }}</span>
                  </div>
                  <div v-if="msg.data.error" class="card-row error-row">
                    <i class="fa-solid fa-triangle-exclamation field-icon"></i>
                    <span>{{ msg.data.error }}</span>
                  </div>
                </div>
              </div>

              <!-- A2UI_BudgetAdvice (Tư vấn ngân sách AI) -->
              <div v-if="msg.ui_type === 'A2UI_BudgetAdvice'" class="card-inner budget-advice-inner">
                <div class="card-header budget-header">
                  <span class="budget-icon-badge">💰</span>
                  <span class="card-title">{{ currentLang === 'vi' ? 'AI Tư Vấn Ngân Sách Tối Ưu' : 'AI Optimal Budget Advice' }}</span>
                  <span class="budget-tag">{{ currentLang === 'vi' ? '25% - 35% Thu nhập' : '25% - 35% Income' }}</span>
                </div>
                <div class="card-body budget-body">
                  <div class="budget-income-row">
                    <i class="fa-solid fa-sack-dollar income-icon"></i>
                    <span>{{ currentLang === 'vi' ? 'Thu nhập hàng tháng:' : 'Monthly Income:' }}</span>
                    <strong class="income-val">{{ msg.data.monthly_income?.toLocaleString(currentLang === 'vi' ? 'vi-VN' : 'en-US') }} VND</strong>
                  </div>
                  <div class="budget-range-box">
                    <div class="range-label">
                      <i class="fa-solid fa-chart-pie"></i>
                      <span>{{ currentLang === 'vi' ? 'Khoảng ngân sách thuê phòng khuyên dùng:' : 'Recommended Rental Range:' }}</span>
                    </div>
                    <div class="range-values">
                      <span class="min-val">{{ msg.data.min?.toLocaleString(currentLang === 'vi' ? 'vi-VN' : 'en-US') }} VND</span>
                      <i class="fa-solid fa-arrow-right-long range-arrow"></i>
                      <span class="max-val">{{ msg.data.max?.toLocaleString(currentLang === 'vi' ? 'vi-VN' : 'en-US') }} VND</span>
                    </div>
                  </div>
                  <div class="budget-advice-text">
                    <i class="fa-solid fa-lightbulb advice-bulb"></i>
                    <p>{{ currentLang === 'vi' ? (msg.data.advice_vi || msg.data.advice) : (msg.data.advice_en || msg.data.advice) }}</p>
                  </div>
                  <div class="budget-action">
                    <button class="search-budget-btn" @click="triggerBudgetSearch(msg.data.max)">
                      <i class="fa-solid fa-magnifying-glass-dollar"></i>
                      {{ currentLang === 'vi' ? `Tìm phòng trọ ≤ ${msg.data.max?.toLocaleString('vi-VN')} VND ngay` : `Search rooms ≤ ${msg.data.max?.toLocaleString('en-US')} VND now` }}
                    </button>
                  </div>
                </div>
              </div>

              <div v-if="msg.ui_type === 'A2UI_MapCard'" class="card-inner map-card-inner">
                <div class="card-header">
                  <i class="fa-solid fa-location-arrow card-icon map-icon"></i>
                  <span class="card-title">{{ msg.data.title || msg.data.address }}</span>
                  <span v-if="msg.data.property_type" class="pt-badge">
                    {{ msg.data.property_type === 'nha_nguyen_can' || msg.data.property_type === 'house' ? (currentLang === 'vi' ? 'Nhà nguyên căn' : 'House') : (currentLang === 'vi' ? 'Phòng trọ' : 'Room') }}
                  </span>
                </div>
                <div class="card-body">
                  <div class="card-row">
                    <i class="fa-solid fa-money-bill-wave field-icon price-icon"></i>
                    <span class="field-label">{{ t.price }}:</span>
                    <span class="price-val">{{ cleanPriceDisplay(msg.data.price) }}</span>
                  </div>
                  <p v-if="msg.data.distance_meters != null && !isNaN(Number(msg.data.distance_meters))" class="card-row" style="margin: 0;">
                    <i class="fa-solid fa-route field-icon dist-icon"></i>
                    <strong>{{ t.distance }}:</strong> <span>{{ (Number(msg.data.distance_meters) / 1000).toFixed(1) }} km</span>
                  </p>
                  <p class="card-row" style="margin: 0;">
                    <i class="fa-solid fa-location-dot field-icon"></i>
                    <strong>{{ t.address }}:</strong> <span>{{ msg.data.address }}</span>
                  </p>
                  <p class="card-row" style="margin: 0;">
                    <i class="fa-solid fa-phone field-icon"></i>
                    <strong>{{ t.phone }}:</strong> <span :class="{ muted: !msg.data.phone }">{{ msg.data.phone || 'Đang cập nhật' }}</span>
                  </p>
                  <div class="card-row coords-row">
                    <i class="fa-solid fa-compass field-icon"></i>
                    <span class="field-label">{{ t.coordinates }}:</span>
                    <span class="coords-val">{{ msg.data.lat?.toFixed(4) }}, {{ msg.data.lng?.toFixed(4) }}</span>
                  </div>
                  <div :id="'map-' + msg.data.id" class="map-container"></div>
                </div>
              </div>

            </div>

            <!-- User Avatar -->
            <div v-if="msg.role === 'user'" class="avatar user-avatar">
              <i class="fa-solid fa-user"></i>
            </div>
          </div>

          <!-- Typing indicator while AI is thinking -->
          <div v-if="isSearching" class="message-row ai">
            <div class="avatar ai-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="bubble ai typing-bubble">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>
          </div>
        </div>

        <!-- Input Bar -->
        <div class="input-bar">
          <div class="input-wrapper">
            <i class="fa-solid fa-wand-magic-sparkles input-icon"></i>
            <input
              v-model="userQuery"
              @keyup.enter="handleSearch"
              type="text"
              :placeholder="t.placeholder"
              :disabled="isSearching"
              autocomplete="off"
            />
          </div>
          <button @click="handleSearch" :disabled="isSearching" class="send-btn">
            <i class="fa-solid fa-paper-plane"></i>
            <span>{{ t.sendBtn }}</span>
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0; padding: 0;
  background: #0f172a;
  font-family: 'Plus Jakarta Sans', sans-serif;
  min-height: 100vh;
  overflow: hidden;
}

/* ═══ LAYOUT ═══ */
.chat-app-container { display: flex; height: 100vh; overflow: hidden; }

/* ═══ SIDEBAR ═══ */
.sidebar {
  width: 280px; flex-shrink: 0;
  background: #0d1424;
  border-right: 1px solid rgba(255,255,255,0.06);
  display: flex; flex-direction: column; overflow: hidden;
}

.sidebar-brand {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 1.15rem 0.85rem;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.brand-icon {
  font-size: 1.3rem; flex-shrink: 0;
  background: linear-gradient(135deg, #38bdf8, #3b82f6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}

.brand-name {
  font-size: 0.86rem; font-weight: 700; color: #f1f5f9;
  letter-spacing: -0.2px; white-space: nowrap; flex: 1;
  min-width: 0; overflow: hidden; text-overflow: ellipsis;
}

.sidebar-actions-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem;
  margin: 0.75rem 0.75rem 0.5rem;
}
.action-box-btn {
  display: flex; align-items: center; gap: 0.45rem;
  padding: 0.55rem 0.55rem; border-radius: 10px;
  cursor: pointer; transition: all 0.2s;
  font-family: inherit; border: 1px solid transparent;
  text-align: left; min-width: 0;
}
.gis-row-btn {
  background: rgba(15, 23, 42, 0.6);
  border-color: rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
}
.gis-row-btn:hover {
  background: rgba(30, 41, 59, 0.85);
  border-color: rgba(56, 189, 248, 0.35);
  transform: translateY(-1px);
}
.gis-row-btn.active {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.18), rgba(5, 150, 105, 0.18));
  border-color: #10b981;
}
.new-chat-row-btn {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #fff;
  box-shadow: 0 3px 12px rgba(37, 99, 235, 0.3);
}
.new-chat-row-btn:hover {
  background: linear-gradient(135deg, #1d4ed8, #1e40af);
  transform: translateY(-1px);
}
.action-icon-wrap {
  width: 26px; height: 26px; border-radius: 7px;
  background: rgba(56, 189, 248, 0.12);
  color: #38bdf8; display: flex; align-items: center; justify-content: center;
  font-size: 0.78rem; flex-shrink: 0;
}
.gis-row-btn.active .action-icon-wrap {
  background: rgba(16, 185, 129, 0.22); color: #10b981;
}
.blue-icon {
  background: rgba(255, 255, 255, 0.18); color: #fff;
}
.action-text-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.action-label {
  font-size: 0.74rem; font-weight: 700;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.action-sub {
  font-size: 0.62rem; color: #64748b; font-weight: 500; margin-top: 0.06rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gis-row-btn.active .action-sub { color: #34d399; font-weight: 600; }
.new-chat-row-btn .action-sub { color: rgba(255, 255, 255, 0.75); }
.gis-pulse-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #10b981; box-shadow: 0 0 6px #10b981; flex-shrink: 0;
  animation: gisPulse 2s infinite ease-in-out;
}
@keyframes gisPulse {
  0%, 100% { transform: scale(1); opacity: 0.95; }
  50% { transform: scale(1.4); opacity: 0.35; }
}

.session-list-label {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.65rem 1rem 0.35rem;
  font-size: 0.68rem; font-weight: 600; color: #475569;
  text-transform: uppercase; letter-spacing: 0.8px;
}

.session-list {
  flex: 1; overflow-y: auto; padding: 0.2rem 0.5rem;
  scrollbar-width: thin; scrollbar-color: #1e293b transparent;
}
.session-list::-webkit-scrollbar { width: 4px; }
.session-list::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 4px; }

.session-item {
  display: flex; align-items: center; gap: 0.7rem;
  padding: 0.6rem 0.7rem; border-radius: 8px; cursor: pointer;
  transition: all 0.18s; margin-bottom: 2px; border: 1px solid transparent;
}
.session-item:hover { background: rgba(255,255,255,0.05); }
.session-item.active { background: rgba(59,130,246,0.14); border-color: rgba(59,130,246,0.2); }

.session-item-icon {
  width: 30px; height: 30px; display: flex; align-items: center; justify-content: center;
  border-radius: 7px; background: rgba(255,255,255,0.06);
  color: #64748b; font-size: 0.82rem; flex-shrink: 0;
}
.session-item.active .session-item-icon { background: rgba(59,130,246,0.2); color: #60a5fa; }

.session-item-info { flex: 1; min-width: 0; }
.session-title {
  margin: 0; font-size: 0.82rem; font-weight: 500; color: #94a3b8;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.session-item.active .session-title, .session-item:hover .session-title { color: #e2e8f0; }
.session-time { margin: 0; font-size: 0.68rem; color: #334155; }
.session-item.active .session-time { color: #475569; }

.sidebar-footer {
  padding: 0.7rem 1rem;
  border-top: 1px solid rgba(255,255,255,0.05);
}
.footer-info { display: flex; align-items: center; gap: 0.5rem; color: #334155; font-size: 0.75rem; }
.footer-info i { color: #38bdf8; }

/* ═══ MAIN CONTENT ═══ */
.main-content {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  padding: 1.5rem 1.75rem 1.25rem; gap: 1rem;
}

.app-header { position: relative; text-align: center; color: #f8fafc; flex-shrink: 0; min-height: 58px; display: flex; flex-direction: column; justify-content: center; align-items: center; }
.header-left-action {
  position: absolute; left: 0; top: 0; display: flex; align-items: center; gap: 0.6rem; z-index: 10;
}
.header-right-action {
  position: absolute; right: 0; top: 0; display: flex; align-items: center; z-index: 10;
}
@media (max-width: 950px) {
  .header-left-action { position: relative; margin-bottom: 0.6rem; justify-content: center; width: 100%; }
  .header-right-action { position: absolute; right: 0; top: 0; }
}

/* ═══ PREMIUM UNIFIED LANGUAGE CONSOLE WIDGET ═══ */
.premium-lang-widget {
  display: flex; align-items: center; gap: 0.55rem;
  padding: 0.3rem 0.35rem 0.3rem 0.85rem;
  background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.8));
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 50px;
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.45), inset 0 1px 1px rgba(255, 255, 255, 0.15);
  cursor: pointer; user-select: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.premium-lang-widget:hover {
  border-color: rgba(251, 191, 36, 0.55);
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 22px rgba(251, 191, 36, 0.25);
  transform: translateY(-1.5px);
}
.lang-widget-prefix {
  display: flex; align-items: center; gap: 0.42rem;
}
.prefix-icon {
  font-size: 0.92rem; transition: all 0.4s ease;
}
.gold-icon { color: #fbbf24; filter: drop-shadow(0 0 5px rgba(251, 191, 36, 0.6)); }
.blue-icon-spin { color: #38bdf8; filter: drop-shadow(0 0 5px rgba(56, 189, 248, 0.6)); transform: rotate(180deg); }

.prefix-text {
  font-size: 0.78rem; font-weight: 700; color: #f1f5f9;
  letter-spacing: 0.3px;
}
.lang-divider {
  width: 1px; height: 18px; background: rgba(255, 255, 255, 0.16); margin: 0 0.05rem;
}
.lang-toggle-track {
  position: relative; display: flex; align-items: center;
  background: rgba(0, 0, 0, 0.5); border-radius: 30px;
  padding: 3px; width: 110px; height: 32px;
  box-shadow: inset 0 2px 5px rgba(0,0,0,0.6);
  border: 1px solid rgba(255, 255, 255, 0.07);
}
.lang-glider {
  position: absolute; top: 3px; left: 3px; width: calc(50% - 3px); height: calc(100% - 6px);
  border-radius: 24px;
  transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.35s, box-shadow 0.35s;
}
.lang-glider.vi {
  transform: translateX(0);
  background: linear-gradient(135deg, #ffffff, #f1f5f9);
  box-shadow: 0 2px 12px rgba(255, 255, 255, 0.45), 0 2px 6px rgba(0,0,0,0.5);
  border: 1px solid #ffffff;
}
.lang-glider.en {
  transform: translateX(100%);
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  box-shadow: 0 2px 12px rgba(59, 130, 246, 0.65);
  border: 1px solid rgba(191, 219, 254, 0.45);
}
.track-opt {
  flex: 1; z-index: 2; display: flex; align-items: center; justify-content: center; gap: 0.28rem;
  color: #94a3b8; transition: all 0.3s ease;
}
.opt-flag-svg { width: 16px; height: 11px; border-radius: 2px; box-shadow: 0 1px 3px rgba(0,0,0,0.4); flex-shrink: 0; }
.opt-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.5px; }
.track-opt.active {
  color: #ffffff; font-weight: 800; transform: scale(1.08);
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}
.opt-vi.active {
  color: #dc2626;
  text-shadow: none;
}
.header-center-content { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; }
.mobile-menu-btn {
  display: none; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
  color: #fff; font-size: 1.1rem; padding: 0.5rem 0.75rem; border-radius: 8px; cursor: pointer; transition: all 0.2s;
}
.mobile-menu-btn:hover { background: rgba(255,255,255,0.2); }

.sidebar-backdrop {
  position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(3px); z-index: 998;
}

.logo-wrapper { display: flex; align-items: center; justify-content: center; gap: 0.7rem; }
.logo-icon {
  font-size: 2rem;
  background: linear-gradient(135deg, #38bdf8, #3b82f6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
h1 { font-size: 1.8rem; font-weight: 700; margin: 0; letter-spacing: -0.5px; color: #fff; }
.ai-badge {
  background: linear-gradient(135deg, #3b82f6, #6366f1); color: white;
  font-size: 0.8rem; padding: 0.18rem 0.5rem; border-radius: 5px;
  vertical-align: middle; font-weight: 600;
  box-shadow: 0 3px 10px rgba(59,130,246,0.4);
}
.subtitle { color: #94a3b8; font-size: 0.88rem; margin: 0; }
.subtitle-icon { color: #38bdf8; margin-right: 0.3rem; }

/* ═══ CHAT BOX ═══ */
.chat-box {
  flex: 1; display: flex; flex-direction: column; min-height: 0;
  background: rgba(255,255,255,0.97);
  border-radius: 18px; overflow: hidden;
  box-shadow: 0 20px 50px -12px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.07);
}

/* ═══ MESSAGES AREA ═══ */
.messages-area {
  flex: 1; overflow-y: auto; padding: 1.5rem 1.25rem 0.75rem;
  display: flex; flex-direction: column; gap: 1rem;
  background: #f8fafc;
  scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent;
}
.messages-area::-webkit-scrollbar { width: 5px; }
.messages-area::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 5px; }

/* Message Row */
.message-row {
  display: flex; align-items: flex-end; gap: 0.6rem;
}
.message-row.user { flex-direction: row-reverse; }
.message-row.ai { flex-direction: row; }

/* Avatars */
.avatar {
  width: 34px; height: 34px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.95rem; flex-shrink: 0;
}
.ai-avatar {
  background: linear-gradient(135deg, #2563eb, #6366f1);
  color: #fff; box-shadow: 0 3px 10px rgba(37,99,235,0.3);
}
.user-avatar {
  background: linear-gradient(135deg, #0f172a, #1e293b);
  color: #94a3b8;
}

/* Text Bubbles */
.bubble {
  max-width: 68%; padding: 0.75rem 1.1rem;
  border-radius: 16px; font-size: 0.92rem; line-height: 1.55;
  white-space: pre-line;
}
.bubble.ai {
  background: #fff; color: #1e293b;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.bubble.user {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #fff; border-bottom-right-radius: 4px;
  box-shadow: 0 3px 12px rgba(37,99,235,0.25);
}

/* Typing dots */
.typing-bubble { display: flex; gap: 4px; align-items: center; padding: 0.7rem 1rem; }
.dot {
  width: 7px; height: 7px; border-radius: 50%; background: #94a3b8;
  animation: bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%,80%,100% { transform: scale(0.7); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

/* Cards bubble */
.cards-bubble { max-width: 90%; display: flex; flex-direction: column; gap: 0.75rem; }

/* Room Card */
.room-card { width: 100%; }
.card-inner {
  background: #fff; border-radius: 14px; overflow: hidden;
  border: 1px solid #e2e8f0;
  box-shadow: 0 6px 20px -5px rgba(0,0,0,0.07);
  transition: transform 0.18s, box-shadow 0.18s;
}
.card-inner:hover { transform: translateY(-2px); box-shadow: 0 12px 28px -8px rgba(0,0,0,0.1); }

.card-header {
  display: flex; align-items: center; gap: 0.65rem;
  padding: 0.9rem 1.2rem; background: #fafbfc;
  border-bottom: 1px solid #f1f5f9;
}
.card-icon { font-size: 1.1rem; color: #3b82f6; }
.map-icon { color: #f97316; }
.card-title { font-weight: 600; color: #1e293b; font-size: 1rem; flex: 1; }

.pt-badge {
  padding: 0.18rem 0.55rem; border-radius: 6px;
  background: rgba(59, 130, 246, 0.12); color: #2563eb; font-size: 0.75rem; font-weight: 700; white-space: nowrap; border: 1px solid rgba(59, 130, 246, 0.25);
}


/* Filter Bar */
.filter-bar {
  display: flex; align-items: center; justify-content: center; gap: 0.5rem;
  margin-top: 0.65rem; flex-wrap: wrap;
}
.filter-label {
  font-size: 0.82rem; color: #94a3b8; font-weight: 600; display: flex; align-items: center; gap: 0.35rem; margin-right: 0.2rem;
}
.filter-chip {
  background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1; padding: 0.35rem 0.85rem; border-radius: 20px; font-size: 0.82rem;
  font-weight: 600; cursor: pointer; transition: all 0.2s; font-family: inherit;
  display: flex; align-items: center; gap: 0.4rem; backdrop-filter: blur(8px);
}
.filter-chip:hover { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.4); color: #60a5fa; transform: translateY(-1px); }
.filter-chip.active {
  background: linear-gradient(135deg, #3b82f6, #2563eb); border-color: #3b82f6; color: #fff; box-shadow: 0 2px 10px rgba(59, 130, 246, 0.3);
}
.location-chip.active {
  background: linear-gradient(135deg, #10b981, #059669); border-color: #10b981; color: #fff; box-shadow: 0 2px 10px rgba(16, 185, 129, 0.3);
}

.card-body { padding: 1rem 1.2rem; display: flex; flex-direction: column; gap: 0.45rem; }
.card-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }

.card-row {
  display: flex; align-items: center; gap: 0.45rem;
  font-size: 0.87rem; color: #475569;
}
.field-icon { width: 16px; text-align: center; flex-shrink: 0; font-size: 0.88rem; color: #94a3b8; }
.field-label { font-weight: 600; color: #334155; white-space: nowrap; }
.price-icon { color: #10b981; }
.dist-icon { color: #ef4444; }
.price-val { font-weight: 700; color: #059669; font-size: 0.95rem; }
.dist-badge {
  background: #fef2f2; color: #dc2626; padding: 0.12rem 0.45rem;
  border-radius: 5px; font-weight: 600; border: 1px solid #fee2e2; font-size: 0.82rem;
}
.coords-row { font-size: 0.8rem; }
.coords-val { color: #94a3b8; font-family: monospace; }
.muted { color: #94a3b8; font-style: italic; }

.success-row { color: #059669; }
.success-row .field-icon { color: #10b981; }
.error-row { color: #dc2626; }
.error-row .field-icon { color: #ef4444; }

.map-container {
  height: 200px; width: 100%; margin-top: 0.75rem;
  border-radius: 10px; overflow: hidden; border: 1px solid #cbd5e1; z-index: 1;
}

/* ═══ INPUT BAR ═══ */
.input-bar {
  display: flex; gap: 0.65rem; padding: 0.9rem 1.1rem;
  background: #fff; border-top: 1px solid #e2e8f0; flex-shrink: 0;
}
.input-wrapper {
  flex: 1; position: relative; display: flex; align-items: center;
}
.input-icon {
  position: absolute; left: 1rem; color: #94a3b8; font-size: 0.95rem; pointer-events: none;
}
input {
  width: 100%; padding: 0.8rem 0.9rem 0.8rem 2.8rem;
  border: 1.5px solid #e2e8f0; border-radius: 11px;
  font-size: 0.9rem; font-family: inherit; color: #1e293b;
  background: #f8fafc; transition: all 0.2s; box-sizing: border-box;
}
input:focus { outline: none; border-color: #3b82f6; background: #fff; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
input:disabled { opacity: 0.6; cursor: not-allowed; }

.send-btn {
  display: flex; align-items: center; gap: 0.45rem; padding: 0 1.3rem;
  background: linear-gradient(135deg, #3b82f6, #2563eb); color: white;
  border: none; border-radius: 11px; font-weight: 600; font-size: 0.9rem;
  font-family: inherit; cursor: pointer; transition: all 0.2s;
  box-shadow: 0 3px 10px rgba(37,99,235,0.25); white-space: nowrap;
}
.send-btn:hover:not(:disabled) { background: linear-gradient(135deg,#2563eb,#1d4ed8); transform: translateY(-1px); }
.send-btn:disabled { background: #cbd5e1; cursor: not-allowed; box-shadow: none; transform: none; }

/* ═══ AI BUDGET ADVICE CARD ═══ */
.budget-advice-inner {
  border: 1.5px solid #10b981 !important;
  background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%) !important;
  box-shadow: 0 10px 25px rgba(16, 185, 129, 0.15) !important;
}
.budget-header {
  background: linear-gradient(135deg, #059669, #10b981) !important;
  color: #ffffff !important;
}
.budget-icon-badge {
  font-size: 1.25rem;
}
.budget-tag {
  background: rgba(255, 255, 255, 0.22);
  padding: 0.2rem 0.65rem; border-radius: 20px;
  font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.5px;
}
.budget-body {
  display: flex; flex-direction: column; gap: 0.85rem; padding: 1.2rem 1.3rem !important;
}
.budget-income-row {
  display: flex; align-items: center; gap: 0.6rem;
  font-size: 0.92rem; color: #065f46;
}
.income-icon { font-size: 1.1rem; color: #10b981; }
.income-val { color: #047857; font-size: 1.05rem; }

.budget-range-box {
  background: #ffffff; border: 1px solid #a7f3d0;
  border-radius: 12px; padding: 0.85rem 1rem;
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.08);
}
.range-label {
  display: flex; align-items: center; gap: 0.45rem;
  font-size: 0.8rem; color: #047857; font-weight: 600; margin-bottom: 0.4rem;
}
.range-values {
  display: flex; align-items: center; gap: 0.75rem; justify-content: center;
  font-size: 1.25rem; font-weight: 800; color: #065f46;
}
.min-val { color: #059669; }
.max-val { color: #dc2626; }
.range-arrow { color: #9ca3af; font-size: 1rem; }

.budget-advice-text {
  display: flex; align-items: flex-start; gap: 0.65rem;
  background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981;
  padding: 0.75rem 0.9rem; border-radius: 0 8px 8px 0;
  color: #065f46; font-size: 0.9rem; line-height: 1.5; margin: 0;
}
.advice-bulb { font-size: 1.1rem; color: #f59e0b; margin-top: 0.1rem; }
.budget-advice-text p { margin: 0; }

.budget-action {
  display: flex; justify-content: flex-end; margin-top: 0.2rem;
}
.search-budget-btn {
  display: inline-flex; align-items: center; gap: 0.5rem;
  background: linear-gradient(135deg, #10b981, #059669);
  color: #ffffff; border: none; padding: 0.65rem 1.15rem;
  border-radius: 10px; font-size: 0.88rem; font-weight: 700;
  cursor: pointer; transition: all 0.25s ease;
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}
.search-budget-btn:hover {
  background: linear-gradient(135deg, #059669, #047857);
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4);
}

/* ═══ RESPONSIVE BREAKPOINTS ═══ */
/* Tablet & Small Desktop (<= 1024px) */
@media (max-width: 1024px) {
  .sidebar { width: 250px; }
  .main-content { padding: 1.25rem 1.25rem 1rem; }
  h1 { font-size: 1.5rem; }
}

/* Mobile & Tablet Portrait (<= 768px) */
@media (max-width: 768px) {
  .mobile-menu-btn { display: block; }
  .sidebar {
    position: fixed; top: 0; left: -280px; width: 280px; height: 100vh;
    z-index: 999; transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 5px 0 25px rgba(0,0,0,0.5);
  }
  .sidebar.sidebar-open { left: 0; }
  .main-content { padding: 1rem 0.75rem 0.75rem; gap: 0.75rem; }
  .header-top { justify-content: center; padding: 0 2.5rem; }
  h1 { font-size: 1.3rem; }
  .logo-icon { font-size: 1.5rem; }
  .subtitle { font-size: 0.78rem; line-height: 1.4; }
  .chat-box { border-radius: 14px; }
  .messages-area { padding: 1rem 0.75rem 0.5rem; }
  .message-row { max-width: 95%; }
  .card-grid { grid-template-columns: 1fr; }
  .input-bar { padding: 0.7rem 0.75rem; gap: 0.5rem; }
  input { padding: 0.75rem 0.75rem 0.75rem 2.4rem; font-size: 0.85rem; }
  .input-icon { left: 0.8rem; }
  .send-btn { padding: 0 1rem; font-size: 0.85rem; }
}

/* Small Phone (<= 480px) */
@media (max-width: 480px) {
  h1 { font-size: 1.15rem; }
  .ai-badge { font-size: 0.7rem; padding: 0.12rem 0.4rem; }
  .subtitle { font-size: 0.72rem; }
  .message-bubble { padding: 0.75rem 0.9rem; font-size: 0.9rem; }
  .card-header { padding: 0.75rem 1rem; }
  .card-body { padding: 0.8rem 1rem; }
}
</style>
(() => {

  /* ======================================================
     ワラいどっとこむ
     配信カレンダー
  ====================================================== */

  const STREAM_DEFAULT_PERFORMERS = [
    {
      id: "maison",
      name: "めぞん",
      short: "め",
      color: "#E74C3C",
      soft: "#FDECEA",
    },
    {
      id: "pyuto",
      name: "ピュート",
      short: "ピ",
      color: "#F4C430",
      soft: "#FFF7D6",
    },
    {
      id: "nansui",
      name: "軟水",
      short: "軟",
      color: "#3498DB",
      soft: "#EAF4FD",
    },
  ];


  const STREAM_WEEKDAYS = [
    "日",
    "月",
    "火",
    "水",
    "木",
    "金",
    "土",
  ];


  let streamEvents = [];


  let streamMonth =
    new Date();


  streamMonth =
    new Date(
      streamMonth.getFullYear(),
      streamMonth.getMonth(),
      1
    );


  let streamSelectedDate =
    streamDateKey(
      new Date()
    );


  let streamActiveFilters =
    new Set();


  let currentCalendarMode =
    "live";


  /* ======================================================
     STYLE
  ====================================================== */

  function injectStreamStyles() {

    const style =
      document.createElement(
        "style"
      );


    style.textContent = `

      .calendar-mode-switch {
        display: grid;
        grid-template-columns: 1fr 1fr;

        gap: 5px;

        margin:
          0
          10px
          13px;

        padding: 4px;

        border:
          1px solid
          #e4e9f0;

        border-radius: 14px;

        background: #eef2f6;

        box-shadow:
          0 4px 16px
          rgba(
            20,
            32,
            54,
            0.04
          );
      }

      .calendar-mode-button {
        min-height: 43px;

        padding:
          8px
          9px;

        border: 0;

        border-radius: 11px;

        background: transparent;

        color: #647084;

        font-size: 13px;
        font-weight: 900;

        cursor: pointer;
      }

      .calendar-mode-button:active {
        transform: scale(0.97);
      }

      .calendar-mode-button.active {
        background: #fff;

        color: #172033;

        box-shadow:
          0 3px 12px
          rgba(
            19,
            32,
            51,
            0.08
          );
      }

      .calendar-mode-button.stream-active {
        background:
          linear-gradient(
            135deg,
            #2483eb,
            #1266c7
          );

        color: #fff;

        box-shadow:
          0 5px 15px
          rgba(
            31,
            110,
            212,
            0.23
          );
      }


      #streamCalendarView {
        display: none;
      }

      #streamCalendarView.show {
        display: block;
      }


      .stream-intro {
        margin-bottom: 12px;

        padding: 14px;

        border:
          1px solid
          #deebfa;

        border-radius: 17px;

        background:
          linear-gradient(
            135deg,
            #eef7ff,
            #fbfdff
          );
      }

      .stream-intro-top {
        display: flex;
        align-items: center;

        gap: 10px;
      }

      .stream-play-icon {
        display: flex;
        align-items: center;
        justify-content: center;

        width: 39px;
        height: 39px;

        flex:
          0
          0
          39px;

        border-radius: 12px;

        background: #1f76d5;

        color: #fff;

        font-size: 17px;
      }

      .stream-intro-title {
        font-size: 18px;
        font-weight: 900;
      }

      .stream-intro-text {
        margin-top: 8px;

        color: #667387;

        font-size: 12px;
        line-height: 1.65;

        font-weight: 650;
      }

      .stream-data-status {
        display: inline-flex;
        align-items: center;

        margin-top: 9px;

        padding:
          5px
          8px;

        border-radius: 999px;

        background: #eef5fd;

        color: #286eb8;

        font-size: 10px;
        font-weight: 900;
      }


      .stream-filter {
        display: grid;

        grid-template-columns:
          repeat(
            4,
            1fr
          );

        gap: 5px;

        margin-bottom: 12px;
      }

      .stream-filter-button {
        min-width: 0;

        min-height: 40px;

        padding:
          7px
          3px;

        border:
          1px solid
          #e5eaf0;

        border-radius: 11px;

        background: #fff;

        color: #4e5a6d;

        font-size: 12px;
        font-weight: 900;

        cursor: pointer;
      }

      .stream-filter-button.all.active {
        border-color: #18263a;
        background: #18263a;
        color: #fff;
      }

      .stream-filter-button.maison.active {
        border-color: #f0afa9;
        background: #fdecea;
        color: #bc3028;
      }

      .stream-filter-button.pyuto.active {
        border-color: #ead574;
        background: #fff7d6;
        color: #806700;
      }

      .stream-filter-button.nansui.active {
        border-color: #9bc7ee;
        background: #eaf4fd;
        color: #1766a8;
      }


      .stream-calendar-card {
        overflow: hidden;

        border:
          1px solid
          #edf0f4;

        border-radius: 22px;

        background: #fff;

        box-shadow:
          0 7px 28px
          rgba(
            20,
            32,
            54,
            0.06
          );
      }

      .stream-month-header {
        display: grid;

        grid-template-columns:
          44px
          44px
          1fr
          58px;

        align-items: center;

        gap: 3px;

        padding:
          12px
          9px
          10px;
      }

      .stream-month-arrow {
        width: 40px;
        height: 40px;

        border: 0;
        border-radius: 50%;

        background: #f2f5f8;

        color: #142137;

        font-size: 26px;

        cursor: pointer;
      }

      .stream-month-title {
        text-align: center;

        font-size:
          clamp(
            22px,
            6.5vw,
            31px
          );

        font-weight: 900;

        letter-spacing: -0.03em;
      }

      .stream-today-button {
        min-height: 39px;

        border:
          1px solid
          #dce8f6;

        border-radius: 11px;

        background: #f3f8fe;

        color: #286eb8;

        font-size: 11px;
        font-weight: 900;

        cursor: pointer;
      }


      .stream-week-row,
      .stream-calendar-grid {
        display: grid;

        grid-template-columns:
          repeat(
            7,
            minmax(
              0,
              1fr
            )
          );
      }

      .stream-weekday {
        padding:
          7px
          0
          9px;

        text-align: center;

        color: #536176;

        font-size: 11px;
        font-weight: 900;
      }

      .stream-weekday.saturday {
        color: #287dd1;
      }

      .stream-weekday.sunday {
        color: #df4d51;
      }


      .stream-calendar-grid {
        overflow: hidden;

        border-top:
          1px solid
          #e4e9f0;

        border-left:
          1px solid
          #e4e9f0;
      }

      .stream-day-cell {
        position: relative;

        min-width: 0;
        min-height: 92px;

        overflow: hidden;

        padding:
          5px
          3px;

        border-right:
          1px solid
          #e4e9f0;

        border-bottom:
          1px solid
          #e4e9f0;

        background: #fff;

        cursor: pointer;
      }

      .stream-day-cell.other-month {
        background: #fafbfd;
      }

      .stream-day-cell.other-month
      .stream-day-number {
        color: #bbc3ce;
      }

      .stream-day-cell.selected {
        z-index: 1;

        background: #f7fbff;

        box-shadow:
          inset
          0
          0
          0
          1.5px
          #68a9ec;
      }

      .stream-day-number {
        min-height: 19px;

        color: #263248;

        font-size: 13px;
        font-weight: 900;
      }

      .stream-day-cell.selected
      .stream-day-number {
        color: #126bc5;
      }


      .stream-day-event {
        display: block;

        overflow: hidden;

        width: 100%;

        margin-top: 3px;

        padding:
          4px
          3px;

        border-radius: 6px;

        color: #202939;

        font-size: 8px;
        line-height: 1.25;

        font-weight: 900;

        white-space: nowrap;
        text-overflow: ellipsis;
      }

      .stream-day-event.maison {
        background: #fdecea;
        color: #b8342c;
      }

      .stream-day-event.pyuto {
        background: #fff5ca;
        color: #756000;
      }

      .stream-day-event.nansui {
        background: #e6f2fc;
        color: #196baa;
      }

      .stream-more-count {
        margin-top: 3px;

        color: #778395;

        font-size: 8px;
        font-weight: 900;
      }


      .stream-selected-section {
        margin-top: 12px;

        padding:
          14px
          10px;

        border:
          1px solid
          #edf0f4;

        border-radius: 19px;

        background: #fff;

        box-shadow:
          0 7px 28px
          rgba(
            20,
            32,
            54,
            0.05
          );
      }

      .stream-selected-head {
        display: flex;
        align-items: baseline;

        gap: 8px;

        margin:
          0
          3px
          11px;
      }

      .stream-selected-title {
        margin: 0;

        font-size: 20px;
        font-weight: 900;
      }

      .stream-selected-count {
        color: #748094;

        font-size: 11px;
        font-weight: 800;
      }


      .stream-event-list {
        overflow: hidden;

        border:
          1px solid
          #e4e9f0;

        border-radius: 13px;
      }

      .stream-event-row {
        display: grid;

        grid-template-columns:
          56px
          1fr
          22px;

        align-items: center;

        gap: 7px;

        width: 100%;

        min-height: 67px;

        padding:
          8px
          7px;

        border: 0;

        border-bottom:
          1px solid
          #e4e9f0;

        background: #fff;

        text-align: left;

        cursor: pointer;
      }

      .stream-event-row:last-child {
        border-bottom: 0;
      }

      .stream-event-time {
        color: #273449;

        font-size: 14px;
        font-weight: 900;
      }

      .stream-event-main {
        min-width: 0;
      }

      .stream-event-title {
        overflow: hidden;

        margin-bottom: 5px;

        color: #131d2d;

        font-size: 13px;
        font-weight: 900;

        white-space: nowrap;
        text-overflow: ellipsis;
      }

      .stream-event-tags {
        display: flex;
        align-items: center;

        gap: 4px;

        flex-wrap: wrap;
      }

      .stream-performer-chip {
        display: inline-flex;
        align-items: center;

        gap: 3px;

        padding:
          3px
          6px;

        border-radius: 999px;

        font-size: 9px;
        font-weight: 900;
      }

      .stream-row-sub {
        color: #738096;

        font-size: 9px;
        font-weight: 700;
      }

      .stream-event-arrow {
        color: #8590a0;

        font-size: 22px;
      }


      .stream-empty {
        padding:
          28px
          15px;

        text-align: center;

        color: #7a8696;

        font-size: 12px;
        font-weight: 800;
      }


      .stream-info-card {
        margin-top: 12px;

        padding: 14px;

        border:
          1px solid
          #dceafa;

        border-radius: 17px;

        background:
          linear-gradient(
            135deg,
            #f3f9ff,
            #fff
          );
      }

      .stream-info-title {
        color: #286db5;

        font-size: 13px;
        font-weight: 900;
      }

      .stream-info-text {
        margin-top: 6px;

        color: #68768b;

        font-size: 11px;
        line-height: 1.65;

        font-weight: 700;
      }


      .stream-sheet-overlay {
        position: fixed;
        inset: 0;
        z-index: 260;

        display: none;

        align-items: flex-end;
        justify-content: center;

        background:
          rgba(
            15,
            23,
            42,
            0.45
          );
      }

      .stream-sheet-overlay.open {
        display: flex;
      }

      .stream-sheet {
        width: 100%;
        max-width: 760px;

        max-height: 88dvh;

        overflow-y: auto;

        padding:
          17px
          18px
          calc(
            28px
            +
            env(
              safe-area-inset-bottom
            )
          );

        border-radius:
          26px
          26px
          0
          0;

        background: #fff;

        box-shadow:
          0
          -15px
          50px
          rgba(
            15,
            23,
            42,
            0.15
          );

        -webkit-overflow-scrolling:
          touch;
      }

      .stream-sheet-handle {
        width: 47px;
        height: 5px;

        margin:
          -4px
          auto
          14px;

        border-radius: 999px;

        background: #ced5df;
      }

      .stream-sheet-close {
        float: right;

        width: 43px;
        height: 43px;

        border: 0;
        border-radius: 50%;

        background: #f2f4f7;

        color: #2477ce;

        font-size: 25px;

        cursor: pointer;
      }

      .stream-detail-badge {
        display: inline-flex;

        margin-bottom: 9px;

        padding:
          5px
          8px;

        border-radius: 999px;

        background: #eaf4fd;

        color: #176cba;

        font-size: 10px;
        font-weight: 900;
      }

      .stream-sheet-title {
        padding-right: 53px;

        color: #101827;

        font-size: 24px;
        line-height: 1.35;

        font-weight: 900;
      }

      .stream-detail-performers {
        display: flex;

        gap: 6px;

        flex-wrap: wrap;

        margin-top: 13px;
      }

      .stream-detail-performer {
        padding:
          6px
          10px;

        border-radius: 999px;

        font-size: 11px;
        font-weight: 900;
      }


      .stream-sheet-block {
        margin-top: 20px;

        padding-top: 17px;

        border-top:
          1px solid
          #e4e9f0;
      }

      .stream-sheet-block-title {
        margin-bottom: 9px;

        font-size: 16px;
        font-weight: 900;
      }


      .stream-detail-info-list {
        overflow: hidden;

        border:
          1px solid
          #e5eaf0;

        border-radius: 14px;

        background: #fff;
      }

      .stream-detail-info-row {
        display: grid;

        grid-template-columns:
          92px
          1fr;

        gap: 12px;

        align-items: center;

        min-height: 48px;

        padding:
          10px
          12px;

        border-bottom:
          1px solid
          #edf0f4;
      }

      .stream-detail-info-row:last-child {
        border-bottom: 0;
      }

      .stream-detail-info-label {
        color: #7a8596;

        font-size: 11px;
        font-weight: 900;
      }

      .stream-detail-info-value {
        color: #172033;

        font-size: 13px;
        font-weight: 900;

        word-break: break-word;
      }

      .stream-period-arrow {
        margin:
          4px
          0;

        color: #738096;

        font-size: 11px;
      }

      .stream-period-note {
        margin-top: 5px;

        color: #7a8596;

        font-size: 11px;
        font-weight: 700;
      }


      .stream-performers-text {
        padding:
          12px
          13px;

        border-radius: 13px;

        background: #f6f8fb;

        color: #536176;

        font-size: 12px;
        line-height: 1.75;

        font-weight: 700;
      }

      .stream-source-note {
        color: #7b8799;

        font-size: 11px;
        line-height: 1.6;
      }


      .stream-fany-button {
        display: block;

        width: 100%;

        margin-top: 17px;

        padding: 15px;

        border: 0;
        border-radius: 999px;

        background:
          linear-gradient(
            135deg,
            #2788ee,
            #146aca
          );

        color: #fff;

        text-align: center;
        text-decoration: none;

        font-size: 14px;
        font-weight: 900;

        cursor: pointer;

        box-sizing: border-box;
      }

      .stream-fany-button.mock {
        opacity: 0.65;
      }


      @media (max-width: 520px) {

        .calendar-mode-switch {
          margin-left: 4px;
          margin-right: 4px;
        }

        .stream-month-header {
          grid-template-columns:
            39px
            39px
            1fr
            53px;

          padding-left: 5px;
          padding-right: 5px;
        }

        .stream-month-arrow {
          width: 36px;
          height: 36px;
        }

        .stream-day-cell {
          min-height: 87px;

          padding:
            4px
            2px;
        }

        .stream-day-event {
          padding:
            4px
            2px;

          font-size: 7px;
        }

      }


      @media (max-width: 370px) {

        .stream-day-cell {
          min-height: 81px;
        }

        .stream-day-event {
          font-size: 6.5px;
        }

      }

    `;


    document.head.appendChild(
      style
    );
  }


  /* ======================================================
     UTIL
  ====================================================== */

  function streamEscapeHtml(
    value
  ) {

    return String(
      value ?? ""
    )
      .replaceAll(
        "&",
        "&amp;"
      )
      .replaceAll(
        "<",
        "&lt;"
      )
      .replaceAll(
        ">",
        "&gt;"
      )
      .replaceAll(
        '"',
        "&quot;"
      )
      .replaceAll(
        "'",
        "&#039;"
      );
  }


  function streamDateKey(
    date
  ) {

    return (
      `${date.getFullYear()}-`
      +
      `${String(
        date.getMonth() + 1
      ).padStart(
        2,
        "0"
      )}-`
      +
      `${String(
        date.getDate()
      ).padStart(
        2,
        "0"
      )}`
    );
  }


  function streamParseDate(
    key
  ) {

    const match =
      /^(\d{4})-(\d{2})-(\d{2})$/
        .exec(
          key
        );


    if (!match) {
      return null;
    }


    return new Date(
      Number(
        match[1]
      ),
      Number(
        match[2]
      ) - 1,
      Number(
        match[3]
      )
    );
  }


  function streamGetPerformer(
    id
  ) {

    return (
      STREAM_DEFAULT_PERFORMERS
        .find(
          performer =>
            performer.id === id
        )
      ||
      {
        id,
        name: id,
        short:
          String(
            id
          ).slice(
            0,
            1
          ),
        color: "#7d8796",
        soft: "#f1f3f6",
      }
    );
  }


  function streamVisibleEvents() {

    if (
      streamActiveFilters.size
      ===
      0
    ) {

      return streamEvents;
    }


    return streamEvents.filter(
      event =>
        Array.isArray(
          event.performerIds
        )
        &&
        event.performerIds.some(
          id =>
            streamActiveFilters.has(
              id
            )
        )
    );
  }


  /* ======================================================
     CREATE UI
  ====================================================== */

  function createModeSwitcher() {

    if (
      document.getElementById(
        "calendarModeSwitch"
      )
    ) {

      return;
    }


    const header =
      document.querySelector(
        ".app-header"
      );


    if (!header) {
      return;
    }


    const switcher =
      document.createElement(
        "div"
      );


    switcher.className =
      "calendar-mode-switch";


    switcher.id =
      "calendarModeSwitch";


    switcher.innerHTML = `
      <button
        id="normalCalendarMode"
        class="
          calendar-mode-button
          active
        "
      >
        📅 通常ライブ
      </button>

      <button
        id="streamCalendarMode"
        class="calendar-mode-button"
      >
        ▶ 配信カレンダー
      </button>
    `;


    header.insertAdjacentElement(
      "afterend",
      switcher
    );


    document
      .getElementById(
        "normalCalendarMode"
      )
      .addEventListener(
        "click",
        () => {

          setCalendarMode(
            "live"
          );
        }
      );


    document
      .getElementById(
        "streamCalendarMode"
      )
      .addEventListener(
        "click",
        () => {

          setCalendarMode(
            "stream"
          );
        }
      );
  }


  function createStreamView() {

    if (
      document.getElementById(
        "streamCalendarView"
      )
    ) {

      return;
    }


    const legend =
      document.getElementById(
        "legend"
      );


    if (!legend) {
      return;
    }


    const view =
      document.createElement(
        "div"
      );


    view.id =
      "streamCalendarView";


    view.innerHTML = `
      <section class="stream-intro">

        <div class="stream-intro-top">

          <div class="stream-play-icon">
            ▶
          </div>

          <div class="stream-intro-title">
            配信カレンダー
          </div>

        </div>

        <div class="stream-intro-text">
          FANYオンラインチケットから取得した
          めぞん・ピュート・軟水の配信公演を表示しています。
        </div>

        <div
          id="streamDataStatus"
          class="stream-data-status"
        >
          ▶ FANY配信情報を読み込み中
        </div>

      </section>


      <div
        id="streamFilter"
        class="stream-filter"
      ></div>


      <section class="stream-calendar-card">

        <div class="stream-month-header">

          <button
            id="streamPrevMonth"
            class="stream-month-arrow"
            aria-label="前の月"
          >
            ‹
          </button>

          <button
            id="streamNextMonth"
            class="stream-month-arrow"
            aria-label="次の月"
          >
            ›
          </button>

          <div
            id="streamMonthTitle"
            class="stream-month-title"
          ></div>

          <button
            id="streamTodayButton"
            class="stream-today-button"
          >
            今日
          </button>

        </div>


        <div class="stream-week-row">

          <div class="stream-weekday">
            月
          </div>

          <div class="stream-weekday">
            火
          </div>

          <div class="stream-weekday">
            水
          </div>

          <div class="stream-weekday">
            木
          </div>

          <div class="stream-weekday">
            金
          </div>

          <div class="
            stream-weekday
            saturday
          ">
            土
          </div>

          <div class="
            stream-weekday
            sunday
          ">
            日
          </div>

        </div>


        <div
          id="streamCalendarGrid"
          class="stream-calendar-grid"
        ></div>

      </section>


      <section
        id="streamSelectedSection"
        class="stream-selected-section"
      ></section>


      <section class="stream-info-card">

        <div class="stream-info-title">
          ▶ FANYオンラインチケット
        </div>

        <div class="stream-info-text">
          FANYオンラインチケットから取得した
          配信公演を自動で表示しています。
        </div>

      </section>
    `;


    legend.insertAdjacentElement(
      "beforebegin",
      view
    );


    createStreamSheet();


    document
      .getElementById(
        "streamPrevMonth"
      )
      .addEventListener(
        "click",
        () => {

          streamMonth =
            new Date(
              streamMonth.getFullYear(),
              streamMonth.getMonth() - 1,
              1
            );


          streamSelectedDate =
            streamDateKey(
              streamMonth
            );


          renderStreamCalendar();

          renderStreamSelectedDay();
        }
      );


    document
      .getElementById(
        "streamNextMonth"
      )
      .addEventListener(
        "click",
        () => {

          streamMonth =
            new Date(
              streamMonth.getFullYear(),
              streamMonth.getMonth() + 1,
              1
            );


          streamSelectedDate =
            streamDateKey(
              streamMonth
            );


          renderStreamCalendar();

          renderStreamSelectedDay();
        }
      );


    document
      .getElementById(
        "streamTodayButton"
      )
      .addEventListener(
        "click",
        () => {

          const today =
            new Date();


          streamMonth =
            new Date(
              today.getFullYear(),
              today.getMonth(),
              1
            );


          streamSelectedDate =
            streamDateKey(
              today
            );


          renderStreamCalendar();

          renderStreamSelectedDay();
        }
      );
  }


  function createStreamSheet() {

    if (
      document.getElementById(
        "streamSheetOverlay"
      )
    ) {

      return;
    }


    const overlay =
      document.createElement(
        "div"
      );


    overlay.id =
      "streamSheetOverlay";


    overlay.className =
      "stream-sheet-overlay";


    overlay.innerHTML = `
      <div
        id="streamSheet"
        class="stream-sheet"
      ></div>
    `;


    document.body.appendChild(
      overlay
    );


    overlay.addEventListener(
      "click",
      event => {

        if (
          event.target === overlay
        ) {

          closeStreamSheet();
        }
      }
    );
  }


  /* ======================================================
     MODE
  ====================================================== */

  function setCalendarMode(
    mode
  ) {

    currentCalendarMode =
      mode;


    const liveButton =
      document.getElementById(
        "normalCalendarMode"
      );


    const streamButton =
      document.getElementById(
        "streamCalendarMode"
      );


    const streamView =
      document.getElementById(
        "streamCalendarView"
      );


    const legend =
      document.getElementById(
        "legend"
      );


    const calendarView =
      document.getElementById(
        "calendarView"
      );


    const pageSection =
      document.getElementById(
        "pageSection"
      );


    if (
      mode === "stream"
    ) {

      liveButton?.classList.remove(
        "active"
      );


      streamButton?.classList.add(
        "active",
        "stream-active"
      );


      if (legend) {
        legend.style.display =
          "none";
      }


      if (calendarView) {
        calendarView.style.display =
          "none";
      }


      if (pageSection) {

        pageSection.classList.remove(
          "show"
        );

        pageSection.style.display =
          "none";
      }


      streamView?.classList.add(
        "show"
      );


      renderStreamAll();


    } else {

      liveButton?.classList.add(
        "active"
      );


      streamButton?.classList.remove(
        "active",
        "stream-active"
      );


      streamView?.classList.remove(
        "show"
      );


      if (legend) {
        legend.style.display =
          "";
      }


      if (calendarView) {
        calendarView.style.display =
          "";
      }


      if (pageSection) {
        pageSection.style.display =
          "";
      }
    }
  }


  /* ======================================================
     FILTER
  ====================================================== */

  function renderStreamFilter() {

    const container =
      document.getElementById(
        "streamFilter"
      );


    if (!container) {
      return;
    }


    container.innerHTML = `
      <button
        class="
          stream-filter-button
          all
          ${
            streamActiveFilters.size === 0
              ?
              "active"
              :
              ""
          }
        "
        data-stream-filter="all"
      >
        すべて
      </button>

      ${
        STREAM_DEFAULT_PERFORMERS
          .map(
            performer => `
              <button
                class="
                  stream-filter-button
                  ${streamEscapeHtml(
                    performer.id
                  )}
                  ${
                    streamActiveFilters.has(
                      performer.id
                    )
                      ?
                      "active"
                      :
                      ""
                  }
                "
                data-stream-filter="${streamEscapeHtml(
                  performer.id
                )}"
              >
                ${streamEscapeHtml(
                  performer.name
                )}
              </button>
            `
          )
          .join("")
      }
    `;


    container
      .querySelectorAll(
        "[data-stream-filter]"
      )
      .forEach(
        button => {

          button.addEventListener(
            "click",
            () => {

              const id =
                button.dataset
                  .streamFilter;


              if (
                id === "all"
              ) {

                streamActiveFilters.clear();

              } else {

                if (
                  streamActiveFilters.has(
                    id
                  )
                ) {

                  streamActiveFilters.delete(
                    id
                  );

                } else {

                  streamActiveFilters.add(
                    id
                  );
                }
              }


              renderStreamAll();
            }
          );
        }
      );
  }


  /* ======================================================
     CALENDAR
  ====================================================== */

  function renderStreamCalendar() {

    const title =
      document.getElementById(
        "streamMonthTitle"
      );


    const grid =
      document.getElementById(
        "streamCalendarGrid"
      );


    if (
      !title
      ||
      !grid
    ) {

      return;
    }


    title.textContent =
      `${streamMonth.getFullYear()}年`
      +
      `${streamMonth.getMonth() + 1}月`;


    const year =
      streamMonth.getFullYear();


    const month =
      streamMonth.getMonth();


    const firstDay =
      new Date(
        year,
        month,
        1
      );


    const lastDay =
      new Date(
        year,
        month + 1,
        0
      );


    const mondayOffset =
      (
        firstDay.getDay()
        +
        6
      )
      %
      7;


    const totalCells =
      Math.ceil(
        (
          mondayOffset
          +
          lastDay.getDate()
        )
        /
        7
      )
      *
      7;


    const startDate =
      new Date(
        year,
        month,
        1 - mondayOffset
      );


    const visible =
      streamVisibleEvents();


    let html =
      "";


    for (
      let i = 0;
      i < totalCells;
      i++
    ) {

      const date =
        new Date(
          startDate
        );


      date.setDate(
        startDate.getDate()
        +
        i
      );


      const key =
        streamDateKey(
          date
        );


      const dayEvents =
        visible
          .filter(
            event =>
              event.date === key
          )
          .sort(
            (
              a,
              b
            ) =>
              String(
                a.startTime || ""
              ).localeCompare(
                String(
                  b.startTime || ""
                )
              )
          );


      const isOther =
        date.getMonth()
        !==
        month;


      const isSelected =
        key
        ===
        streamSelectedDate;


      const shown =
        dayEvents.slice(
          0,
          2
        );


      const eventHtml =
        shown
          .map(
            event => {

              const firstId =
                Array.isArray(
                  event.performerIds
                )
                  ?
                  event.performerIds[0]
                  :
                  "";


              const performer =
                streamGetPerformer(
                  firstId
                );


              return `
                <div
                  class="
                    stream-day-event
                    ${streamEscapeHtml(
                      firstId
                    )}
                  "
                >
                  ${streamEscapeHtml(
                    performer.short
                  )}
                  ${streamEscapeHtml(
                    event.startTime || ""
                  )}
                </div>
              `;
            }
          )
          .join("");


      const more =
        dayEvents.length > 2
          ?
          `
            <div class="stream-more-count">
              ＋${dayEvents.length - 2}件
            </div>
          `
          :
          "";


      html += `
        <div
          class="
            stream-day-cell
            ${
              isOther
                ?
                "other-month"
                :
                ""
            }
            ${
              isSelected
                ?
                "selected"
                :
                ""
            }
          "
          data-stream-date="${key}"
        >

          <div class="stream-day-number">
            ${date.getDate()}
          </div>

          ${eventHtml}

          ${more}

        </div>
      `;
    }


    grid.innerHTML =
      html;


    grid
      .querySelectorAll(
        "[data-stream-date]"
      )
      .forEach(
        cell => {

          cell.addEventListener(
            "click",
            () => {

              const key =
                cell.dataset
                  .streamDate;


              const date =
                streamParseDate(
                  key
                );


              if (!date) {
                return;
              }


              if (
                date.getFullYear()
                !==
                streamMonth.getFullYear()
                ||
                date.getMonth()
                !==
                streamMonth.getMonth()
              ) {

                streamMonth =
                  new Date(
                    date.getFullYear(),
                    date.getMonth(),
                    1
                  );
              }


              streamSelectedDate =
                key;


              renderStreamCalendar();

              renderStreamSelectedDay();
            }
          );
        }
      );
  }


  /* ======================================================
     SELECTED DAY
  ====================================================== */

  function renderStreamSelectedDay() {

    const section =
      document.getElementById(
        "streamSelectedSection"
      );


    if (!section) {
      return;
    }


    const date =
      streamParseDate(
        streamSelectedDate
      );


    if (!date) {
      return;
    }


    const events =
      streamVisibleEvents()
        .filter(
          event =>
            event.date
            ===
            streamSelectedDate
        )
        .sort(
          (
            a,
            b
          ) =>
            String(
              a.startTime || ""
            ).localeCompare(
              String(
                b.startTime || ""
              )
            )
        );


    const title =
      `${date.getMonth() + 1}月`
      +
      `${date.getDate()}日`
      +
      `（${STREAM_WEEKDAYS[
        date.getDay()
      ]}）`;


    section.innerHTML = `
      <div class="stream-selected-head">

        <h2 class="stream-selected-title">
          ${streamEscapeHtml(
            title
          )}
        </h2>

        <div class="stream-selected-count">
          ${events.length}件の配信
        </div>

      </div>

      ${
        events.length
          ?
          `
            <div class="stream-event-list">

              ${
                events
                  .map(
                    renderStreamEventRow
                  )
                  .join("")
              }

            </div>
          `
          :
          `
            <div class="stream-empty">
              この日の配信予定はありません。
            </div>
          `
      }
    `;


    section
      .querySelectorAll(
        "[data-stream-event]"
      )
      .forEach(
        button => {

          button.addEventListener(
            "click",
            () => {

              const event =
                streamEvents.find(
                  item =>
                    item.id
                    ===
                    button.dataset
                      .streamEvent
                );


              if (event) {

                openStreamSheet(
                  event
                );
              }
            }
          );
        }
      );
  }


  function renderStreamEventRow(
    event
  ) {

    const performerIds =
      Array.isArray(
        event.performerIds
      )
        ?
        event.performerIds
        :
        [];


    const chips =
      performerIds
        .map(
          id => {

            const performer =
              streamGetPerformer(
                id
              );


            return `
              <span
                class="stream-performer-chip"
                style="
                  background:
                  ${streamEscapeHtml(
                    performer.soft
                  )};

                  color:
                  ${streamEscapeHtml(
                    performer.color
                  )};
                "
              >
                ${streamEscapeHtml(
                  performer.name
                )}
              </span>
            `;
          }
        )
        .join("");


    return `
      <button
        class="stream-event-row"
        data-stream-event="${streamEscapeHtml(
          event.id
        )}"
      >

        <div class="stream-event-time">
          ${streamEscapeHtml(
            event.startTime || ""
          )}
        </div>

        <div class="stream-event-main">

          <div class="stream-event-title">
            ${streamEscapeHtml(
              event.title || ""
            )}
          </div>

          <div class="stream-event-tags">

            ${chips}

            <span class="stream-row-sub">
              ▶ 配信
            </span>

          </div>

        </div>

        <div class="stream-event-arrow">
          ›
        </div>

      </button>
    `;
  }


  /* ======================================================
     DETAIL SHEET
  ====================================================== */

  function openStreamSheet(
    event
  ) {

    const overlay =
      document.getElementById(
        "streamSheetOverlay"
      );


    const sheet =
      document.getElementById(
        "streamSheet"
      );


    if (
      !overlay
      ||
      !sheet
    ) {

      return;
    }


    const performerIds =
      Array.isArray(
        event.performerIds
      )
        ?
        event.performerIds
        :
        [];


    const performersHtml =
      performerIds
        .map(
          id => {

            const performer =
              streamGetPerformer(
                id
              );


            return `
              <span
                class="stream-detail-performer"
                style="
                  background:
                  ${streamEscapeHtml(
                    performer.soft
                  )};

                  color:
                  ${streamEscapeHtml(
                    performer.color
                  )};
                "
              >
                ${streamEscapeHtml(
                  performer.name
                )}
              </span>
            `;
          }
        )
        .join("");


    const hasRealUrl =
      event.sourceUrl
      &&
      event.sourceUrl !== "#";


    const statusText =
      event.status
      &&
      event.status !==
        "販売状況不明"
        ?
        event.status
        :
        "FANYで確認";


    const streamStart =
      event.streamStart
      ||
      (
        event.date
        &&
        event.startTime
          ?
          `${event.date} ${event.startTime}`
          :
          ""
      );


    const streamEnd =
      event.streamEnd
      ||
      event.archiveEnd
      ||
      "";


    const streamPeriodBlock =
      streamStart
        ?
        `
          <div class="stream-detail-info-row">

            <div class="stream-detail-info-label">
              配信期間
            </div>

            <div class="stream-detail-info-value">

              <div>
                ${streamEscapeHtml(
                  streamStart
                )}
              </div>

              ${
                streamEnd
                  ?
                  `
                    <div class="stream-period-arrow">
                      ↓
                    </div>

                    <div>
                      ${streamEscapeHtml(
                        streamEnd
                      )}
                    </div>
                  `
                  :
                  `
                    <div class="stream-period-note">
                      終了日時はFANYで確認
                    </div>
                  `
              }

            </div>

          </div>
        `
        :
        "";


    sheet.innerHTML = `
      <div class="stream-sheet-handle"></div>

      <button
        id="streamSheetClose"
        class="stream-sheet-close"
        aria-label="閉じる"
      >
        ×
      </button>

      <div class="stream-detail-badge">
        ▶ FANY配信
      </div>

      <div class="stream-sheet-title">
        ${streamEscapeHtml(
          event.title || ""
        )}
      </div>

      <div class="stream-detail-performers">
        ${performersHtml}
      </div>


      <div class="stream-sheet-block">

        <div class="stream-sheet-block-title">
          配信情報
        </div>

        <div class="stream-detail-info-list">

          <div class="stream-detail-info-row">

            <div class="stream-detail-info-label">
              配信日
            </div>

            <div class="stream-detail-info-value">
              ${streamEscapeHtml(
                event.date || ""
              )}
            </div>

          </div>


          <div class="stream-detail-info-row">

            <div class="stream-detail-info-label">
              配信開始
            </div>

            <div class="stream-detail-info-value">
              ${streamEscapeHtml(
                event.startTime || ""
              )}
            </div>

          </div>


          ${streamPeriodBlock}


          <div class="stream-detail-info-row">

            <div class="stream-detail-info-label">
              料金
            </div>

            <div class="stream-detail-info-value">

              ${
                event.price
                  ?
                  streamEscapeHtml(
                    event.price
                  )
                  :
                  "FANYで確認"
              }

            </div>

          </div>


          <div class="stream-detail-info-row">

            <div class="stream-detail-info-label">
              販売状況
            </div>

            <div class="stream-detail-info-value">
              ${streamEscapeHtml(
                statusText
              )}
            </div>

          </div>

        </div>

      </div>


      ${
        event.performersText
          ?
          `
            <div class="stream-sheet-block">

              <div class="stream-sheet-block-title">
                出演者
              </div>

              <div class="stream-performers-text">
                ${streamEscapeHtml(
                  event.performersText
                )}
              </div>

            </div>
          `
          :
          ""
      }


      <div class="stream-sheet-block">

        <div class="stream-source-note">
          掲載元：
          ${streamEscapeHtml(
            event.source
            ||
            "FANYオンラインチケット"
          )}
        </div>

      </div>


      ${
        hasRealUrl
          ?
          `
            <a
              class="stream-fany-button"
              href="${streamEscapeHtml(
                event.sourceUrl
              )}"
              target="_blank"
              rel="noopener noreferrer"
            >
              FANYオンラインチケットで見る ↗
            </a>
          `
          :
          `
            <button
              class="
                stream-fany-button
                mock
              "
              type="button"
              disabled
            >
              FANYリンクなし
            </button>
          `
      }
    `;


    overlay.classList.add(
      "open"
    );


    document.body.style.overflow =
      "hidden";


    document
      .getElementById(
        "streamSheetClose"
      )
      .addEventListener(
        "click",
        closeStreamSheet
      );
  }


  function closeStreamSheet() {

    const overlay =
      document.getElementById(
        "streamSheetOverlay"
      );


    if (overlay) {

      overlay.classList.remove(
        "open"
      );
    }


    document.body.style.overflow =
      "";
  }


  /* ======================================================
     LOAD
  ====================================================== */

  async function loadStreamEvents() {

    const status =
      document.getElementById(
        "streamDataStatus"
      );


    try {

      const response =
        await fetch(
          `stream_events.json?t=${Date.now()}`,
          {
            cache: "no-store",
          }
        );


      if (!response.ok) {

        throw new Error(
          `HTTP ${response.status}`
        );
      }


      const data =
        await response.json();


      const events =
        Array.isArray(
          data
        )
          ?
          data
          :
          (
            Array.isArray(
              data.events
            )
              ?
              data.events
              :
              []
          );


      streamEvents =
        events;


      if (status) {

        status.textContent =
          `▶ FANY配信 ${events.length}件`;

        status.style.background =
          "#e8f5ec";

        status.style.color =
          "#237a3b";
      }


    } catch (error) {

      console.error(
        "配信データ取得失敗:",
        error
      );


      streamEvents =
        [];


      if (status) {

        status.textContent =
          "⚠ 配信情報を取得できませんでした";

        status.style.background =
          "#fdecec";

        status.style.color =
          "#b63b3b";
      }
    }
  }


  /* ======================================================
     DRAWER
  ====================================================== */

  function bindDrawerReturnToLive() {

    document
      .querySelectorAll(
        ".drawer-item"
      )
      .forEach(
        item => {

          item.addEventListener(
            "click",
            () => {

              if (
                currentCalendarMode
                ===
                "stream"
              ) {

                setCalendarMode(
                  "live"
                );
              }
            }
          );
        }
      );
  }


  /* ======================================================
     RENDER
  ====================================================== */

  function renderStreamAll() {

    renderStreamFilter();

    renderStreamCalendar();

    renderStreamSelectedDay();
  }


  /* ======================================================
     START
  ====================================================== */

  async function startStreamCalendar() {

    injectStreamStyles();

    createModeSwitcher();

    createStreamView();

    bindDrawerReturnToLive();

    await loadStreamEvents();

    renderStreamAll();
  }


  startStreamCalendar();

})();

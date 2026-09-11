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

      /* ======================================
         LIVE / STREAM SWITCH
      ====================================== */

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

        transition:
          background 0.18s,
          color 0.18s,
          box-shadow 0.18s,
          transform 0.1s;
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


      /* ======================================
         STREAM VIEW
      ====================================== */

      #streamCalendarView {
        display: none;
      }

      #streamCalendarView.show {
        display: block;
      }

      .stream-intro {
        margin-bottom: 12px;

        padding:
          14px
          14px
          13px;

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

        flex: 0 0 39px;

        border-radius: 12px;

        background: #1f76d5;

        color: #fff;

        font-size: 17px;
      }

      .stream-intro-title {
        font-size: 18px;
        font-weight: 900;
      }

      .stream

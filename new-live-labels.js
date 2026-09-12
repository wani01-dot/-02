(() => {

  /* ======================================================
     ワラいどっとこむ
     新着ライブ 出演者ラベル
  ====================================================== */

  const NEW_LIVE_PERFORMERS = {
    maison: {
      name: "めぞん",
      short: "め",
      color: "#E74C3C",
      textColor: "#FFFFFF",
      soft: "#FDECEA",
    },

    pyuto: {
      name: "ピュート",
      short: "ピ",
      color: "#F4C430",
      textColor: "#5E4D00",
      soft: "#FFF7D6",
    },

    nansui: {
      name: "軟水",
      short: "軟",
      color: "#3498DB",
      textColor: "#FFFFFF",
      soft: "#EAF4FD",
    },
  };


  /* ======================================================
     STYLE
  ====================================================== */

  function addStyles() {

    if (
      document.getElementById(
        "newLiveLabelStyles"
      )
    ) {
      return;
    }


    const style =
      document.createElement(
        "style"
      );


    style.id =
      "newLiveLabelStyles";


    style.textContent = `

      .new-live-performer-area {
        display: flex;
        align-items: center;
        flex-wrap: wrap;

        gap: 5px;

        margin-top: 8px;
      }

      .new-live-performer-label {
        display: inline-flex;
        align-items: center;

        gap: 5px;

        min-height: 25px;

        padding:
          4px
          8px
          4px
          5px;

        border-radius: 999px;

        font-size: 10px;
        font-weight: 900;

        line-height: 1;
      }

      .new-live-performer-dot {
        display: inline-flex;
        align-items: center;
        justify-content: center;

        width: 19px;
        height: 19px;

        flex:
          0
          0
          19px;

        border-radius: 50%;

        color: #fff;

        font-size: 8px;
        font-weight: 900;
      }

      .new-live-performer-label.maison {
        background: #FDECEA;
        color: #BA332B;
      }

      .new-live-performer-label.pyuto {
        background: #FFF7D6;
        color: #715E00;
      }

      .new-live-performer-label.nansui {
        background: #EAF4FD;
        color: #1767A8;
      }

      .new-live-performer-label.maison
      .new-live-performer-dot {
        background: #E74C3C;
      }

      .new-live-performer-label.pyuto
      .new-live-performer-dot {
        background: #F4C430;
        color: #594900;
      }

      .new-live-performer-label.nansui
      .new-live-performer-dot {
        background: #3498DB;
      }

      .new-live-label-title {
        margin-top: 7px;

        color: #8A94A3;

        font-size: 9px;
        font-weight: 800;

        letter-spacing: 0.02em;
      }

    `;


    document.head.appendChild(
      style
    );
  }


  /* ======================================================
     DATA
  ====================================================== */

  async function getEvents() {

    try {

      const response =
        await fetch(
          `events.json?t=${Date.now()}`,
          {
            cache: "no-store",
          }
        );


      if (!response.ok) {
        return [];
      }


      const data =
        await response.json();


      return Array.isArray(
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


    } catch (
      error
    ) {

      console.error(
        "新着出演者ラベル用データ取得失敗:",
        error
      );


      return [];
    }
  }


  /* ======================================================
     NORMALIZE
  ====================================================== */

  function clean(
    value
  ) {

    return String(
      value ?? ""
    )
      .replace(
        /\s+/g,
        " "
      )
      .trim();
  }


  function normalizeTitle(
    value
  ) {

    return clean(
      value
    )
      .toLowerCase()
      .replace(
        /[ 　「」『』【】・！!？?：:〜～]/g,
        ""
      );
  }


  function normalizeVenue(
    value
  ) {

    return clean(
      value
    )
      .toLowerCase()
      .replace(
        /[ 　]/g,
        ""
      );
  }


  function eventKey(
    event
  ) {

    return [
      event.date || "",
      event.startTime || "",
      normalizeTitle(
        event.title
      ),
      normalizeVenue(
        event.venue
      ),
    ].join(
      "|"
    );
  }


  /* ======================================================
     GROUP PERFORMERS
  ====================================================== */

  function makePerformerMap(
    events
  ) {

    const result =
      new Map();


    events.forEach(
      event => {

        const key =
          eventKey(
            event
          );


        if (
          !result.has(
            key
          )
        ) {

          result.set(
            key,
            new Set()
          );
        }


        const ids =
          result.get(
            key
          );


        if (
          event.performerId
          &&
          NEW_LIVE_PERFORMERS[
            event.performerId
          ]
        ) {

          ids.add(
            event.performerId
          );
        }


        if (
          Array.isArray(
            event.trackedPerformers
          )
        ) {

          event
            .trackedPerformers
            .forEach(
              id => {

                if (
                  NEW_LIVE_PERFORMERS[
                    id
                  ]
                ) {

                  ids.add(
                    id
                  );
                }
              }
            );
        }
      }
    );


    return result;
  }


  /* ======================================================
     RESULT ROW → KEY
  ====================================================== */

  function rowToKey(
    row
  ) {

    const key =
      row.dataset
        .eventKey;


    if (key) {
      return key;
    }


    return "";
  }


  /* ======================================================
     RENDER LABEL
  ====================================================== */

  function renderLabels(
    ids
  ) {

    const order = [
      "maison",
      "pyuto",
      "nansui",
    ];


    const labels =
      order
        .filter(
          id =>
            ids.has(
              id
            )
        )
        .map(
          id => {

            const performer =
              NEW_LIVE_PERFORMERS[
                id
              ];


            return `
              <span
                class="
                  new-live-performer-label
                  ${id}
                "
              >

                <span
                  class="new-live-performer-dot"
                >
                  ${performer.short}
                </span>

                ${performer.name}

              </span>
            `;
          }
        )
        .join("");


    if (!labels) {
      return "";
    }


    return `
      <div class="new-live-label-title">
        この芸人の新着
      </div>

      <div class="new-live-performer-area">
        ${labels}
      </div>
    `;
  }


  /* ======================================================
     APPLY
  ====================================================== */

  function applyLabels(
    performerMap
  ) {

    const pageSection =
      document.getElementById(
        "pageSection"
      );


    if (!pageSection) {
      return;
    }


    const pageTitle =
      pageSection.querySelector(
        ".page-title"
      );


    if (
      !pageTitle
      ||
      clean(
        pageTitle.textContent
      )
      !==
      "新着ライブ"
    ) {

      return;
    }


    pageSection
      .querySelectorAll(
        ".result-row[data-event-key]"
      )
      .forEach(
        row => {

          if (
            row.querySelector(
              ".new-live-performer-area"
            )
          ) {
            return;
          }


          const key =
            rowToKey(
              row
            );


          if (!key) {
            return;
          }


          const ids =
            performerMap.get(
              key
            );


          if (
            !ids
            ||
            ids.size
            ===
            0
          ) {

            return;
          }


          const sub =
            row.querySelector(
              ".result-sub"
            );


          if (!sub) {
            return;
          }


          sub.insertAdjacentHTML(
            "afterend",
            renderLabels(
              ids
            )
          );
        }
      );
  }


  /* ======================================================
     WATCH
  ====================================================== */

  async function start() {

    addStyles();


    const events =
      await getEvents();


    const performerMap =
      makePerformerMap(
        events
      );


    /*
      新着ライブページは
      メニューを押したあとに生成されるので
      DOMの変更を監視する。
    */

    const observer =
      new MutationObserver(
        () => {

          applyLabels(
            performerMap
          );
        }
      );


    observer.observe(
      document.body,
      {
        childList: true,
        subtree: true,
      }
    );


    applyLabels(
      performerMap
    );
  }


  start();

})();

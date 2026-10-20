

(() => {

  const DEFAULT_PERFORMERS = [
    {
      id: "maison",
      name: "めぞん",
      color: "#E74C3C",
      short: "め",
    },
    {
      id: "pyuto",
      name: "ピュート",
      color: "#F4C430",
      short: "ピ",
    },
    {
      id: "nansui",
      name: "軟水",
      color: "#3498DB",
      short: "軟",
    },
  ];


  const WEEKDAYS = [
    "日",
    "月",
    "火",
    "水",
    "木",
    "金",
    "土",
  ];


  const FAVORITES_KEY =
    "warai-dot-com-favorites";


  const VISIBLE_KEY =
    "warai-dot-com-visible-performers";


  const SALE_NEAR_DAYS = 7;

  const SALE_STARTED_DAYS = 5;


  let rawEvents = [];

  let groups = [];

  let performers = [
    ...DEFAULT_PERFORMERS
  ];

  let performerMap = {};


  let favorites =
    new Set(
      readStorageArray(
        FAVORITES_KEY
      )
    );


  let visiblePerformers =
    new Set(
      readStorageArray(
        VISIBLE_KEY
      )
    );


  let activePerformerFilters =
    new Set();


  let currentMonth =
    new Date(
      new Date().getFullYear(),
      new Date().getMonth(),
      1
    );


  let selectedDate =
    formatDateKey(
      new Date()
    );


  let currentPage =
    "calendar";


  let dayExpanded =
    false;


  let sheetScrollY = 0;

  let sheetBodyLocked = false;


  const legend =
    document.getElementById(
      "legend"
    );


  const monthTitle =
    document.getElementById(
      "monthTitle"
    );


  const calendarGrid =
    document.getElementById(
      "calendarGrid"
    );


  const daySection =
    document.getElementById(
      "daySection"
    );


  const calendarView =
    document.getElementById(
      "calendarView"
    );


  const pageSection =
    document.getElementById(
      "pageSection"
    );


  const drawerOverlay =
    document.getElementById(
      "drawerOverlay"
    );


  const sheetOverlay =
    document.getElementById(
      "sheetOverlay"
    );


  const sheet =
    document.getElementById(
      "sheet"
    );


  function escapeHtml(
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


  function readStorageArray(
    key
  ) {

    try {

      const value =
        JSON.parse(
          localStorage.getItem(
            key
          )
          ||
          "[]"
        );


      return Array.isArray(
        value
      )
        ?
        value
        :
        [];

    } catch {

      return [];
    }
  }


  function saveFavorites() {

    localStorage.setItem(
      FAVORITES_KEY,
      JSON.stringify(
        [
          ...favorites
        ]
      )
    );
  }


  function saveVisible() {

    localStorage.setItem(
      VISIBLE_KEY,
      JSON.stringify(
        [
          ...visiblePerformers
        ]
      )
    );
  }


  function formatDateKey(
    date
  ) {

    const y =
      date.getFullYear();


    const m =
      String(
        date.getMonth()
        +
        1
      ).padStart(
        2,
        "0"
      );


    const d =
      String(
        date.getDate()
      ).padStart(
        2,
        "0"
      );


    return (
      `${y}-${m}-${d}`
    );
  }


  function parseDateKey(
    value
  ) {

    const match =
      /^(\d{4})-(\d{2})-(\d{2})$/
        .exec(
          value
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
      )
      -
      1,

      Number(
        match[3]
      )
    );
  }


  function getPerformer(
    id
  ) {

    return (
      performerMap[id]
      ||
      {
        id,
        name: id,
        color: "#8993a3",
        short:
          String(
            id
          ).slice(
            0,
            1
          ),
      }
    );
  }


  function sourceLabel(
    source
  ) {

    const map = {
      fany:
        "FANY",

      tiget:
        "TIGET",

      eplus:
        "イープラス",

      livepocket:
        "LivePocket",

      theater:
        "劇場公式",
    };


    return (
      map[source]
      ||
      String(
        source
        ||
        ""
      ).toUpperCase()
    );
  }


  function unique(
    values
  ) {

    return [
      ...new Set(
        values.filter(
          Boolean
        )
      )
    ];
  }


  async function loadData() {

  try {

    /*
      =========================================
      1. events.json と discovered_events.json
         を両方読み込む
      =========================================
    */

    const [
      eventsResult,
      discoveredResult,
    ] = await Promise.allSettled([

      fetch(
        `events.json?t=${Date.now()}`,
        {
          cache: "no-store",
        }
      ),

      fetch(
        `discovered_events.json?t=${Date.now()}`,
        {
          cache: "no-store",
        }
      ),

    ]);


    /*
      =========================================
      2. events.json
      =========================================
    */

    let eventsData = [];

    let eventsConfigPerformers = [];


    if (
      eventsResult.status
      ===
      "fulfilled"
      &&
      eventsResult.value.ok
    ) {

      try {

        const data =
          await eventsResult
            .value
            .json();


        eventsData =
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


        eventsConfigPerformers =
          (
            !Array.isArray(
              data
            )
            &&
            Array.isArray(
              data.performers
            )
          )
            ?
            data.performers
            :
            [];


        console.log(
          `events.json: ${eventsData.length}件`
        );

      } catch (
        error
      ) {

        console.warn(
          "events.json の解析に失敗しました。",
          error
        );
      }

    } else {

      console.warn(
        "events.json を読み込めませんでした。"
      );
    }


    /*
      =========================================
      3. discovered_events.json
      =========================================
    */

    let discoveredData = [];

    let discoveredConfigPerformers = [];


    if (
      discoveredResult.status
      ===
      "fulfilled"
      &&
      discoveredResult.value.ok
    ) {

      try {

        const data =
          await discoveredResult
            .value
            .json();


        discoveredData =
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


        discoveredConfigPerformers =
          (
            !Array.isArray(
              data
            )
            &&
            Array.isArray(
              data.performers
            )
          )
            ?
            data.performers
            :
            [];


        console.log(
          `discovered_events.json: ${discoveredData.length}件`
        );

      } catch (
        error
      ) {

        console.warn(
          "discovered_events.json の解析に失敗しました。",
          error
        );
      }

    } else {

      /*
        discovered_events.json が
        まだ存在しない段階でも
        サイト自体は普通に動かす
      */

      console.info(
        "discovered_events.json はまだありません。"
      );
    }


    /*
      =========================================
      4. 2つのJSONを合流
      =========================================
    */

    rawEvents = [
      ...eventsData,
      ...discoveredData,
    ];


    /*
      同じ公演の複数媒体・複数芸人レコードは buildGroups で統合する。
      ここで source / URL / performerId を比較してしまうと
      同じ公演が重複表示されるため、情報を捨てずに渡す。
    */
    console.log(`取得した公演レコード: ${rawEvents.length}件`);

    /*
      =========================================
      6. performers設定も合流
      =========================================
    */

    const configPerformers = [
      ...eventsConfigPerformers,
      ...discoveredConfigPerformers,
    ];


    performers =
      DEFAULT_PERFORMERS.map(
        fallback => {

          /*
            後から読み込んだ設定を優先する
          */

          const found =
            [
              ...configPerformers,
            ]
              .reverse()
              .find(
                item =>
                  item.id
                  ===
                  fallback.id
              );


          return {
            ...fallback,
            ...(found || {}),

            /*
              め / ピ / 軟 は
              現在の表示を維持
            */

            short:
              fallback.short,
          };
        }
      );


    performerMap =
      Object.fromEntries(
        performers.map(
          performer => [
            performer.id,
            performer,
          ]
        )
      );


    /*
      =========================================
      7. 初回表示設定
      =========================================
    */

    if (
      visiblePerformers.size
      ===
      0
    ) {

      visiblePerformers =
        new Set(
          performers.map(
            performer =>
              performer.id
          )
        );


      saveVisible();
    }


    /*
      =========================================
      8. 既存処理へ渡す
      =========================================
    */

    groups =
      buildGroups(
        rawEvents
      );


    renderAll();


    /*
      =========================================
      9. 両方とも取得できなかった場合だけ
         エラー表示
      =========================================
    */

    if (
      eventsData.length
      ===
      0
      &&
      discoveredData.length
      ===
      0
    ) {

      console.warn(
        "読み込めるライブデータがありません。"
      );
    }

  } catch (
    error
  ) {

    console.error(
      "ライブデータ読み込みエラー:",
      error
    );


    daySection.innerHTML = `
      <div class="empty-message">
        ライブデータの読み込みに失敗しました。
      </div>
    `;
  }
}


  // 販売サイト間の表記ゆれを吸収。日時・会場・題名の組合せで判定。
  function matchTitle(value) {
    return String(value || "").normalize("NFKC").toLowerCase()
      .replace(/^\s*\d{1,2}[:：]\d{2}\s*(?:開演|開場)?\s*/g, "")
      .replace(/※[\s\S]*$/, "")
      .replace(/[.…]+$/g, "")
      .replace(/[\s　「」『』【】（）()・!！?？:：～〜\-―–]/g, "");
  }
  function matchVenue(value) {
    return String(value || "").normalize("NFKC").toLowerCase()
      .replace(/[（(](?:東京都|大阪府|京都府|北海道|.{2,3}県)[）)]/g, "")
      .replace(/よしもと福岡\s*大和証券劇場/g, "福岡よしもと劇場")
      .replace(/yoshimoto\s*roppongi\s*theater/g, "六本木よしもと劇場")
      .replace(/よしもと六本木シアター/g, "六本木よしもと劇場")
      .replace(/[\s　・（）()]/g, "");
  }
  function similarTitle(a,b) {
    const x=matchTitle(a),y=matchTitle(b);
    if(!x || !y)return false;
    if(x===y)return true;
    const short=x.length<y.length?x:y, long=x.length<y.length?y:x;
    if(short.length>=6 && long.includes(short))return true;
    let prefix=0;
    while(prefix<Math.min(x.length,y.length)&&x[prefix]===y[prefix])prefix++;
    return prefix>=6 && prefix/short.length>=0.65;
  }
  function samePerformance(a,b) {
    if(a.date!==b.date)return false;
    const at=String(a.startTime||"").replace(/[^0-9]/g, "");
    const bt=String(b.startTime||"").replace(/[^0-9]/g, "");
    if(at&&bt&&at!==bt)return false;
    const av=matchVenue(a.venue),bv=matchVenue(b.venue);
    if(av&&bv&&av!==bv)return false;
    return similarTitle(a.title,b.title);
  }
  function calendarKey(event) {
    return [event.date||"",matchTitle(event.title),String(event.startTime||"").replace(/[^0-9]/g, "")].join("|");
  }

  function buildGroups(
    events
  ) {

    const map =
      new Map();


    events.forEach(
      event => {

        let key = calendarKey(event);
        // 時刻・会場・タイトルが一致または類似する既存公演を探す。
        const matching=[...map.values()].filter(g=>samePerformance(g,event));
        if(matching.length===1)key=matching[0].key;
        // 開演時刻の欠落がある場合、複数候補を推測で統合しない。

        if (
          !map.has(
            key
          )
        ) {

          map.set(
            key,
            {
              key,

              date:
                event.date
                ||
                "",

              openTime:
                event.openTime
                ||
                "",

              startTime:
                event.startTime
                ||
                "",

              title:
                event.title
                ||
                "公演名不明",

              venue:
                event.venue
                ||
                "",

              trackedPerformers:
                [],

              performersText:
                [],

              records:
                [],

              newUntil:
                "",
            }
          );
        }


        const group =
          map.get(
            key
          );


        group.records.push(
          event
        );


        const tracked = [
          event.performerId,

          ...(
            Array.isArray(
              event.trackedPerformers
            )
              ?
              event.trackedPerformers
              :
              []
          ),
        ];


        group.trackedPerformers =
          unique([
            ...group.trackedPerformers,
            ...tracked,
          ]);


        const performerText =
          Array.isArray(
            event.performersText
          )
            ?
            event.performersText
            :
            (
              clean(
                event.performersText
              )
                ?
                [
                  clean(
                    event.performersText
                  )
                ]
                :
                []
            );


        group.performersText =
          unique([
            ...group.performersText,
            ...performerText,
          ]);


        if (
          event.newUntil
          &&
          (
            !group.newUntil
            ||
            event.newUntil
            >
            group.newUntil
          )
        ) {

          group.newUntil =
            event.newUntil;
        }


        if (
          !group.openTime
          &&
          event.openTime
        ) {

          group.openTime =
            event.openTime;
        }


        if (
          !group.venue
          &&
          event.venue
        ) {

          group.venue =
            event.venue;
        }
      }
    );


    return [
      ...map.values()
    ].sort(
      (
        a,
        b
      ) =>
        (
          a.date
          +
          a.startTime
        )
          .localeCompare(
            b.date
            +
            b.startTime
          )
    );
  }


  function visibleGroups() {

    return groups.filter(
      group => {

        const isVisible =
          group.trackedPerformers
            .some(
              id =>
                visiblePerformers
                  .has(
                    id
                  )
            );


        if (
          !isVisible
        ) {

          return false;
        }


        if (
          activePerformerFilters.size
          >
          0
        ) {

          return (
            group
              .trackedPerformers
              .some(
                id =>
                  activePerformerFilters
                    .has(
                      id
                    )
              )
          );
        }


        return true;
      }
    );
  }


  function getActiveFilterNames() {

    return performers
      .filter(
        performer =>
          activePerformerFilters
            .has(
              performer.id
            )
      )
      .map(
        performer =>
          performer.name
      );
  }


  function renderLegend() {

    const visible =
      performers.filter(
        performer =>
          visiblePerformers
            .has(
              performer.id
            )
      );


    const selectedNames =
      getActiveFilterNames();


    legend.innerHTML =
      visible.map(
        performer => {

          const selected =
            activePerformerFilters
              .has(
                performer.id
              );


          const dimmed =
            activePerformerFilters.size
            >
            0
            &&
            !selected;


          return `
            <button
              class="
                legend-item
                ${
                  selected
                    ?
                    "filter-selected"
                    :
                    ""
                }
                ${
                  dimmed
                    ?
                    "filter-dimmed"
                    :
                    ""
                }
              "
              data-performer-filter="${escapeHtml(
                performer.id
              )}"
            >

              <span
                class="legend-dot"
                style="
                  background:
                  ${escapeHtml(
                    performer.color
                  )}
                "
              ></span>

              ${escapeHtml(
                performer.name
              )}

            </button>
          `;
        }
      ).join("")
      +
      `
        <div
          class="
            legend-help
            ${
              selectedNames.length
                ?
                "filtering"
                :
                ""
            }
          "
        >
          ${
            selectedNames.length
              ?
              `${escapeHtml(
                selectedNames.join(
                  "＋"
                )
              )}で絞り込み中`
              :
              "名前を押して絞り込み"
          }
        </div>
      `;


    legend
      .querySelectorAll(
        "[data-performer-filter]"
      )
      .forEach(
        button => {

          button.addEventListener(
            "click",
            () => {

              const id =
                button.dataset
                  .performerFilter;


              if (
                activePerformerFilters
                  .has(
                    id
                  )
              ) {

                activePerformerFilters
                  .delete(
                    id
                  );

              } else {

                activePerformerFilters
                  .add(
                    id
                  );
              }


              dayExpanded =
                false;


              renderLegend();

              renderCalendar();

              renderSelectedDay();

              updateDrawerBadges();
            }
          );
        }
      );
  }


  function renderCalendar() {

    monthTitle.textContent =
      `${currentMonth.getFullYear()}年`
      +
      `${currentMonth.getMonth() + 1}月`;


    const year =
      currentMonth.getFullYear();


    const month =
      currentMonth.getMonth();


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
        1
        -
        mondayOffset
      );


    const dayMap =
      buildDayMap();


    let html =
      "";


    const calendarPerformers =
      performers.filter(
        performer => {

          if (
            !visiblePerformers
              .has(
                performer.id
              )
          ) {

            return false;
          }


          if (
            activePerformerFilters.size
            >
            0
          ) {

            return (
              activePerformerFilters
                .has(
                  performer.id
                )
            );
          }


          return true;
        }
      );


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
        formatDateKey(
          date
        );


      const isOther =
        date.getMonth()
        !==
        month;


      const isSelected =
        key
        ===
        selectedDate;


      const dayData =
        dayMap.get(
          key
        )
        ||
        {
          groups: [],
          performerCounts: {},
        };


      const countsHtml =
        calendarPerformers
          .map(
            performer => {

              const count =
                dayData
                  .performerCounts[
                    performer.id
                  ]
                ||
                0;


              if (
                !count
              ) {

                return "";
              }


              return `
                <div
                  class="performer-count"
                >

                  <span
                    class="mini-badge"
                    style="
                      background:
                      ${escapeHtml(
                        performer.color
                      )}
                    "
                  >
                    ${escapeHtml(
                      performer.short
                    )}
                  </span>

                  <span>
                    ${count}
                  </span>

                </div>
              `;
            }
          )
          .join("");


      html += `
        <div
          class="
            day-cell
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
          data-date="${key}"
        >

          <div class="day-number">
            ${date.getDate()}
          </div>

          <div class="performer-counts">
            ${countsHtml}
          </div>

          ${
            dayData.groups.length
              ?
              `
                <div class="day-total">
                  ${dayData.groups.length}件
                </div>
              `
              :
              ""
          }

        </div>
      `;
    }


    calendarGrid.innerHTML =
      html;


    calendarGrid
      .querySelectorAll(
        ".day-cell"
      )
      .forEach(
        cell => {

          cell.addEventListener(
            "click",
            () => {

              const key =
                cell.dataset.date;


              const date =
                parseDateKey(
                  key
                );


              if (
                !date
              ) {

                return;
              }


              if (
                date.getMonth()
                !==
                currentMonth.getMonth()
                ||
                date.getFullYear()
                !==
                currentMonth.getFullYear()
              ) {

                currentMonth =
                  new Date(
                    date.getFullYear(),
                    date.getMonth(),
                    1
                  );
              }


              selectedDate =
                key;


              dayExpanded =
                false;


              renderCalendar();

              renderSelectedDay();


              window.scrollTo({
                top:
                  document
                    .getElementById(
                      "daySection"
                    )
                    .offsetTop
                  -
                  15,

                behavior:
                  "smooth",
              });
            }
          );
        }
      );
  }


  function buildDayMap() {

    const map =
      new Map();


    visibleGroups()
      .forEach(
        group => {

          if (
            !map.has(
              group.date
            )
          ) {

            map.set(
              group.date,
              {
                groups: [],
                performerCounts: {},
              }
            );
          }


          const item =
            map.get(
              group.date
            );


          item.groups.push(
            group
          );


          group
            .trackedPerformers
            .forEach(
              id => {

                if (
                  !visiblePerformers
                    .has(
                      id
                    )
                ) {

                  return;
                }


                item
                  .performerCounts[
                    id
                  ] =
                  (
                    item
                      .performerCounts[
                        id
                      ]
                    ||
                    0
                  )
                  +
                  1;
              }
            );
        }
      );


    return map;
  }


  function renderSelectedDay() {

    const date =
      parseDateKey(
        selectedDate
      );


    if (
      !date
    ) {

      return;
    }


    const dayGroups =
      visibleGroups()
        .filter(
          group =>
            group.date
            ===
            selectedDate
        );


    const selectedNames =
      getActiveFilterNames();


    const title =
      `${date.getMonth() + 1}月`
      +
      `${date.getDate()}日`
      +
      `（${WEEKDAYS[
        date.getDay()
      ]}）`;


    if (
      dayGroups.length
      ===
      0
    ) {

      daySection.innerHTML = `
        <div class="day-section-head">

          <h2 class="day-section-title">
            ${title}
          </h2>

          <div class="day-section-count">
            0件のライブ
          </div>

        </div>

        <div class="empty-message">

          ${
            selectedNames.length
              ?
              `${escapeHtml(
                selectedNames.join(
                  "＋"
                )
              )}の出演ライブはありません。`
              :
              "この日のライブはありません。"
          }

        </div>
      `;


      return;
    }


    const shown =
      dayExpanded
        ?
        dayGroups
        :
        dayGroups.slice(
          0,
          4
        );


    daySection.innerHTML = `
      <div class="day-section-head">

        <h2 class="day-section-title">
          ${title}
        </h2>

        <div class="day-section-count">
          ${dayGroups.length}件のライブ
        </div>

        <div class="selected-label">

          ${
            selectedNames.length
              ?
              `${escapeHtml(
                selectedNames.join(
                  "＋"
                )
              )}`
              :
              "この日を選択中"
          }

        </div>

      </div>

      <div class="event-list">

        ${
          shown
            .map(
              renderEventRow
            )
            .join("")
        }

      </div>

      ${
        dayGroups.length
        >
        4
          ?
          `
            <button
              id="viewAllDay"
              class="view-all-button"
            >

              ${
                dayExpanded
                  ?
                  "表示を戻す"
                  :
                  `${date.getMonth() + 1}月`
                  +
                  `${date.getDate()}日の`
                  +
                  `すべてのライブを見る`
                  +
                  `（${dayGroups.length}件） ›`
              }

            </button>
          `
          :
          `
            <button
              class="view-all-button"
              disabled
            >

              ${date.getMonth() + 1}月
              ${date.getDate()}日の
              すべてのライブ
              （${dayGroups.length}件）

            </button>
          `
      }
    `;


    bindEventRows(
      daySection
    );


    const viewAllButton =
      document.getElementById(
        "viewAllDay"
      );


    if (
      viewAllButton
    ) {

      viewAllButton.addEventListener(
        "click",
        () => {

          dayExpanded =
            !dayExpanded;


          renderSelectedDay();
        }
      );
    }
  }


  function renderEventRow(
    group
  ) {

    const performerBadges =
      performers
        .filter(
          performer =>
            group
              .trackedPerformers
              .includes(
                performer.id
              )
            &&
            visiblePerformers
              .has(
                performer.id
              )
        )
        .map(
          performer => `
            <span
              class="mini-badge"
              style="
                background:
                ${escapeHtml(
                  performer.color
                )}
              "
            >
              ${escapeHtml(
                performer.short
              )}
            </span>
          `
        )
        .join("");


    return `
      <button
        class="event-row"
        data-event-key="${escapeHtml(
          group.key
        )}"
      >

        <div class="event-time">
          ${escapeHtml(
            group.startTime
            ||
            "--:--"
          )}
        </div>

        <div class="event-badges">
          ${performerBadges}
        </div>

        <div class="event-main">

          <div class="event-title">
            ${escapeHtml(
              group.title
            )}
          </div>

          <div class="event-venue">
            📍
            ${escapeHtml(
              group.venue
              ||
              "会場情報なし"
            )}
          </div>

        </div>

        <div class="event-arrow">
          ›
        </div>

      </button>
    `;
  }


  function bindEventRows(
    container
  ) {

    container
      .querySelectorAll(
        "[data-event-key]"
      )
      .forEach(
        element => {

          element.addEventListener(
            "click",
            () => {

              const group =
                groups.find(
                  item =>
                    item.key
                    ===
                    element
                      .dataset
                      .eventKey
                );


              if (
                group
              ) {

                openEventSheet(
                  group
                );
              }
            }
          );
        }
      );
  }


  function lockBodyForSheet() {

    if (
      sheetBodyLocked
    ) {

      return;
    }


    sheetScrollY =
      window.scrollY
      ||
      document
        .documentElement
        .scrollTop
      ||
      0;


    document.body.style.position =
      "fixed";


    document.body.style.top =
      `-${sheetScrollY}px`;


    document.body.style.left =
      "0";


    document.body.style.right =
      "0";


    document.body.style.width =
      "100%";


    document.body.style.overflow =
      "hidden";


    sheetBodyLocked =
      true;
  }


  function unlockBodyForSheet() {

    if (
      !sheetBodyLocked
    ) {

      return;
    }


    document.body.style.position =
      "";


    document.body.style.top =
      "";


    document.body.style.left =
      "";


    document.body.style.right =
      "";


    document.body.style.width =
      "";


    document.body.style.overflow =
      "";


    window.scrollTo(
      0,
      sheetScrollY
    );


    sheetBodyLocked =
      false;
  }


  function getCompactPerformerText(group) {
    const names = [];
    const add = raw => {
      let value = clean(raw).replace(/^[\[【(（]+(?:キャプテン|MC|ゲスト|出演|司会)[\]】)）]+\s*/g, "").trim();
      value = value.replace(/^[\[【(（]+|[\]】)）]+$/g, "").trim();
      if (!value || value.length > 38 || /[。！？!?：:『』「」]/.test(value)) return;
      if (/(?:申込|枚数|座席|整理番号|公演数|チケット|受付|販売|先着|抽選|購入|注意事項|まで|可能|開演|開場|ご案内|料金|入場|詳細|お問い合わせ)/.test(value)) return;
      if (/^(?:\d+|・|前売|当日|キャプテン|MC)$/.test(value)) return;
      if (!names.includes(value)) names.push(value);
    };
    for (const text of group.performersText || []) {
      // Scrapers sometimes supply a Python-list-like string instead of an array.
      const parts = clean(text).replace(/^\[|\]$/g, "").split(/[／/、,，]+/);
      for (const part of parts) add(part.replace(/^[\s'"\[\]]+|[\s'"\[\]]+$/g, ""));
    }
    for (const id of group.trackedPerformers || []) add(getPerformer(id).name);
    return names.join(" / ");
  }

  function openEventSheet(
    group
  ) {

    const wasOpen =
      sheetOverlay
        .classList
        .contains(
          "open"
        );


    const sourceRecords =
      uniqueRecordsBySource(
        group.records
      );


    const ticketOptions =
      getGroupTicketOptions(
        group
      );


    const trackedHtml =
      performers
        .filter(
          performer =>
            group
              .trackedPerformers
              .includes(
                performer.id
              )
        )
        .map(
          performer => `
            <span
              class="performer-pill"
              style="
                background:
                ${escapeHtml(
                  performer.color
                )}
              "
            >
              ${escapeHtml(
                performer.name
              )}
            </span>
          `
        )
        .join(
          " "
        );


    const performerDetails =
      getCompactPerformerText(
        group
      );


    const ticketHtml =
      ticketOptions.length
        ?
        ticketOptions
          .map(
            option => `
              <div class="ticket-option">

                <strong>
                  ${escapeHtml(
                    option.name
                    ||
                    option.type
                    ||
                    "チケット"
                  )}
                </strong>

                ${
                  option.type
                    ?
                    `
                      <div>
                        ${escapeHtml(
                          option.type
                        )}
                      </div>
                    `
                    :
                    ""
                }

                ${
                  option.price
                    ?
                    `
                      <div>
                        ${escapeHtml(
                          option.price
                        )}
                      </div>
                    `
                    :
                    ""
                }

                ${
                  option.status
                    ?
                    `
                      <div
                        style="
                          margin-top:
                          5px;
                        "
                      >

                        <span class="status-pill">
                          ${escapeHtml(
                            option.status
                          )}
                        </span>

                      </div>
                    `
                    :
                    ""
                }

              </div>
            `
          )
          .join("")
        :
        `
          <div class="content-card-sub">
            チケット詳細情報はありません。
          </div>
        `;


    const sourceLinks =
      sourceRecords
        .filter(
          record =>
            record.sourceUrl
        )
        .map(
          record => `
            <a
              class="source-link"
              href="${escapeHtml(
                record.sourceUrl
              )}"
              target="_blank"
              rel="noopener noreferrer"
            >
              ${escapeHtml(
                sourceLabel(
                  record.source
                )
              )}で見る ↗
            </a>
          `
        )
        .join("");


    const isFavorite =
      favorites.has(
        group.key
      );


    sheet.innerHTML = `
      <div class="sheet-handle"></div>

      <button
        id="sheetClose"
        class="sheet-close"
      >
        ×
      </button>

      <div class="sheet-title">
        ${escapeHtml(
          group.title
        )}
      </div>

      <div class="sheet-meta">

        📅
        ${escapeHtml(
          group.date
        )}

        <br>

        ⏰

        ${
          group.openTime
            ?
            `開場 ${escapeHtml(
              group.openTime
            )}　`
            :
            ""
        }

        ${
          group.startTime
            ?
            `開演 ${escapeHtml(
              group.startTime
            )}`
            :
            ""
        }

        ${
          group.venue
            ?
            `
              <br>

              📍
              ${escapeHtml(
                group.venue
              )}
            `
            :
            ""
        }

      </div>

      <div
        style="
          margin-top:
          13px;

          display:
          flex;

          gap:
          6px;

          flex-wrap:
          wrap;
        "
      >
        ${trackedHtml}
      </div>

      <div class="sheet-block">

        <div class="sheet-block-title">
          出演者
        </div>

        <div class="performer-text-compact">

          ${
            performerDetails
              ?
              escapeHtml(
                performerDetails
              )
              :
              "出演者詳細なし"
          }

        </div>

      </div>

      <div class="sheet-block">

        <div class="sheet-block-title">
          チケット情報
        </div>

        ${ticketHtml}

      </div>

      <div class="sheet-block">

        <div class="sheet-block-title">
          掲載元
        </div>

        ${
          sourceLinks
          ||
          `
            <div class="content-card-sub">
              リンク情報なし
            </div>
          `
        }

      </div>

      <button
        id="favoriteButton"
        class="
          favorite-button
          ${
            isFavorite
              ?
              "active"
              :
              ""
          }
        "
      >

        ${
          isFavorite
            ?
            "★ 行きたいライブに登録済み"
            :
            "☆ 行きたいライブに追加"
        }

      </button>
    `;


    if (
      !wasOpen
    ) {

      lockBodyForSheet();

      sheet.scrollTop =
        0;
    }


    sheetOverlay
      .classList
      .add(
        "open"
      );


    document
      .getElementById(
        "sheetClose"
      )
      .addEventListener(
        "click",
        closeSheet
      );


    document
      .getElementById(
        "favoriteButton"
      )
      .addEventListener(
        "click",
        () => {

          if (
            favorites.has(
              group.key
            )
          ) {

            favorites.delete(
              group.key
            );

          } else {

            favorites.add(
              group.key
            );
          }


          saveFavorites();

          updateDrawerBadges();

          openEventSheet(
            group
          );
        }
      );
  }


  function closeSheet() {

    sheetOverlay
      .classList
      .remove(
        "open"
      );


    unlockBodyForSheet();
  }


  function uniqueRecordsBySource(
    records
  ) {

    const seen =
      new Set();


    return records.filter(
      record => {

        const key = [
          record.source,
          record.sourceUrl,
        ].join(
          "|"
        );


        if (
          seen.has(
            key
          )
        ) {

          return false;
        }


        seen.add(
          key
        );


        return true;
      }
    );
  }


  function getGroupTicketOptions(
    group
  ) {

    const result =
      [];


    const seen =
      new Set();


    group.records
      .forEach(
        record => {

          const options =
            Array.isArray(
              record.ticketOptions
            )
              ?
              record.ticketOptions
              :
              [];


          options.forEach(
            option => {

              const key = [
                record.source,
                option.name,
                option.type,
                option.price,
                option.status,
              ].join(
                "|"
              );


              if (
                seen.has(
                  key
                )
              ) {

                return;
              }


              seen.add(
                key
              );


              result.push({
                ...option,

                source:
                  record.source,
              });
            }
          );
        }
      );


    return result;
  }


  function openDrawer() {

    drawerOverlay
      .classList
      .add(
        "open"
      );
  }


  function closeDrawer() {

    drawerOverlay
      .classList
      .remove(
        "open"
      );
  }


  function showPage(
    page
  ) {

    currentPage =
      page;


    document
      .querySelectorAll(
        ".drawer-item"
      )
      .forEach(
        item => {

          item.classList.toggle(
            "active",
            item.dataset.page
            ===
            page
          );
        }
      );


    if (
      page
      ===
      "calendar"
    ) {

      calendarView
        .style
        .display =
        "";


      pageSection
        .classList
        .remove(
          "show"
        );


      closeDrawer();

      return;
    }


    calendarView
      .style
      .display =
      "none";


    pageSection
      .classList
      .add(
        "show"
      );


    if (
      page
      ===
      "new"
    ) {

      renderListPage(
        "新着ライブ",
        "48時間以内に新しく見つかったライブ",
        getNewGroups(),
        true
      );
    }


    if (
      page
      ===
      "favorites"
    ) {

      renderListPage(
        "行きたいライブ",
        "⭐を付けたライブ",

        groups.filter(
          group =>
            favorites.has(
              group.key
            )
        ),
        false
      );
    }


    if (
      page
      ===
      "sales"
    ) {

      renderSalesPage();
    }


    if (
      page
      ===
      "search"
    ) {

      renderSearchPage();
    }


    if (
      page
      ===
      "performers"
    ) {

      renderPerformersPage();
    }


    if (
      page
      ===
      "coappearance"
    ) {

      renderCoappearancePage();
    }


    if (
      page
      ===
      "settings"
    ) {

      renderSettingsPage();
    }


    if (
      page
      ===
      "help"
    ) {

      renderHelpPage();
    }


    closeDrawer();


    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }


  function renderNewLivePerformerLabels(
    group
  ) {

    const performerOrder = [
      "maison",
      "pyuto",
      "nansui",
    ];


    const ids =
      performerOrder.filter(
        id =>
          group
            .trackedPerformers
            .includes(
              id
            )
      );


    if (
      ids.length
      ===
      0
    ) {

      return "";
    }


    const labels =
      ids.map(
        id => {

          const performer =
            getPerformer(
              id
            );


          return `
            <span
              class="
                new-live-performer-label
                ${escapeHtml(
                  id
                )}
              "
            >

              <span
                class="new-live-performer-dot"
              >
                ${escapeHtml(
                  performer.short
                )}
              </span>

              ${escapeHtml(
                performer.name
              )}

            </span>
          `;
        }
      )
      .join("");


    return `
      <div class="new-live-label-title">
        この芸人の新着
      </div>

      <div class="new-live-performer-area">
        ${labels}
      </div>
    `;
  }


  function renderListPage(
    title,
    subtitle,
    items,
    showNewPerformerLabels = false
  ) {

    pageSection.innerHTML = `
      <h2 class="page-title">
        ${escapeHtml(
          title
        )}
      </h2>

      <div class="page-subtitle">
        ${escapeHtml(
          subtitle
        )}
      </div>

      ${
        items.length
          ?
          items.map(
            group => `
              <button
                class="result-row"
                data-event-key="${escapeHtml(
                  group.key
                )}"
              >

                <div class="result-date">
                  ${escapeHtml(
                    group.date
                  )}

                  ${escapeHtml(
                    group.startTime
                  )}
                </div>

                <div class="result-title">
                  ${escapeHtml(
                    group.title
                  )}
                </div>

                <div class="result-sub">
                  ${escapeHtml(
                    group.venue
                  )}
                </div>

                ${
                  showNewPerformerLabels
                    ?
                    renderNewLivePerformerLabels(
                      group
                    )
                    :
                    ""
                }

              </button>
            `
          ).join("")
          :
          `
            <div class="empty-message">
              該当するライブはありません。
            </div>
          `
      }
    `;


    bindEventRows(
      pageSection
    );
  }


  function getNewGroups() {

    const now =
      Date.now();


    return visibleGroups()
      .filter(
        group => {

          if (
            !group.newUntil
          ) {

            return false;
          }


          const time =
            Date.parse(
              group.newUntil
            );


          return (
            Number.isFinite(
              time
            )
            &&
            time
            >
            now
          );
        }
      );
  }


  function getSaleItems() {

    const result =
      [];


    const seen =
      new Set();


    groups.forEach(
      group => {

        group.records
          .forEach(
            record => {

              let options =
                Array.isArray(
                  record.ticketOptions
                )
                  ?
                  record.ticketOptions
                  :
                  [];


              if (
                options.length
                ===
                0
                &&
                Array.isArray(
                  record.salePeriods
                )
                &&
                record.salePeriods
                  .length
              ) {

                options = [
                  {
                    name:
                      "チケット",

                    type:
                      "",

                    status:
                      record.ticketStatus
                      ||
                      "",

                    price:
                      "",

                    salePeriods:
                      record.salePeriods,
                  }
                ];
              }


              options.forEach(
                option => {

                  const periods =
                    Array.isArray(
                      option.salePeriods
                    )
                    &&
                    option.salePeriods
                      .length
                      ?
                      option.salePeriods
                      :
                      (
                        option.saleStartAt
                          ?
                          [
                            {
                              category:
                                option.saleCategory
                                ||
                                "",

                              label:
                                option.saleLabel
                                ||
                                "",

                              startAt:
                                option.saleStartAt
                                ||
                                "",

                              endAt:
                                option.saleEndAt
                                ||
                                "",
                            }
                          ]
                          :
                          []
                      );


                  periods.forEach(
                    period => {

                      if (
                        !period.startAt
                      ) {

                        return;
                      }


                      const key = [
                        group.key,
                        record.source,
                        option.name,
                        option.type,
                        period.category,
                        period.startAt,
                      ].join(
                        "|"
                      );


                      if (
                        seen.has(
                          key
                        )
                      ) {

                        return;
                      }


                      seen.add(
                        key
                      );


                      result.push({
                        group,
                        record,
                        option,
                        period,
                      });
                    }
                  );
                }
              );
            }
          );
      }
    );


    return result;
  }


  function getSaleGroups() {

    const now =
      new Date();


    const nearEnd =
      new Date(
        now.getTime()
        +
        SALE_NEAR_DAYS
        *
        24
        *
        60
        *
        60
        *
        1000
      );


    const startedCutoff =
      new Date(
        now.getTime()
        -
        SALE_STARTED_DAYS
        *
        24
        *
        60
        *
        60
        *
        1000
      );


    const advance =
      [];


    const firstCome =
      [];


    const started =
      [];


    getSaleItems()
      .forEach(
        item => {

          const category =
            item.period.category;


          const start =
            new Date(
              item.period.startAt
            );


          const end =
            item.period.endAt
              ?
              new Date(
                item.period.endAt
              )
              :
              null;


          if (
            Number.isNaN(
              start.getTime()
            )
          ) {

            return;
          }


          if (
            category
            ===
            "advance"
            &&
            end
            &&
            start
            <=
            now
            &&
            now
            <=
            end
          ) {

            advance.push(
              item
            );

            return;
          }


          if (
            category
            ===
            "first_come"
            &&
            start
            >
            now
            &&
            start
            <=
            nearEnd
          ) {

            firstCome.push(
              item
            );

            return;
          }


          if (
            category
            ===
            "first_come"
            &&
            start
            <=
            now
            &&
            start
            >=
            startedCutoff
          ) {

            started.push(
              item
            );
          }
        }
      );


    advance.sort(
      (
        a,
        b
      ) =>
        Date.parse(
          a.period.endAt
        )
        -
        Date.parse(
          b.period.endAt
        )
    );


    firstCome.sort(
      (
        a,
        b
      ) =>
        Date.parse(
          a.period.startAt
        )
        -
        Date.parse(
          b.period.startAt
        )
    );


    started.sort(
      (
        a,
        b
      ) =>
        Date.parse(
          b.period.startAt
        )
        -
        Date.parse(
          a.period.startAt
        )
    );


    return {
      advance,
      firstCome,
      started,
    };
  }


  function renderSalesPage() {

    const saleGroups =
      getSaleGroups();


    pageSection.innerHTML = `
      <h2 class="page-title">
        チケット販売
      </h2>

      <div class="page-subtitle">
        券種ごとの販売期間から表示しています。
      </div>

      ${renderSaleSection(
        "先行販売",
        saleGroups.advance
      )}

      ${renderSaleSection(
        "先着販売",
        saleGroups.firstCome
      )}

      ${renderSaleSection(
        "販売開始済み",
        saleGroups.started
      )}
    `;


    bindEventRows(
      pageSection
    );
  }


  function renderSaleSection(
    title,
    items
  ) {

    return `
      <div class="section-label">
        ${title}
      </div>

      ${
        items.length
          ?
          items.map(
            item => {

              const date =
                new Date(
                  item.period.startAt
                );


              return `
                <button
                  class="result-row"
                  data-event-key="${escapeHtml(
                    item.group.key
                  )}"
                >

                  <div class="result-date">
                    ${escapeHtml(
                      item.group.date
                    )}
                  </div>

                  <div class="result-title">
                    ${escapeHtml(
                      item.group.title
                    )}
                  </div>

                  <div class="result-sub">

                    ${escapeHtml(
                      item.option.name
                      ||
                      "チケット"
                    )}

                    ・

                    ${escapeHtml(
                      sourceLabel(
                        item.record.source
                      )
                    )}

                    <br>

                    販売開始：

                    ${escapeHtml(
                      date.toLocaleString(
                        "ja-JP"
                      )
                    )}

                  </div>

                </button>
              `;
            }
          ).join("")
          :
          `
            <div class="content-card-sub">
              現在ありません。
            </div>
          `
      }
    `;
  }


  function renderSearchPage() {

    pageSection.innerHTML = `
      <h2 class="page-title">
        ライブを検索
      </h2>

      <input
        id="searchInput"
        class="search-input"
        type="search"
        placeholder="公演名・会場・出演者を検索"
        autocomplete="off"
      >

      <div id="searchResults"></div>
    `;


    const input =
      document.getElementById(
        "searchInput"
      );


    const results =
      document.getElementById(
        "searchResults"
      );


    function runSearch() {

      const q =
        clean(
          input.value
        ).toLowerCase();


      if (
        !q
      ) {

        results.innerHTML = `
          <div class="empty-message">
            検索ワードを入力してください。
          </div>
        `;

        return;
      }


      const found =
        visibleGroups()
          .filter(
            group => {

              const trackedNames =
                group
                  .trackedPerformers
                  .map(
                    id =>
                      getPerformer(
                        id
                      ).name
                  )
                  .join(
                    " "
                  );


              const haystack = [
                group.title,
                group.venue,
                trackedNames,
                ...group.performersText,
              ]
                .join(
                  " "
                )
                .toLowerCase();


              return (
                haystack.includes(
                  q
                )
              );
            }
          );


      results.innerHTML =
        found.length
          ?
          found.map(
            group => `
              <button
                class="result-row"
                data-event-key="${escapeHtml(
                  group.key
                )}"
              >

                <div class="result-date">
                  ${escapeHtml(
                    group.date
                  )}

                  ${escapeHtml(
                    group.startTime
                  )}
                </div>

                <div class="result-title">
                  ${escapeHtml(
                    group.title
                  )}
                </div>

                <div class="result-sub">
                  ${escapeHtml(
                    group.venue
                  )}
                </div>

              </button>
            `
          ).join("")
          :
          `
            <div class="empty-message">
              見つかりませんでした。
            </div>
          `;


      bindEventRows(
        results
      );
    }


    input.addEventListener(
      "input",
      runSearch
    );


    runSearch();
  }


  function renderPerformersPage() {

    pageSection.innerHTML = `
      <h2 class="page-title">
        出演者一覧
      </h2>

      ${
        performers
          .map(
            performer => {

              const count =
                groups.filter(
                  group =>
                    group
                      .trackedPerformers
                      .includes(
                        performer.id
                      )
                ).length;


              return `
                <div class="content-card">

                  <div
                    style="
                      display:flex;
                      align-items:center;
                      gap:11px;
                    "
                  >

                    <span
                      class="legend-dot"
                      style="
                        background:
                        ${escapeHtml(
                          performer.color
                        )}
                      "
                    ></span>

                    <div>

                      <div class="content-card-title">
                        ${escapeHtml(
                          performer.name
                        )}
                      </div>

                      <div class="content-card-sub">
                        今後の掲載公演
                        ${count}件
                      </div>

                    </div>

                  </div>

                </div>
              `;
            }
          )
          .join("")
      }
    `;
  }


  function renderCoappearancePage() {

    const pairs =
      [];


    for (
      let i = 0;
      i < performers.length;
      i++
    ) {

      for (
        let j = i + 1;
        j < performers.length;
        j++
      ) {

        const a =
          performers[i];


        const b =
          performers[j];


        const count =
          groups.filter(
            group =>
              group
                .trackedPerformers
                .includes(
                  a.id
                )
              &&
              group
                .trackedPerformers
                .includes(
                  b.id
                )
          ).length;


        pairs.push({
          a,
          b,
          count,
        });
      }
    }


    pageSection.innerHTML = `
      <h2 class="page-title">
        共演検索
      </h2>

      <div class="page-subtitle">
        追跡中の3組が同じ公演に出演する回数です。
      </div>

      ${
        pairs.map(
          pair => `
            <div class="content-card">

              <div class="content-card-title">

                ${escapeHtml(
                  pair.a.name
                )}

                ×

                ${escapeHtml(
                  pair.b.name
                )}

              </div>

              <div class="content-card-sub">
                ${pair.count}公演
              </div>

            </div>
          `
        ).join("")
      }
    `;
  }


  function renderSettingsPage() {

    pageSection.innerHTML = `
      <h2 class="page-title">
        設定
      </h2>

      <div class="content-card">

        <div class="content-card-title">
          カレンダーに表示する芸人
        </div>

        ${
          performers
            .map(
              performer => `
                <div class="settings-row">

                  <div
                    style="
                      display:flex;
                      align-items:center;
                      gap:10px;
                    "
                  >

                    <span
                      class="legend-dot"
                      style="
                        background:
                        ${escapeHtml(
                          performer.color
                        )}
                      "
                    ></span>

                    <strong>
                      ${escapeHtml(
                        performer.name
                      )}
                    </strong>

                  </div>

                  <button
                    class="
                      toggle
                      ${
                        visiblePerformers
                          .has(
                            performer.id
                          )
                          ?
                          "on"
                          :
                          ""
                      }
                    "
                    data-toggle-performer="${escapeHtml(
                      performer.id
                    )}"
                  ></button>

                </div>
              `
            )
            .join("")
        }

      </div>

      <button
        id="clearFavorites"
        class="favorite-button"
      >
        ⭐ 行きたいライブをすべて解除
      </button>
    `;


    pageSection
      .querySelectorAll(
        "[data-toggle-performer]"
      )
      .forEach(
        button => {

          button.addEventListener(
            "click",
            () => {

              const id =
                button.dataset
                  .togglePerformer;


              if (
                visiblePerformers
                  .has(
                    id
                  )
              ) {

                if (
                  visiblePerformers.size
                  ===
                  1
                ) {

                  return;
                }


                visiblePerformers
                  .delete(
                    id
                  );


                activePerformerFilters
                  .delete(
                    id
                  );

              } else {

                visiblePerformers
                  .add(
                    id
                  );
              }


              saveVisible();


              renderLegend();

              renderCalendar();

              renderSelectedDay();

              renderSettingsPage();

              updateDrawerBadges();
            }
          );
        }
      );


    document
      .getElementById(
        "clearFavorites"
      )
      .addEventListener(
        "click",
        () => {

          favorites.clear();

          saveFavorites();

          updateDrawerBadges();


          alert(
            "行きたいライブを解除しました。"
          );
        }
      );
  }


  function renderHelpPage() {

    pageSection.innerHTML = `
      <h2 class="page-title">
        ヘルプ・使い方
      </h2>

      <div class="content-card">

        <div class="content-card-title">
          芸人で絞り込む
        </div>

        <div class="content-card-sub">

          画面上部の
          「めぞん」
          「ピュート」
          「軟水」
          を押すと出演ライブを絞り込めます。

          <br><br>

          複数選択にも対応しています。

          <br>

          例：
          ピュート＋軟水を選択すると、
          ピュートまたは軟水が出演するライブを表示します。

          <br><br>

          選択中の名前をもう一度押すと解除されます。

          全部解除すると通常表示に戻ります。

        </div>

      </div>

      <div class="content-card">

        <div class="content-card-title">
          カレンダー
        </div>

        <div class="content-card-sub">

          赤＝めぞん、
          黄＝ピュート、
          青＝軟水。

          丸の横の数字は、
          その日にその芸人が出演するライブ数です。

        </div>

      </div>

      <div class="content-card">

        <div class="content-card-title">
          新着ライブ
        </div>

        <div class="content-card-sub">

          48時間以内に新しく見つかったライブを表示します。

          <br><br>

          各ライブには
          「めぞん」
          「ピュート」
          「軟水」
          のうち、
          誰の新着ライブなのかを色付きで表示します。

        </div>

      </div>

      <div class="content-card">

        <div class="content-card-title">
          公演詳細
        </div>

        <div class="content-card-sub">

          公演を押すと詳細画面が開きます。

          詳細画面を開いている間は
          後ろのカレンダーは固定され、
          詳細画面だけスクロールします。

        </div>

      </div>

    `;
  }


  function updateDrawerBadges() {

    const newCount =
      getNewGroups()
        .length;


    const favoriteCount =
      groups.filter(
        group =>
          favorites.has(
            group.key
          )
      ).length;


    const sales =
      getSaleGroups();


    const saleCount =
      sales.advance.length
      +
      sales.firstCome.length
      +
      sales.started.length;


    setBadge(
      "newBadge",
      newCount
    );


    setBadge(
      "favoriteBadge",
      favoriteCount
    );


    setBadge(
      "saleBadge",
      saleCount
    );
  }


  function setBadge(
    id,
    count
  ) {

    const element =
      document.getElementById(
        id
      );


    if (
      !element
    ) {

      return;
    }


    element.textContent =
      String(
        count
      );


    element.style.display =
      count
      >
      0
        ?
        ""
        :
        "none";
  }


  function renderAll() {

    renderLegend();

    renderCalendar();

    renderSelectedDay();

    updateDrawerBadges();


    if (
      currentPage
      !==
      "calendar"
    ) {

      showPage(
        currentPage
      );
    }
  }


  document
    .getElementById(
      "menuButton"
    )
    .addEventListener(
      "click",
      openDrawer
    );


  document
    .getElementById(
      "drawerClose"
    )
    .addEventListener(
      "click",
      closeDrawer
    );


  drawerOverlay
    .addEventListener(
      "click",
      event => {

        if (
          event.target
          ===
          drawerOverlay
        ) {

          closeDrawer();
        }
      }
    );


  document
    .querySelectorAll(
      ".drawer-item"
    )
    .forEach(
      item => {

        item.addEventListener(
          "click",
          () => {

            showPage(
              item.dataset.page
            );
          }
        );
      }
    );


  document
    .getElementById(
      "prevMonth"
    )
    .addEventListener(
      "click",
      () => {

        currentMonth =
          new Date(
            currentMonth
              .getFullYear(),

            currentMonth
              .getMonth()
            -
            1,

            1
          );


        selectedDate =
          formatDateKey(
            currentMonth
          );


        dayExpanded =
          false;


        renderCalendar();

        renderSelectedDay();
      }
    );


  document
    .getElementById(
      "nextMonth"
    )
    .addEventListener(
      "click",
      () => {

        currentMonth =
          new Date(
            currentMonth
              .getFullYear(),

            currentMonth
              .getMonth()
            +
            1,

            1
          );


        selectedDate =
          formatDateKey(
            currentMonth
          );


        dayExpanded =
          false;


        renderCalendar();

        renderSelectedDay();
      }
    );


  sheetOverlay
    .addEventListener(
      "click",
      event => {

        if (
          event.target
          ===
          sheetOverlay
        ) {

          closeSheet();
        }
      }
    );


  document.addEventListener(
    "keydown",
    event => {

      if (
        event.key
        ===
        "Escape"
      ) {

        closeDrawer();

        closeSheet();
      }
    }
  );


  loadData();

})();


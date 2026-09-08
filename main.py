def _render_result_line(
    result: dict,
    diagnostic_only: bool = False,
) -> None:

    status = result.get("status")

    if status == "SUCCESS":
        prefix = (
            "🟢"
            if diagnostic_only
            else "✅"
        )

        st.success(
            f"{prefix} {result['label']} — "
            f"Official API — "
            f"`{result['model']}` — "
            f"{result['latency']}s"
        )

        return

    if status == "AUTHENTICATED_NO_FREE_MODEL":

        st.warning(
            f"🟡 {result['label']} — "
            "OpenAI authentication OK, "
            "but no Free API model is configured. "
            "No paid model is selected automatically."
        )

        with st.expander(
            "تفاصيل التشخيص",
            expanded=diagnostic_only,
        ):
            st.write(
                result.get("error")
                or
                "تم توثيق المفتاح، لكن لا يوجد نموذج Free مُكوّن."
            )

        return

    with st.expander(
        f"🔴 {result['label']} — Official API failed",
        expanded=diagnostic_only,
    ):
        st.write(
            result.get("error")
            or
            "تعذر الحصول على رد رسمي."
        )

        st.write(
            "Attempted models:",
            ", ".join(
                result.get(
                    "attempted_models",
                    [],
                )
            )
            or "none",
        )


def _render_diagnostics(
    results: list[dict],
    title: str = "🔎 التشخيص والنتائج",
) -> None:

    official = sum(
        r.get("status") == "SUCCESS"
        for r in results
    )

    authenticated = sum(
        r.get("official_authenticated") is True
        for r in results
    )

    failed = sum(
        r.get("status") == "FAILED"
        for r in results
    )

    st.subheader(title)

    st.info(
        f"آخر عملية: "
        f"{official}/5 استجابات رسمية • "
        f"موثّق API: {authenticated}/5 • "
        f"فشل: {failed} • "
        "Local Engine: غير مستخدم"
    )

    for result in results:
        _render_result_line(result)


def _render_provider_diagnostics(
    results: list[dict],
) -> None:

    if not results:
        return

    st.subheader(
        "🧪 الفحص المستقل للمزودين"
    )

    st.caption(
        "هذا الاختبار لا يستخدم Local Engine؛ "
        "كل نتيجة هنا تخص API الرسمي مباشرة."
    )

    for result in results:
        _render_result_line(
            result,
            diagnostic_only=True,
        )

$(document).on("click", ".product", function (e) {
	e.preventDefault();
	var $popup = $("#popup");
	var popup_url = $(this).data("popup-url");
	$(".modal-body", $popup).load(popup_url, function () {
		$popup.modal("show");
	});
});
